"""
Registry endpoints — discover and inspect registered file-based datasets.
"""

import logging
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only
from sqlmodel import select

from storywrangler_schemas.registry import DatasetCreate, EntityRow

from ..core.database import get_session
from ..core.duckdb_client import get_duckdb_client
from ..core.parquet_introspect import introspect
from ..core.registry_utils import get_latest_entry
from ..models.auth import User
from ..models.registry import RegistryEntry, EntityMapping, EntityGraph
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

# Domains that have actual registered routers. Update when adding a new router to main.py.
VALID_DOMAINS = {
    "wikimedia",
    "storywrangler",
    "babynames",
    "open-academic-analytics",
    "scisciDB",
    "vt-zoning-atlas",
}

async def _upsert_entities(
    db: AsyncSession,
    domain: str,
    dataset_id: str,
    entities: List[EntityRow],
) -> int:
    """Upsert entity mapping rows. Returns count upserted."""
    for entity in entities:
        row_id = f"{domain}:{dataset_id}:{entity.local_id}"
        existing = await db.get(EntityMapping, row_id)
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


# ── Public write endpoints ─────────────────────────────────────────────────────

@router.post(
    "/register",
    status_code=201,
    openapi_extra=_ex({
        "message": "RegistryEntry 'ngrams' registered successfully",
        "dataset": {
            "dataset_id": "ngrams",
            "data_location": "/data/wikigrams",
            "data_format": "parquet_hive",
            "description": "Wikipedia n-grams by frequency, date, and location.",
            "manifest": {},
        },
        "derived": ["data_schema", "filter_values", "availability"],
        "entities_upserted": 12,
    }, status="201"),
)
async def register_dataset(
    dataset: DatasetCreate,
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

    # ── data_location / partition_dimensions consistency ────────────────────────
    # For parquet_hive, data_location must be the root of the hive tree — the
    # directory directly above the first col=val/ level.  If the path already
    # embeds a partition dimension (e.g. "/data/ngram_size=1") and the same key
    # appears in partition_dimensions, queries will double the path segment.
    if dataset.data_format == "parquet_hive" and dataset.transform:
        partition_keys = set()
        pd = dataset.transform.partition_dimensions
        if isinstance(pd, dict):
            partition_keys = set(pd.keys())
        elif isinstance(pd, list):
            partition_keys = set(pd)
        if partition_keys:
            from pathlib import PurePosixPath
            path_parts = PurePosixPath(dataset.data_location or "").parts
            embedded = [
                part for part in path_parts
                if "=" in part and part.split("=", 1)[0] in partition_keys
            ]
            if embedded:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"data_location contains hive partition segment(s) {embedded} that also "
                        f"appear in partition_dimensions {sorted(partition_keys)}. "
                        "data_location must be the root of the hive tree (the directory above "
                        "the first col=val/ level) so that query code can append partition paths "
                        "without duplication."
                    ),
                )

    # ── Pre-registration validation ─────────────────────────────────────────────
    # Introspect first (read-only) so we can validate before touching the DB.
    # When the submitter provides data_schema, glob-based schema introspection
    # is skipped (allows registration during schema transitions).
    derived: Dict[str, Any] = {}
    try:
        conn = get_duckdb_client().connect()
        derived = introspect(conn, dataset, provided_schema=dataset.data_schema)
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

    if dataset.endpoint_schema and dataset.endpoint_schema.type == "types-counts":
        ep = dataset.endpoint_schema

        # 1. Require at least one comparison axis so the allotaxonometer can distinguish
        # system 1 from system 2.  Any of the four axes is sufficient:
        #   entity_mapping        → ?entity=X  vs ?entity2=Y
        #   time_dimension        → ?dates=D1  vs ?dates2=D2
        #   filter_dimensions     → ?sex=M     vs ?sex2=F
        #   partition_dimensions  → ?gran=daily vs ?gran2=weekly
        has_entity    = bool(dataset.entity_mapping)
        has_time      = bool(dataset.transform and dataset.transform.time_dimension)
        has_filter    = bool(dataset.transform and dataset.transform.filter_dimensions)
        has_partition = bool(dataset.transform and dataset.transform.partition_dimensions)
        if not any([has_entity, has_time, has_filter, has_partition]):
            raise HTTPException(
                status_code=422,
                detail=(
                    "types-counts datasets require at least one comparison axis so the "
                    "allotaxonometer can distinguish system 1 from system 2. Declare one of: "
                    "entity_mapping, transform.time_dimension, transform.filter_dimensions, "
                    "or transform.partition_dimensions. "
                    "See https://github.com/vermont-complex-systems/Storywrangler-Specification for the spec."
                ),
            )

        # 2. If we could read the schema, verify the declared columns exist.
        data_schema = derived.get("data_schema") or {}
        if data_schema:
            type_col  = ep.type_column  or "types"
            count_col = ep.count_column or "counts"
            expected = [type_col, count_col]
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

    if dataset.endpoint_schema and dataset.endpoint_schema.type == "time-series":
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
        has_filter    = bool(dataset.transform.filter_dimensions)
        has_partition = bool(dataset.transform.partition_dimensions)
        if not has_filter and not has_partition:
            raise HTTPException(
                status_code=422,
                detail=(
                    "time-series datasets require at least one groupable dimension: "
                    "declare filter_dimensions or partition_dimensions in transform. "
                    "See https://github.com/vermont-complex-systems/Storywrangler-Specification for the spec."
                ),
            )

        # 3. If we could read the schema, verify all declared columns exist.
        data_schema = derived.get("data_schema") or {}
        if data_schema:
            time_col    = dataset.transform.time_dimension
            count_col   = ep.count_column or "count"
            filter_cols = list(dataset.transform.filter_dimensions or [])
            expected    = [time_col, count_col] + filter_cols
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

    # ── Upsert ──────────────────────────────────────────────────────────────────
    result = await db.execute(
        select(RegistryEntry).where(
            RegistryEntry.domain == dataset.domain,
            RegistryEntry.dataset_id == dataset.dataset_id,
            RegistryEntry.version == dataset.version,
        )
    )
    existing = result.scalar_one_or_none()

    # Immutable snapshot guard: reject re-registration of any version except 'latest'
    if existing and dataset.version != "latest":
        raise HTTPException(
            status_code=409,
            detail=(
                f"Version '{dataset.version}' of '{dataset.domain}/{dataset.dataset_id}' "
                "already exists and is immutable. Bump the version string or use "
                "version='latest' for the mutable development slot."
            ),
        )

    # Serialize nested Pydantic models to plain dicts for JSON columns
    def _dump(obj) -> dict | None:
        return obj.model_dump(mode="json") if obj is not None else None

    # Extract partition_index from manifest into its own DB column.
    # This keeps manifest small (fast summary responses) while the
    # full index is available via full=True.
    manifest_dump = _dump(dataset.manifest) or {}
    partition_index = manifest_dump.pop("partition_index", None)
    manifest_small = manifest_dump  # manifest without the large partition_index

    if existing:
        existing.data_location = dataset.data_location
        existing.data_format = dataset.data_format
        existing.description = dataset.description
        existing.manifest = manifest_small
        existing.entity_mapping = _dump(dataset.entity_mapping)
        existing.endpoint_schema = _dump(dataset.endpoint_schema)
        existing.transform = _dump(dataset.transform)
        existing.catalog = dataset.catalog
        existing.ownership = _dump(dataset.ownership)
        existing.lineage = _dump(dataset.lineage)
        existing.schema_version = dataset.schema_version
        if partition_index is not None:
            existing.partition_index = partition_index
        await db.commit()
        await db.refresh(existing)
        response.status_code = 200
        msg: Dict[str, Any] = {"message": f"RegistryEntry '{dataset.dataset_id}' updated successfully"}
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
            transform=_dump(dataset.transform),
            ownership=_dump(dataset.ownership),
            lineage=_dump(dataset.lineage),
            schema_version=dataset.schema_version,
            partition_index=partition_index,
        )
        db.add(db_entry)
        await db.commit()
        await db.refresh(db_entry)
        msg = {
            "message": f"RegistryEntry '{dataset.dataset_id}' registered successfully",
            "dataset": {
                "dataset_id": db_entry.dataset_id,
                "data_location": db_entry.data_location,
                "data_format": db_entry.data_format,
                "description": db_entry.description,
                "manifest": db_entry.manifest,
            },
        }

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
        await db.commit()
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


