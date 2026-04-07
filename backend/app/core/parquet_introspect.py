"""Best-effort parquet introspection for registry enrichment.

Derives two things at registration time:
  - data_schema    : column names + types (cheap — reads parquet footer only)
  - filter_values  : distinct values per filter_dimension

Uses DuckDB (already available) so no extra dependencies.
For parquet_hive, hive_partitioning=true is used throughout:
  - DESCRIBE reads partition columns alongside data columns
  - DISTINCT queries read directory names (not file contents) — cheap even for
    large datasets since DuckDB resolves partition values from the file tree.

Schema introspection failure (empty data_schema) causes the registration endpoint to reject with 422.
"""

import logging
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)


def _path_expr(dataset) -> Optional[str]:
    """Return a DuckDB read_parquet() expression for this dataset.

    Includes hive_partitioning=true for parquet_hive so that partition columns
    (entity, time, granularity, ngram_size, etc.) appear in DESCRIBE output
    and are efficiently scannable via metadata rather than file contents.
    """
    fmt = dataset.data_format
    loc = dataset.data_location

    if not loc:
        return None

    if fmt == "parquet_hive":
        return f"read_parquet('{loc}/**/*.parquet', hive_partitioning=true)"

    if fmt == "parquet":
        if isinstance(loc, list):
            quoted = ", ".join(f"'{p}'" for p in loc)
            return f"read_parquet([{quoted}])"
        return f"read_parquet('{loc}')"

    return None


def introspect(conn, dataset) -> Dict[str, Any]:
    """Derive schema and filter_values from parquet files.

    Returns a dict with any subset of:
      {
        "data_schema": {"col": "TYPE", ...},        # → stored in data_schema column
        "filter_values": {"dim": ["val1", ...], ...} # → stored in filter_values column
      }

    Never raises — returns {} on any error.
    """
    result: Dict[str, Any] = {}

    path_expr = _path_expr(dataset)
    if not path_expr:
        return result

    # ── schema (cheap: reads parquet footer + hive directory metadata) ──────────
    try:
        rows = conn.execute(
            f"DESCRIBE SELECT * FROM {path_expr}"
        ).fetchall()
        result["data_schema"] = {r[0]: r[1] for r in rows}
    except Exception as e:
        log.debug("Schema introspection failed for %s: %s", path_expr, e)

    # ── filter values ────────────────────────────────────────────────────────────
    # Source: transform.filter_dimensions + transform.partition_dimensions.
    # For parquet_hive, partition columns are resolved from directory names —
    # no file contents are read, making this efficient even for large datasets.
    tr = dataset.transform
    filter_dims: List[str] = list((tr.filter_dimensions or []) if tr else [])
    partition_dims: List[str] = list((tr.partition_dimensions or []) if tr else [])
    all_dims = filter_dims + partition_dims

    if not all_dims:
        return result

    filter_values: Dict[str, List[Any]] = {}
    for dim in all_dims:
        try:
            rows = conn.execute(
                f"SELECT DISTINCT {dim} FROM {path_expr} "
                f"WHERE {dim} IS NOT NULL ORDER BY {dim}"
            ).fetchall()
            filter_values[dim] = [r[0] for r in rows]
        except Exception as e:
            log.debug("Filter introspection failed for dim '%s': %s", dim, e)

    if filter_values:
        result["filter_values"] = filter_values

    return result
