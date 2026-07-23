"""MongoDB pass-through query engine for registry-driven datasets.

The Mongo twin of duckdb_query.py: generic mechanics for datasets registered
with data_format="mongodb". Scope guardrail (see CLAUDE.md): equality filters
+ time range + sort/limit only — never aggregation pipelines. The moment an
endpoint needs an aggregation, that slice of the data wants to be parquet.

Collection routing follows the three data_location forms:

  - "db/collection" literal   → resolved directly (no router code needed)
  - "{placeholder}" template  → formatted with the request's filter values
  - host form (no "/")        → the domain's registered routing hook — the
                                bespoke router owns the layout and registers
                                it here at import time (register_mongo_routing)

load_system() returns the same {"types": [...], "counts": [...]} contract as
duckdb_query.load_system(), which is what lets the platform instruments
(/storywrangler/allotax, /storywrangler/rtd) serve both engines through one
endpoint. Mongo systems are single-date only: the pipeline precomputes
per-day rows, so find + sort + limit suffices and the guardrail holds.
"""

import logging
from datetime import datetime, timedelta
from typing import Callable, Dict, Optional, Tuple

from fastapi import HTTPException

from .mongo_client import (
    QUERY_TIMEOUT_S, get_mongo_collection_by_name, handle_mongo_error,
    parse_mongo_location,
)

log = logging.getLogger(__name__)

_TIMEOUT_MS = QUERY_TIMEOUT_S * 1000


# ── Routing ───────────────────────────────────────────────────────────────────

# domain → fn(filter_vals) -> (database, collection). Registered by bespoke
# routers for host-form datasets; literal and template forms need no hook.
MONGO_ROUTING: Dict[str, Callable[[dict], Tuple[str, str]]] = {}


def register_mongo_routing(domain: str, fn: Callable[[dict], Tuple[str, str]]) -> None:
    MONGO_ROUTING[domain] = fn


def resolve_collection(dataset_obj, domain: str, filter_vals: dict):
    """Resolve the collection a request routes to, per data_location form."""
    loc = dataset_obj.data_location
    label = f"{domain}/{dataset_obj.dataset_id}"
    if isinstance(loc, str) and "/" not in loc:
        route = MONGO_ROUTING.get(domain)
        if route is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"mongodb dataset '{label}' uses host-form data_location but "
                    f"domain '{domain}' has not registered collection routing."
                ),
            )
        db_name, coll_name = route(filter_vals)
        return get_mongo_collection_by_name(db_name, coll_name, label)
    if isinstance(loc, str) and "{" in loc:
        try:
            loc = loc.format(**filter_vals)
        except KeyError as e:
            raise HTTPException(
                status_code=400,
                detail=f"data_location template for '{label}' needs a value for {e}.",
            )
    db_name, coll_name = parse_mongo_location(loc)
    return get_mongo_collection_by_name(db_name, coll_name, label)


# ── Registered-column resolution ──────────────────────────────────────────────

def dataset_columns(dataset_obj) -> Tuple[str, str]:
    """(type_column, time_dimension) from the registry entry."""
    ep = dataset_obj.endpoint_schema or {}
    type_col = ep.get("type_column") or "types"
    time_col = (dataset_obj.transform or {}).get("time_dimension") or "time"
    return type_col, time_col


def resolve_measures(dataset_obj, count_col: str) -> Tuple[str, Optional[str], Optional[str]]:
    """(count_col, rank_field, freq_field) for the chosen measure.

    Companion rank/freq fields share the count column's suffix (e.g.
    count_noRT → rank_noRT/freq_noRT) and are included only when present in
    the registered data_schema.
    """
    suffix = "_" + count_col.split("_", 1)[1] if "_" in count_col else ""
    schema = dataset_obj.data_schema or {}
    rank_field = f"rank{suffix}" if f"rank{suffix}" in schema else None
    freq_field = f"freq{suffix}" if f"freq{suffix}" in schema else None
    return count_col, rank_field, freq_field


# ── Time filters ──────────────────────────────────────────────────────────────

def parse_day(date_str: str) -> datetime:
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date: {date_str!r} (expected YYYY-MM-DD)")


def _stores_datetimes(dataset_obj, time_col: str) -> bool:
    return (dataset_obj.data_schema or {}).get(time_col, "").upper() in ("TIMESTAMP", "DATE")


