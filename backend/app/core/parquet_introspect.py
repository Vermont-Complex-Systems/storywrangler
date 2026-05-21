"""Best-effort parquet introspection for registry enrichment.

Derives three things at registration time:
  - data_schema    : column names + types (cheap — reads parquet footer only)
  - filter_values  : distinct values per filter_dimension
  - availability   : min/max of time_dimension per entity and partition_dimension

Uses DuckDB (already available) so no extra dependencies.
For parquet_hive with level_order available:
  - Schema DESCRIBE pins ALL levels to their discovered first values so DuckDB
    reads exactly one partition's footer — instant even on NFS.
  - Filter values for hive-level columns use os.listdir() (directory listing)
    instead of DuckDB SELECT DISTINCT — instant regardless of dataset size.
  - DuckDB SELECT DISTINCT is reserved for non-hive filter_dimensions only.

Schema introspection failure (empty data_schema) causes the registration endpoint to reject with 422.
"""

import logging
import os
from typing import Any, Dict, List, Optional
from urllib.parse import quote, unquote

log = logging.getLogger(__name__)


def _discover_levels(root: str) -> List[Dict[str, str]]:
    """Walk one path from hive root to leaf, returning partition keys and first values.

    Follows the first hive-named entry (key=value) at each level, sorted so the
    result is deterministic regardless of filesystem ordering.

    Returns e.g. [{"column": "ngram_size", "value": "1"},
                   {"column": "country",    "value": "Afghanistan"},
                   {"column": "alpha",      "value": "0.17"}]
    """
    levels: List[Dict[str, str]] = []
    current = root
    while os.path.isdir(current):
        try:
            entries = sorted(os.listdir(current))
        except OSError:
            break
        hive_entry = next((e for e in entries if "=" in e), None)
        if hive_entry is None:
            break
        dim, val = hive_entry.split("=", 1)
        levels.append({"column": dim, "value": unquote(val)})
        current = os.path.join(current, hive_entry)
    return levels


def _hive_distinct_values(root: str, level_order: List[Dict[str, Any]], column: str) -> List[Any]:
    """Read distinct values for a hive partition column using os.listdir().

    Walks the directory tree from *root* through each level in *level_order*
    until reaching the target *column*, then lists all directory entries at
    that level, extracts the values from `col=val` names, and returns them
    sorted.

    For levels above the target, uses the first sorted entry (same as
    _discover_levels) to pick a single deterministic path.

    This is instant on NFS because it only reads directory metadata — no
    parquet files are opened.
    """
    current = root
    for lv in level_order:
        col = lv["column"]
        if col == column:
            # This is the target level — list all entries
            try:
                entries = sorted(os.listdir(current))
            except OSError:
                return []
            values = []
            for e in entries:
                if "=" in e:
                    _, val = e.split("=", 1)
                    values.append(unquote(val))
            return sorted(values)
        else:
            # Intermediate level — follow the first entry to go deeper
            try:
                entries = sorted(os.listdir(current))
            except OSError:
                return []
            hive_entry = next((e for e in entries if "=" in e), None)
            if hive_entry is None:
                return []
            current = os.path.join(current, hive_entry)
    return []


