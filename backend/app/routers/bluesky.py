"""
Bluesky endpoints — per-term n-gram time series.

The bluesky/ngrams dataset is served from a term-bucketed sparkline tree
(hive levels n / lang / ngram_bucket, date inside the files): every request
is a hash-bucket point lookup, so there is no slow-scan fallback and window=0
(full history) is cheap. A top-ngrams endpoint needs a date-sharded dist tree
like reddit's — add it when the pipeline produces one.
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from ..core.database import get_session
from ..core.duckdb_client import get_duckdb_client, run_blocking
from ..core.duckdb_query import handle_query_error
from ..core.query_utils import latest_from_manifest, resolve_count_column
from ..core.registry_utils import get_latest_entry
from ..core.term_series import (
    bucket_files, build_date_filter, series_entry, validated_dims,
)
from ..core.timing import timed
from . import openapi_docs as docs

log = logging.getLogger(__name__)

router = APIRouter()

# The registered count-column menu (endpoint_schema.count_column) is the
# source of truth for valid values; core/openapi_menus.py enriches this
# description with the enumerated menu at OpenAPI build time.
_WEIGHT_DESC = "Count measure."


def _series_cols(ngrams_obj, weight) -> str:
    """SELECT columns for term-series rows under the chosen measure.

    The rank and freq companions share the measure's suffix (count → rank,
    freq; count_all → rank_all, freq_all) — bluesky ranks are per-measure,
    unlike reddit's single canonical rank. NULL when a companion is absent.
    """
    count_col = resolve_count_column(ngrams_obj, weight)
    schema = ngrams_obj.data_schema or {}
    suffix = count_col[len("count"):]
    rank_col = f"rank{suffix}"
    freq_col = f"freq{suffix}"
    if rank_col not in schema:
        rank_col = "NULL"
    if freq_col not in schema:
        freq_col = "NULL"
    return f"ngram, date, {count_col}, {rank_col}, {freq_col}"


def _fetch_series(conn, ngrams_obj, select_cols, terms, n, lang, date_filter, date_params) -> list:
    """Bucket-routed read from the term-bucketed tree.

    Terms hash to their ngram_bucket; the matching bucket file holds every
    date for its terms, ngram-sorted, so this is a point lookup on one file
    per bucket. Terms with no rows simply contribute nothing.
    """
    files = bucket_files(ngrams_obj, terms, entity_value=None, filter_vals={"n": n, "lang": lang})
    file_list = ", ".join(f"'{f}'" for f in files)
    placeholders = ", ".join(["?"] * len(terms))
    return conn.execute(
        f"SELECT {select_cols} FROM read_parquet([{file_list}]) "
        f"WHERE ngram IN ({placeholders}) AND {date_filter} ORDER BY ngram, date",
        [*terms, *date_params],
    ).fetchall()


async def _series_context(db, n: int, lang: str, weight, date: Optional[str]):
    """Shared endpoint preamble: registry lookup, validation, date defaulting.

    Returns (ngrams_obj, select_cols, latest_date, date) or an early
    JSONResponse when the language has no data to default the date from.
    """
    ngrams_obj = await get_latest_entry(db, "bluesky", "ngrams")
    if not ngrams_obj:
        raise HTTPException(status_code=404, detail="'bluesky/ngrams' dataset not found")

    select_cols = _series_cols(ngrams_obj, weight)
    validated_dims(ngrams_obj, {"n": n, "lang": lang})

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
    return ngrams_obj, select_cols, latest_date, date


# ── term-series ───────────────────────────────────────────────────────────────

@router.get(
    "/term-series",
    openapi_extra={**docs.BLUESKY_TERM_SERIES, "x-dataset": "ngrams"},
)
async def term_series(
    type: str = Query(..., description="The n-gram term to look up. Case-sensitive."),
    date: Optional[str] = Query(None, description="End date (YYYY-MM-DD). Defaults to latest available."),
    window: int = Query(365, description="Number of days to look back from date. 0 = full history (cheap here — every request is a bucket point lookup)."),
    lang: str = Query("en", description="Language code (hive `lang` partition)."),
    n: int = Query(1, description="N-gram size (1 = unigrams, 2 = bigrams)"),
    weight: Optional[str] = Query(None, description=_WEIGHT_DESC),
    db: AsyncSession = Depends(get_session),
):
    """Per-date time series for a single n-gram term.

    Returns counts, rank, and frequency under the chosen weight for each date.
    Always a hash-bucket point lookup on the term-bucketed tree (~tens of ms).
    """
    ctx = await _series_context(db, n, lang, weight, date)
    if isinstance(ctx, JSONResponse):
        return ctx
    ngrams_obj, select_cols, latest_date, date = ctx

    date_filter, date_params = build_date_filter(date, window)

    def _query():
        with handle_query_error("bluesky/ngrams"):
            with get_duckdb_client().timed_connect() as conn:
                return _fetch_series(conn, ngrams_obj, select_cols, [type], n, lang,
                                     date_filter, date_params)

    with timed("query", "sparkline bucket read"):
        series_rows = await run_blocking(_query)

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
    window: int = Query(365, description="Number of days to look back from date. 0 = full history (cheap here — every request is a bucket point lookup)."),
    lang: str = Query("en", description="Language code (hive `lang` partition)."),
    n: int = Query(1, description="N-gram size (1 = unigrams, 2 = bigrams)"),
    weight: Optional[str] = Query(None, description=_WEIGHT_DESC),
    db: AsyncSession = Depends(get_session),
):
    """Batch time series lookup for multiple terms in a single request.

    Returns a map of term -> time series. Terms with no data return empty
    arrays. Terms hashing to the same bucket share one file read.
    """
    type_list = [t.strip() for t in types.split(",") if t.strip()]
    if not type_list:
        raise HTTPException(status_code=400, detail="types parameter must contain at least one term")

    ctx = await _series_context(db, n, lang, weight, date)
    if isinstance(ctx, JSONResponse):
        return ctx
    ngrams_obj, select_cols, latest_date, date = ctx

    date_filter, date_params = build_date_filter(date, window)

    def _query():
        with handle_query_error("bluesky/ngrams"):
            with get_duckdb_client().timed_connect() as conn:
                return _fetch_series(conn, ngrams_obj, select_cols, type_list, n, lang,
                                     date_filter, date_params)

    with timed("query", "sparkline bucket read"):
        rows = await run_blocking(_query)

    results: dict = {t: [] for t in type_list}
    for row in rows:
        results[row[0]].append(series_entry(str(row[1]), row[2], row[3], row[4]))

    return {
        "results": results,
        "latest_available_date": latest_date,
    }
