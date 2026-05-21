"""Shared DuckDB query utilities for registry-driven datasets.

Two query patterns, one for each endpoint schema type:

  load_system()       — endpoint_schema.type == 'types-counts'
                        Returns {types: [...], counts: [...]} for allotax / rank distributions.
                        Consumed by: routers/wikimedia.py, routers/storywrangler.py

  load_time_series()  — endpoint_schema.type == 'time-series'
                        Returns [{col1: v, ..., "count": n}, ...] for flexible GROUP BY queries.
                        Consumed by: routers/scisciDB.py (and any future time-series router)

Both support parquet and parquet_hive; all filtering is done via WHERE clauses.
For parquet_hive, hive_partitioning=true handles partition pruning automatically.
"""

import re
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any, List, Optional
from urllib.parse import quote

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from storywrangler_schemas.hashing import assign_bucket
from storywrangler_schemas.standards import Standards
from ..core.exceptions import DataNotAvailableError, QueryError
from ..models.registry import EntityMapping, RegistryEntry


# ── Hash-bucket routing ─────────────────────────────────────────────────────────
# Generic helpers for content-sharded hive datasets (transform.hash_bucket).
# Resolution: overrides[entity][str(dim_value)] → default_count.
#
# assign_bucket() is imported from storywrangler_schemas.hashing — the single
# source of truth shared by backend, SDK, and pipeline code.


def get_bucket_config(dataset_obj) -> dict:
    """Read hash_bucket config from a dataset's transform metadata.

    Returns the hash_bucket dict (with ``column``, ``default_count``,
    and optionally ``overrides``), or an empty dict if not configured.
    """
    if not dataset_obj:
        return {}
    return (dataset_obj.transform or {}).get("hash_bucket") or {}


