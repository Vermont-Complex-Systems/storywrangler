"""DuckDB/parquet query engine for registry-driven datasets.

Everything here is specific to the parquet path: hive path construction and
pruning, hash-bucket routing, DuckDB error translation, and the two query
patterns:

  load_system()       — endpoint_schema.type == 'types-counts'
                        Returns {types: [...], counts: [...]} for allotax / rank distributions.

  load_time_series()  — endpoint_schema.type == 'time-series'
                        Returns [{col1: v, ..., "count": n}, ...] for flexible GROUP BY queries.

Both support parquet and parquet_hive; all filtering is done via WHERE clauses.
For parquet_hive, hive_partitioning=true handles partition pruning automatically.

Format-agnostic helpers (registry metadata, entity resolution, date parsing)
live in query_utils.py; mongodb pass-through loading lives in mongo_client.py.
"""

import logging
import os
import re
from contextlib import contextmanager
from typing import Any, List, Optional
from urllib.parse import quote

import duckdb
from fastapi import HTTPException

from storywrangler_schemas.hashing import assign_bucket  # noqa: F401  # re-export (single source of truth)
from ..core.exceptions import DataNotAvailableError, QueryError, QueryTimeoutError
from .query_utils import resolve_count_column

log = logging.getLogger(__name__)


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


def bucket_override_key(dataset_obj, *, entity_value=None, filter_vals=None) -> Optional[str]:
    """Override-lookup key for a request: the expanded level values above the
    bucket level, joined in level_order order.

    Must mirror the key built by ``_derive_bucket_config`` at registration.
    Returns None (→ default_count) when a needed level value is missing.
    """
    level_order = getattr(dataset_obj, "level_order", None) or []
    vals = []
    for lv in level_order:
        if lv["type"] == "hash_bucket":
            break
        if lv["type"] == "entity":
            if entity_value is None:
                return None
            vals.append(str(entity_value))
        elif lv["type"] in ("partition", "time_partition"):
            v = (filter_vals or {}).get(lv["column"])
            if v is None:
                return None
            vals.append(str(v))
    return "/".join(vals)


def resolve_bucket_count(hb: dict, key: Optional[str] = None) -> int:
    """Bucket count for one combo: ``overrides[key]`` → ``default_count``.

    *key* comes from ``bucket_override_key()``. Returns 1 (no sharding) if
    hash_bucket is not configured.
    """
    default = hb.get("default_count", 1)
    overrides = hb.get("overrides")
    if not overrides or key is None:
        return default
    return overrides.get(key, default)


# ── Time-partition derivation ──────────────────────────────────────────────
# Derives year/month/day values from requested dates for time_partition levels.

# Date-component extractors. Values iterate as datetime.date, so only
# day-granularity components are supported; unknown components (including
# hour/minute) are left as wildcards with no pruning condition.
_TEMPORAL_EXTRACTORS = {
    "year":   lambda d: d.year,
    "month":  lambda d: d.month,
    "day":    lambda d: d.day,
}

# Fallback zero-pad width for temporal hive directories, used only for
# datasets registered before level_order stored raw_value. Matches the
# PySpark/pandas convention: month=03, day=15.
_TEMPORAL_PAD_WIDTH = {
    "month": 2,
    "day":   2,
}


def _format_tp_value(val, level: dict):
    """Format a time-partition value to match its on-disk directory naming.

    Uses the level's raw on-disk sample (``raw_value``, captured at
    registration) to decide zero-padding: a ``month=03`` directory yields
    '03', a ``month=3`` directory yields '3'. Falls back to the conventional
    zero-padded form for datasets registered before raw_value was stored.
    """
    raw = level.get("raw_value")
    if isinstance(raw, str) and raw.isdigit():
        return str(val).zfill(len(raw)) if raw.startswith("0") else str(val)
    pad = _TEMPORAL_PAD_WIDTH.get(level["column"].lower())
    return str(val).zfill(pad) if pad else val


