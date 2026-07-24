"""MongoDB connection management for pass-through (`mongodb`) datasets.

Mirrors the two concerns of ``core/duckdb_client.py`` at a much smaller scale:

  - one lazy pymongo ``MongoClient`` singleton (pymongo pools connections
    internally, so a single client serves all requests);
  - blocking calls run on a dedicated executor via ``run_blocking_mongo()``
    so a slow Mongo query can't freeze the event loop or starve the DuckDB
    worker pool.

Per-query timeouts use Mongo's native ``maxTimeMS`` — the server kills the
operation, which surfaces as ``pymongo.errors.ExecutionTimeout`` and is
mapped to ``QueryTimeoutError`` (the same 504 contract as DuckDB interrupts).

The client is optional: with ``MONGODB_URI`` unset, mongodb datasets return
``DataNotAvailableError`` (404) while the rest of the API is unaffected.

Scope guardrail: this module only supports equality filters, time ranges,
and sort/limit — never aggregation pipelines. The moment an endpoint needs
an aggregation, that slice of the data wants to be parquet.
"""

import asyncio
import contextvars
import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import date, datetime
from functools import lru_cache
from typing import Any, Callable, Dict, Optional, Tuple, TypeVar

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.errors import ExecutionTimeout, PyMongoError

from .config import settings
from .exceptions import DataNotAvailableError, QueryError, QueryTimeoutError

log = logging.getLogger(__name__)

T = TypeVar("T")

# Small dedicated pool — Mongo queries must not compete with DuckDB's
# executor slots, and mongodb datasets are expected to be few.
_MONGO_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="mongo")

QUERY_TIMEOUT_S = 30       # user-facing find()s — indexed lookups, well under the proxy's 60s
INTROSPECT_TIMEOUT_S = 10  # registration-time probes — best-effort, never blocking registration
_MAX_FILTER_VALUES = 1000  # distinct() results larger than this are dropped (not categorical)


async def run_blocking_mongo(fn: Callable[[], T]) -> T:
    """Run a blocking pymongo workload off the event loop.

    Copies the caller's contextvars into the worker thread so per-request
    instrumentation (core.timing) keeps working inside the closure.
    """
    ctx = contextvars.copy_context()
    return await asyncio.get_running_loop().run_in_executor(
        _MONGO_EXECUTOR, lambda: ctx.run(fn)
    )


# ── Client lifecycle ──────────────────────────────────────────────────────────

@lru_cache()
def get_mongo_client() -> Optional[MongoClient]:
    """Lazy MongoClient singleton, or None when MONGODB_URI is not configured.

    Short server-selection timeout so a down Mongo fails requests fast
    instead of hanging them; secondaryPreferred matches the analytics
    read pattern and is a no-op on a standalone server.
    """
    if not settings.mongodb_uri:
        return None
    return MongoClient(
        settings.mongodb_uri,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
        readPreference="secondaryPreferred",
    )


async def ping_mongo() -> bool:
    """Startup probe. Logs the outcome; never raises (Mongo is optional)."""
    client = get_mongo_client()
    if client is None:
        log.info("MONGODB_URI not set — mongodb datasets will be unavailable.")
        return False
    try:
        await run_blocking_mongo(lambda: client.admin.command("ping"))
        log.info("Successfully connected to MongoDB.")
        return True
    except PyMongoError as e:
        log.warning("MongoDB connection failed (%s) — mongodb datasets unavailable.", e)
        return False


def close_mongo() -> None:
    client = get_mongo_client()
    if client is not None:
        client.close()
    get_mongo_client.cache_clear()


# ── Collection resolution ─────────────────────────────────────────────────────

def parse_mongo_location(data_location: Any) -> Tuple[str, str]:
    """Split a mongodb data_location into (database, collection).

    The registered form is '<database>/<collection>' — the connection URI
    lives in server config, never in the registry.
    """
    if not isinstance(data_location, str):
        raise ValueError(f"mongodb data_location must be a string, got {type(data_location).__name__}")
    parts = data_location.strip("/").split("/")
    if len(parts) != 2 or not all(parts):
        raise ValueError(
            f"mongodb data_location must be '<database>/<collection>', got {data_location!r}"
        )
    return parts[0], parts[1]


def get_mongo_collection_by_name(db_name: str, coll_name: str, label: str) -> Collection:
    """Resolve an explicit (database, collection) to a live Collection.

    For datasets whose router routes across sibling databases/collections
    (e.g. classic Storywrangler, where n-gram size is the database and
    language the collection). Raises DataNotAvailableError when Mongo is
    unconfigured — the 404 contract for missing data.
    """
    client = get_mongo_client()
    if client is None:
        raise DataNotAvailableError(label)
    return client[db_name][coll_name]


def get_mongo_collection(dataset_obj, label: str) -> Collection:
    """Resolve a registry entry's data_location to a live Collection.

    *label* is the 'domain/dataset_id' string used in error responses.
    Raises DataNotAvailableError when Mongo is unconfigured or the
    location is malformed — the 404 contract for missing data.
    """
    try:
        db_name, coll_name = parse_mongo_location(dataset_obj.data_location)
    except ValueError:
        log.warning("%s: malformed mongodb data_location %r", label, dataset_obj.data_location)
        raise DataNotAvailableError(label)
    return get_mongo_collection_by_name(db_name, coll_name, label)


