"""Reads over type-first (hash-bucketed) datasets.

A type-first dataset shards its rows by term: ``assign_bucket(term)`` names
the one hive directory holding a term's entire history, so a lookup reads one
bucket file instead of scanning a date-partitioned tree. Two dataset kinds
are read this way:

  - types-counts sparklines (``orientation: type-first``) — the term-series
    fast path, whether a companion resolved from lineage or the queried
    dataset itself;
  - type-documents provenance sets (``?include=``) — ranked source documents
    per (type, date).

Both reads share one shape (`_bucket_read`): glob the buckets that can hold
the terms, filter by type + date, and classify failures — a missing shard is
an expected empty, anything else is either logged (when a scan fallback
exists) or re-raised (``strict=True``, when this read is the only read).
"""

import logging
from typing import List, Optional

from .duckdb_query import (
    assign_bucket, bucket_override_key, build_hive_path, get_bucket_config,
    is_data_missing, resolve_bucket_count,
)

log = logging.getLogger(__name__)


def log_fast_path_miss(label: str, exc: Exception) -> None:
    """Classify a bucket-read failure before the caller falls back to a scan."""
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
    partition-level values, *entity_value* the entity level when one exists.
    Each bucket is globbed with ``/*.parquet`` — never a pinned filename:
    DuckLake-backed buckets hold several uniquely-named
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


def _bucket_read(
    conn, dataset_obj, terms: List[str], *, entity_value, filter_vals: dict,
    select_cols: str, date_condition: str, date_params: list, label: str,
    type_col: str, time_col: str, order_extra: Optional[str] = None,
    strict: bool = False,
) -> list:
    """Bucket-routed read shared by the sparkline and provenance lookups.

    Selects *select_cols* from the buckets that can hold *terms*, filtered by
    type + *date_condition*, ordered by (type, time) plus *order_extra*.
    Returns rows — or [] with a classified log line on failure.

    *strict* is for reads with no fallback behind them (a type-first dataset
    serving itself): a missing shard still yields [], but any other failure
    re-raises so the caller's handle_query_error classifies it as 504/500
    instead of it reading as "no data".
    """
    files = bucket_files(dataset_obj, terms, entity_value=entity_value, filter_vals=filter_vals)
    file_list = ", ".join(f"'{f}'" for f in files)
    placeholders = ", ".join(["?"] * len(terms))
    order_by = f"{type_col}, {time_col}" + (f", {order_extra}" if order_extra else "")
    try:
        return conn.execute(
            f"""
            SELECT {select_cols}
            FROM read_parquet([{file_list}])
            WHERE {type_col} IN ({placeholders})
              AND {date_condition}
            ORDER BY {order_by}
            """,
            [*terms, *date_params],
        ).fetchall()
    except Exception as exc:
        if strict and not is_data_missing(exc):
            raise
        log_fast_path_miss(label, exc)
        return []


def fetch_sparkline_rows(
    conn, sparkline_obj, terms: List[str],
    *, entity_value, filter_vals: dict, select_cols: str,
    date_condition: str, date_params: list, label: str,
    type_col: str = "ngram", time_col: str = "date",
    strict: bool = False,
) -> list:
    """Bucket-routed sparkline lookup for *terms*.

    *select_cols* is the caller's SELECT list (the primary's registered
    count/rank/freq columns — sparkline files mirror them); *type_col* /
    *time_col* are the registered type/time columns. Rows come back ordered
    by (type, time), or [] with a classified log line on failure.
    """
    return _bucket_read(
        conn, sparkline_obj, terms, entity_value=entity_value, filter_vals=filter_vals,
        select_cols=select_cols, date_condition=date_condition, date_params=date_params,
        label=label, type_col=type_col, time_col=time_col, strict=strict,
    )


def fetch_provenance(
    conn, prov_obj, terms: List[str],
    *, entity_value, filter_vals: dict,
    date_condition: str, date_params: list, label: str,
    time_col: str = "date",
) -> dict:
    """Ranked source documents per (type, date) for *terms* — the ?include= read.

    Reads a type-documents dataset (doc/score/order columns from its own
    endpoint_schema) and returns ``{(type, date): [[document, score], ...]}``
    ordered by the declared order_column (default: score descending). Missing
    files or an undeclared doc/score column yield ``{}``.
    """
    ep = prov_obj.endpoint_schema or {}
    type_col = ep.get("type_column") or "ngram"
    doc_col = ep.get("doc_column")
    score_col = ep.get("score_column")
    if not doc_col or not score_col:
        return {}
    order_by = ep.get("order_column") or f"{score_col} DESC"

    rows = _bucket_read(
        conn, prov_obj, sorted(terms), entity_value=entity_value, filter_vals=filter_vals,
        select_cols=f"{type_col}, {time_col}, {doc_col}, {score_col}",
        date_condition=date_condition, date_params=date_params, label=label,
        type_col=type_col, time_col=time_col, order_extra=order_by,
    )
    out: dict = {}
    for term, dt, doc, score in rows:
        out.setdefault((term, str(dt)), []).append([doc, float(score) if score else 0.0])
    return out
