"""
Registry endpoints — discover and inspect registered file-based datasets.
"""

import logging
import re
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only
from sqlmodel import select

from storywrangler_schemas.registry import DatasetCreate, EntityRow

from ..core.database import get_session
from ..core.duckdb_client import get_admin_duckdb_client
from ..core.mongo_client import mongo_introspect, run_blocking_mongo
from ..core.openapi_menus import refresh_weight_menus
from ..core.parquet_introspect import (
    _derive_bucket_config,
    _discover_levels,
    introspect,
    validate_and_build_level_order,
)
from ..core.registry_utils import get_latest_entry
from ..models.auth import User
from ..models.registry import RegistryEntry, EntityMapping
from .auth import get_admin_user, get_current_user

log = logging.getLogger(__name__)

router = APIRouter()
admin_router = APIRouter()

# ── Response examples for OpenAPI docs ─────────────────────────────────────────
_EXAMPLE_DATASET = {
    "catalog": "vcsi",
    "domain": "babynames",
    "dataset_id": "ngrams",
    "data_location": "/data/babynames/names.parquet",
    "data_format": "parquet",
    "description": "US baby name frequencies by state, year, and sex.",
    "created_at": "2024-01-15T10:00:00Z",
    "updated_at": "2024-01-15T10:00:00Z",
}

def _ex(body: dict, status: str = "200") -> dict:
    """Wrap an example body in the openapi_extra responses structure."""
    return {"responses": {status: {"content": {"application/json": {"example": body}}}}}

# Domains that have actual registered routers. Populated by main.py from its
# DOMAIN_ROUTERS map at import time — one source of truth for both routing
# and registration validation. Empty only when this module is used without
# the app (in which case rejecting every domain is the loud, correct failure).
VALID_DOMAINS: set = set()

async def _upsert_entities(
    db: AsyncSession,
    domain: str,
    dataset_id: str,
    entities: List[EntityRow],
) -> int:
    """Upsert entity mapping rows. Returns count upserted.

    Fetches all existing rows in one SELECT (instead of one db.get per
    entity) so large rosters don't pay an N+1 round-trip cost.
    """
    row_ids = [f"{domain}:{dataset_id}:{e.local_id}" for e in entities]
    result = await db.execute(
        select(EntityMapping).where(EntityMapping.id.in_(row_ids))
    )
    existing_rows = {row.id: row for row in result.scalars()}

    for entity, row_id in zip(entities, row_ids):
        existing = existing_rows.get(row_id)
        if existing:
            existing.entity_id = entity.entity_id
            existing.entity_name = entity.entity_name
            existing.entity_ids = entity.entity_ids
        else:
            db.add(EntityMapping(
                id=row_id,
                domain=domain,
                dataset_id=dataset_id,
                local_id=entity.local_id,
                entity_id=entity.entity_id,
                entity_name=entity.entity_name,
                entity_ids=entity.entity_ids,
            ))
    return len(entities)


# ── Registration validation helpers ────────────────────────────────────────────

# Declared column names are interpolated (unparameterized) into DuckDB SQL by
# the query layer, so they must be plain identifiers. This is the trust
# boundary that keeps a submitter-provided data_schema from becoming SQL
# injection.
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_column_identifiers(dataset: DatasetCreate) -> None:
    """Reject declared column names that are not plain SQL identifiers."""
    declared: Dict[str, Any] = {}
    if dataset.endpoint_schema:
        declared["endpoint_schema.type_column"] = dataset.endpoint_schema.type_column
        cc = dataset.endpoint_schema.count_column
        if isinstance(cc, list):
            for col in cc:
                declared[f"endpoint_schema.count_column[{col!r}]"] = col
        else:
            declared["endpoint_schema.count_column"] = cc
    if dataset.transform:
        declared["transform.time_dimension"] = dataset.transform.time_dimension
        for fd in dataset.transform.filter_dimensions or []:
            declared[f"transform.filter_dimensions[{fd!r}]"] = fd
        for tp in getattr(dataset.transform, "time_partitions", None) or []:
            declared[f"transform.time_partitions[{tp!r}]"] = tp
        hb = dataset.transform.hash_bucket
        if isinstance(hb, str):
            declared["transform.hash_bucket"] = hb
    if dataset.entity_mapping:
        declared["entity_mapping.local_id_column"] = dataset.entity_mapping.local_id_column
    for col in (dataset.data_schema or {}):
        declared[f"data_schema[{col!r}]"] = col

    bad = sorted(
        f"{where} = {name!r}"
        for where, name in declared.items()
        if name is not None and not _IDENT_RE.match(str(name))
    )
    if bad:
        raise HTTPException(
            status_code=422,
            detail=(
                "Column names must be plain identifiers "
                "(letters, digits, underscore; not starting with a digit). "
                f"Invalid: {bad}"
            ),
        )


