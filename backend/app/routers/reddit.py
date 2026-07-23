"""
Reddit endpoints — corpus-wide n-grams and term time series.

The reddit/ngrams dataset has no entity dimension: hive levels are
n / lang / year / month, and `date` lives inside the parquet files.
Queries slice by language and n-gram size and compare across dates.
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from ..core.database import get_session
from ..core.duckdb_client import get_duckdb_client, run_blocking
from ..core.duckdb_query import handle_query_error, is_data_missing
from ..core.query_utils import latest_from_manifest, resolve_count_column
from ..core.registry_utils import get_latest_entry
from ..core.term_series import (
    build_date_filter, fetch_sparkline_rows, ngrams_context, series_entry,
    validated_dims, year_pruning,
)
from ..core.timing import timed
from . import openapi_docs as docs

log = logging.getLogger(__name__)

router = APIRouter()

# The registered count-column menu (endpoint_schema.count_column) is the
# source of truth for valid values; core/openapi_menus.py enriches this
# description with the enumerated menu at OpenAPI build time.
_WEIGHT_DESC = "Count measure (content type × weighting)."


def _series_cols(ngrams_obj, weight) -> tuple:
    """SELECT columns for term-series rows under the chosen measure.

    Returns (select_expr, count_col). The frequency companion follows the
    dataset's naming convention ({x}_weighted → {x}_freq, else {col}_freq);
    NULL when no such column exists. `rank` is the pipeline's canonical
    ranking (score-weighted) and does not change with the measure.
    """
    count_col = resolve_count_column(ngrams_obj, weight)
    schema = ngrams_obj.data_schema or {}
    if count_col.endswith("_weighted"):
        freq_col = count_col[: -len("_weighted")] + "_freq"
    else:
        freq_col = f"{count_col}_freq"
    if freq_col not in schema:
        freq_col = "NULL"
    return f"ngram, date, {count_col}, rank, {freq_col}", count_col


def _fetch_sparkline(conn, sparkline_obj, select_cols, terms, n, lang, date_filter, date_params) -> list:
    """Bucket-routed read from the reddit sparkline precompute.

    Terms hash to their ngram_bucket; the matching bucket file holds every date
    for its terms, ngram-sorted, so this is a point lookup on one file instead
    of a scan of the whole weekly tree. No year pruning — the precompute is not
    year-partitioned (date is an in-file column). Returns [] on a missing shard,
    signalling the caller to fall back to the raw-tree scan.
    """
    return fetch_sparkline_rows(
        conn, sparkline_obj, terms,
        entity_value=None, filter_vals={"n": n, "lang": lang},
        select_cols=select_cols, date_condition=date_filter, date_params=date_params,
        label="reddit/term-series",
    )


# ── term-series ───────────────────────────────────────────────────────────────

@router.get(
    "/term-series",
    openapi_extra={**docs.REDDIT_TERM_SERIES, "x-dataset": "ngrams"},
)
async def term_series(
    type: str = Query(..., description="The n-gram term to look up. Case-sensitive."),
    date: Optional[str] = Query(None, description="End date (YYYY-MM-DD). Defaults to latest available."),
    window: int = Query(365, description="Number of days to look back from date. 0 = full history — slow (scans every weekly file, minutes for large languages) and likely to exceed the proxy timeout."),
    lang: str = Query("en", description="Language code (hive `lang` partition)."),
    n: int = Query(1, description="N-gram size (1 = unigrams, 2 = bigrams)"),
    weight: Optional[str] = Query(None, description=_WEIGHT_DESC),
    sparkline_dataset: str = Query("sparklines", description="Registry dataset_id for the precomputed term-bucketed sparklines (default: 'sparklines'). Empty falls back to the raw-tree scan."),
    db: AsyncSession = Depends(get_session),
):
    """Per-date time series for a single n-gram term.

    Returns counts under the chosen weight, canonical rank, and frequency
    for each date.

    **Fast path**: point lookup on the term's hash bucket in the sparkline
    precompute (~tens of ms). **Slow fallback**: scan of the raw weekly tree
    when no sparkline dataset is registered.
    """
    ngrams_obj = await get_latest_entry(db, "reddit", "ngrams")
    if not ngrams_obj:
        raise HTTPException(status_code=404, detail="'reddit/ngrams' dataset not found")

    select_cols, _ = _series_cols(ngrams_obj, weight)
    dims = validated_dims(ngrams_obj, {"n": n, "lang": lang})
    _, base_path = ngrams_context(ngrams_obj, None, dims)

    with timed("discover", "Latest date from manifest"):
        # Availability is keyed n → lang; lang is the preferred lookup key.
        latest_date = latest_from_manifest(ngrams_obj, None, lang)

    if not date:
        if not latest_date:
            return JSONResponse(
                status_code=404,
                content={"detail": "No data found for this language", "latest_available_date": None},
            )
        date = latest_date

    date_filter, date_params = build_date_filter(date, window)

    # ── Fast path: bucket lookup on the sparkline precompute ──
    series_rows = []
    with timed("registry", "Sparkline registry lookup"):
        sparkline_obj = await get_latest_entry(db, "reddit", sparkline_dataset)
    if sparkline_obj:
        def _fast():
            with get_duckdb_client().timed_connect() as conn:
                return _fetch_sparkline(conn, sparkline_obj, select_cols, [type], n, lang,
                                        date_filter, date_params)
        with timed("fast_query", "sparkline bucket read"):
            series_rows = await run_blocking(_fast)

    # ── Slow fallback: raw weekly-tree scan ──
    if not series_rows:
        year_filter, year_params = year_pruning(date_params)
        glob_pattern = f"{base_path}/*.parquet"

        def _slow():
            with handle_query_error("reddit/ngrams"):
                with get_duckdb_client().timed_connect() as conn:
                    return conn.execute(
                        f"""
                        SELECT {select_cols}
                        FROM read_parquet('{glob_pattern}', hive_partitioning=true)
                        WHERE ngram = ? AND {date_filter} AND {year_filter}
                        ORDER BY date
                        """,
                        [type, *date_params, *year_params],
                    ).fetchall()

        with timed("slow_query", "DuckDB partition scan"):
            series_rows = await run_blocking(_slow)

    return {
        "type": type,
        "latest_available_date": latest_date,
        "series": [series_entry(str(row[1]), row[2], row[3], row[4]) for row in series_rows],
    }


# ── term-series/batch ────────────────────────────────────────────────────────

@router.get("/term-series/batch", openapi_extra={"x-dataset": "ngrams"})
async def term_series_batch(
    types: str = Query(..., description="Comma-separated n-gram terms, e.g. 'trump,covid,the'. Case-sensitive."),
    date: Optional[str] = Query(None, description="End date (YYYY-MM-DD). Defaults to latest available."),
    window: int = Query(365, description="Number of days to look back from date. 0 = full history — slow (scans every weekly file, minutes for large languages) and likely to exceed the proxy timeout."),
    lang: str = Query("en", description="Language code (hive `lang` partition)."),
    n: int = Query(1, description="N-gram size (1 = unigrams, 2 = bigrams)"),
    weight: Optional[str] = Query(None, description=_WEIGHT_DESC),
    sparkline_dataset: str = Query("sparklines", description="Registry dataset_id for the precomputed term-bucketed sparklines (default: 'sparklines'). Empty falls back to the raw-tree scan."),
    db: AsyncSession = Depends(get_session),
):
    """Batch time series lookup for multiple terms in a single request.

    Returns a map of term -> time series. Ideal for fetching sparklines for all
    terms in an RTD wordshift comparison at once. Uses the sparkline precompute
    (hash-bucket point lookups) when registered; falls back to the raw-tree scan.
    """
    ngrams_obj = await get_latest_entry(db, "reddit", "ngrams")
    if not ngrams_obj:
        raise HTTPException(status_code=404, detail="'reddit/ngrams' dataset not found")

    select_cols, _ = _series_cols(ngrams_obj, weight)
    dims = validated_dims(ngrams_obj, {"n": n, "lang": lang})
    _, base_path = ngrams_context(ngrams_obj, None, dims)
    latest_date = latest_from_manifest(ngrams_obj, None, lang)

    if not date:
        if not latest_date:
            return JSONResponse(
                status_code=404,
                content={"detail": "No data found for this language", "latest_available_date": None},
            )
        date = latest_date

    date_filter, date_params = build_date_filter(date, window)

    type_list = [t.strip() for t in types.split(",") if t.strip()]
    if not type_list:
        raise HTTPException(status_code=400, detail="types parameter must contain at least one term")

    # ── Fast path: bucket lookups on the sparkline precompute ──
    rows = []
    with timed("registry", "Sparkline registry lookup"):
        sparkline_obj = await get_latest_entry(db, "reddit", sparkline_dataset)
    if sparkline_obj:
        def _fast():
            with get_duckdb_client().timed_connect() as conn:
                return _fetch_sparkline(conn, sparkline_obj, select_cols, type_list, n, lang,
                                        date_filter, date_params)
        with timed("fast_query", "sparkline bucket read"):
            rows = await run_blocking(_fast)

    # ── Slow fallback: raw weekly-tree scan ──
    if not rows:
        year_filter, year_params = year_pruning(date_params)
        glob_pattern = f"{base_path}/*.parquet"
        placeholders = ", ".join(["?"] * len(type_list))

        def _slow():
            with get_duckdb_client().timed_connect() as conn:
                try:
                    return conn.execute(
                        f"""
                        SELECT {select_cols}
                        FROM read_parquet('{glob_pattern}', hive_partitioning=true)
                        WHERE ngram IN ({placeholders})
                          AND {date_filter} AND {year_filter}
                        ORDER BY ngram, date
                        """,
                        [*type_list, *date_params, *year_params],
                    ).fetchall()
                except Exception as exc:
                    # Batch semantics: terms with no data return empty arrays,
                    # so a missing partition is fine — but log real errors.
                    if is_data_missing(exc):
                        log.info("reddit/term-series/batch: no partition data for %s", type_list)
                    else:
                        log.warning("reddit/term-series/batch: partition scan failed: %s", exc)
                    return []

        with timed("slow_query", "DuckDB partition scan"):
            rows = await run_blocking(_slow)

    results: dict = {t: [] for t in type_list}
    for row in rows:
        results[row[0]].append(series_entry(str(row[1]), row[2], row[3], row[4]))

    return {
        "results": results,
        "latest_available_date": latest_date,
    }
