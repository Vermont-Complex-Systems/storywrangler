"""Format-agnostic query helpers for registry-driven datasets.

The registry's query-time view: which dimensions are filterable, which count
column a request selects, how identifiers resolve to entities, and how
manifest availability is read. Nothing here touches DuckDB or Mongo — the
parquet engine lives in duckdb_query.py, the mongodb pass-through in
mongo_client.py.
"""

import logging
from types import SimpleNamespace
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import defer

from storywrangler_schemas.coercion import coerce_scalar
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


def extract_filter_vals(dataset_obj, query_params, suffix: str = "",
                        inject_defaults: bool = True) -> dict:
    """Filter-dimension values for one system, from raw request query params.

    The generic-endpoint convention (/storywrangler/*): any queryable
    dimension can be passed as ``?dim=val`` — or ``?dim2=val`` with
    ``suffix="2"`` for a second system. Missing partition dims get the
    dataset's registered level_order defaults injected, and every value is
    validated against the introspected filter_values with type coercion
    (query params arrive as strings; filter_values stores typed values).
    Raises 400 on a value not in the valid set.

    ``inject_defaults=False`` returns only the explicitly-passed dims (no
    level_order defaults) — used by extract_filter_pair to distinguish "system 2
    said nothing about this dim" (inherit system 1) from "system 2 wants the
    default".
    """
    vals = {
        dim: query_params[f"{dim}{suffix}"]
        for dim in get_queryable_dims(dataset_obj)
        if f"{dim}{suffix}" in query_params
    }
    if inject_defaults:
        for dim, default_val in get_partition_defaults(dataset_obj).items():
            vals.setdefault(dim, default_val)

    fv = dataset_obj.filter_values or {}
    for dim, val in list(vals.items()):
        valid = fv.get(dim, [])
        if not valid or val in valid:
            continue
        coerced = coerce_scalar(val)
        if coerced not in valid:
            raise HTTPException(
                status_code=400,
                detail=f"{dim} must be one of {sorted(map(str, valid))}",
            )
        vals[dim] = coerced
    return vals


def extract_filter_pair(dataset_obj, query_params) -> tuple:
    """(system-1 filters, system-2 filters) for the two-system instruments.

    System 2 inherits system 1's filters per dimension, overridden by any
    explicit ``?dim2=`` param — so bare ``?sex=M`` filters *both* systems, while
    ``?sex=M&sex2=F`` compares them. This is the single source of the
    convention: allotax / rtd / wordshift all use it, so the behaviour is
    identical across endpoints and storage formats. (Previously the merge was
    inlined per-endpoint and had drifted — parquet allotax/wordshift silently
    left system 2 unfiltered, a comparison-skewing trap.)

    System 2 takes only its *explicit* ``?dim2=`` overrides (no default
    injection) merged over system 1 — otherwise a hive dataset's level_order
    defaults would snap unspecified system-2 dims to the default instead of
    inheriting system 1 (e.g. bare ``?granularity=weekly`` would compare weekly
    vs the default daily).
    """
    fv1 = extract_filter_vals(dataset_obj, query_params)
    explicit2 = extract_filter_vals(
        dataset_obj, query_params, suffix="2", inject_defaults=False)
    return fv1, {**fv1, **explicit2}


# ── Count-column menu ────────────────────────────────────────────────────────
# endpoint_schema.count_column is a single column or a list of selectable
# measure columns (first = default). Endpoints expose the choice as ?weight=.

def dates_mode(dataset_obj) -> str:
    """How the dataset's endpoints accept dates: 'range' | 'single' | 'none'.

    Derived from the registration, never stored: no transform.time_dimension
    → 'none' (dateless corpus — omit dates entirely); mongodb pass-through
    → 'single' (per-day precomputed rows, no range aggregation); otherwise
    → 'range' ('2024-10-01' or '2024-10-01,2024-10-31'). Surfaced as the
    `dates` field in registry responses; manifest.availability holds the
    actual bounds.
    """
    if not (getattr(dataset_obj, "transform", None) or {}).get("time_dimension"):
        return "none"
    if dataset_obj.data_format == "mongodb":
        return "single"
    return "range"


def require_dates_supported(dataset_obj, label: str, *date_params) -> None:
    """400 when dates are passed to a dataset that has no time dimension.

    Silent-ignore is the alternative — load_system skips the time clause
    when time_dimension is absent — and a 200 that quietly drops a filter
    teaches the caller nothing.
    """
    if any(date_params) and dates_mode(dataset_obj) == "none":
        raise HTTPException(
            status_code=400,
            detail=f"'{label}' has no time dimension — omit dates to load "
                   "the full dataset.",
        )


def require_types_counts(dataset_obj) -> None:
    """400 unless the dataset serves the types-counts endpoint family.

    The generic endpoints and instruments load {types, counts} systems, so
    they only work for datasets registered with
    endpoint_schema.type='types-counts'.
    """
    ep = dataset_obj.endpoint_schema
    if not ep or ep.get("type") != "types-counts":
        raise HTTPException(
            status_code=400,
            detail="Dataset does not support the types-counts endpoint. "
                   "Register with endpoint_schema.type='types-counts'.",
        )


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


def _pick_companion(companion, index: int) -> Optional[str]:
    """Resolve a scalar-or-parallel-list companion column for one weight.

    Scalar → the same column for every weight (a canonical rank/freq).
    List → the entry parallel to the chosen count column (per-measure).
    None → no companion declared.
    """
    if companion is None:
        return None
    if isinstance(companion, list):
        return companion[index] if index < len(companion) else None
    return companion