def _validate_types_counts(dataset: DatasetCreate, derived: Dict[str, Any]) -> None:
    """Pre-registration checks for endpoint_schema.type == 'types-counts'."""
    ep = dataset.endpoint_schema

    # 1. Require at least one comparison axis so the allotaxonometer can distinguish
    # system 1 from system 2.  Any of the four axes is sufficient:
    #   entity_mapping        → ?entity=X  vs ?entity2=Y
    #   time_dimension        → ?dates=D1  vs ?dates2=D2
    #   filter_dimensions     → ?sex=M     vs ?sex2=F
    #   hive_levels           → ?gran=daily vs ?gran2=weekly (auto-discovered)
    has_entity      = bool(dataset.entity_mapping)
    has_time        = bool(dataset.transform and dataset.transform.time_dimension)
    has_filter      = bool(dataset.transform and dataset.transform.filter_dimensions)
    has_hive_levels = bool(derived.get("level_order"))
    if not any([has_entity, has_time, has_filter, has_hive_levels]):
        raise HTTPException(
            status_code=422,
            detail=(
                "types-counts datasets require at least one comparison axis so the "
                "allotaxonometer can distinguish system 1 from system 2. Declare one of: "
                "entity_mapping, transform.time_dimension, transform.filter_dimensions, "
                "or use parquet_hive format (hive levels are auto-discovered). "
                "See https://github.com/vermont-complex-systems/Storywrangler-Specification for the spec."
            ),
        )

    # 2. If we could read the schema, verify the declared columns exist.
    # count_column may be a list (selectable measure menu) — every entry
    # must exist, since any of them can reach SUM() via ?weight=.
    data_schema = derived.get("data_schema") or {}
    if data_schema:
        type_col   = ep.type_column  or "types"
        count_cols = ep.count_column or "counts"
        count_cols = count_cols if isinstance(count_cols, list) else [count_cols]
        expected = [type_col, *count_cols]
        if dataset.transform and dataset.transform.time_dimension:
            expected.append(dataset.transform.time_dimension)
        missing = [c for c in expected if c not in data_schema]
        if missing:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Column(s) {missing} not found in dataset schema {sorted(data_schema)}. "
                    "Verify endpoint_schema.type_column, endpoint_schema.count_column, "
                    "and transform.time_dimension match the actual column names. "
                    "See https://github.com/vermont-complex-systems/Storywrangler-Specification for the spec."
                ),
            )


def _validate_time_series(dataset: DatasetCreate, derived: Dict[str, Any]) -> None:
    """Pre-registration checks for endpoint_schema.type == 'time-series'."""
    ep = dataset.endpoint_schema

    # 1. Require transform.time_dimension — a time series without a time column is invalid.
    if not (dataset.transform and dataset.transform.time_dimension):
        raise HTTPException(
            status_code=422,
            detail=(
                "time-series datasets require transform.time_dimension to declare the temporal column "
                "(e.g. 'year' or 'date'). "
                "See https://github.com/vermont-complex-systems/Storywrangler-Specification for the spec."
            ),
        )

    # 2. Require at least one groupable dimension.
    has_filter      = bool(dataset.transform.filter_dimensions)
    has_hive_levels = bool(derived.get("level_order"))
    if not has_filter and not has_hive_levels:
        raise HTTPException(
            status_code=422,
            detail=(
                "time-series datasets require at least one groupable dimension: "
                "declare transform.filter_dimensions or use parquet_hive format "
                "(hive levels are auto-discovered). "
                "See https://github.com/vermont-complex-systems/Storywrangler-Specification for the spec."
            ),
        )

    # 3. If we could read the schema, verify all declared columns exist.
    data_schema = derived.get("data_schema") or {}
    if data_schema:
        time_col    = dataset.transform.time_dimension
        count_cols  = ep.count_column or "count"
        count_cols  = count_cols if isinstance(count_cols, list) else [count_cols]
        filter_cols = list(dataset.transform.filter_dimensions or [])
        expected    = [time_col, *count_cols] + filter_cols
        missing     = [c for c in expected if c not in data_schema]
        if missing:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Column(s) {missing} not found in dataset schema {sorted(data_schema)}. "
                    "Verify transform.time_dimension, endpoint_schema.count_column (defaults to 'count'), "
                    "and transform.filter_dimensions match the actual column names. "
                    "See https://github.com/vermont-complex-systems/Storywrangler-Specification for the spec."
                ),
            )


