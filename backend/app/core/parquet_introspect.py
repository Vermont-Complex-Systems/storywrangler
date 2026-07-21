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

import duckdb

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


def _hive_entry_sort_key(entry: str):
    """Sort key for hive directory entries that orders numeric values numerically.

    Lexicographic sort puts month=10 before month=2; this key parses the value
    part so unpadded numeric partitions order correctly (month=2 < month=10).
    Non-numeric values sort lexicographically after numeric ones.
    """
    _, val = entry.split("=", 1)
    try:
        return (0, float(val), "")
    except ValueError:
        return (1, 0.0, val)


# Safety cap on tree fan-out for every walk — pathological NFS trees must not
# blow up registration memory or run unbounded.
_MAX_WORK = 5000


def _walk_levels(root: str, levels: List[Dict[str, Any]], classify) -> List[tuple]:
    """Generic hive-tree walk shared by all introspection passes.

    Walks the directory tree from *root* through each level in *levels*
    (a prefix of level_order), descending according to
    ``classify(level) -> action``:

      - ``"expand"``    — follow every entry, recording {column: value} in
                          the context (the value becomes a grouping key)
      - ``"pin"``       — follow only the first entry (value not recorded);
                          used for levels where any branch is representative
                          (e.g. hash buckets share the same date range)
      - ``"endpoints"`` — follow only the first and last entries, tracking
                          which bound ("min"/"max") each descendant serves;
                          used for time_partition levels where only the
                          extremes matter

    Entries are sorted numeric-aware (month=2 < month=10) so "pin" and
    "endpoints" pick correct representatives for unpadded numeric partitions.

    Only reads directory metadata (os.listdir) — instant on NFS, no parquet
    files opened. Fan-out is capped at _MAX_WORK with a warning.

    Returns a list of ``(path, ctx, bound)`` work items, where *ctx* maps
    expanded columns to their (unquoted) values and *bound* is None unless an
    "endpoints" level was traversed.
    """
    work: List[tuple] = [(root, {}, None)]
    for lv in levels:
        col = lv["column"]
        action = classify(lv)
        next_work: List[tuple] = []
        for path, ctx, bound in work:
            try:
                entries = os.listdir(path)
            except OSError:
                continue
            hive_entries = sorted(
                (e for e in entries if "=" in e), key=_hive_entry_sort_key)
            if not hive_entries:
                continue

            if action == "expand":
                for entry in hive_entries:
                    _, val = entry.split("=", 1)
                    next_work.append(
                        (os.path.join(path, entry), {**ctx, col: unquote(val)}, bound))
            elif action == "endpoints":
                if bound is None:
                    # First endpoints level: split into the two directions.
                    next_work.append(
                        (os.path.join(path, hive_entries[0]), ctx, "min"))
                    next_work.append(
                        (os.path.join(path, hive_entries[-1]), ctx, "max"))
                elif bound == "min":
                    next_work.append(
                        (os.path.join(path, hive_entries[0]), ctx, "min"))
                else:  # "max"
                    next_work.append(
                        (os.path.join(path, hive_entries[-1]), ctx, "max"))
            else:  # "pin"
                next_work.append(
                    (os.path.join(path, hive_entries[0]), ctx, bound))
        work = next_work
        if len(work) > _MAX_WORK:
            log.warning(
                "Hive walk too wide (%d entries) at level '%s'; truncating to %d",
                len(work), col, _MAX_WORK,
            )
            work = work[:_MAX_WORK]
    return work


def _hive_distinct_values(root: str, level_order: List[Dict[str, Any]], column: str) -> List[Any]:
    """Read distinct values for a hive partition column using os.listdir().

    Expands all entries at every level above the target *column*, then
    collects the union of values at the target level. This ensures
    completeness: e.g. ``month`` values are collected across all ``year``
    directories, not just the first one.
    """
    idx = next(
        (i for i, lv in enumerate(level_order) if lv["column"] == column), None)
    if idx is None:
        return []

    paths = _walk_levels(root, level_order[:idx], lambda lv: "expand")

    values = set()
    for path, _ctx, _bound in paths:
        try:
            entries = os.listdir(path)
        except OSError:
            continue
        for e in entries:
            if e.startswith(f"{column}="):
                _, val = e.split("=", 1)
                values.add(unquote(val))
    return sorted(values)


