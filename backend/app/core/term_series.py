"""Shared helpers for sparkline-backed domain routers (wikimedia, reddit, bluesky).

These routers expose the same term-series endpoint family over hive-partitioned
ngram datasets with precomputed, hash-bucket-sharded sparkline files (and, for
reddit/bluesky, a date-sharded dist tree for the slow fallback). Everything that
is not genuinely domain-specific lives here:

  validated_dims()        — validate query params against introspected filter_values
  ngrams_context()        — (filter_vals, entity base path) for partition scans
  build_date_filter()     — date/window → SQL condition + params
  year_pruning()          — prune year=* dist-tree dirs from an in-file date filter
  series_entry()          — one time-series response row
  log_fast_path_miss()    — classify a sparkline failure before scan fallback
  fetch_sparkline_rows()  — bucket-routed sparkline lookup for a set of terms
  fetch_provenance()      — bucket-routed source-document lookup (?include=)
  run_top_ngrams()        — the full top-ngrams endpoint body (off the event loop)
"""

import logging
from datetime import date as dt_date, datetime, timedelta
from typing import List, Optional

from fastapi import HTTPException

from .duckdb_client import get_duckdb_client, run_blocking
from .duckdb_query import (
    assign_bucket, bucket_override_key, build_hive_path, entity_base_path,
    get_bucket_config, handle_query_error, is_data_missing, load_system,
    resolve_bucket_count,
)
from .query_utils import get_queryable_dims, latest_from_manifest, parse_dates

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


def latest_series_date(
    ngrams_obj, sparkline_obj, local_id, granularity: str, n: int,
) -> Optional[str]:
    """Latest available date for term-series defaults and responses.

    Takes the max across the ngrams and sparkline manifests: the two are
    built by separate pipelines, so either can run ahead of the other
    (e.g. DuckLake sparklines update nightly while the raw ngrams sync
    lags). Sparkline data is daily-only, so its manifest — keyed by
    entity → ngram_size — only participates for daily requests.
    """
    candidates = [latest_from_manifest(ngrams_obj, local_id, granularity)]
    if sparkline_obj and granularity == "daily":
        candidates.append(latest_from_manifest(sparkline_obj, local_id, str(n)))
    dates = [d for d in candidates if d]
    return max(dates) if dates else None


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


def bucket_files(dataset_obj, terms, *, entity_value=None, filter_vals=None) -> List[str]:
    """Glob paths of the hash-bucket directories that can contain *terms*.

    Generic over the dataset's level layout: *filter_vals* holds the
    partition-level values ({"ngram_size": 1} for wikimedia, {"n": 1,
    "lang": "en"} for reddit), *entity_value* the entity level when one
    exists. Each bucket is globbed with ``/*.parquet`` — never a pinned
    filename: DuckLake-backed buckets hold several uniquely-named
    ``ducklake-<uuid>.parquet`` files whose set changes on every compaction.
    """
    hb = get_bucket_config(dataset_obj)
    key = bucket_override_key(dataset_obj, entity_value=entity_value, filter_vals=filter_vals)
    n_buckets = resolve_bucket_count(hb, key)
    buckets = {assign_bucket(t, n_buckets) for t in terms}
    return [
        build_hive_path(
            dataset_obj,
            filter_vals=filter_vals,
            entity_value=entity_value,
            bucket_value=b,
            glob_suffix="/*.parquet",
        )
        for b in sorted(buckets)
    ]


def year_pruning(date_params: list) -> tuple:
    """Prune year=* hive directories from an in-file date filter's bounds.

    For dist trees whose ``date`` column lives inside the files while
    ``year`` is a hive partition (reddit, bluesky): this condition lets
    DuckDB drop whole year directories from directory names alone, without
    reading file footers. Bounds are padded by one week so weekly files
    bucketed under the year their ISO week starts in stay reachable (a
    no-op for daily trees).
    """
    pad = timedelta(days=6)
    bounds = [dt_date.fromisoformat(str(p)[:10]) for p in date_params]
    if len(bounds) == 2:
        return "year BETWEEN ? AND ?", [(bounds[0] - pad).year, (bounds[1] + pad).year]
    return "year <= ?", [(bounds[0] + pad).year]