# ── Public endpoints ───────────────────────────────────────────────────────────

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
                "created_at": ds.created_at,
                "updated_at": ds.updated_at,
            }
            for ds in datasets
        ],
        "total": len(datasets),
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
    RegistryEntry.schema_version,
    RegistryEntry.created_at, RegistryEntry.updated_at,
    # excluded: filter_values (medium), partition_index (can be large)
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
        return {
            "domain": ds.domain,
            "dataset_id": ds.dataset_id,
            "version": ds.version,
            "schema_version": ds.schema_version,
            "data_location": ds.data_location,
            "data_format": ds.data_format,
            "description": ds.description,
            "manifest": manifest_full,
            "data_schema": ds.data_schema,
            "entity_mapping": ds.entity_mapping,
            "endpoint_schema": ds.endpoint_schema,
            "transform": ds.transform,
            "ownership": ds.ownership,
            "lineage": ds.lineage,
            "filter_values": ds.filter_values,
            "created_at": ds.created_at,
            "updated_at": ds.updated_at,
        }

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

    return {
        "domain": ds.domain,
        "dataset_id": ds.dataset_id,
        "version": ds.version,
        "schema_version": ds.schema_version,
        "data_location": ds.data_location,
        "data_format": ds.data_format,
        "description": ds.description,
        "manifest": ds.manifest or {},
        "data_schema": ds.data_schema,
        "entity_mapping": ds.entity_mapping,
        "endpoint_schema": ds.endpoint_schema,
        "transform": ds.transform,
        "ownership": ds.ownership,
        "lineage": ds.lineage,
        "created_at": ds.created_at,
        "updated_at": ds.updated_at,
    }


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

    for dimension, locations in sources.items():
        validation_results[dimension] = {}
        for location, urls in locations.items():
            url_list = [urls] if isinstance(urls, str) else urls
            location_results = []
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, headers=headers) as client:
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


