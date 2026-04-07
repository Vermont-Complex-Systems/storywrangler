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

from types import SimpleNamespace
from typing import Any, List, Optional

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from storywrangler_schemas.standards import Standards
from ..models.registry import EntityMapping, RegistryEntry


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
    - parquet_hive:           read_parquet('{path}/**/*.parquet', hive_partitioning=true)
    """
    loc = dataset_obj.data_location
    if dataset_obj.data_format == "parquet_hive":
        return f"read_parquet('{loc}/**/*.parquet', hive_partitioning=true)"
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
) -> List[dict]:
    """Execute a flexible GROUP BY query for a time-series dataset.

    group_cols defines both the SELECT and GROUP BY. Any extra dimensions declared in
    transform.filter_dimensions that are not in group_cols and not in filter_vals are
    aggregated over (SUM). The time column comes from transform.time_dimension.
    The measure column comes from endpoint_schema.count_column (defaults to 'count').

    start / end are optional bounds on the time dimension; their type is derived from
    data_schema so integer years and date strings both work correctly.

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

    if start is not None:
        col_type = schema.get(time_col, "")
        conditions.append(f"{time_col} >= ?")
        params.append(_cast_dates([str(start)], col_type)[0])
    if end is not None:
        col_type = schema.get(time_col, "")
        conditions.append(f"{time_col} <= ?")
        params.append(_cast_dates([str(end)], col_type)[0])
    for col, val in filter_vals.items():
        conditions.append(f"{col} = ?")
        params.append(val)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    group_clause = ", ".join(group_cols)

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