def _derive_time_partitions(
    dates: List[str],
    level_order: list,
) -> tuple:
    """Derive time_partition path values and WHERE conditions from dates.

    Returns (path_vals, conditions, params):
      - path_vals: {col: value} for single-value cases (pinned in hive path)
      - conditions: SQL WHERE fragments for multi-value cases
      - params: corresponding bind parameters
    """
    from datetime import date as dt_date, timedelta

    tp_levels = [lv for lv in level_order if lv["type"] == "time_partition"]
    if not tp_levels or not dates:
        return {}, [], []

    # Files can span partition boundaries — e.g. reddit's weekly files are
    # bucketed under the month/year their ISO week starts in, so rows near a
    # range edge may live in a neighboring directory. Pad the candidate window
    # by one week on each side: pruning reads at most one extra directory per
    # edge, and the in-file time filter keeps results exact.
    pad = timedelta(days=6)
    start = dt_date.fromisoformat(str(dates[0])[:10]) - pad
    end = dt_date.fromisoformat(str(dates[1])[:10]) + pad

    path_vals: dict = {}
    conditions: list = []
    params: list = []

    for lv in tp_levels:
        col = lv["column"]
        extractor = _TEMPORAL_EXTRACTORS.get(col.lower())
        if extractor is None:
            continue  # unknown component — leave as wildcard

        # Collect all distinct values across the date range
        values = set()
        cur = start
        while cur <= end:
            values.add(extractor(cur))
            cur += timedelta(days=1)

        if len(values) == 1:
            # Format to match on-disk directory names (e.g. month=03 vs month=3).
            path_vals[col] = _format_tp_value(values.pop(), lv)
        else:
            sorted_vals = sorted(values)
            placeholders = ",".join("?" * len(sorted_vals))
            conditions.append(f"{col} IN ({placeholders})")
            params.extend(sorted_vals)

    return path_vals, conditions, params


# ── Hive path construction ───────────────────────────────────────────────────
# Generic path builder using the stored level_order from registration.

