"""Best-effort parquet introspection for registry enrichment.

Derives three things at registration time:
  - data_schema    : column names + types (cheap — reads parquet footer only)
  - filter_values  : distinct values per filter_dimension
  - availability   : min/max of time_dimension per entity and partition_dimension

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


def introspect(conn, dataset, provided_schema: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Derive schema, filter_values, and availability from parquet files.

    When *provided_schema* is given, it is used as the authoritative data_schema
    and glob-based schema introspection is skipped.  This allows registration to
    succeed even when older partition files have a different schema (submitter
    takes responsibility for consistency).

    Returns a dict with any subset of:
      {
        "data_schema": {"col": "TYPE", ...},                       # → data_schema column
        "filter_values": {"dim": ["val1", ...], ...},              # → filter_values column
        "availability": {"entity": {"gran": {"min":..,"max":..}}}  # → merged into manifest
      }

    Never raises — returns {} on any error.
    """
    result: Dict[str, Any] = {}

    path_expr = _path_expr(dataset)
    if not path_expr:
        return result

    # ── schema ─────────────────────────────────────────────────────────────────
    if provided_schema is not None:
        result["data_schema"] = provided_schema
    else:
        # Cheap: reads parquet footer + hive directory metadata.
        # Fails when files in the glob have inconsistent schemas.
        try:
            rows = conn.execute(
                f"DESCRIBE SELECT * FROM {path_expr}"
            ).fetchall()
            result["data_schema"] = {r[0]: r[1] for r in rows}
        except Exception as e:
            log.warning("Schema introspection failed for %s: %s", path_expr, e)
            result["introspect_error"] = str(e)

    # ── filter values ────────────────────────────────────────────────────────────
    # Source: transform.filter_dimensions + transform.partition_dimensions.
    # For parquet_hive, partition columns are resolved from directory names —
    # no file contents are read, making this efficient even for large datasets.
    tr = dataset.transform
    filter_dims: List[str] = list((tr.filter_dimensions or []) if tr else [])
    partition_dims: List[str] = list((tr.partition_dimensions or []) if tr else [])
    all_dims = filter_dims + partition_dims

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

    # ── availability (min/max of time_dimension per entity × partition_dimension) ─
    # Produces entity-first format:
    #   {"United States": {"daily": {"min": "2024-01-01", "max": "2026-04-20"}, ...}}
    # For datasets without entity_mapping: {"daily": {"min": ..., "max": ...}}
    time_col = tr.time_dimension if tr else None
    if time_col:
        entity_col = (
            dataset.entity_mapping.local_id_column
            if dataset.entity_mapping else None
        )
        # partition_dimensions whose distinct values define separate availability
        # ranges (e.g. granularity: daily vs weekly have different date bounds)
        group_dims = list(partition_dims)

        select_cols = []
        group_by = []
        if entity_col:
            select_cols.append(entity_col)
            group_by.append(entity_col)
        for dim in group_dims:
            select_cols.append(dim)
            group_by.append(dim)

        select_str = ", ".join(select_cols)
        if select_str:
            select_str += ", "
        group_str = ", ".join(group_by)

        try:
            if group_str:
                sql = (
                    f"SELECT {select_str}MIN({time_col})::TEXT, MAX({time_col})::TEXT "
                    f"FROM {path_expr} GROUP BY {group_str}"
                )
            else:
                sql = (
                    f"SELECT MIN({time_col})::TEXT, MAX({time_col})::TEXT "
                    f"FROM {path_expr}"
                )
            rows = conn.execute(sql).fetchall()

            availability: Dict[str, Any] = {}
            for row in rows:
                idx = 0
                ent = row[idx] if entity_col else None
                if entity_col:
                    idx += 1
                dim_vals = {}
                for dim in group_dims:
                    dim_vals[dim] = row[idx]
                    idx += 1
                min_val, max_val = row[idx], row[idx + 1]
                bounds = {"min": min_val, "max": max_val}

                if entity_col and group_dims:
                    # entity-first, multi-granularity
                    availability.setdefault(ent, {})[dim_vals[group_dims[0]]] = bounds
                elif entity_col:
                    # entity-keyed, single granularity
                    availability[ent] = bounds
                elif group_dims:
                    # global, multi-granularity
                    availability[dim_vals[group_dims[0]]] = bounds
                else:
                    # global, single granularity
                    availability = bounds

            if availability:
                result["availability"] = availability
        except Exception as e:
            log.debug("Availability introspection failed: %s", e)

    return result
