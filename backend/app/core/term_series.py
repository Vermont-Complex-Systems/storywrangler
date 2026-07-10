"""Shared helpers for sparkline-backed domain routers (wikimedia, reddit).

Both routers expose the same endpoint family — top-ngrams, term-series, and
term-series/batch — over hive-partitioned ngram datasets with precomputed,
hash-bucket-sharded sparkline files. Everything that is not genuinely
domain-specific lives here:

  validated_dims()        — validate query params against introspected filter_values
  ngrams_context()        — (filter_vals, entity base path) for partition scans
  build_date_filter()     — date/window → SQL condition + params
  series_entry()          — one time-series response row
  log_fast_path_miss()    — classify a sparkline failure before scan fallback
  fetch_sparkline_rows()  — bucket-routed sparkline lookup for a set of terms
  run_top_ngrams()        — the full top-ngrams endpoint body (off the event loop)
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import HTTPException

from .duckdb_client import get_duckdb_client, run_blocking
from .query_utils import (
    assign_bucket, build_hive_path, entity_base_path, get_bucket_config,
    get_queryable_dims, handle_query_error, is_data_missing, load_system,
    parse_dates, resolve_bucket_count,
)

log = logging.getLogger(__name__)


def validated_dims(dataset_obj, candidates: dict) -> dict:
    """Return the subset of *candidates* that are queryable dimensions.

    Each value is validated against the introspected filter_values (the
    authoritative record of what is actually on disk); an invalid value
    raises 400. Candidates that are not queryable dims are dropped —
    they are not hive levels for this dataset.
    """
    fv = dataset_obj.filter_values or {}
    queryable = get_queryable_dims(dataset_obj)
    extra: dict = {}
    for dim, val in candidates.items():
        if dim not in queryable:
            continue
        valid = fv.get(dim, [])
        if valid and val not in valid:
            raise HTTPException(
                status_code=400,
                detail=f"{dim} must be one of {sorted(valid)}",
            )
        extra[dim] = val
    return extra


def ngrams_context(ngrams_obj, local_id, dim_values: dict) -> tuple:
    """Build (filter_vals, entity_base_path) for term-series partition scans."""
    dims = get_queryable_dims(ngrams_obj)
    filter_vals = {d: dim_values[d] for d in dims if d in dim_values}
    return filter_vals, entity_base_path(ngrams_obj, local_id, filter_vals)


def build_date_filter(date_str: str, window: int) -> tuple:
    """Parse a date + look-back window into a SQL condition and bind params.

    Returns ("date BETWEEN ? AND ?", [start, end]) when window > 0,
    or ("date <= ?", [end]) for full history. Raises 400 on a bad date.
    """
    try:
        end = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date: {date_str}")

    if window > 0:
        start_str = (end - timedelta(days=window)).strftime("%Y-%m-%d")
        return "date BETWEEN ? AND ?", [start_str, date_str]
    return "date <= ?", [date_str]


def series_entry(date_str: str, count, rank, freq) -> dict:
    """Shape one (date, count, rank, freq) row for a term-series response."""
    return {
        "date": date_str,
        "counts": int(count) if count else 0,
        "rank": int(rank) if rank else 0,
        "freq": float(freq) if freq else 0.0,
    }


def log_fast_path_miss(label: str, exc: Exception) -> None:
    """Classify a sparkline fast-path failure before falling back to the scan."""
    if is_data_missing(exc):
        log.info("%s: sparkline files missing; falling back to partition scan", label)
    else:
        log.warning(
            "%s: sparkline fast path failed (%s); falling back to partition scan",
            label, exc,
        )


def bucket_files(dataset_obj, terms, local_id, n: int) -> List[str]:
    """Glob paths of the hash-bucket directories that can contain *terms*.

    Each bucket is globbed with ``/*.parquet`` — never a pinned filename:
    DuckLake-backed buckets hold several uniquely-named
    ``ducklake-<uuid>.parquet`` files whose set changes on every compaction.
    """
    hb = get_bucket_config(dataset_obj)
    n_buckets = resolve_bucket_count(hb, local_id, n)
    buckets = {assign_bucket(t, n_buckets) for t in terms}
    return [
        build_hive_path(
            dataset_obj,
            filter_vals={"ngram_size": n},
            entity_value=local_id,
            bucket_value=b,
            glob_suffix="/*.parquet",
        )
        for b in sorted(buckets)
    ]


def fetch_sparkline_rows(
    conn, sparkline_obj, terms: List[str], local_id, n: int,
    date_condition: str, date_params: list, label: str,
) -> list:
    """Bucket-routed sparkline lookup for *terms*.

    Returns rows of (ngram, date, pv_count, pv_rank, pv_freq) ordered by
    ngram, date — or [] with a classified log line on failure (missing
    sparkline files are expected; anything else is a warning).
    """
    files = bucket_files(sparkline_obj, terms, local_id, n)
    file_list = ", ".join(f"'{f}'" for f in files)
    placeholders = ", ".join(["?"] * len(terms))
    try:
        return conn.execute(
            f"""
            SELECT ngram, date, pv_count, pv_rank, pv_freq
            FROM read_parquet([{file_list}])
            WHERE ngram IN ({placeholders})
              AND {date_condition}
            ORDER BY ngram, date
            """,
            [*terms, *date_params],
        ).fetchall()
    except Exception as exc:
        log_fast_path_miss(label, exc)
        return []


async def run_top_ngrams(
    dataset_obj,
    label: str,
    local_id: Optional[str],
    dates: str,
    dates2: Optional[str],
    filter_vals: dict,
    limit: int,
    metadata: dict,
    range_sep: str = "_",
) -> dict:
    """Shared top-ngrams endpoint body, executed off the event loop.

    Loads one types-counts system (or two for a temporal comparison keyed
    by date range) and formats the response. *range_sep* joins start/end
    in the comparison keys (wikimedia/reddit use "_", babynames "-").
    """
    def _query():
        with handle_query_error(label):
            with get_duckdb_client().timed_connect() as conn:
                dr1 = parse_dates(dates)
                sys1 = load_system(conn, dataset_obj, local_id, dr1, filter_vals, limit)
                formatted1 = [{"types": t, "counts": c} for t, c in zip(sys1["types"], sys1["counts"])]

                if dates2:
                    dr2 = parse_dates(dates2)
                    sys2 = load_system(conn, dataset_obj, local_id, dr2, filter_vals, limit)
                    formatted2 = [{"types": t, "counts": c} for t, c in zip(sys2["types"], sys2["counts"])]
                    key1 = dr1[0] if dr1[0] == dr1[1] else f"{dr1[0]}{range_sep}{dr1[1]}"
                    key2 = dr2[0] if dr2[0] == dr2[1] else f"{dr2[0]}{range_sep}{dr2[1]}"
                    return {key1: formatted1, key2: formatted2, "metadata": metadata}

                return {"data": formatted1, "metadata": metadata}

    return await run_blocking(_query)