_INT_TYPES = {"BIGINT", "INTEGER", "SMALLINT", "TINYINT", "INT", "INT4", "INT8", "INT2"}
_FLOAT_TYPES = {"DOUBLE", "FLOAT", "REAL", "DECIMAL", "NUMERIC"}


def _coerce(val, col_type: str):
    """Coerce a string value to the appropriate Python type based on schema."""
    upper = col_type.upper()
    try:
        if upper in _INT_TYPES:
            return int(val)
        if upper in _FLOAT_TYPES:
            return float(val)
    except (ValueError, TypeError):
        pass
    return val


def _coerce_derived(derived: Dict[str, Any]) -> None:
    """Type-coerce filter_values and level_order defaults using data_schema.

    os.listdir()-based filter_values are always strings ("1", "0.17") but
    query-time validation expects typed values (int 1, float 0.17). Mutates
    *derived* in place.
    """
    schema = derived.get("data_schema") or {}

    fv = derived.get("filter_values") or {}
    for col, values in fv.items():
        col_type = schema.get(col, "")
        if col_type and values and isinstance(values[0], str):
            fv[col] = [_coerce(v, col_type) for v in values]

    for lv in derived.get("level_order") or []:
        col_type = schema.get(lv["column"], "")
        if col_type and lv.get("default_value") is not None:
            lv["default_value"] = _coerce(lv["default_value"], col_type)


# ── Public write endpoints ─────────────────────────────────────────────────────