def resolve_bucket_count(hb: dict, entity: Optional[str] = None, dim_value: Any = None) -> int:
    """Look up bucket count for a specific entity + partition dimension value.

    Resolution order: ``overrides[entity][str(dim_value)]`` → ``default_count``.
    Returns 1 (no sharding) if hash_bucket is not configured.
    """
    default = hb.get("default_count", 1)
    overrides = hb.get("overrides")
    if not overrides or entity is None:
        return default
    entity_overrides = overrides.get(str(entity))
    if not entity_overrides or dim_value is None:
        return default
    return entity_overrides.get(str(dim_value), default)


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

    Reads from the stored level_order computed at registration time.
    """
    level_order = getattr(dataset_obj, "level_order", None)
    if not level_order:
        return []
    return [
        lv["column"] for lv in level_order
        if lv["type"] in ("partition", "filter")
    ]


# ── Hive path construction ───────────────────────────────────────────────────
# Generic path builder using the stored level_order from registration.

def build_hive_path(
    dataset_obj,
    *,
    entity_value: Optional[str] = None,
    filter_vals: Optional[dict] = None,
    time_value: Optional[str] = None,
    bucket_value: Optional[int] = None,
    glob_suffix: str = "/*.parquet",
) -> Optional[str]:
    """Build an exact hive partition path from the stored level_order.

    Walks the level_order list in sequence. For each level:
      - "partition" / "filter" → look up value in filter_vals[column]
      - "entity"               → use entity_value
      - "hash_bucket"          → use bucket_value
      - "time"                 → use time_value

    If a level's value is None (not provided), appends ``/*`` (glob wildcard).
    This allows partial path construction — e.g. omitting time to get
    an entity-level path for slow-path fallback.

    Returns None when level_order is absent (pre-migration datasets or
    parquet format), signalling the caller to use the existing glob fallback.

    All values are URL-encoded for safe hive directory names.
    """
    level_order = getattr(dataset_obj, "level_order", None)
    if not level_order:
        return None

    filter_vals = filter_vals or {}
    path = dataset_obj.data_location

    for level in level_order:
        col = level["column"]
        ltype = level["type"]

        if ltype == "entity":
            val = entity_value
        elif ltype == "hash_bucket":
            val = bucket_value
        elif ltype == "time":
            val = time_value
        elif ltype in ("partition", "filter"):
            val = filter_vals.get(col)
        else:
            val = None

        if val is not None:
            path += f"/{col}={quote(str(val), safe='')}"
        else:
            path += "/*"

    return path + glob_suffix


# ── DuckDB error classification ──────────────────────────────────────────────

_DATA_MISSING_PATTERNS = [
    re.compile(r"No files found that match the pattern", re.IGNORECASE),
    re.compile(r"Cannot open file", re.IGNORECASE),
    re.compile(r"File .+ does not exist", re.IGNORECASE),
]


def _is_data_missing(exc: Exception) -> bool:
    msg = str(exc)
    return any(p.search(msg) for p in _DATA_MISSING_PATTERNS)


@contextmanager
def handle_query_error(dataset_label: str):
    """Wrap DuckDB queries with user-friendly error translation.

    Usage::

        with handle_query_error("wikimedia/ngrams"):
            rows = conn.execute(...).fetchall()

    Catches raw DuckDB exceptions and raises custom exceptions that are
    converted to JSON responses by the global handlers in main.py.

    - File-not-found → DataNotAvailableError (→ 404)
    - Other errors   → QueryError (→ 500, no internal paths leaked)
    - HTTPExceptions pass through unchanged
    """
    try:
        yield
    except (HTTPException, DataNotAvailableError, QueryError):
        raise
    except Exception as exc:
        if _is_data_missing(exc):
            raise DataNotAvailableError(dataset_label)
        raise QueryError(dataset_label)


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


def _cast_dates(dates: List[str], col_type: str) -> List[Any]:
    """Cast date strings to the correct Python type for DuckDB BETWEEN.

    Reads the DuckDB column type from data_schema (introspected at registration)
    so the router never needs to know whether the time column is an integer year,
    a DATE, a TIMESTAMP, or a VARCHAR.

      INTEGER / BIGINT / …  →  int("1980")  →  1980
      FLOAT / DOUBLE / …    →  float("1980.0")
      DATE / TIMESTAMP / VARCHAR / …  →  "2024-01-01"  (DuckDB casts natively)
    """
    t = (col_type or "").upper()
    int_types = ("INT", "BIGINT", "SMALLINT", "HUGEINT", "TINYINT",
                 "UBIGINT", "UINTEGER", "USMALLINT", "UTINYINT")
    float_types = ("FLOAT", "DOUBLE", "DECIMAL", "NUMERIC", "REAL")
    if any(t.startswith(k) for k in int_types):
        return [int(d) for d in dates]
    if any(k in t for k in float_types):
        return [float(d) for d in dates]
    return list(dates)


def _path_expr(dataset_obj) -> str:
    """Return a DuckDB FROM expression for the dataset.

    - parquet (single path):  read_parquet('{path}')
    - parquet (file list):    read_parquet([file1, file2, ...])
    - parquet_hive:           read_parquet('{path}/*/*/.../*.parquet', hive_partitioning=true)

    For parquet_hive, builds a wildcard path from the stored level_order
    (all levels become ``/*``), avoiding recursive NFS directory walking.
    Requires level_order — all datasets must be registered with it.
    """
    loc = dataset_obj.data_location
    if dataset_obj.data_format == "parquet_hive":
        hive_path = build_hive_path(dataset_obj)
        if hive_path is None:
            raise ValueError(
                f"parquet_hive dataset at '{loc}' has no level_order. "
                "Re-register the dataset to populate level_order."
            )
        return f"read_parquet('{hive_path}', hive_partitioning=true)"
    if isinstance(loc, list):
        quoted = ", ".join(f"'{p}'" for p in loc)
        return f"read_parquet([{quoted}])"
    return f"read_parquet('{loc}')"


def load_system(
    conn,
    dataset_obj,
    local_id: Optional[str],
    dates: Optional[List[str]],
    filter_vals: dict,
    limit: int,
) -> dict:
    """Load types-counts for one system.

    Identical query logic for both parquet and parquet_hive: all filtering
    is done via WHERE clauses. For parquet_hive, hive_partitioning=true means
    DuckDB prunes partition directories automatically.

    Column names come from endpoint_schema (type_column / count_column),
    defaulting to 'types' / 'counts'. The time column comes from
    transform.time_dimension.

    Extra filter dimensions (e.g. granularity='daily', ngram_size=1) are
    passed directly in filter_vals by the caller.

    Returns {"types": [...], "counts": [...]} ready for allotax or serialization.
    """
    ep = dataset_obj.endpoint_schema or {}
    tr = dataset_obj.transform or {}
    entity_col = (dataset_obj.entity_mapping or {}).get("local_id_column")
    type_col  = ep.get("type_column")  or "types"
    count_col = ep.get("count_column") or "counts"
    time_col  = tr.get("time_dimension")

    from_clause = _path_expr(dataset_obj)

    schema = dataset_obj.data_schema or {}
    conditions, params = [], []
    if entity_col and local_id is not None:
        conditions.append(f"{entity_col} = ?")
        params.append(local_id)
    if time_col and dates:
        col_type = schema.get(time_col, "")
        cast = _cast_dates([str(d) for d in dates], col_type)
        conditions.append(f"{time_col} BETWEEN ? AND ?")
        params.extend(cast)
    for col, val in filter_vals.items():
        conditions.append(f"{col} = ?")
        params.append(val)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    rows = conn.execute(
        f"""
        SELECT {type_col}, SUM({count_col}) AS counts
        FROM {from_clause}
        {where}
        GROUP BY {type_col}
        ORDER BY counts DESC
        LIMIT ?
        """,
        [*params, limit],
    ).fetchall()

    if not rows and entity_col and local_id is not None:
        # Distinguish "entity not found" from "entity exists but no data in range".
        # For parquet_hive, hive partition pruning makes this cheap: DuckDB only
        # opens files in the matching entity= directory (or returns 0 if absent).
        exists = conn.execute(
            f"SELECT COUNT(*) FROM {from_clause} WHERE {entity_col} = ? LIMIT 1",
            [local_id],
        ).fetchone()[0]
        if not exists:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"Entity '{local_id}' not found in column '{entity_col}'. "
                    "If this dataset uses entity_namespace (Pattern 2), verify the column "
                    "stores full URL values (e.g. https://openalex.org/ID, not just A...)."
                ),
            )

    return {"types": [r[0] for r in rows], "counts": [float(r[1]) for r in rows]}


def load_time_series(
    conn,
    dataset_obj,
    group_cols: List[str],
    filter_vals: dict,
    start: Any = None,
    end: Any = None,
    limit: int = 1000,
    exclude_nulls: bool = True,
    top_n: Optional[int] = None,
) -> List[dict]:
    """Execute a flexible GROUP BY query for a time-series dataset.

    group_cols defines both the SELECT and GROUP BY. Any extra dimensions declared in
    transform.filter_dimensions that are not in group_cols and not in filter_vals are
    aggregated over (SUM). The time column comes from transform.time_dimension.
    The measure column comes from endpoint_schema.count_column (defaults to 'count').

    start / end are optional bounds on the time dimension; their type is derived from
    data_schema so integer years and date strings both work correctly.

    exclude_nulls: when True (default), adds IS NOT NULL for each group_by column.
    top_n: when set, restricts results to only the top N non-time groups ranked by
    total count. E.g. group_by=primary_subfield,year&top_n=10 returns the full
    time-series for only the 10 largest primary_subfields.

    Returns [{col1: v1, ..., "count": n}, ...] ordered by group_cols ASC.
    """
    ep = dataset_obj.endpoint_schema or {}
    tr = dataset_obj.transform or {}
    time_col = tr.get("time_dimension") or "year"
    count_col = ep.get("count_column") or "count"

    schema = dataset_obj.data_schema or {}
    from_clause = _path_expr(dataset_obj)

    conditions: List[str] = []
    params: List[Any] = []

    if exclude_nulls:
        for col in group_cols:
            conditions.append(f"{col} IS NOT NULL")

    if start is not None:
        col_type = schema.get(time_col, "")
        conditions.append(f"{time_col} >= ?")
        params.append(_cast_dates([str(start)], col_type)[0])
    if end is not None:
        col_type = schema.get(time_col, "")
        conditions.append(f"{time_col} <= ?")
        params.append(_cast_dates([str(end)], col_type)[0])
    for col, val in filter_vals.items():
        if isinstance(val, list):
            placeholders = ",".join(["?"] * len(val))
            conditions.append(f"{col} IN ({placeholders})")
            params.extend(val)
        else:
            conditions.append(f"{col} = ?")
            params.append(val)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    group_clause = ", ".join(group_cols)

    # When top_n is set, identify the top N non-time groups by total count,
    # then restrict the main query to only those groups.
    if top_n is not None:
        non_time_cols = [c for c in group_cols if c != time_col]
        if non_time_cols:
            non_time_clause = ", ".join(non_time_cols)
            rows = conn.execute(
                f"""
                WITH top_groups AS (
                    SELECT {non_time_clause}
                    FROM {from_clause}
                    {where}
                    GROUP BY {non_time_clause}
                    ORDER BY SUM({count_col}) DESC
                    LIMIT ?
                )
                SELECT {group_clause}, SUM({count_col}) AS count
                FROM {from_clause}
                {where}
                  AND ({non_time_clause}) IN (SELECT {non_time_clause} FROM top_groups)
                GROUP BY {group_clause}
                ORDER BY {group_clause}
                """,
                [*params, top_n, *params],
            ).fetchall()

            col_names = group_cols + ["count"]
            return [dict(zip(col_names, row)) for row in rows]

    rows = conn.execute(
        f"""
        SELECT {group_clause}, SUM({count_col}) AS count
        FROM {from_clause}
        {where}
        GROUP BY {group_clause}
        ORDER BY {group_clause}
        LIMIT ?
        """,
        [*params, limit],
    ).fetchall()

    col_names = group_cols + ["count"]
    return [dict(zip(col_names, row)) for row in rows]


# ── Term-series helpers ──────────────────────────────────────────────────────
# Shared between wikimedia.py, reddit.py, and any future domain router that
# provides sparkline / partition-scan term lookups.


def entity_base_path(dataset_obj, local_id, filter_vals):
    """Build the Hive path up to the entity level (no date).

    Used for DuckDB glob patterns in the slow-path daily partition fallback.
    Uses build_hive_path with no time_value, so the time level becomes a
    wildcard.
    """
    path = build_hive_path(
        dataset_obj,
        entity_value=local_id,
        filter_vals=filter_vals,
        glob_suffix="",
    )
    if path is None:
        raise ValueError(
            f"parquet_hive dataset '{dataset_obj.dataset_id}' has no level_order. "
            "Re-register the dataset to populate level_order."
        )
    return path


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
