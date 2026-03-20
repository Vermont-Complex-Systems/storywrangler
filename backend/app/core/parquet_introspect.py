"""Best-effort parquet introspection for registry enrichment.

Derives two things at registration time:
  - data_schema    : column names + types (cheap — reads parquet footer only)
  - filter_values  : distinct values per filter_dimension (scan — skipped for parquet_hive)

Uses DuckDB (already available) so no extra dependencies.
Failures are silently logged and never block registration.
"""

import logging
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)


def _sample_path_expr(dataset) -> Optional[str]:
    """Return a DuckDB read_parquet() path expression sampling one file.

    Used for schema introspection only (reads parquet footer — cheap).
    Accepts a DatasetCreate Pydantic object (at registration time).
    Returns None if no path can be determined.
    """
    fmt = dataset.data_format

    if fmt == "parquet":
        loc = dataset.data_location
        return f"'{loc}'" if loc else None

    if fmt in ("ducklake", "duckdb"):
        fc = dataset.format_config
        tm = (fc.tables_metadata or {}) if fc else {}
        for key, files in tm.items():
            if key != "adapter" and files:
                return f"'{files[0]}'"  # sample first file only — schema is uniform

    if fmt == "parquet_hive":
        loc = dataset.data_location
        return f"'{loc}/**/*.parquet'" if loc else None

    return None


def _full_path_expr(dataset) -> Optional[str]:
    """Return a DuckDB read_parquet() path expression covering all files.

    Used for filter_values scans where distinct values must span the whole dataset.
    Falls back to _sample_path_expr for formats that already glob everything.
    """
    fmt = dataset.data_format

    if fmt in ("ducklake", "duckdb"):
        fc = dataset.format_config
        tm = (fc.tables_metadata or {}) if fc else {}
        for key, files in tm.items():
            if key != "adapter" and files:
                if len(files) == 1:
                    return f"'{files[0]}'"
                files_expr = ", ".join(f"'{f}'" for f in files)
                return f"[{files_expr}]"

    return _sample_path_expr(dataset)


def introspect(conn, dataset) -> Dict[str, Any]:
    """Derive schema and filter_values from parquet files.

    Returns a dict with any subset of:
      {
        "data_schema": {"col": "TYPE", ...},        # → stored in format_config
        "filter_values": {"dim": ["val1", ...], ...} # → stored in endpoint_schema
      }

    Never raises — returns {} on any error.
    """
    result: Dict[str, Any] = {}

    sample_expr = _sample_path_expr(dataset)
    if not sample_expr:
        return result

    # ── schema (cheap: reads parquet footer metadata only) ─────────────────────
    try:
        rows = conn.execute(
            f"DESCRIBE SELECT * FROM read_parquet({sample_expr})"
        ).fetchall()
        result["data_schema"] = {r[0]: r[1] for r in rows}
    except Exception as e:
        log.debug("Schema introspection failed for %s: %s", sample_expr, e)

    # ── filter values (requires a scan — skip for parquet_hive) ────────────────
    ep = dataset.endpoint_schema
    filter_dims: List[str] = (ep.filter_dimensions or []) if ep else []

    if not filter_dims or dataset.data_format == "parquet_hive":
        return result  # hive datasets could be huge — skip

    full_expr = _full_path_expr(dataset)
    filter_values: Dict[str, List[Any]] = {}
    for dim in filter_dims:
        try:
            rows = conn.execute(
                f"SELECT DISTINCT {dim} FROM read_parquet({full_expr}) "
                f"WHERE {dim} IS NOT NULL ORDER BY {dim}"
            ).fetchall()
            filter_values[dim] = [r[0] for r in rows]
        except Exception as e:
            log.debug("Filter introspection failed for dim '%s': %s", dim, e)

    if filter_values:
        result["filter_values"] = filter_values

    return result