@contextmanager
def handle_mongo_error(label: str):
    """Map pymongo failures onto the platform's exception contract.

    ExecutionTimeout → QueryTimeoutError (504); connection/server-selection
    failures → DataNotAvailableError (404); anything else → QueryError (500).
    Mirrors handle_query_error in core/query_utils.py.
    """
    try:
        yield
    except ExecutionTimeout:
        raise QueryTimeoutError(label)
    except PyMongoError as e:
        from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
        if isinstance(e, (ConnectionFailure, ServerSelectionTimeoutError)):
            log.warning("%s: MongoDB unreachable: %s", label, e)
            raise DataNotAvailableError(label)
        log.error("%s: MongoDB query failed: %s", label, e)
        raise QueryError(label)


# ── Registration-time introspection (best-effort, mirrors parquet_introspect) ──

_BSON_TO_DUCKDB = {
    str: "VARCHAR",
    bool: "BOOLEAN",
    int: "BIGINT",
    float: "DOUBLE",
    datetime: "TIMESTAMP",
    date: "DATE",
    list: "LIST",
    dict: "STRUCT",
}


def _bson_type(value: Any) -> str:
    for py_type, duck_type in _BSON_TO_DUCKDB.items():
        if isinstance(value, py_type) and not (py_type is int and isinstance(value, bool)):
            return duck_type
    return "VARCHAR"


def _iso(value: Any) -> Any:
    """Availability bounds as ISO date strings (matches the parquet format)."""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def mongo_introspect(dataset) -> Dict[str, Any]:
    """Derive data_schema, filter_values, and availability from a live collection.

    Same contract as parquet_introspect.introspect(): never raises — failures
    are logged and registration proceeds without the derived field. A
    submitter-provided data_schema is authoritative and skips sampling.
    """
    derived: Dict[str, Any] = {}

    # Only a literal '<database>/<collection>' can be sampled. A host or a
    # '{placeholder}' routing template has no single collection to probe, so the
    # schema must be declared explicitly (the schema validator enforces this) and
    # no Mongo connection is needed — registration does not depend on the data
    # being reachable. Per-collection availability is derived by the router live.
    loc = dataset.data_location
    segments = [s for s in loc.strip("/").split("/") if s] if isinstance(loc, str) else []
    is_concrete_collection = len(segments) == 2 and "{" not in loc
    if not is_concrete_collection:
        if dataset.data_schema:
            derived["data_schema"] = dataset.data_schema
        else:
            log.warning(
                "mongo_introspect: data_location %r is a host or template — requires explicit data_schema.", loc)
        # A host-form router may register an introspection hook that walks its
        # own collection layout for availability / filter_values (twitter: per
        # (ngram_size, lang) min/max). Local import avoids a mongo_query cycle.
        from .mongo_query import MONGO_INTROSPECT
        hook = MONGO_INTROSPECT.get(getattr(dataset, "domain", None))
        client = get_mongo_client()
        if hook and client is not None:
            try:
                derived.update(hook(client, dataset))
            except PyMongoError as e:
                log.warning("mongo_introspect: %s host-form hook failed: %s",
                            getattr(dataset, "domain", "?"), e)
        return derived

    client = get_mongo_client()
    if client is None:
        log.warning("mongo_introspect: MONGODB_URI not set — nothing derived.")
        return derived

    try:
        db_name, coll_name = parse_mongo_location(dataset.data_location)
    except ValueError as e:
        log.warning("mongo_introspect: %s", e)
        return derived
    coll = client[db_name][coll_name]
    timeout_ms = INTROSPECT_TIMEOUT_S * 1000

    # data_schema — sample one document; field names double as query keys.
    if dataset.data_schema:
        derived["data_schema"] = dataset.data_schema
    else:
        try:
            sample = coll.find_one({}, max_time_ms=timeout_ms)
            if sample:
                derived["data_schema"] = {
                    field: _bson_type(v) for field, v in sample.items() if field != "_id"
                }
        except PyMongoError as e:
            log.warning("mongo_introspect: sampling %s failed: %s", dataset.data_location, e)
            derived["introspect_error"] = str(e)

    transform = dataset.transform
    filter_dims = (transform.filter_dimensions if transform else None) or []
    time_dim = transform.time_dimension if transform else None

    # filter_values — distinct() per declared filter dimension.
    filter_values: Dict[str, list] = {}
    for dim in filter_dims:
        try:
            values = coll.distinct(dim, maxTimeMS=timeout_ms)
            if len(values) > _MAX_FILTER_VALUES:
                log.warning(
                    "mongo_introspect: %s.%s has %d distinct values (> %d) — not categorical, skipped.",
                    dataset.data_location, dim, len(values), _MAX_FILTER_VALUES,
                )
                continue
            vals = [v for v in values if v is not None]
            try:
                filter_values[dim] = sorted(vals)
            except TypeError:
                # Mixed BSON types (e.g. int 1 and str "1") — order by string
                # form rather than let sorted() break the never-raises contract.
                filter_values[dim] = sorted(vals, key=str)
        except PyMongoError as e:
            log.warning("mongo_introspect: distinct(%s) failed: %s", dim, e)
    if filter_values:
        derived["filter_values"] = filter_values

    # availability — min/max of the time dimension (index-cheap when indexed,
    # otherwise bounded by maxTimeMS and skipped).
    if time_dim:
        try:
            lo = coll.find_one({time_dim: {"$ne": None}}, {time_dim: True},
                               sort=[(time_dim, 1)], max_time_ms=timeout_ms)
            hi = coll.find_one({time_dim: {"$ne": None}}, {time_dim: True},
                               sort=[(time_dim, -1)], max_time_ms=timeout_ms)
            if lo and hi:
                derived["availability"] = {
                    "min": _iso(lo[time_dim]),
                    "max": _iso(hi[time_dim]),
                }
        except PyMongoError as e:
            log.warning("mongo_introspect: availability probe failed: %s", e)

    return derived