def fetch_sparkline_rows(
    conn, sparkline_obj, terms: List[str],
    *, entity_value, filter_vals: dict, select_cols: str,
    date_condition: str, date_params: list, label: str,
) -> list:
    """Bucket-routed sparkline lookup for *terms*.

    Generic over the dataset's layout: *filter_vals* holds the partition
    values ({"ngram_size": n} for wikimedia, {"n": n, "lang": lang} for
    reddit/bluesky), *entity_value* the entity level when one exists, and
    *select_cols* the SELECT list (columns vary per domain: pv_* for
    wikimedia, count/rank/freq for reddit/bluesky). Rows come back ordered
    by ngram, date — or [] with a classified log line on failure (missing
    sparkline files are expected; anything else is a warning).
    """
    files = bucket_files(sparkline_obj, terms, entity_value=entity_value, filter_vals=filter_vals)
    file_list = ", ".join(f"'{f}'" for f in files)
    placeholders = ", ".join(["?"] * len(terms))
    try:
        return conn.execute(
            f"""
            SELECT {select_cols}
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


def fetch_provenance(
    conn, prov_obj, terms: List[str],
    *, entity_value, filter_vals: dict,
    date_condition: str, date_params: list, label: str,
) -> dict:
    """Ranked source documents per (type, date) for *terms* — the include=.

    Reads a type-documents provenance dataset (doc/score/order columns from its
    endpoint_schema) via the same hash-bucket routing as the sparklines, and
    returns ``{(type, date): [[document, score], ...]}`` ordered by the declared
    order_column (or score descending). Missing files or an undeclared doc/score
    column yield ``{}`` (a classified log line, same as the sparkline path).
    """
    ep = prov_obj.endpoint_schema or {}
    type_col = ep.get("type_column") or "ngram"
    doc_col = ep.get("doc_column")
    score_col = ep.get("score_column")
    if not doc_col or not score_col:
        return {}
    order_by = ep.get("order_column") or f"{score_col} DESC"

    terms = sorted(terms)
    files = bucket_files(prov_obj, terms, entity_value=entity_value, filter_vals=filter_vals)
    file_list = ", ".join(f"'{f}'" for f in files)
    placeholders = ", ".join(["?"] * len(terms))
    try:
        rows = conn.execute(
            f"""
            SELECT {type_col}, date, {doc_col}, {score_col}
            FROM read_parquet([{file_list}])
            WHERE {type_col} IN ({placeholders})
              AND {date_condition}
            ORDER BY {type_col}, date, {order_by}
            """,
            [*terms, *date_params],
        ).fetchall()
    except Exception as exc:
        log_fast_path_miss(label, exc)
        return {}

    out: dict = {}
    for term, dt, doc, score in rows:
        out.setdefault((term, str(dt)), []).append([doc, float(score) if score else 0.0])
    return out


async def run_top_ngrams(
    dataset_obj,
    label: str,
    local_id: Optional[str],
    dates: Optional[str],
    dates2: Optional[str],
    filter_vals: dict,
    limit: int,
    metadata: dict,
    count_col: Optional[str] = None,
) -> dict:
    """The generic top-ngrams endpoint body, executed off the event loop.

    Loads one types-counts system (or two for a temporal comparison keyed
    by date range, start/end joined with "_") and formats the response.
    *dates* may be None for all-time / dateless datasets. *count_col*
    selects a measure from the registered count-column menu (resolve via
    resolve_count_column); None uses the dataset default.
    """
    if dates2 and parse_dates(dates) == parse_dates(dates2):
        # Identical ranges collide into one JSON key and silently drop system 1
        # — reject rather than return half the comparison with HTTP 200.
        raise HTTPException(
            status_code=400,
            detail="dates and dates2 resolve to the same range; "
                   "use different dates to compare two systems.",
        )

    def _query():
        with handle_query_error(label):
            with get_duckdb_client().timed_connect() as conn:
                dr1 = parse_dates(dates)
                sys1 = load_system(conn, dataset_obj, local_id, dr1, filter_vals, limit, count_col=count_col)
                formatted1 = [{"types": t, "counts": c} for t, c in zip(sys1["types"], sys1["counts"])]

                if dates2:
                    dr2 = parse_dates(dates2)
                    sys2 = load_system(conn, dataset_obj, local_id, dr2, filter_vals, limit, count_col=count_col)
                    formatted2 = [{"types": t, "counts": c} for t, c in zip(sys2["types"], sys2["counts"])]
                    key1 = dr1[0] if dr1[0] == dr1[1] else f"{dr1[0]}_{dr1[1]}"
                    key2 = dr2[0] if dr2[0] == dr2[1] else f"{dr2[0]}_{dr2[1]}"
                    return {key1: formatted1, key2: formatted2, "metadata": metadata}

                return {"data": formatted1, "metadata": metadata}

    return await run_blocking(_query)