def _hive_availability(
    root: str,
    level_order: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Compute availability (min/max of time dimension) by walking the directory tree.

    Uses os.listdir() at each level — no DuckDB, no parquet files opened.
    Walks all combinations of partition × entity levels, then reads the time
    level directory names to determine min/max.

    Returns availability in entity-first format:
      {"United States": {"daily": {"min": "2024-01-01", "max": "2026-04-20"}, ...}}
    Or without entity: {"daily": {"min": ..., "max": ...}}
    Or flat: {"min": ..., "max": ...}
    """
    # Classify levels
    time_idx = None
    entity_idx = None
    partition_indices = []
    for i, lv in enumerate(level_order):
        if lv["type"] == "time":
            time_idx = i
        elif lv["type"] == "entity":
            entity_idx = i
        elif lv["type"] == "partition":
            partition_indices.append(i)

    if time_idx is None:
        return {}

    # Build paths to all time-level directories by walking the tree.
    # At each level above time, expand the appropriate values:
    #   partition → all values (they become grouping keys)
    #   entity   → all values (they become top-level keys)
    #   other    → skip (hash_bucket, filter — not relevant for availability)
    #
    # Each work item is (current_path, context_dict)
    work = [(root, {})]
    for i, lv in enumerate(level_order):
        if i == time_idx:
            break  # reached the time level — enumerate below
        col = lv["column"]
        next_work = []
        for path, ctx in work:
            try:
                entries = sorted(os.listdir(path))
            except OSError:
                continue
            hive_entries = [e for e in entries if "=" in e]
            if lv["type"] in ("partition", "entity"):
                # Expand: include all values as grouping/entity keys
                for entry in hive_entries:
                    _, val = entry.split("=", 1)
                    new_ctx = dict(ctx)
                    new_ctx[col] = unquote(val)
                    next_work.append((os.path.join(path, entry), new_ctx))
            else:
                # Non-grouping level (hash_bucket, filter) — follow first entry
                if hive_entries:
                    next_work.append((os.path.join(path, hive_entries[0]), ctx))
        work = next_work

    if not work:
        return {}

    # Now enumerate time values at the time level for each path
    time_col = level_order[time_idx]["column"]
    entity_col = level_order[entity_idx]["column"] if entity_idx is not None else None
    group_cols = [level_order[i]["column"] for i in partition_indices]

    availability: Dict[str, Any] = {}
    for path, ctx in work:
        try:
            entries = sorted(os.listdir(path))
        except OSError:
            continue
        time_vals = sorted([unquote(e.split("=", 1)[1]) for e in entries if e.startswith(f"{time_col}=")])
        if not time_vals:
            continue

        bounds = {"min": time_vals[0], "max": time_vals[-1]}
        ent = ctx.get(entity_col) if entity_col else None

        # Build nested dict for partition dims.
        # For [ngram_size, granularity] with values {1, daily}:
        #   entity-first: {"US": {"1": {"daily": {"min":.., "max":..}}}}
        #   no entity:    {"1": {"daily": {"min":.., "max":..}}}
        if group_cols:
            keys = [ctx.get(col, "") for col in group_cols]
            if ent:
                target = availability.setdefault(ent, {})
            else:
                target = availability
            for key in keys[:-1]:
                target = target.setdefault(key, {})
            target[keys[-1]] = bounds
        elif ent:
            availability[ent] = bounds
        else:
            availability = bounds

    return availability


def _derive_bucket_config(
    root: str,
    level_order: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Derive hash_bucket config (counts + overrides) by counting bucket directories.

    Walks the directory tree to the hash_bucket level, counting how many
    bucket directories exist for each entity × partition combination.
    Returns a full config dict ready for query-time use::

        {"column": "ngram_bucket", "default_count": 1,
         "overrides": {"United States": {"1": 16, "2": 32}}}

    Returns None if no hash_bucket level exists in level_order.
    """
    # Find hash_bucket level
    bucket_idx = None
    bucket_col = None
    for i, lv in enumerate(level_order):
        if lv["type"] == "hash_bucket":
            bucket_idx = i
            bucket_col = lv["column"]
            break
    if bucket_idx is None:
        return None

    # Walk tree to the hash_bucket level, expanding entity + partition levels
    entity_col = next(
        (lv["column"] for lv in level_order if lv["type"] == "entity"), None
    )
    partition_cols = [
        lv["column"] for lv in level_order[:bucket_idx]
        if lv["type"] == "partition"
    ]

    work = [(root, {})]
    for i, lv in enumerate(level_order):
        if i == bucket_idx:
            break
        col = lv["column"]
        next_work = []
        for path, ctx in work:
            try:
                entries = sorted(os.listdir(path))
            except OSError:
                continue
            hive_entries = [e for e in entries if "=" in e]
            if lv["type"] in ("partition", "entity"):
                for entry in hive_entries:
                    _, val = entry.split("=", 1)
                    new_ctx = dict(ctx)
                    new_ctx[col] = unquote(val)
                    next_work.append((os.path.join(path, entry), new_ctx))
            else:
                # Non-grouping level — follow first entry
                if hive_entries:
                    next_work.append((os.path.join(path, hive_entries[0]), ctx))
        work = next_work

    # Count bucket directories at each path
    counts: Dict[tuple, int] = {}
    for path, ctx in work:
        try:
            entries = os.listdir(path)
        except OSError:
            continue
        n_buckets = sum(1 for e in entries if e.startswith(f"{bucket_col}="))
        entity = ctx.get(entity_col) if entity_col else None
        # Use first partition dim as the override inner key
        dim_val = str(ctx[partition_cols[0]]) if partition_cols else None
        counts[(entity, dim_val)] = n_buckets

    if not counts:
        return None

    # Determine default_count (most common count)
    from collections import Counter
    count_freq = Counter(counts.values())
    default_count = count_freq.most_common(1)[0][0]
    if default_count < 1:
        default_count = 1

    # Build overrides for entity × dim combinations that differ from default
    overrides: Dict[str, Dict[str, int]] = {}
    for (entity, dim_val), n in counts.items():
        if n != default_count and entity is not None:
            if dim_val is not None:
                overrides.setdefault(entity, {})[dim_val] = n
            else:
                overrides.setdefault(entity, {})["_"] = n

    config: Dict[str, Any] = {"column": bucket_col, "default_count": default_count}
    if overrides:
        config["overrides"] = overrides
    return config


def _targeted_availability(
    conn, root: str, level_order: List[Dict[str, Any]], time_col: str, dataset,
) -> Dict[str, Any]:
    """Compute availability by reading ONE file per entity × partition combo.

    When time is inside the parquet files (not a hive level), we need DuckDB
    to read MIN/MAX.  But we don't need to scan every file — all hash buckets
    within the same entity share the same date range.  This function walks the
    directory tree, pins hash_bucket (and other non-grouping levels) to their
    first value, and queries a single parquet file per entity × partition
    combination.

    For sparklines (2 ngram_sizes × 11 countries × 16 buckets = 352 files),
    this reads 22 files instead of 352 — ~0.5s vs ~90s over NFS.
    """
    entity_col = (
        dataset.entity_mapping.local_id_column
        if dataset.entity_mapping else None
    )

    # Classify levels
    partition_cols = []
    for lv in level_order:
        if lv["type"] == "partition":
            partition_cols.append(lv["column"])

    # Walk the tree, expanding entity + partition levels,
    # pinning hash_bucket/filter/time to their first value.
    work = [(root, {})]
    for lv in level_order:
        col = lv["column"]
        if lv["type"] == "time":
            break  # time is inside files, stop here
        next_work = []
        for path, ctx in work:
            try:
                entries = sorted(os.listdir(path))
            except OSError:
                continue
            hive_entries = [e for e in entries if "=" in e]
            if lv["type"] in ("partition", "entity"):
                # Expand: include all values as grouping/entity keys
                for entry in hive_entries:
                    _, val = entry.split("=", 1)
                    new_ctx = dict(ctx)
                    new_ctx[col] = unquote(val)
                    next_work.append((os.path.join(path, entry), new_ctx))
            else:
                # Non-grouping level (hash_bucket, filter) — follow first entry only
                if hive_entries:
                    next_work.append((os.path.join(path, hive_entries[0]), ctx))
        work = next_work

    if not work:
        return {}

    # Query MIN/MAX from one file per entity × partition combo
    availability: Dict[str, Any] = {}
    for path, ctx in work:
        # Find the first parquet file at this path
        try:
            files = [f for f in os.listdir(path) if f.endswith(".parquet")]
        except OSError:
            continue
        if not files:
            # Try one level deeper (e.g. hash_bucket directories we stopped before)
            try:
                subdirs = sorted(os.listdir(path))
                for sd in subdirs:
                    sd_path = os.path.join(path, sd)
                    if os.path.isdir(sd_path):
                        files = [f for f in os.listdir(sd_path) if f.endswith(".parquet")]
                        if files:
                            path = sd_path
                            break
            except OSError:
                continue
        if not files:
            continue

        pq_file = os.path.join(path, sorted(files)[0])
        try:
            rows = conn.execute(
                f"SELECT MIN({time_col})::TEXT, MAX({time_col})::TEXT "
                f"FROM read_parquet('{pq_file}')"
            ).fetchall()
        except Exception:
            continue
        if not rows or rows[0][0] is None:
            continue

        min_val, max_val = rows[0][0], rows[0][1]
        bounds = {"min": min_val, "max": max_val}
        ent = ctx.get(entity_col) if entity_col else None

        # Build nested dict keyed by entity then partition dims
        part_keys = [ctx.get(col, "") for col in partition_cols]
        if ent and part_keys:
            target = availability.setdefault(ent, {})
            for key in part_keys[:-1]:
                target = target.setdefault(key, {})
            target[part_keys[-1]] = bounds
        elif ent:
            availability[ent] = bounds
        elif part_keys:
            target = availability
            for key in part_keys[:-1]:
                target = target.setdefault(key, {})
            target[part_keys[-1]] = bounds
        else:
            availability = bounds

    return availability


def _pinned_path_expr(loc: str, level_order: List[Dict[str, Any]]) -> str:
    """Build a read_parquet() expression with ALL levels pinned to first values.

    Produces e.g.:
      read_parquet('.../ngram_size=1/granularity=daily/country=Afghanistan/date=2015-07-01/*.parquet',
                   hive_partitioning=true)

    This forces DuckDB to read exactly one partition — instant even on NFS
    with millions of partitions.
    """
    parts = [f"{lv['column']}={quote(str(lv['default_value']), safe='')}" for lv in level_order]
    glob = f"{loc}/{'/'.join(parts)}/*.parquet"
    return f"read_parquet('{glob}', hive_partitioning=true)"


def validate_and_build_level_order(
    discovered_levels: List[Dict[str, str]],
    dataset,
) -> List[Dict[str, Any]]:
    """Match every discovered hive level to a declaration, return annotated order.

    *discovered_levels* comes from ``_discover_levels()`` and is a list of
    ``{"column": name, "value": first_value}`` dicts in on-disk nesting order.

    Each level is classified by matching it against declarations in
    ``transform`` and ``entity_mapping``:

      - entity_mapping.local_id_column      → type "entity"
      - transform.hash_bucket               → type "hash_bucket"
      - transform.time_dimension            → type "time"
      - transform.filter_dimensions item    → type "filter"
      - everything else                     → type "partition"

    The first on-disk value is stored as ``default_value`` for each level.
    At query time, partition/filter levels use this as the injected default
    when the caller omits the parameter.

    hash_bucket MUST appear in the discovered levels when declared.

    Raises ValueError with a descriptive message on any mismatch.
    """
    tr = getattr(dataset, "transform", None)
    em = getattr(dataset, "entity_mapping", None)

    # Build column → type lookup from explicit declarations
    declared: Dict[str, str] = {}

    if em and getattr(em, "local_id_column", None):
        declared[em.local_id_column] = "entity"

    hb = (tr.hash_bucket if tr else None)
    if hb:
        if hb in declared:
            raise ValueError(
                f"hash_bucket '{hb}' conflicts with "
                f"existing declaration '{declared[hb]}' for the same column"
            )
        declared[hb] = "hash_bucket"

    time_col = (tr.time_dimension if tr else None)
    if time_col:
        if time_col in declared:
            raise ValueError(
                f"time_dimension '{time_col}' conflicts with "
                f"existing declaration '{declared[time_col]}' for the same column"
            )
        declared[time_col] = "time"

    filter_dims = (tr.filter_dimensions if tr else None) or []
    for fd in filter_dims:
        if fd not in declared:
            declared[fd] = "filter"

    # Match each discovered level
    discovered_names = [lv["column"] for lv in discovered_levels]
    result: List[Dict[str, Any]] = []
    for lv in discovered_levels:
        col_name = lv["column"]
        col_type = declared.get(col_name, "partition")  # undeclared → partition
        entry: Dict[str, Any] = {
            "column": col_name,
            "type": col_type,
            "default_value": lv["value"],
        }
        result.append(entry)

    # Validate that hash_bucket column appears in discovered levels
    if hb and hb not in set(discovered_names):
        raise ValueError(
            f"hash_bucket '{hb}' not found in on-disk hive "
            f"levels {discovered_names}. The hash bucket column must be "
            f"an actual hive directory level."
        )

    return result


def _path_expr(dataset) -> Optional[str]:
    """Return a DuckDB read_parquet() expression for this dataset.

    Used as a fallback in introspect() when level_order is not yet available
    (i.e. during registration before level_order is computed, or for plain
    parquet datasets).

    For parquet_hive without level_order, falls back to ``**/*.parquet`` glob.
    This is only hit during introspection — query-time code uses
    ``build_hive_path()`` from query_utils.py which requires level_order.
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


def introspect(
    conn, dataset, provided_schema: Optional[Dict[str, str]] = None,
    level_order: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Derive schema, filter_values, and availability from parquet files.

    When *provided_schema* is given, it is used as the authoritative data_schema
    and glob-based schema introspection is skipped.  This allows registration to
    succeed even when older partition files have a different schema (submitter
    takes responsibility for consistency).

    When *level_order* is given (computed by validate_and_build_level_order before
    this call), it is used to determine which columns to introspect for filter_values
    and which to group by for availability.

    Performance strategy for parquet_hive with level_order:
      - Schema: pin ALL levels to first values → DuckDB reads one partition (instant)
      - Filter values: os.listdir() on hive directories (instant, no DuckDB)
      - Availability: os.listdir() walk of directory tree (instant, full coverage)

    Returns a dict with any subset of:
      {
        "data_schema": {"col": "TYPE", ...},                       # → data_schema column
        "filter_values": {"dim": ["val1", ...], ...},              # → filter_values column
        "availability": {"entity": {"gran": {"min":..,"max":..}}}  # → merged into manifest
      }

    Never raises — returns {} on any error.
    """
    result: Dict[str, Any] = {}
    loc = dataset.data_location
    is_hive = dataset.data_format == "parquet_hive"
    has_level_order = bool(level_order) and is_hive and loc

    # ── path expressions ──────────────────────────────────────────────────────
    # For parquet_hive with level_order, build a fully-pinned path that targets
    # exactly one leaf partition.  This avoids any recursive NFS scan.
    if has_level_order:
        pinned_expr = _pinned_path_expr(loc, level_order)
    else:
        pinned_expr = None

    # Fallback path for non-hive or when level_order is absent
    path_expr = pinned_expr or _path_expr(dataset)
    if not path_expr:
        return result

    # ── schema ─────────────────────────────────────────────────────────────────
    if provided_schema is not None:
        result["data_schema"] = provided_schema
    else:
        # Uses pinned path when available — reads exactly one partition's footer.
        try:
            rows = conn.execute(
                f"DESCRIBE SELECT * FROM {path_expr}"
            ).fetchall()
            result["data_schema"] = {r[0]: r[1] for r in rows}
        except Exception as e:
            log.warning("Schema introspection failed for %s: %s", path_expr, e)
            result["introspect_error"] = str(e)

    # ── filter values ────────────────────────────────────────────────────────────
    tr = dataset.transform

    if level_order:
        all_dims = [lv["column"] for lv in level_order
                    if lv["type"] in ("partition", "filter")]
    else:
        all_dims = list((tr.filter_dimensions or []) if tr else [])

    # Columns that are hive-level (present in level_order) — use os.listdir()
    hive_columns = {lv["column"] for lv in (level_order or [])}

    filter_values: Dict[str, List[Any]] = {}
    for dim in all_dims:
        # Priority 1: os.listdir() for hive-level columns (instant on NFS)
        if has_level_order and dim in hive_columns:
            try:
                values = _hive_distinct_values(loc, level_order, dim)
                if values:
                    filter_values[dim] = values
            except Exception as e:
                log.debug("Hive listdir failed for dim '%s': %s", dim, e)
            continue

        # Priority 2: DuckDB SELECT DISTINCT for non-hive columns
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
    # parquet_hive with level_order AND time as a hive level: os.listdir() walk
    #   (instant, full coverage across all entities and partitions).
    # Otherwise (flat parquet, or hive where time is a data column): DuckDB MIN/MAX.
    time_col = tr.time_dimension if tr else None
    if time_col:
        time_is_hive_level = has_level_order and any(
            lv["column"] == time_col and lv["type"] == "time"
            for lv in (level_order or [])
        )
        if time_is_hive_level:
            try:
                availability = _hive_availability(loc, level_order)
                if availability:
                    result["availability"] = availability
            except Exception as e:
                log.debug("Hive availability walk failed: %s", e)
        elif has_level_order:
            # DuckDB MIN/MAX with targeted file reads.
            # Instead of scanning ALL files via **/*.parquet, iterate over
            # entity × partition combos and read ONE file each (pin hash_bucket
            # to its first value).  This avoids opening redundant bucket files
            # that share the same date range.
            try:
                availability = _targeted_availability(conn, loc, level_order, time_col, dataset)
                if availability:
                    result["availability"] = availability
            except Exception as e:
                log.debug("Targeted availability introspection failed: %s", e)
        else:
            # Fallback for non-hive datasets: single DuckDB MIN/MAX query.
            try:
                sql = (
                    f"SELECT MIN({time_col})::TEXT, MAX({time_col})::TEXT "
                    f"FROM {path_expr}"
                )
                rows = conn.execute(sql).fetchall()
                if rows and rows[0][0] is not None:
                    result["availability"] = {"min": rows[0][0], "max": rows[0][1]}
            except Exception as e:
                log.debug("Availability introspection failed: %s", e)

    return result
