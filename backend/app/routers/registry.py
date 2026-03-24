"""
Registry endpoints — discover and inspect registered file-based datasets.
"""

import logging
from typing import Any, Dict, List

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only
from sqlmodel import select

from storywrangler_schemas.registry import DatasetCreate, EntityRow

from ..core.database import get_session
from ..core.duckdb_client import get_duckdb_client
from ..core.parquet_introspect import introspect
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

def _ex(body: dict) -> dict:
    """Wrap an example body in the openapi_extra responses structure."""
    return {"responses": {"200": {"content": {"application/json": {"example": body}}}}}

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
    openapi_extra=_ex({
        "message": "RegistryEntry 'ngrams' registered successfully",
        "dataset": {
            "dataset_id": "ngrams",
            "data_location": "/data/babynames/names.parquet",
            "data_format": "parquet",
            "description": "US baby name frequencies by state, year, and sex.",
            "format_config": {},
        },
        "derived": ["data_schema", "filter_values"],
    }),
)
async def register_dataset(
    dataset: DatasetCreate,
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
    # Introspect first (read-only) so we can validate before touching the DB.
    derived: Dict[str, Any] = {}
    try:
        conn = get_duckdb_client().connect()
        derived = introspect(conn, dataset)
    except Exception as e:
        log.warning("Parquet introspection failed for %s/%s: %s", dataset.domain, dataset.dataset_id, e)

    if dataset.endpoint_schema and dataset.endpoint_schema.type == "types-counts":
        ep = dataset.endpoint_schema

        # 1. Require at least one comparison axis.
        # entity_mapping counts if it declares a local_id_column (with or without
        # entity_namespace / entities rows — namespace-only registrations are valid).
        has_entity = bool(dataset.entity_mapping)
        has_filter = bool(ep.filter_dimensions)
        if not has_entity and not has_filter:
            raise HTTPException(
                status_code=422,
                detail=(
                    "types-counts datasets require at least one comparison axis: "
                    "set entity_mapping (with entities) or declare filter_dimensions. "
                    "See https://github.com/vermont-complex-systems/Storywrangler-Specification for the spec."
                ),
            )

        # 2. If we could read the schema, verify the declared columns exist.
        data_schema = derived.get("data_schema") or {}
        if data_schema:
            type_col  = ep.type_column  or "types"
            count_col = ep.count_column or "counts"
            missing = [c for c in [type_col, count_col] if c not in data_schema]
            if missing:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"Column(s) {missing} not found in dataset schema {sorted(data_schema)}. "
                        "Declare the correct column names via endpoint_schema.type_column and "
                        "endpoint_schema.count_column. "
                        "See https://github.com/vermont-complex-systems/Storywrangler-Specification for the spec."
                    ),
                )

    # ── Upsert ──────────────────────────────────────────────────────────────────
    result = await db.execute(
        select(RegistryEntry).where(
            RegistryEntry.domain == dataset.domain,
            RegistryEntry.dataset_id == dataset.dataset_id,
        )
    )
    existing = result.scalar_one_or_none()

    # Serialize nested Pydantic models to plain dicts for JSON columns
    def _dump(obj) -> dict | None:
        return obj.model_dump(mode="json") if obj is not None else None

    if existing:
        existing.data_location = dataset.data_location
        existing.data_format = dataset.data_format
        existing.description = dataset.description
        existing.format_config = _dump(dataset.format_config)
        existing.entity_mapping = _dump(dataset.entity_mapping)
        existing.endpoint_schema = _dump(dataset.endpoint_schema)
        existing.catalog = dataset.catalog
        existing.ownership = _dump(dataset.ownership)
        existing.lineage = _dump(dataset.lineage)
        await db.commit()
        await db.refresh(existing)
        msg: Dict[str, Any] = {"message": f"RegistryEntry '{dataset.dataset_id}' updated successfully"}
    else:
        db_entry = RegistryEntry(
            dataset_id=dataset.dataset_id,
            domain=dataset.domain,
            data_location=dataset.data_location,
            data_format=dataset.data_format,
            description=dataset.description,
            catalog=dataset.catalog,
            format_config=_dump(dataset.format_config),
            entity_mapping=_dump(dataset.entity_mapping),
            endpoint_schema=_dump(dataset.endpoint_schema),
            ownership=_dump(dataset.ownership),
            lineage=_dump(dataset.lineage),
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
                "format_config": db_entry.format_config,
            },
        }

    # Upsert entities after the parent RegistryEntry is committed (FK requirement)
    entities_count = 0
    if dataset.entities:
        entities_count = await _upsert_entities(db, dataset.domain, dataset.dataset_id, dataset.entities)
        await db.commit()

    entry = existing if existing else db_entry

    # Persist introspection results derived before the DB write.
    if derived:
        fc = dict(entry.format_config or {})
        if "data_schema" in derived:
            fc["data_schema"] = derived["data_schema"]
            entry.format_config = fc
        ep_stored = dict(entry.endpoint_schema or {})
        if "filter_values" in derived:
            ep_stored["filter_values"] = derived["filter_values"]
            entry.endpoint_schema = ep_stored
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
    result = await db.execute(
        select(RegistryEntry).where(RegistryEntry.domain == domain, RegistryEntry.dataset_id == dataset_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail=f"RegistryEntry '{domain}/{dataset_id}' not found")

    count = await _upsert_entities(db, domain, dataset_id, entities)
    await db.commit()
    return {"domain": domain, "dataset_id": dataset_id, "entities_upserted": count}


# ── Public endpoints ───────────────────────────────────────────────────────────

@router.get("/", openapi_extra=_ex({"datasets": [_EXAMPLE_DATASET], "total": 1}))
async def list_registered_datasets(db: AsyncSession = Depends(get_session)):
    """List all registered datasets."""
    result = await db.execute(
        select(RegistryEntry).order_by(RegistryEntry.domain, RegistryEntry.dataset_id)
    )
    datasets = result.scalars().all()
    return {
        "datasets": [
            {
                "catalog": ds.catalog,
                "domain": ds.domain,
                "dataset_id": ds.dataset_id,
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
    RegistryEntry.domain, RegistryEntry.dataset_id,
    RegistryEntry.data_location, RegistryEntry.data_format,
    RegistryEntry.description, RegistryEntry.catalog,
    RegistryEntry.entity_mapping, RegistryEntry.lineage,
    RegistryEntry.endpoint_schema,
    RegistryEntry.created_at, RegistryEntry.updated_at,
]


@router.get(
    "/{domain}/{dataset_id}",
    openapi_extra=_ex({
        "domain": "babynames",
        "dataset_id": "ngrams",
        "data_location": "/data/babynames/names.parquet",
        "data_format": "parquet",
        "description": "US baby name frequencies by state, year, and sex.",
        "format_config": {"data_schema": {"year": "int32", "sex": "varchar", "types": "varchar", "counts": "int64"}},
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
    full: bool = False,
    db: AsyncSession = Depends(get_session),
):
    """Get metadata for a specific registered dataset. """
    where = (RegistryEntry.domain == domain, RegistryEntry.dataset_id == dataset_id)

    if full:
        result = await db.execute(select(RegistryEntry).where(*where))
        ds = result.scalar_one_or_none()
        if not ds:
            raise HTTPException(status_code=404, detail=f"RegistryEntry '{domain}/{dataset_id}' not found")
        return {
            "domain": ds.domain,
            "dataset_id": ds.dataset_id,
            "data_location": ds.data_location,
            "data_format": ds.data_format,
            "description": ds.description,
            "format_config": ds.format_config or {},
            "entity_mapping": ds.entity_mapping,
            "lineage": ds.lineage,
            "endpoint_schema": ds.endpoint_schema,
            "created_at": ds.created_at,
            "updated_at": ds.updated_at,
        }

    # Non-full: skip format_config (can be MB-sized) and strip filter_values
    # from endpoint_schema so the summary response stays lightweight.
    result = await db.execute(
        select(RegistryEntry).options(load_only(*_SUMMARY_COLUMNS)).where(*where)
    )
    ds = result.scalar_one_or_none()
    if not ds:
        raise HTTPException(status_code=404, detail=f"RegistryEntry '{domain}/{dataset_id}' not found")

    ep = ds.endpoint_schema or {}
    return {
        "domain": ds.domain,
        "dataset_id": ds.dataset_id,
        "data_location": ds.data_location,
        "data_format": ds.data_format,
        "description": ds.description,
        "format_config": {},
        "entity_mapping": ds.entity_mapping,
        "lineage": ds.lineage,
        "endpoint_schema": {k: v for k, v in ep.items() if k != "filter_values"},
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
    result = await db.execute(
        select(RegistryEntry).where(RegistryEntry.domain == domain, RegistryEntry.dataset_id == dataset_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail=f"RegistryEntry '{domain}/{dataset_id}' not found")

    rows_result = await db.execute(
        select(EntityMapping).where(
            EntityMapping.domain == domain,
            EntityMapping.dataset_id == dataset_id,
        )
    )
    rows = rows_result.scalars().all()
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
    result = await db.execute(
        select(RegistryEntry).where(RegistryEntry.domain == domain, RegistryEntry.dataset_id == dataset_id)
    )
    ds = result.scalar_one_or_none()
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


# ── Entity graph endpoints ─────────────────────────────────────────────────────

_KNOWN_PREDICATES = {"affiliated_with", "same_as", "country", "broader"}


@router.get(
    "/entity-graph/path",
    openapi_extra=_ex({
        "from_id": "openalex:A5002034958",
        "to_namespace": "wikidata",
        "path": [
            {"subject": "openalex:A5002034958", "predicate": "affiliated_with", "object": "openalex:I26873012"},
            {"subject": "openalex:I26873012",   "predicate": "same_as",         "object": "wikidata:Q1068"},
            {"subject": "wikidata:Q1068",        "predicate": "country",         "object": "wikidata:Q30"},
        ],
        "hops": 3,
    }),
)
async def find_entity_path(
    from_id: str,
    to_namespace: str,
    max_hops: int = 6,
    db: AsyncSession = Depends(get_session),
):
    """BFS traversal of the entity graph from `from_id` until reaching `to_namespace`.

    Example: from_id=openalex:A5002034958 & to_namespace=wikidata
    returns the chain openalex:A → openalex:I → wikidata:Q (institution country)
    which is the join path into any dataset keyed on Wikidata entities (e.g. babynames).
    """
    visited = {from_id}
    # queue entries: (current_id, path_so_far)
    queue: list[tuple[str, list[dict]]] = [(from_id, [])]

    while queue:
        current_id, path = queue.pop(0)

        # Reached the target namespace (and moved at least one hop)
        if path and current_id.startswith(f"{to_namespace}:"):
            return {"from_id": from_id, "to_namespace": to_namespace, "path": path, "hops": len(path)}

        if len(path) >= max_hops:
            continue

        result = await db.execute(
            select(EntityGraph).where(EntityGraph.subject_id == current_id)
        )
        for edge in result.scalars().all():
            if edge.object_id not in visited:
                visited.add(edge.object_id)
                queue.append((
                    edge.object_id,
                    path + [{"subject": current_id, "predicate": edge.predicate, "object": edge.object_id}],
                ))

    raise HTTPException(
        status_code=404,
        detail=f"No path found from '{from_id}' to namespace '{to_namespace}' within {max_hops} hops.",
    )


@router.get("/entity-graph/neighbors")
async def get_entity_neighbors(
    entity_id: str,
    db: AsyncSession = Depends(get_session),
):
    """Return all direct edges from entity_id in the graph."""
    result = await db.execute(
        select(EntityGraph).where(EntityGraph.subject_id == entity_id)
    )
    edges = result.scalars().all()
    return {
        "entity_id": entity_id,
        "edges": [
            {"predicate": e.predicate, "object": e.object_id, "source": e.source}
            for e in edges
        ],
    }


@admin_router.post("/entity-graph")
async def upsert_entity_graph_edges(
    edges: List[Dict[str, str]],
    _: None = Depends(get_admin_user),
    db: AsyncSession = Depends(get_session),
):
    """Upsert edges into the entity graph. Each edge: {subject_id, predicate, object_id, source}.

    Predicates: affiliated_with | same_as | country | broader
    """
    upserted = 0
    for edge in edges:
        subject_id = edge.get("subject_id", "")
        predicate   = edge.get("predicate", "")
        object_id   = edge.get("object_id", "")
        source      = edge.get("source", "manual")

        if not (subject_id and predicate and object_id):
            raise HTTPException(status_code=422, detail=f"Missing fields in edge: {edge}")
        if predicate not in _KNOWN_PREDICATES:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown predicate '{predicate}'. Supported: {sorted(_KNOWN_PREDICATES)}",
            )

        result = await db.execute(
            select(EntityGraph).where(
                EntityGraph.subject_id == subject_id,
                EntityGraph.predicate  == predicate,
                EntityGraph.object_id  == object_id,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            existing.source = source
        else:
            db.add(EntityGraph(subject_id=subject_id, predicate=predicate, object_id=object_id, source=source))
        upserted += 1

    await db.commit()
    return {"edges_upserted": upserted}