def range_filter(dataset_obj, time_col: str, date_str: str, window: int) -> dict:
    """Time sub-filter for a date + look-back window (window=0 → full history).

    Matches the stored BSON type: datetime bounds when introspection saw
    TIMESTAMP/DATE, ISO strings otherwise.
    """
    end = parse_day(date_str)
    if _stores_datetimes(dataset_obj, time_col):
        cond = {"$lt": end + timedelta(days=1)}
        if window > 0:
            cond["$gte"] = end - timedelta(days=window)
        return cond
    cond = {"$lte": date_str}
    if window > 0:
        cond["$gte"] = (end - timedelta(days=window)).strftime("%Y-%m-%d")
    return cond


def day_filter(dataset_obj, time_col: str, date_str: str):
    """Exact-day sub-filter. Single days only — summing counts over a range
    needs an aggregation pipeline, which pass-through datasets do not get."""
    day = parse_day(date_str)
    if _stores_datetimes(dataset_obj, time_col):
        return {"$gte": day, "$lt": day + timedelta(days=1)}
    return date_str


def require_single_dates(pairs, required: bool = True) -> None:
    """400 unless every (label, value) date param is a single YYYY-MM-DD.

    The pass-through guardrail at the parameter level: range aggregation is
    parquet territory, so mongo endpoints only accept single dates. With
    ``required=False``, absent values pass (for optional params like dates2).
    """
    for label, val in pairs:
        if not val and not required:
            continue
        if not val or "," in val:
            raise HTTPException(
                status_code=400,
                detail=f"{label} must be a single YYYY-MM-DD date for mongodb "
                       "datasets — range aggregation is not supported on the "
                       "pass-through path.",
            )


def latest_available(coll, time_col: str) -> Optional[str]:
    """Latest date present in the routed collection (indexed on time).

    Per-collection, so it can't come from the dataset-level manifest —
    a live max-time probe. Blocking; call inside run_blocking_mongo.
    """
    doc = coll.find_one({time_col: {"$ne": None}}, {time_col: True},
                        sort=[(time_col, -1)], max_time_ms=_TIMEOUT_MS)
    return str(doc[time_col])[:10] if doc else None


def series_projection(type_col, time_col, count_col, rank_field, freq_field) -> dict:
    proj = {type_col: True, time_col: True, count_col: True, "_id": False}
    for f in (rank_field, freq_field):
        if f:
            proj[f] = True
    return proj


# ── System loading (the instruments' contract) ────────────────────────────────

def load_system(coll, type_col, count_col, time_col, dataset_obj, date_str: str, limit: int) -> dict:
    """Top-N type/count distribution for one (collection, single date) system.

    Returns {"types": [...], "counts": [...]} — the allotax library's input,
    same contract as duckdb_query.load_system(). Single date only: find +
    sort + limit over the precomputed per-day rows, no aggregation. `limit`
    bounds the sort (a top-K heap), so it stays cheap even on billion-row
    collections.
    """
    q = {time_col: day_filter(dataset_obj, time_col, date_str)}
    # Over-fetch so the dedupe below still yields ~limit unique terms on
    # heavily-duplicated days: some days are uniformly ~5x duplicated at the
    # source (whole-day re-ingestion), so top-N by count is 1/5 unique. 8x
    # covers that with margin; pathological days may still fall short (the
    # real fix is upstream deduplication of the collection). limit=0 means
    # no limit in pymongo, so it needs no over-fetch.
    cursor = (
        coll.find(q, projection={type_col: True, count_col: True, "_id": False},
                  max_time_ms=_TIMEOUT_MS)
        .sort(count_col, -1)
        .limit(limit * 8)
    )
    # allotax (Rust) requires types to be a list of unique str. Coerce numeric
    # tokens to str, and dedupe the source's duplicate (word, day) rows —
    # duplicate types would corrupt the vocabulary merge.
    types, counts, seen = [], [], set()
    for d in cursor:
        term = d.get(type_col)
        if term is None:
            continue
        key = str(term)
        if key in seen:
            continue
        seen.add(key)
        types.append(key)
        counts.append(float(d.get(count_col) or 0))
        if limit and len(types) >= limit:
            break
    return {"types": types, "counts": counts}


def load_instrument_system(dataset_obj, domain: str, filter_vals: dict,
                           date_str: str, limit: int, count_col: str) -> dict:
    """One types-counts system for the platform instruments (/storywrangler/*).

    Works for any mongodb dataset: routing comes from data_location (or the
    domain's registered hook), columns from the registration.
    """
    type_col, time_col = dataset_columns(dataset_obj)
    label = f"{domain}/{dataset_obj.dataset_id}"
    with handle_mongo_error(label):
        coll = resolve_collection(dataset_obj, domain, filter_vals)
        return load_system(coll, type_col, count_col, time_col, dataset_obj, date_str, limit)