def _leaf_type_count(conn, leaf_dir: str) -> Optional[int]:
    """Row count of one leaf partition, read from parquet footers only.

    For types-counts datasets a time-leaf holds one row per distinct type,
    so COUNT(*) equals the vocabulary size at that date. The ``**`` glob
    also covers hash_bucket subdirectories below the leaf — types are
    disjoint across buckets, so the sum is still the distinct count.
    """
    try:
        row = conn.execute(
            f"SELECT COUNT(*) FROM read_parquet('{leaf_dir}/**/*.parquet')"
        ).fetchone()
    except duckdb.InterruptException:
        raise
    except Exception as e:
        log.debug("Type count failed for %s: %s", leaf_dir, e)
        return None
    return row[0] if row else None


def _hive_availability(
    root: str,
    level_order: List[Dict[str, Any]],
    conn=None,
    count_types: bool = False,
) -> Dict[str, Any]:
    """Compute availability (min/max of time dimension) by walking the directory tree.

    Uses os.listdir() at each level — no DuckDB, no parquet files opened.
    Walks all combinations of partition × entity levels, then reads the time
    level directory names to determine min/max.

    When *count_types* is set (types-counts datasets), each leaf gains a
    ``types`` key: the row count of the latest date's partition, read from
    parquet footers via *conn* — one cheap query per entity × partition
    combo. Count failures degrade to bounds-only leaves.

    Returns availability in entity-first format:
      {"United States": {"daily": {"min": "2024-01-01", "max": "2026-04-20", "types": 560198}, ...}}
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
        elif lv["type"] in ("partition", "time_partition"):
            partition_indices.append(i)

    if time_idx is None:
        return {}

    # Build paths to all time-level directories: expand grouping levels
    # (partition/entity/time_partition values become keys), pin the rest
    # (hash_bucket, filter — not relevant for availability).
    work = _walk_levels(
        root, level_order[:time_idx],
        lambda lv: "expand" if lv["type"] in ("partition", "entity", "time_partition") else "pin",
    )
    if not work:
        return {}

    # Now enumerate time values at the time level for each path
    time_col = level_order[time_idx]["column"]
    entity_col = level_order[entity_idx]["column"] if entity_idx is not None else None
    group_cols = [level_order[i]["column"] for i in partition_indices]

    availability: Dict[str, Any] = {}
    for path, ctx, _bound in work:
        try:
            entries = os.listdir(path)
        except OSError:
            continue
        # (value, raw_entry) pairs — sorted by unquoted value, raw entry kept
        # so the max leaf's on-disk directory name can be re-joined for counting.
        time_entries = sorted(
            (unquote(e.split("=", 1)[1]), e)
            for e in entries if e.startswith(f"{time_col}=")
        )
        if not time_entries:
            continue

        bounds = {"min": time_entries[0][0], "max": time_entries[-1][0]}
        if count_types and conn is not None:
            try:
                n = _leaf_type_count(conn, os.path.join(path, time_entries[-1][1]))
            except duckdb.InterruptException:
                # Admin timeout fired mid-count: keep every leaf's bounds and
                # stop counting — a partial types index is still valid.
                log.warning(
                    "Type counting interrupted for %s; remaining leaves get bounds only", root,
                )
                count_types = False
                n = None
            if n:
                bounds["types"] = n
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
         "overrides": {"1/United States": 16, "2/United States": 32}}

    Override keys are the expanded level values above the bucket level
    (entity and partition dims), joined in level_order order.

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
    work = _walk_levels(
        root, level_order[:bucket_idx],
        lambda lv: "expand" if lv["type"] in ("partition", "entity", "time_partition") else "pin",
    )

    # Count bucket directories per expanded combo. The override key is the
    # full path of expanded level values above the bucket level, joined in
    # level_order order — same rule as bucket_override_key() in
    # duckdb_query.py, and valid with or without an entity level.
    key_cols = [
        lv["column"] for lv in level_order[:bucket_idx]
        if lv["type"] in ("entity", "partition", "time_partition")
    ]
    counts: Dict[str, int] = {}
    for path, ctx, _bound in work:
        try:
            entries = os.listdir(path)
        except OSError:
            continue
        n_buckets = sum(1 for e in entries if e.startswith(f"{bucket_col}="))
        key = "/".join(str(ctx[c]) for c in key_cols if c in ctx)
        counts[key] = n_buckets

    if not counts:
        return None

    # Determine default_count (most common count)
    from collections import Counter
    count_freq = Counter(counts.values())
    default_count = count_freq.most_common(1)[0][0]
    if default_count < 1:
        default_count = 1

    # Overrides for combos that differ from the default count
    overrides: Dict[str, int] = {}
    for key, n in counts.items():
        if n != default_count:
            overrides[key] = n

    config: Dict[str, Any] = {"column": bucket_col, "default_count": default_count}
    if overrides:
        config["overrides"] = overrides
    return config


def _parquet_glob(path: str) -> Optional[str]:
    """Glob covering every parquet file in *path* or one directory level below.

    Must be a glob, not a single file: multi-file leaves (e.g. DuckLake
    buckets) split their date range across files — the alphabetically-first
    file may hold a single day's append, so per-file MIN/MAX is wrong.
    """
    try:
        entries = os.listdir(path)
    except OSError:
        return None
    if any(f.endswith(".parquet") for f in entries):
        return os.path.join(path, "*.parquet")
    # Try one level deeper (e.g. hash_bucket directories below the leaf);
    # buckets share the same date range, so the first one is representative.
    for sd in sorted(entries):
        sd_path = os.path.join(path, sd)
        if not os.path.isdir(sd_path):
            continue
        try:
            if any(f.endswith(".parquet") for f in os.listdir(sd_path)):
                return os.path.join(sd_path, "*.parquet")
        except OSError:
            continue
    return None


def _targeted_availability(
    conn, root: str, level_order: List[Dict[str, Any]], time_col: str, dataset,
) -> Dict[str, Any]:
    """Compute availability by reading a minimal number of parquet files.

    When time is inside the parquet files (not a hive level), we need DuckDB
    to read MIN/MAX.  This function walks the directory tree to find the
    date range for each user-facing dimension combination:

    * **entity, partition, filter** levels are *expanded* — each distinct
      value becomes a grouping key in the output.  (Filter expansion is
      enabled only when time_partition levels exist; otherwise filters are
      pinned to their first value to match pre-time_partition behaviour.)
    * **time_partition** levels are handled smartly: only the *first* and
      *last* sorted entries are followed (for min/max date bounds).
      This reads 2 leaf directories per filter combo instead of scanning
      every year×month directory.
    * **hash_bucket** levels are pinned to their first value (all buckets
      share the same date range).
    """
    entity_col = (
        dataset.entity_mapping.local_id_column
        if dataset.entity_mapping else None
    )

    has_tp = any(lv["type"] == "time_partition" for lv in level_order)

    # Grouping columns for the availability tree — these appear as keys in
    # the nested output dict.  time_partition columns are collapsed into
    # min/max bounds so they do NOT appear as grouping keys.
    grouping_cols = []
    for lv in level_order:
        if lv["type"] in ("partition",):
            grouping_cols.append(lv["column"])
        elif lv["type"] == "filter" and has_tp:
            grouping_cols.append(lv["column"])

    # Walk the hive tree up to the time level (time is inside files):
    # expand grouping levels, follow only min/max endpoints through
    # time_partition levels, pin hash_bucket (and filter when no
    # time_partitions — matches pre-time_partition behaviour).
    walk_levels = []
    for lv in level_order:
        if lv["type"] == "time":
            break
        walk_levels.append(lv)

    def _classify(lv):
        if lv["type"] in ("entity", "partition") or (lv["type"] == "filter" and has_tp):
            return "expand"
        if lv["type"] == "time_partition":
            return "endpoints"
        return "pin"  # hash_bucket / filter (when no time_partitions)

    work = _walk_levels(root, walk_levels, _classify)
    if not work:
        return {}

    # Group leaf paths by context to merge min/max from the two endpoints.
    from collections import defaultdict
    ctx_paths: Dict[tuple, Dict[str, list]] = defaultdict(
        lambda: {"min": [], "max": []})
    for path, ctx, bound in work:
        key = tuple(sorted(ctx.items()))
        if bound in ("min", None):
            ctx_paths[key]["min"].append(path)
        if bound in ("max", None):
            ctx_paths[key]["max"].append(path)

    # Read MIN/MAX across each endpoint directory.  A path can serve min,
    # max, or both (bound=None when the dataset has no time_partition
    # levels) — read each directory exactly once with a combined MIN/MAX query.
    availability: Dict[str, Any] = {}
    for ctx_key, endpoints in ctx_paths.items():
        ctx = dict(ctx_key)
        overall_min: Optional[str] = None
        overall_max: Optional[str] = None

        need: Dict[str, set] = {}
        for path in endpoints["min"]:
            need.setdefault(path, set()).add("min")
        for path in endpoints["max"]:
            need.setdefault(path, set()).add("max")

        for path, bounds_needed in need.items():
            pq_glob = _parquet_glob(path)
            if not pq_glob:
                continue
            try:
                row = conn.execute(
                    f"SELECT MIN({time_col})::TEXT, MAX({time_col})::TEXT "
                    f"FROM read_parquet('{pq_glob}')"
                ).fetchone()
            except duckdb.InterruptException:
                # Timeout fired — propagate so the caller records the failure
                # instead of registering silently truncated availability.
                raise
            except Exception:
                continue
            if row is None:
                continue
            if "min" in bounds_needed and row[0] is not None:
                if overall_min is None or row[0] < overall_min:
                    overall_min = row[0]
            if "max" in bounds_needed and row[1] is not None:
                if overall_max is None or row[1] > overall_max:
                    overall_max = row[1]

        if overall_min is None or overall_max is None:
            continue

        bounds = {"min": overall_min, "max": overall_max}
        ent = ctx.get(entity_col) if entity_col else None

        # Build nested dict keyed by entity → grouping dims → {min, max}
        part_keys = [ctx.get(col, "") for col in grouping_cols]
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

    # Found partition leaves but derived no bounds → every leaf read failed
    # (the data is unreachable, e.g. an NFS blip). Raise rather than return an
    # empty index the caller would silently accept.
    if work and not availability:
        raise RuntimeError(
            f"availability walk found {len(work)} partition leaves under {root} "
            "but could not read date bounds from any — data unreachable?"
        )
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
      - transform.time_partitions item       → type "time_partition"
      - transform.filter_dimensions item    → type "filter"
      - everything else                     → type "partition"

    The first on-disk value is stored as ``default_value`` for each level.
    At query time, partition/filter levels use this as the injected default
    when the caller omits the parameter.  The same value is also stored as
    ``raw_value``, which (unlike default_value) is never type-coerced —
    query-time path pinning reads it to match the on-disk naming convention
    (zero-padded vs unpadded numeric directories).

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

    time_partitions = (tr.time_partitions if tr else None) or []
    for tp in time_partitions:
        if tp not in declared:
            declared[tp] = "time_partition"

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
            # Raw on-disk string, never type-coerced (unlike default_value).
            # Query-time path pinning uses it to match the directory naming
            # convention (e.g. zero-padded month=03 vs unpadded month=3).
            "raw_value": lv["value"],
        }
        result.append(entry)

    # Validate that hash_bucket column appears in discovered levels
    if hb and hb not in set(discovered_names):
        raise ValueError(
            f"hash_bucket '{hb}' not found in on-disk hive "
            f"levels {discovered_names}. The hash bucket column must be "
            f"an actual hive directory level."
        )

    # Validate that time_partition columns appear in discovered levels
    for tp in time_partitions:
        if tp not in set(discovered_names):
            raise ValueError(
                f"time_partition '{tp}' not found in on-disk hive "
                f"levels {discovered_names}. Each time_partition must be "
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
    ``build_hive_path()`` from duckdb_query.py which requires level_order.
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
                    if lv["type"] in ("partition", "filter", "time_partition")]
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
    # types-counts datasets get a `types` (vocabulary size) key in each
    # availability leaf — the topN ceiling hint for allotax-style consumers.
    ep = getattr(dataset, "endpoint_schema", None)
    count_types = bool(ep) and getattr(ep, "type", None) == "types-counts"
    if time_col:
        time_is_hive_level = has_level_order and any(
            lv["column"] == time_col and lv["type"] == "time"
            for lv in (level_order or [])
        )
        if time_is_hive_level:
            try:
                availability = _hive_availability(
                    loc, level_order, conn=conn, count_types=count_types)
                if availability:
                    result["availability"] = availability
            except Exception as e:
                # Don't swallow silently — the caller refuses to register a
                # hive+time dataset without availability, and needs the reason.
                log.warning("Hive availability walk failed for %s: %s", loc, e)
                result["introspect_error"] = f"availability walk failed: {e}"
        elif has_level_order:
            # DuckDB MIN/MAX with targeted directory reads.
            # Instead of scanning ALL files via **/*.parquet, iterate over
            # entity × partition combos and read ONE leaf directory each
            # (pin hash_bucket to its first value).  This avoids opening
            # redundant bucket directories that share the same date range.
            try:
                availability = _targeted_availability(conn, loc, level_order, time_col, dataset)
                if availability:
                    result["availability"] = availability
            except duckdb.InterruptException:
                # Admin timeout fired mid-walk. Record the failure rather
                # than registering a silently truncated availability index.
                log.warning(
                    "Availability introspection timed out for %s; "
                    "manifest.availability not derived", loc,
                )
                result["introspect_error"] = (
                    "availability introspection timed out; "
                    "manifest.availability not derived — re-register to retry"
                )
            except Exception as e:
                log.warning("Targeted availability introspection failed for %s: %s", loc, e)
                result["introspect_error"] = f"availability introspection failed: {e}"
        else:
            # Fallback for non-hive datasets: DuckDB MIN/MAX, grouped by the
            # entity column when one is declared (entity-first format, matching
            # the hive walk); dataset-level otherwise.
            em = getattr(dataset, "entity_mapping", None)
            entity_col = getattr(em, "local_id_column", None) if em else None
            type_col = (getattr(ep, "type_column", None) or "types") if count_types else None
            try:
                if entity_col:
                    rows = conn.execute(
                        f"SELECT {entity_col}, MIN({time_col})::TEXT, MAX({time_col})::TEXT "
                        f"FROM {path_expr} WHERE {entity_col} IS NOT NULL "
                        f"GROUP BY {entity_col} ORDER BY {entity_col}"
                    ).fetchall()
                    if rows:
                        result["availability"] = {
                            ent: {"min": mn, "max": mx} for ent, mn, mx in rows
                        }
                        if type_col:
                            # Per-entity vocabulary size at that entity's latest
                            # time value. Best-effort — bounds survive a failed count.
                            try:
                                counts = conn.execute(
                                    f"SELECT {entity_col}, COUNT(DISTINCT {type_col}) "
                                    f"FROM {path_expr} t "
                                    f"WHERE {time_col} = ("
                                    f"  SELECT MAX({time_col}) FROM {path_expr} "
                                    f"  WHERE {entity_col} = t.{entity_col}) "
                                    f"GROUP BY {entity_col}"
                                ).fetchall()
                                for ent, n in counts:
                                    if n and ent in result["availability"]:
                                        result["availability"][ent]["types"] = n
                            except Exception as e:
                                log.debug("Per-entity type count failed: %s", e)
                else:
                    rows = conn.execute(
                        f"SELECT MIN({time_col})::TEXT, MAX({time_col})::TEXT "
                        f"FROM {path_expr}"
                    ).fetchall()
                    if rows and rows[0][0] is not None:
                        result["availability"] = {"min": rows[0][0], "max": rows[0][1]}
                        if type_col:
                            # Dataset-level vocabulary size (flat parquet has no
                            # per-combo leaves). Best-effort — bounds survive a
                            # failed count.
                            try:
                                n = conn.execute(
                                    f"SELECT COUNT(DISTINCT {type_col}) FROM {path_expr}"
                                ).fetchone()[0]
                                if n:
                                    result["availability"]["types"] = n
                            except Exception as e:
                                log.debug("Type count failed: %s", e)
            except Exception as e:
                log.debug("Availability introspection failed: %s", e)

    return result