def resolve_series_columns(dataset_obj, weight: Optional[str] = None) -> Optional[dict]:
    """Resolve the per-type time-series measure columns for a request.

    Returns ``{"count": ..., "rank": ... | None, "freq": ... | None}`` from the
    registered ``endpoint_schema`` — the count via ``resolve_count_column`` (so
    the ``weight`` allowlist still applies), and the rank/freq companions via
    the declared ``rank_column`` / ``freq_column`` (scalar = canonical, list =
    parallel to ``count_column``; see EndpointSchemaConfig).

    Returns ``None`` when neither companion is declared — the signal that this
    dataset predates the contract, so the caller should fall back to its legacy
    per-router derivation. Once a dataset is (re-)registered with the columns,
    the declared path takes over with no behaviour change.
    """
    ep = dataset_obj.endpoint_schema or {}
    rank_decl = ep.get("rank_column")
    freq_decl = ep.get("freq_column")
    if rank_decl is None and freq_decl is None:
        return None

    count_col = resolve_count_column(dataset_obj, weight)
    menu = get_count_columns(dataset_obj)
    index = menu.index(count_col) if count_col in menu else 0
    return {
        "count": count_col,
        "rank": _pick_companion(rank_decl, index),
        "freq": _pick_companion(freq_decl, index),
    }


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


async def _domain_latest_entries(db: AsyncSession, domain: str) -> List[RegistryEntry]:
    """All datasets in a domain, each resolved to its latest entry.

    One row per dataset_id, using the same precedence as get_latest_entry
    (the mutable 'latest' slot wins, else the newest snapshot). A domain holds
    a handful of datasets, so this is a cheap scan.
    """
    result = await db.execute(
        select(RegistryEntry)
        # The returned entries are reused downstream (sparkline routing, the
        # availability probe, provenance reads), so we can only defer the one
        # deliberately-large column that is never read here or downstream —
        # partition_index (registry.py excludes it from responses for the same
        # reason). Deferring anything else triggers an async lazy-load.
        .options(defer(RegistryEntry.partition_index))
        .where(RegistryEntry.domain == domain)
        .order_by(
            RegistryEntry.dataset_id,
            (RegistryEntry.version != "latest"),
            RegistryEntry.created_at.desc(),
        )
    )
    latest: dict = {}
    for entry in result.scalars().all():
        latest.setdefault(entry.dataset_id, entry)  # first per id wins (ordered)
    return list(latest.values())


async def resolve_companions(db: AsyncSession, domain: str, dataset: str) -> dict:
    """Resolve a primary dataset's declared companions via lineage + orientation.

    Returns ``{"type_first": entry | None, "documents": {role: entry, ...}}``.
    A companion is any latest dataset in the domain whose
    ``lineage.derived_from`` includes ``"<domain>/<dataset>"`` — so the pairing
    is deduced from *declared provenance*, never sniffed from structure. Among
    those companions:

      - the ``types-counts`` dataset with ``orientation: type-first`` is the
        term-series fast-path (sparkline);
      - each ``type-documents`` dataset is an ``?include=`` source, keyed by its
        declared ``role`` (or its dataset_id when no role is declared).

    Decoupled: a sparkline or provenance set is added later by registering it
    with ``derived_from``, with no change to the primary.
    """
    ref = f"{domain}/{dataset}"
    type_first = None
    documents: dict = {}
    for entry in await _domain_latest_entries(db, domain):
        derived = (entry.lineage or {}).get("derived_from") or []
        if ref not in derived:
            continue
        ep = entry.endpoint_schema or {}
        etype = ep.get("type")
        if etype == "types-counts" and ep.get("orientation") == "type-first":
            type_first = type_first or entry
        elif etype == "type-documents":
            documents[ep.get("role") or entry.dataset_id] = entry
    return {"type_first": type_first, "documents": documents}


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


def _availability_leaf_for(dataset_obj, local_id, filter_vals: Optional[dict] = None):
    """The availability leaf (``{"min", "max", ...}``) for a request's slice.

    The availability tree nests differently per dataset (reddit `{n: {lang:
    ...}}`, wikimedia `{country: {ngram_size: {granularity: ...}}}`), so rather
    than matching a single key, descend preferring any level key that equals the
    entity local_id or one of the request's filter values, falling back to the
    first branch when nothing matches. Returns the leaf dict, or None.
    """
    node = (dataset_obj.manifest or {}).get("availability", {})
    targets = {str(local_id)} if local_id is not None else set()
    targets.update(str(v) for v in (filter_vals or {}).values())
    while isinstance(node, dict):
        if "max" in node:
            return node
        match = next((node[k] for k in node if str(k) in targets), None)
        node = match if match is not None else (next(iter(node.values()), None) if node else None)
    return None


def latest_available_for(dataset_obj, local_id, filter_vals: Optional[dict] = None):
    """Latest available date for a request's slice (the leaf `max`), or None."""
    leaf = _availability_leaf_for(dataset_obj, local_id, filter_vals)
    return leaf.get("max") if leaf else None


def availability_range_for(dataset_obj, local_id, filter_vals: Optional[dict] = None):
    """(min, max) available dates for a request's slice — (None, None) if absent.

    The generic term-series endpoint clamps an undated request to this range so
    the fallback scan is always bounded (and directory-pruned) instead of
    walking the whole date-first tree.
    """
    leaf = _availability_leaf_for(dataset_obj, local_id, filter_vals)
    return (leaf.get("min"), leaf.get("max")) if leaf else (None, None)