@router.post(
    "/register",
    status_code=201,
    openapi_extra=_ex({
            "catalog": "vcsi",
            "domain": "wikimedia",
            "dataset_id": "ngrams",
            "version": "latest",
            "schema_version": "0.3.0",
            "data_location": "/data/wikigrams",
            "data_format": "parquet_hive",
            "description": "Wikipedia n-grams by frequency, date, and location.",
            "manifest": {
                "availability": {
                    "United States": {
                        "daily": {"min": "2024-01-01", "max": "2026-04-20"},
                    },
                },
            },
            "data_schema": {
                "ngram": "VARCHAR",
                "pv_count": "BIGINT",
                "date": "DATE",
            },
            "entity_mapping": {
                "local_id_column": "location",
                "namespace": "wikidata",
            },
            "endpoint_schema": {
                "type": "types-counts",
                "type_column": "ngram",
                "count_column": "pv_count",
            },
            "transform": {
                "time_dimension": "date",
                "hash_bucket": {
                    "column": "ngram_bucket",
                    "default_count": 1,
                    "overrides": {"United States": {"1": 16, "2": 32}},
                },
            },
            "ownership": {
                "owner_group": "Vermont Complex Systems Center",
                "contact": "admin@example.org",
            },
            "lineage": {
                "repo": "https://github.com/Vermont-Complex-Systems/wikigrams",
            },
            "level_order": [
                {"column": "ngram_size", "type": "partition", "default_value": 1},
                {"column": "granularity", "type": "partition", "default_value": "daily"},
                {"column": "location", "type": "entity", "default_value": "Afghanistan"},
                {"column": "ngram_bucket", "type": "hash_bucket", "default_value": 0},
                {"column": "date", "type": "time", "default_value": "2020-01-01"},
            ],
            "created_at": "2024-01-15T10:00:00Z",
            "updated_at": "2024-01-15T10:00:00Z",
    }, status="201"),
)
async def register_dataset(
    dataset: DatasetCreate,
    request: Request,
    response: Response,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Register a new dataset or update an existing one (upsert)."""
    if dataset.domain not in VALID_DOMAINS:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown domain '{dataset.domain}'. Valid: {sorted(VALID_DOMAINS)}",
        )

    # ── Pre-registration validation ─────────────────────────────────────────────

    # 0a. Column names end up interpolated into SQL — reject non-identifiers
    #     before anything else.
    _validate_column_identifiers(dataset)

    # 0b. Immutable snapshot guard — check before the (expensive) filesystem
    #     walk and parquet introspection, not after.
    result = await db.execute(
        select(RegistryEntry).where(
            RegistryEntry.domain == dataset.domain,
            RegistryEntry.dataset_id == dataset.dataset_id,
            RegistryEntry.version == dataset.version,
        )
    )
    existing = result.scalar_one_or_none()
    if existing and dataset.version != "latest":
        raise HTTPException(
            status_code=409,
            detail=(
                f"Version '{dataset.version}' of '{dataset.domain}/{dataset.dataset_id}' "
                "already exists and is immutable. Bump the version string or use "
                "version='latest' for the mutable development slot."
            ),
        )

    # 1. Discover hive levels first (cheap filesystem walk) — needed by introspect()
    #    to know which columns to scan for filter_values.
    derived: Dict[str, Any] = {}
    if dataset.data_format == "parquet_hive":
        levels = _discover_levels(dataset.data_location)
        if levels:
            try:
                level_order = validate_and_build_level_order(levels, dataset)
                derived["level_order"] = level_order
            except ValueError as e:
                raise HTTPException(status_code=422, detail=str(e))

            # Derive hash_bucket config (counts + overrides) from disk
            if dataset.transform and dataset.transform.hash_bucket:
                bucket_config = _derive_bucket_config(dataset.data_location, level_order)
                if bucket_config:
                    derived["bucket_config"] = bucket_config

    # 2. Introspect the storage backend (read-only) — schema, filter_values,
    #    availability. When the submitter provides data_schema, schema
    #    introspection is skipped (allows registration during schema transitions).
    #    mongodb datasets are pass-through: no DuckDB — best-effort pymongo
    #    probes (sampled data_schema, distinct() filter_values, min/max
    #    availability), same never-raises contract as parquet introspection.
    if dataset.data_format == "mongodb":
        derived.update(await run_blocking_mongo(lambda: mongo_introspect(dataset)))
        if "data_schema" not in derived:
            reason = derived.get("introspect_error", "")
            hint = f" MongoDB error: {reason}" if reason else ""
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Collection '{dataset.data_location}' is not accessible.{hint} "
                    "Ensure MONGODB_URI is configured on the server and the "
                    "database/collection exist, or provide data_schema in the "
                    "registration payload to declare the authoritative schema."
                ),
            )
    else:
        try:
            with get_admin_duckdb_client().timed_connect() as conn:
                derived.update(
                    introspect(conn, dataset, provided_schema=dataset.data_schema,
                               level_order=derived.get("level_order"))
                )
        except Exception as e:
            log.warning("Parquet introspection failed for %s/%s: %s", dataset.domain, dataset.dataset_id, e)
            derived["introspect_error"] = str(e)

        if "data_schema" not in derived:
            reason = derived.get("introspect_error", "")
            hint = f" DuckDB error: {reason}" if reason else ""
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Data not accessible at '{dataset.data_location}'.{hint} "
                    "Ensure the path exists and is available to the API before registering. "
                    "If your files have inconsistent schemas (e.g. after a column was added or "
                    "removed), provide data_schema in the registration payload to declare the "
                    "authoritative schema and skip glob-based introspection."
                ),
            )

    # 2b. Refuse to register data we can't serve. A parquet_hive dataset with a
    #     time dimension resolves its "latest date" (and coverage) from
    #     manifest.availability; an empty result means the data was unreachable
    #     at registration (e.g. an NFS blip) — fail loudly instead of storing a
    #     silent null that 404s at query time.
    if (
        dataset.data_format == "parquet_hive"
        and dataset.transform and dataset.transform.time_dimension
        and derived.get("level_order")
        and not derived.get("availability")
    ):
        reason = derived.get("introspect_error", "")
        hint = f" ({reason})" if reason else ""
        raise HTTPException(
            status_code=422,
            detail=(
                f"Could not derive manifest.availability for "
                f"'{dataset.domain}/{dataset.dataset_id}'.{hint} The data may be unreachable "
                "(e.g. NFS). Refusing to register a dataset whose latest date can't be "
                "resolved — retry when the data is reachable."
            ),
        )

    # 3. Type-coerce filter_values and level_order default_values using data_schema.
    _coerce_derived(derived)

    # 4. Endpoint-type validation suites.
    if dataset.endpoint_schema and dataset.endpoint_schema.type == "types-counts":
        _validate_types_counts(dataset, derived)
    if dataset.endpoint_schema and dataset.endpoint_schema.type == "time-series":
        _validate_time_series(dataset, derived)

    # ── Upsert ──────────────────────────────────────────────────────────────────
    # `existing` was fetched (and the immutability guard applied) before introspection.

    # Serialize nested Pydantic models to plain dicts for JSON columns
    def _dump(obj) -> dict | None:
        return obj.model_dump(mode="json") if obj is not None else None

    # Extract partition_index from manifest into its own DB column.
    # This keeps manifest small (fast summary responses) while the
    # full index is available via full=True.
    manifest_dump = _dump(dataset.manifest) or {}
    partition_index = manifest_dump.pop("partition_index", None)
    manifest_small = manifest_dump  # manifest without the large partition_index

    # Replace string hash_bucket with the derived full config dict.
    # Submission sends "ngram_bucket"; stored format is
    # {"column": "ngram_bucket", "default_count": 1, "overrides": {...}}.
    transform_dump = _dump(dataset.transform)
    if "bucket_config" in derived and transform_dump:
        transform_dump["hash_bucket"] = derived["bucket_config"]

    if existing:
        existing.data_location = dataset.data_location
        existing.data_format = dataset.data_format
        existing.description = dataset.description
        existing.manifest = manifest_small
        existing.entity_mapping = _dump(dataset.entity_mapping)
        existing.endpoint_schema = _dump(dataset.endpoint_schema)
        existing.transform = transform_dump
        existing.catalog = dataset.catalog
        existing.ownership = _dump(dataset.ownership)
        existing.lineage = _dump(dataset.lineage)
        existing.schema_version = dataset.schema_version
        if partition_index is not None:
            existing.partition_index = partition_index
        await db.commit()
        await db.refresh(existing)
        response.status_code = 200
        action = "updated"
    else:
        db_entry = RegistryEntry(
            dataset_id=dataset.dataset_id,
            domain=dataset.domain,
            version=dataset.version,
            data_location=dataset.data_location,
            data_format=dataset.data_format,
            description=dataset.description,
            catalog=dataset.catalog,
            manifest=manifest_small,
            entity_mapping=_dump(dataset.entity_mapping),
            endpoint_schema=_dump(dataset.endpoint_schema),
            transform=transform_dump,
            ownership=_dump(dataset.ownership),
            lineage=_dump(dataset.lineage),
            schema_version=dataset.schema_version,
            partition_index=partition_index,
        )
        db.add(db_entry)
        await db.commit()
        await db.refresh(db_entry)
        action = "registered"

    # Upsert entities after the parent RegistryEntry is committed (FK requirement)
    entities_count = 0
    if dataset.entities:
        entities_count = await _upsert_entities(db, dataset.domain, dataset.dataset_id, dataset.entities)
        await db.commit()

    entry = existing if existing else db_entry

    # Persist introspection results into their own dedicated columns.
    if derived:
        if "data_schema" in derived:
            entry.data_schema = derived["data_schema"]
        if "filter_values" in derived:
            entry.filter_values = derived["filter_values"]
        if "availability" in derived:
            manifest = dict(entry.manifest or {})
            manifest["availability"] = derived["availability"]
            entry.manifest = manifest
        if "level_order" in derived:
            entry.level_order = derived["level_order"]
        await db.commit()

    # Refresh to avoid MissingGreenlet on lazy-loaded attributes after commit.
    await db.refresh(entry)

    # Keep the OpenAPI weight enums in step with the registry: rebuild the
    # menu snapshot and drop FastAPI's cached spec so the next /openapi.json
    # request re-renders with this registration's count_column menu.
    await refresh_weight_menus(db)
    request.app.openapi_schema = None

    # Build full response after all fields (including derived) are persisted.
    msg: Dict[str, Any] = {
        "message": f"RegistryEntry '{dataset.dataset_id}' {action} successfully",
        "dataset": _entry_response(entry),
    }
    if derived:
        msg["derived"] = list(derived.keys())
    if entities_count:
        msg["entities_upserted"] = entities_count
    return msg


@admin_router.post("/{domain}/{dataset_id}/entities")
async def upsert_dataset_entities(
    domain: str,
    dataset_id: str,
    entities: List[EntityRow],
    _: None = Depends(get_admin_user),
    db: AsyncSession = Depends(get_session),
):
    """Batch upsert entity mapping rows for a registered dataset. Idempotent."""
    if not await get_latest_entry(db, domain, dataset_id):
        raise HTTPException(status_code=404, detail=f"RegistryEntry '{domain}/{dataset_id}' not found")

    count = await _upsert_entities(db, domain, dataset_id, entities)
    await db.commit()
    return {"domain": domain, "dataset_id": dataset_id, "entities_upserted": count}


@admin_router.delete("/{domain}/{dataset_id}")
async def delete_dataset(
    domain: str,
    dataset_id: str,
    _: None = Depends(get_admin_user),
    db: AsyncSession = Depends(get_session),
):
    """Retire a dataset: remove all registry versions and its entity mappings.

    Data on disk is untouched — a retired dataset can be re-registered at any time.
    """
    result = await db.execute(
        select(RegistryEntry).where(
            RegistryEntry.domain == domain, RegistryEntry.dataset_id == dataset_id
        )
    )
    entries = result.scalars().all()
    if not entries:
        raise HTTPException(status_code=404, detail=f"RegistryEntry '{domain}/{dataset_id}' not found")

    em_result = await db.execute(
        select(EntityMapping).where(
            EntityMapping.domain == domain, EntityMapping.dataset_id == dataset_id
        )
    )
    entity_rows = em_result.scalars().all()

    for row in entity_rows:
        await db.delete(row)
    for entry in entries:
        await db.delete(entry)
    await db.commit()
    log.info("Retired dataset '%s/%s' (%d versions, %d entity rows)",
             domain, dataset_id, len(entries), len(entity_rows))
    return {
        "domain": domain,
        "dataset_id": dataset_id,
        "versions_deleted": len(entries),
        "entities_deleted": len(entity_rows),
    }


# ── Public endpoints ───────────────────────────────────────────────────────────

@router.get(
    "/domains",
    openapi_extra=_ex({"domains": sorted(VALID_DOMAINS)}),
)
async def list_valid_domains():
    """List accepted domain names for dataset registration."""
    return {"domains": sorted(VALID_DOMAINS)}


@router.get("/", openapi_extra=_ex({"datasets": [_EXAMPLE_DATASET], "total": 1}))
async def list_registered_datasets(db: AsyncSession = Depends(get_session)):
    """List all registered datasets (latest version per dataset)."""
    # DISTINCT ON (domain, dataset_id) ordered by created_at DESC gives the
    # most recently registered version for each dataset identity.
    result = await db.execute(
        select(RegistryEntry)
        .distinct(RegistryEntry.domain, RegistryEntry.dataset_id)
        .order_by(RegistryEntry.domain, RegistryEntry.dataset_id, RegistryEntry.created_at.desc())
    )
    datasets = result.scalars().all()
    return {
        "datasets": [
            {
                "catalog": ds.catalog,
                "domain": ds.domain,
                "dataset_id": ds.dataset_id,
                "version": ds.version,
                "data_location": ds.data_location,
                "data_format": ds.data_format,
                "description": ds.description,
                "endpoint_schema": ds.endpoint_schema,
                "level_order": ds.level_order,
                "filter_values": ds.filter_values,
                "created_at": ds.created_at,
                "updated_at": ds.updated_at,
            }
            for ds in datasets
        ],
        "total": len(datasets),
    }


def _entry_response(ds, *, manifest: Optional[dict] = None) -> Dict[str, Any]:
    """Serialize a RegistryEntry for API responses.

    *manifest* overrides ds.manifest (used by ?full=true to re-inject
    partition_index).
    """
    return {
        "catalog": ds.catalog,
        "domain": ds.domain,
        "dataset_id": ds.dataset_id,
        "version": ds.version,
        "schema_version": ds.schema_version,
        "data_location": ds.data_location,
        "data_format": ds.data_format,
        "description": ds.description,
        "manifest": manifest if manifest is not None else (ds.manifest or {}),
        "data_schema": ds.data_schema,
        "entity_mapping": ds.entity_mapping,
        "endpoint_schema": ds.endpoint_schema,
        "transform": ds.transform,
        "ownership": ds.ownership,
        "lineage": ds.lineage,
        "filter_values": ds.filter_values,
        "level_order": ds.level_order,
        "created_at": ds.created_at,
        "updated_at": ds.updated_at,
    }


_SUMMARY_COLUMNS = [
    RegistryEntry.domain, RegistryEntry.dataset_id, RegistryEntry.version,
    RegistryEntry.data_location, RegistryEntry.data_format,
    RegistryEntry.description, RegistryEntry.catalog,
    RegistryEntry.manifest,         # always small (availability only — partition_index excluded)
    RegistryEntry.data_schema,      # introspected column types — small, useful for SDK consumers
    RegistryEntry.entity_mapping, RegistryEntry.lineage,
    RegistryEntry.endpoint_schema,
    RegistryEntry.transform,        # query slice axes — small, needed by consumers
    RegistryEntry.ownership,        # governance metadata — small
    RegistryEntry.level_order,      # hive nesting order — small, shows full structure at a glance
    RegistryEntry.filter_values,   # introspected distinct values per filter dim — small dict
    RegistryEntry.schema_version,
    RegistryEntry.created_at, RegistryEntry.updated_at,
    # excluded: partition_index (can be large)
]


@router.get(
    "/{domain}/{dataset_id}",
    openapi_extra=_ex({
        "domain": "babynames",
        "dataset_id": "ngrams",
        "data_location": "/data/babynames/names.parquet",
        "data_format": "parquet",
        "description": "US baby name frequencies by state, year, and sex.",
        "manifest": {"data_schema": {"year": "int32", "sex": "varchar", "types": "varchar", "counts": "int64"}},
        "entity_mapping": None,
        "lineage": {},
        "endpoint_schema": {"type": "types-counts", "time_dimension": "year", "filter_dimensions": ["sex"]},
        "created_at": "2024-01-15T10:00:00Z",
        "updated_at": "2024-01-15T10:00:00Z",
    }),
)


async def get_dataset_info(
    domain: str,
    dataset_id: str,
    version: Optional[str] = None,
    full: bool = False,
    db: AsyncSession = Depends(get_session),
):
    """Get metadata for a specific registered dataset.

    Defaults to the latest version. Pass `?version=1.0.0` to retrieve an immutable snapshot.
    Pass `?full=true` to include filter_values and partition_index.
    """
    if full:
        ds = await get_latest_entry(db, domain, dataset_id, version)
        if not ds:
            raise HTTPException(status_code=404, detail=f"RegistryEntry '{domain}/{dataset_id}' not found")
        manifest_full = dict(ds.manifest or {})
        if ds.partition_index is not None:
            manifest_full["partition_index"] = ds.partition_index
        return _entry_response(ds, manifest=manifest_full)

    # Non-full: lightweight query — skips filter_values and partition_index.
    where = [RegistryEntry.domain == domain, RegistryEntry.dataset_id == dataset_id]
    if version:
        where.append(RegistryEntry.version == version)
    result = await db.execute(
        select(RegistryEntry)
        .options(load_only(*_SUMMARY_COLUMNS))
        .where(*where)
        .order_by(RegistryEntry.created_at.desc())
        .limit(1)
    )
    ds = result.scalar_one_or_none()
    if not ds:
        raise HTTPException(status_code=404, detail=f"RegistryEntry '{domain}/{dataset_id}' not found")

    return _entry_response(ds)


@router.get(
    "/{domain}/{dataset_id}/adapter",
    openapi_extra=_ex([
        {"local_id": "united_states", "entity_id": "wd:Q30", "entity_name": "United States", "entity_ids": ["wd:Q30"]},
        {"local_id": "california", "entity_id": "wd:Q99", "entity_name": "California", "entity_ids": ["wd:Q99"]},
    ]),
)
async def get_adapter_info(
    domain: str,
    dataset_id: str,
    db: AsyncSession = Depends(get_session),
):
    """List entity mapping rows for a dataset (entity_id ↔ local_id)."""
    rows_result = await db.execute(
        select(EntityMapping).where(
            EntityMapping.domain == domain,
            EntityMapping.dataset_id == dataset_id,
        )
    )
    rows = rows_result.scalars().all()
    if not rows:
        raise HTTPException(status_code=404, detail=f"No entity mappings for '{domain}/{dataset_id}'")

    return [
        {
            "local_id": r.local_id,
            "entity_id": r.entity_id,
            "entity_name": r.entity_name,
            "entity_ids": r.entity_ids,
        }
        for r in rows
    ]


@router.get(
    "/{domain}/{dataset_id}/validate-sources",
    openapi_extra=_ex({
        "domain": "babynames",
        "dataset_id": "ngrams",
        "summary": {"total_urls": 2, "accessible": 2, "inaccessible": 0, "all_accessible": True},
        "sources": {
            "national": {"url": [{"url": "https://example.org/names.zip", "status": "accessible", "status_code": 200, "method": "HEAD"}]}
        },
    }),
)
async def validate_dataset_sources(
    domain: str,
    dataset_id: str,
    db: AsyncSession = Depends(get_session),
):
    """Validate that all source URLs for a dataset are still accessible."""
    ds = await get_latest_entry(db, domain, dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail=f"RegistryEntry '{domain}/{dataset_id}' not found")

    sources = (ds.lineage or {}).get("sources")
    if not sources:
        return {"domain": domain, "dataset_id": dataset_id, "message": "No sources configured", "sources": {}}

    validation_results: Dict[str, Any] = {}
    headers = {"User-Agent": "Mozilla/5.0"}

    # One client for the whole validation pass — per-location clients waste
    # connections and TLS handshakes.
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, headers=headers) as client:
        for dimension, locations in sources.items():
            validation_results[dimension] = {}
            for location, urls in locations.items():
                url_list = [urls] if isinstance(urls, str) else urls
                location_results = []
                for url in url_list:
                    method_used = "HEAD"
                    try:
                        response = await client.head(url)
                        if response.status_code in [403, 405]:
                            method_used = "GET"
                            response = await client.get(url, headers={"Range": "bytes=0-0"})
                        location_results.append({
                            "url": url,
                            "status": "accessible" if response.status_code < 400 else "error",
                            "status_code": response.status_code,
                            "method": method_used,
                        })
                    except httpx.TimeoutException:
                        location_results.append({"url": url, "status": "timeout", "error": "Request timed out"})
                    except httpx.RequestError as e:
                        location_results.append({"url": url, "status": "error", "error": str(e)})
                validation_results[dimension][location] = location_results

    total_urls = sum(len(locs) for dim in validation_results.values() for locs in dim.values())
    accessible = sum(
        1 for dim in validation_results.values()
        for locs in dim.values()
        for r in locs
        if r.get("status") == "accessible"
    )
    return {
        "domain": domain,
        "dataset_id": dataset_id,
        "summary": {
            "total_urls": total_urls,
            "accessible": accessible,
            "inaccessible": total_urls - accessible,
            "all_accessible": accessible == total_urls,
        },
        "sources": validation_results,
    }


# ── Version history ────────────────────────────────────────────────────────────

@router.get("/{domain}/{dataset_id}/versions")
async def list_dataset_versions(
    domain: str,
    dataset_id: str,
    db: AsyncSession = Depends(get_session),
):
    """List all registered versions for a dataset, newest first.

    Returns the full version history: 'latest' (the mutable dev slot, if present)
    plus any immutable semver snapshots (e.g. '1.0.0', '2.0.0').
    """
    result = await db.execute(
        select(
            RegistryEntry.version,
            RegistryEntry.schema_version,
            RegistryEntry.description,
            RegistryEntry.created_at,
            RegistryEntry.updated_at,
        )
        .where(RegistryEntry.domain == domain, RegistryEntry.dataset_id == dataset_id)
        .order_by(RegistryEntry.created_at.desc())
    )
    rows = result.all()
    if not rows:
        raise HTTPException(status_code=404, detail=f"RegistryEntry '{domain}/{dataset_id}' not found")
    return {
        "domain": domain,
        "dataset_id": dataset_id,
        "versions": [
            {
                "version": r.version,
                "schema_version": r.schema_version,
                "description": r.description,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
            }
            for r in rows
        ],
        "total": len(rows),
    }