# ── Entity graph endpoints ─────────────────────────────────────────────────────

# _KNOWN_PREDICATES = {"affiliated_with", "same_as", "country", "broader"}


# @router.get(
#     "/entity-graph/path",
#     openapi_extra=_ex({
#         "from_id": "openalex:A5002034958",
#         "to_namespace": "wikidata",
#         "path": [
#             {"subject": "openalex:A5002034958", "predicate": "affiliated_with", "object": "openalex:I26873012"},
#             {"subject": "openalex:I26873012",   "predicate": "same_as",         "object": "wikidata:Q1068"},
#             {"subject": "wikidata:Q1068",        "predicate": "country",         "object": "wikidata:Q30"},
#         ],
#         "hops": 3,
#     }),
# )
# async def find_entity_path(
#     from_id: str,
#     to_namespace: str,
#     max_hops: int = 6,
#     db: AsyncSession = Depends(get_session),
# ):
#     """BFS traversal of the entity graph from `from_id` until reaching `to_namespace`.

#     Example: from_id=openalex:A5002034958 & to_namespace=wikidata
#     returns the chain openalex:A → openalex:I → wikidata:Q (institution country)
#     which is the join path into any dataset keyed on Wikidata entities (e.g. babynames).
#     """
#     visited = {from_id}
#     # queue entries: (current_id, path_so_far)
#     queue: list[tuple[str, list[dict]]] = [(from_id, [])]

#     while queue:
#         current_id, path = queue.pop(0)

#         # Reached the target namespace (and moved at least one hop)
#         if path and current_id.startswith(f"{to_namespace}:"):
#             return {"from_id": from_id, "to_namespace": to_namespace, "path": path, "hops": len(path)}

#         if len(path) >= max_hops:
#             continue

#         result = await db.execute(
#             select(EntityGraph).where(EntityGraph.subject_id == current_id)
#         )
#         for edge in result.scalars().all():
#             if edge.object_id not in visited:
#                 visited.add(edge.object_id)
#                 queue.append((
#                     edge.object_id,
#                     path + [{"subject": current_id, "predicate": edge.predicate, "object": edge.object_id}],
#                 ))

#     raise HTTPException(
#         status_code=404,
#         detail=f"No path found from '{from_id}' to namespace '{to_namespace}' within {max_hops} hops.",
#     )


# @router.get("/entity-graph/neighbors")
# async def get_entity_neighbors(
#     entity_id: str,
#     db: AsyncSession = Depends(get_session),
# ):
#     """Return all direct edges from entity_id in the graph."""
#     result = await db.execute(
#         select(EntityGraph).where(EntityGraph.subject_id == entity_id)
#     )
#     edges = result.scalars().all()
#     return {
#         "entity_id": entity_id,
#         "edges": [
#             {"predicate": e.predicate, "object": e.object_id, "source": e.source}
#             for e in edges
#         ],
#     }


# @admin_router.post("/entity-graph")
# async def upsert_entity_graph_edges(
#     edges: List[Dict[str, str]],
#     _: None = Depends(get_admin_user),
#     db: AsyncSession = Depends(get_session),
# ):
#     """Upsert edges into the entity graph. Each edge: {subject_id, predicate, object_id, source}.

#     Predicates: affiliated_with | same_as | country | broader
#     """
#     upserted = 0
#     for edge in edges:
#         subject_id = edge.get("subject_id", "")
#         predicate   = edge.get("predicate", "")
#         object_id   = edge.get("object_id", "")
#         source      = edge.get("source", "manual")

#         if not (subject_id and predicate and object_id):
#             raise HTTPException(status_code=422, detail=f"Missing fields in edge: {edge}")
#         if predicate not in _KNOWN_PREDICATES:
#             raise HTTPException(
#                 status_code=422,
#                 detail=f"Unknown predicate '{predicate}'. Supported: {sorted(_KNOWN_PREDICATES)}",
#             )

#         result = await db.execute(
#             select(EntityGraph).where(
#                 EntityGraph.subject_id == subject_id,
#                 EntityGraph.predicate  == predicate,
#                 EntityGraph.object_id  == object_id,
#             )
#         )
#         existing = result.scalar_one_or_none()
#         if existing:
#             existing.source = source
#         else:
#             db.add(EntityGraph(subject_id=subject_id, predicate=predicate, object_id=object_id, source=source))
#         upserted += 1

#     await db.commit()
#     return {"edges_upserted": upserted}
