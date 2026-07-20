"""Format-agnostic query helpers for registry-driven datasets.

The registry's query-time view: which dimensions are filterable, which count
column a request selects, how identifiers resolve to entities, and how
manifest availability is read. Nothing here touches DuckDB or Mongo — the
parquet engine lives in duckdb_query.py, the mongodb pass-through in
mongo_client.py.
"""

import logging
from types import SimpleNamespace
from typing import Any, List, Optional

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from storywrangler_schemas.standards import Standards
from ..models.registry import EntityMapping, RegistryEntry

log = logging.getLogger(__name__)


# ── Level-order helpers ──────────────────────────────────────────────────────
# Utilities that derive query-time metadata from the stored level_order.

def get_partition_defaults(dataset_obj) -> dict:
    """Build a {column: default_value} dict from the stored level_order.

    Returns defaults for "partition" and "filter" type levels — the columns
    where omitting a value should inject a safe default rather than aggregate.
    Entity, time, and hash_bucket levels are excluded (handled separately).
    """
    level_order = getattr(dataset_obj, "level_order", None)
    if not level_order:
        return {}
    return {
        lv["column"]: lv["default_value"]
        for lv in level_order
        if lv["type"] in ("partition", "filter") and lv.get("default_value") is not None
    }


def get_queryable_dims(dataset_obj) -> list:
    """Return column names that callers can filter on (partition + filter types).

    Reads from the stored level_order computed at registration time. Datasets
    without one (flat parquet, mongodb pass-through) fall back to the declared
    transform.filter_dimensions.
    """
    level_order = getattr(dataset_obj, "level_order", None)
    if not level_order:
        transform = getattr(dataset_obj, "transform", None) or {}
        return list(transform.get("filter_dimensions") or [])
    return [
        lv["column"] for lv in level_order
        if lv["type"] in ("partition", "filter")
    ]


# ── Count-column menu ────────────────────────────────────────────────────────
# endpoint_schema.count_column is a single column or a list of selectable
# measure columns (first = default). Endpoints expose the choice as ?weight=.

def get_count_columns(dataset_obj) -> list:
    """Registered count-column menu as a list (may be empty)."""
    cc = (dataset_obj.endpoint_schema or {}).get("count_column")
    if not cc:
        return []
    return cc if isinstance(cc, list) else [cc]


def resolve_count_column(dataset_obj, weight: Optional[str] = None, default: str = "counts") -> str:
    """Pick the count column for a request.

    No weight → the first registered column (or *default* when the dataset
    declares none). With a weight, it must be one of the registered columns:
    the menu doubles as the SQL-injection allowlist, since the result is
    interpolated into SUM() unparameterized.
    """
    menu = get_count_columns(dataset_obj)
    if weight is None:
        return menu[0] if menu else default
    if weight not in menu:
        detail = (
            f"weight must be one of {menu}" if len(menu) > 1
            else "this dataset has a single count column; omit the weight parameter"
        )
        raise HTTPException(status_code=400, detail=detail)
    return weight


def _derive_local_id(namespace: Optional[str], canonical_id: str) -> Optional[str]:
    """Derive the stored local_id from a canonical entity_id.

    Returns None when no known transform exists for the namespace, meaning an
    explicit entity row is still required.

    Examples:
        openalex  openalex:A5002034958  →  https://openalex.org/A5002034958
        doi       doi:10.1234/xyz       →  https://doi.org/10.1234/xyz
    """
    if not namespace:
        return None
    url_base = Standards.NAMESPACE_URL_PREFIXES.get(namespace)
    if not url_base:
        return None
    prefix = f"{namespace}:"
    if canonical_id.startswith(prefix):
        return url_base + canonical_id[len(prefix):]
    return None


async def resolve_entity(
    db: AsyncSession, domain: str, dataset: str, identifier: str
) -> EntityMapping:
    """Resolve an identifier → EntityMapping row.

    Accepts either a canonical entity_id (e.g. 'wikidata:Q675558') or a
    local_id (e.g. 'Arlington'). Tries entity_id first, then local_id.

    Fallback for global-identifier columns: if no entity row exists but the
    dataset declares entity_namespace (e.g. "openalex"), the local_id is
    derived from the canonical ID without requiring explicit entity rows.
    Raises 400 if no resolution path is found.
    """
    result = await db.execute(
        select(EntityMapping).where(
            EntityMapping.domain == domain,
            EntityMapping.dataset_id == dataset,
            EntityMapping.entity_id == identifier,
        )
    )
    em = result.scalar_one_or_none()
    if em:
        return em

    result = await db.execute(
        select(EntityMapping).where(
            EntityMapping.domain == domain,
            EntityMapping.dataset_id == dataset,
            EntityMapping.local_id == identifier,
        )
    )
    em = result.scalar_one_or_none()
    if em:
        return em

    # Namespace-aware fallback: no entity row needed when the column already
    # holds globally-typed values (e.g. OpenAlex URLs, DOI URLs).
    reg_result = await db.execute(
        select(RegistryEntry).where(
            RegistryEntry.domain == domain,
            RegistryEntry.dataset_id == dataset,
        )
    )
    ds = reg_result.scalar_one_or_none()
    namespace = ((ds.entity_mapping or {}) if ds else {}).get("entity_namespace")
    local_id = _derive_local_id(namespace, identifier)
    if local_id:
        return SimpleNamespace(local_id=local_id)  # type: ignore[return-value]

    raise HTTPException(
        status_code=400,
        detail=f"Entity '{identifier}' not found in entity mappings for {domain}/{dataset}",
    )


def parse_dates(s: Optional[str]) -> Optional[List[str]]:
    """Split a 'start' or 'start,end' date string into a two-element list.

    Always returns strings — type casting for the BETWEEN clause is deferred to
    _cast_dates() inside load_system(), which reads the column type from data_schema.
    """
    if s is None:
        return None
    parts = s.split(",")
    return [parts[0], parts[0]] if len(parts) == 1 else [parts[0], parts[1]]


def latest_from_manifest(dataset_obj, local_id, granularity=None):
    """Read the latest available date from manifest.availability.

    Availability is keyed by local_id (entity column value) with nested
    partition dims and min/max bounds — populated at registration time by
    parquet_introspect.

    Handles any nesting depth:
      - {"min": ..., "max": ...}                          (flat)
      - {"daily": {"min": ..., "max": ...}}               (single partition)
      - {"1": {"daily": {"min": ..., "max": ...}}}        (multi partition)
      - {"US": {"1": {"daily": {"min":..,  "max":..}}}}   (entity + multi partition)

    Searches recursively for the granularity key, or falls back to traversing
    the first path at each level until reaching a leaf with "max".
    """
    availability = (dataset_obj.manifest or {}).get("availability", {})
    if not availability:
        return None
    if local_id is not None and local_id in availability:
        entry = availability[local_id]
    elif local_id is None:
        entry = availability
    else:
        return None

    def _find_max(d, target):
        """Recursively find bounds, preferring *target* key at any depth."""
        if not isinstance(d, dict):
            return None
        if "min" in d and "max" in d:
            return d["max"]
        if target and target in d:
            return _find_max(d[target], None)
        for v in d.values():
            if isinstance(v, dict):
                result = _find_max(v, target)
                if result is not None:
                    return result
        return None

    return _find_max(entry, granularity)
