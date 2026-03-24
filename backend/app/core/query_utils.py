"""Shared DuckDB query utilities for registry-driven types-counts datasets.

Used by any router that loads data from a registered dataset with
endpoint_schema.type == 'types-counts'. Currently consumed by:
  - routers/wikimedia.py  (allotax2, top-ngrams3)

Three time cases handled by load_system:
  1. No time axis   (parquet, no time_dimension)         — compare entities directly
  2. Time column    (parquet/ducklake, time_dimension)   — WHERE year BETWEEN ...
  3. Hive-partitioned time (parquet_hive, granularities) — path-level entity+time
"""

from types import SimpleNamespace
from typing import List, Optional
from urllib.parse import quote

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


def resolve_flat_path(dataset_obj) -> str:
    """Return a DuckDB read_parquet() expression for non-hive datasets.

    - parquet:   reads data_location directly (single flat file or glob)
    - ducklake:  reads parquet files via convention:
                 {data_location}/data/main/{domain}/*.parquet
                 Override the base path with format_config.ducklake_data_path.
    - duckdb:    reads files listed in format_config.tables_metadata

    Raises 400 for parquet_hive — those use path-based loading in load_system.
    """
    fmt = dataset_obj.data_format
    if fmt == "parquet":
        return f"'{dataset_obj.data_location}'"
    if fmt == "ducklake":
        fc = dataset_obj.format_config or {}
        data_path = fc.get("ducklake_data_path") or f"{dataset_obj.data_location}/data"
        glob = f"{data_path}/main/{dataset_obj.domain}/*.parquet"
        return f"'{glob}'"
    if fmt == "duckdb":
        fc = dataset_obj.format_config or {}
        tm = fc.get("tables_metadata", {})
        for key, files in tm.items():
            if key != "adapter" and files:
                if len(files) == 1:
                    return f"'{files[0]}'"
                files_expr = ", ".join(f"'{f}'" for f in files)
                return f"[{files_expr}]"
    raise HTTPException(
        status_code=400,
        detail=f"Cannot resolve path for data_format '{fmt}'.",
    )


def load_system(
    conn,
    dataset_obj,
    local_id: Optional[str],
    dates: Optional[List[str]],
    filter_vals: dict,
    granularity: Optional[str],
    limit: int,
    n: Optional[int] = None,
) -> dict:
    """Load types-counts for one system, handling all three time cases.

    Branches on data_format:
    - parquet_hive: path-based — entity and time are hive partition keys.
                    Reads only the relevant partition directories.
    - parquet / ducklake / duckdb: WHERE-based — entity and time are column values.

    Column names come from endpoint_schema (type_column / count_column),
    defaulting to 'types' / 'counts' for datasets that follow the convention.

    When endpoint_schema.ngram_sizes is set, the data lives under {n}grams/
    subdirectories. Pass n= to select the desired size (e.g. n=1 → 1grams/).

    Returns {"types": [...], "counts": [...]} ready for allotax or direct serialization.
    """
    ep = dataset_obj.endpoint_schema or {}
    entity_col = (dataset_obj.entity_mapping or {}).get("local_id_column")
    type_col  = ep.get("type_column")  or "types"
    count_col = ep.get("count_column") or "counts"

    if dataset_obj.data_format == "parquet_hive":
        time_col = ep["granularities"][granularity]  # already validated by caller
        encoded = quote(local_id, safe="") if local_id else "*"
        ngram_sizes = ep.get("ngram_sizes")
        if ngram_sizes is not None:
            n_val = n if n is not None else ngram_sizes[0]
            ngram_prefix = f"{n_val}grams/"
        else:
            ngram_prefix = ""
        glob_path = (
            f"{dataset_obj.data_location}/{ngram_prefix}{granularity}"
            f"/{entity_col}={encoded}/{time_col}=*/data_0.parquet"
        )

        conditions, params = [], []
        if dates:
            conditions.append(f"{time_col} BETWEEN ? AND ?")
            params.extend(dates)
        for col, val in filter_vals.items():
            conditions.append(f"{col} = ?")
            params.append(val)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        rows = conn.execute(
            f"""
            SELECT {type_col}, SUM({count_col}) AS counts
            FROM read_parquet('{glob_path}')
            {where}
            GROUP BY {type_col}
            ORDER BY counts DESC
            LIMIT ?
            """,
            [*params, limit],
        ).fetchall()

    else:
        time_col = ep.get("time_dimension")
        path_expr = resolve_flat_path(dataset_obj)
        from_clause = f"read_parquet({path_expr})"

        conditions, params = [], []
        if entity_col and local_id is not None:
            conditions.append(f"{entity_col} = ?")
            params.append(local_id)
        if time_col and dates:
            conditions.append(f"{time_col} BETWEEN ? AND ?")
            params.extend(dates)
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

    if not rows and entity_col and local_id is not None and dataset_obj.data_format != "parquet_hive":
        # Distinguish "entity not found" from "entity exists but no data in range".
        # Only needed for flat formats (parquet, ducklake, duckdb) — for parquet_hive
        # a missing partition directory already results in an empty/error response.
        # Catches Pattern 2 misconfiguration: column stores short IDs like "A5002034958"
        # but derived local_id is "https://openalex.org/A5002034958".
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