def build_hive_path(
    dataset_obj,
    *,
    entity_value: Optional[str] = None,
    filter_vals: Optional[dict] = None,
    time_value: Optional[str] = None,
    time_partition_vals: Optional[dict] = None,
    bucket_value: Optional[int] = None,
    glob_suffix: str = "/*.parquet",
) -> Optional[str]:
    """Build an exact hive partition path from the stored level_order.

    Walks the level_order list in sequence. For each level:
      - "partition" / "filter"  → look up value in filter_vals[column]
      - "entity"                → use entity_value
      - "hash_bucket"           → use bucket_value
      - "time"                  → use time_value
      - "time_partition"        → look up value in time_partition_vals[column]

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
    time_partition_vals = time_partition_vals or {}
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
        elif ltype == "time_partition":
            val = time_partition_vals.get(col)
        elif ltype in ("partition", "filter"):
            val = filter_vals.get(col)
        else:
            val = None

        if val is not None:
            path += f"/{col}={quote(str(val), safe='')}"
        else:
            path += "/*"

    return path + glob_suffix


def _diagnose_pinned_miss(
    dataset_obj,
    *,
    entity_value=None,
    filter_vals: Optional[dict] = None,
    time_value=None,
    time_partition_vals: Optional[dict] = None,
) -> Optional[tuple]:
    """After a pinned-path query matched no files, find the first missing segment.

    Walks the pinned hive path level by level with ``os.path.isdir`` (a handful
    of cheap stat calls) and returns ``(level_type, segment)`` for the first
    pinned directory that does not exist on disk — e.g. ``("entity",
    "country=Foo")`` for a DB/disk entity mismatch, or ``("time_partition",
    "month=03")`` for a naming-convention mismatch. Returns None when every
    pinned segment exists (the miss is at or below the first wildcard level).
    """
    filter_vals = filter_vals or {}
    time_partition_vals = time_partition_vals or {}
    path = dataset_obj.data_location

    for level in dataset_obj.level_order:
        col, ltype = level["column"], level["type"]
        if ltype == "entity":
            val = entity_value
        elif ltype == "time":
            val = time_value
        elif ltype == "time_partition":
            val = time_partition_vals.get(col)
        elif ltype in ("partition", "filter"):
            val = filter_vals.get(col)
        else:
            val = None  # hash_bucket — never pinned by load_system

        if val is None:
            return None  # wildcard — cannot attribute the miss further down
        segment = f"{col}={quote(str(val), safe='')}"
        path = f"{path}/{segment}"
        if not os.path.isdir(path):
            return ltype, segment
    return None


# ── DuckDB error classification ──────────────────────────────────────────────

_DATA_MISSING_PATTERNS = [
    re.compile(r"No files found that match the pattern", re.IGNORECASE),
    re.compile(r"Cannot open file", re.IGNORECASE),
    re.compile(r"File .+ does not exist", re.IGNORECASE),
]


def is_data_missing(exc: Exception) -> bool:
    """True when *exc* is DuckDB's way of saying the target files don't exist."""
    msg = str(exc)
    return any(p.search(msg) for p in _DATA_MISSING_PATTERNS)


# Internal alias — module-private call sites predate the public name.
_is_data_missing = is_data_missing


@contextmanager
def handle_query_error(dataset_label: str):
    """Wrap DuckDB queries with user-friendly error translation.

    Usage::

        with handle_query_error("wikimedia/ngrams"):
            rows = conn.execute(...).fetchall()

    Catches raw DuckDB exceptions and raises custom exceptions that are
    converted to JSON responses by the global handlers in main.py.

    - Timeout (InterruptException) → QueryTimeoutError (→ 504)
    - File-not-found → DataNotAvailableError (→ 404)
    - Other errors   → QueryError (→ 500, no internal paths leaked)
    - HTTPExceptions pass through unchanged
    """
    try:
        yield
    except (HTTPException, DataNotAvailableError, QueryError, QueryTimeoutError):
        raise
    except duckdb.InterruptException:
        raise QueryTimeoutError(dataset_label)
    except Exception as exc:
        if _is_data_missing(exc):
            raise DataNotAvailableError(dataset_label)
        raise QueryError(dataset_label)


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
    count_col: Optional[str] = None,
) -> dict:
    """Load types-counts for one system.

    Identical query logic for both parquet and parquet_hive: all filtering
    is done via WHERE clauses. For parquet_hive, hive_partitioning=true means
    DuckDB prunes partition directories automatically.

    For parquet_hive with level_order, builds a *pinned* path that bakes
    concrete entity and filter values into the directory path rather than
    relying on post-enumeration WHERE pruning.  Only the time level remains
    a wildcard (``/*``), dramatically reducing NFS directory enumeration.

    Column names come from endpoint_schema (type_column / count_column),
    defaulting to 'types' / 'counts'. When count_column is a list, the first
    entry is used unless *count_col* overrides it — callers must resolve the
    override through resolve_count_column() so only registered columns reach
    the SQL. The time column comes from transform.time_dimension.

    Extra filter dimensions (e.g. granularity='daily', ngram_size=1) are
    passed directly in filter_vals by the caller.

    Returns {"types": [...], "counts": [...]} ready for allotax or serialization.
    """
    ep = dataset_obj.endpoint_schema or {}
    tr = dataset_obj.transform or {}
    entity_col = (dataset_obj.entity_mapping or {}).get("local_id_column")
    type_col  = ep.get("type_column")  or "types"
    count_col = count_col or resolve_count_column(dataset_obj)
    time_col  = tr.get("time_dimension")

    schema = dataset_obj.data_schema or {}

    # For parquet_hive, build a pinned path: concrete values for entity,
    # filter, time_partition, and (when single-date) time — so DuckDB skips
    # NFS directory enumeration entirely.
    if dataset_obj.data_format == "parquet_hive" and getattr(dataset_obj, "level_order", None):
        # Pin time for single-date queries (avoids date-directory enumeration).
        # Only works when a time-type level exists in level_order — otherwise
        # time_dimension is an internal parquet column and needs a WHERE clause.
        has_time_level = any(lv["type"] == "time" for lv in dataset_obj.level_order)
        time_value = None
        if has_time_level and time_col and dates and str(dates[0]) == str(dates[1]):
            time_value = str(dates[0])

        # Derive time_partition values (year/month/day) from dates.
        # Single-value → pinned in path; multi-value → wildcard + WHERE IN.
        tp_path_vals, tp_conditions, tp_params = _derive_time_partitions(
            dates or [], dataset_obj.level_order,
        )

        pinned_path = build_hive_path(
            dataset_obj,
            entity_value=local_id,
            filter_vals=filter_vals,
            time_value=time_value,
            time_partition_vals=tp_path_vals,
        )
        from_clause = f"read_parquet('{pinned_path}', hive_partitioning=true)"

        # WHERE: time_partition pruning + date BETWEEN for the actual time column.
        conditions = tp_conditions
        params = tp_params
        if time_col and dates and time_value is None:
            col_type = schema.get(time_col, "")
            cast = _cast_dates([str(d) for d in dates], col_type)
            conditions.append(f"{time_col} BETWEEN ? AND ?")
            params.extend(cast)

        # Columns that are not hive levels live inside the parquet files —
        # the pinned path can't encode them, so they still need WHERE clauses
        # (e.g. an in-file filter_dimension like 'sex', or an in-file entity).
        level_cols = {lv["column"] for lv in dataset_obj.level_order}
        if entity_col and local_id is not None and entity_col not in level_cols:
            conditions.append(f"{entity_col} = ?")
            params.append(local_id)
        for col, val in filter_vals.items():
            if col not in level_cols:
                conditions.append(f"{col} = ?")
                params.append(val)

        pinned = True
    else:
        from_clause = _path_expr(dataset_obj)

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

        pinned = False

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    # limit=0 means "no limit" (documented contract of the rtd/allotax endpoints).
    limit_clause = "LIMIT ?" if limit else ""
    limit_params = [limit] if limit else []

    try:
        rows = conn.execute(
            f"""
            SELECT {type_col}, SUM({count_col}) AS counts
            FROM {from_clause}
            {where}
            GROUP BY {type_col}
            ORDER BY counts DESC
            {limit_clause}
            """,
            [*params, *limit_params],
        ).fetchall()
    except Exception as exc:
        if pinned and _is_data_missing(exc):
            # Pinned path targets a specific partition that doesn't exist.
            # Cheap filesystem walk to attribute the miss: an entity-level
            # mismatch is a misconfiguration worth a diagnostic 404; anything
            # else (e.g. a date partition that genuinely doesn't exist)
            # returns empty and the caller decides whether that is an error.
            missing = _diagnose_pinned_miss(
                dataset_obj,
                entity_value=local_id,
                filter_vals=filter_vals,
                time_value=time_value,
                time_partition_vals=tp_path_vals,
            )
            if missing and missing[0] == "entity":
                raise HTTPException(
                    status_code=404,
                    detail=(
                        f"Entity '{local_id}' not found: hive directory "
                        f"'{missing[1]}' does not exist on disk. If this dataset "
                        "uses entity_namespace (Pattern 2), verify the column "
                        "stores full URL values (e.g. https://openalex.org/ID, not just A...)."
                    ),
                )
            if missing:
                log.warning(
                    "Pinned hive path miss for %s/%s: segment '%s' (%s level) "
                    "not on disk — check the on-disk naming convention",
                    getattr(dataset_obj, "domain", "?"),
                    getattr(dataset_obj, "dataset_id", "?"),
                    missing[1], missing[0],
                )
            rows = []
        else:
            raise

    if not rows and entity_col and local_id is not None and not pinned:
        # Distinguish "entity not found" from "entity exists but no data in range".
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
    tr = dataset_obj.transform or {}
    time_col = tr.get("time_dimension") or "year"
    count_col = resolve_count_column(dataset_obj, default="count")

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
