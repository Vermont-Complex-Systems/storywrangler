"""
Bluesky endpoints — per-term n-gram time series.

Same two-dataset layout as reddit: `bluesky/ngrams` is a date-sharded dist
tree (hive levels n / lang / year / month, `date` inside the files) and
`bluesky/sparklines` is a term-bucketed precompute (n / lang / ngram_bucket).
Term-series takes the fast path — a hash-bucket point lookup on the sparkline
tree (~tens of ms) — and falls back to a year-pruned scan of the dist tree for
terms outside the precomputed vocabulary. Corpus-wide top-ngrams is served by
the generic GET /storywrangler/top-ngrams (domain=bluesky).
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


def _fetch_sparkline(conn, sparkline_obj, select_cols, terms, n, lang, date_filter, date_params) -> list:
    """Bucket-routed read from the bluesky sparkline precompute.

    Terms hash to their ngram_bucket; the matching bucket file holds every date
    for its terms, ngram-sorted, so this is a point lookup on one file instead
    of a scan of the whole dist tree. Returns [] on a missing shard, signalling
    the caller to fall back to the dist-tree scan.
    """
    return fetch_sparkline_rows(
        conn, sparkline_obj, terms,
        entity_value=None, filter_vals={"n": n, "lang": lang},
        select_cols=select_cols, date_condition=date_filter, date_params=date_params,
        label="bluesky/term-series",
    )


# ── term-series ───────────────────────────────────────────────────────────────

@router.get(
    "/term-series",
    openapi_extra={**docs.BLUESKY_TERM_SERIES, "x-dataset": "ngrams"},
)
async def term_series(
    type: str = Query(..., description="The n-gram term to look up. Case-sensitive."),
    date: Optional[str] = Query(None, description="End date (YYYY-MM-DD). Defaults to latest available."),
    window: int = Query(365, description="Number of days to look back from date. 0 = full history — cheap on the sparkline fast path, slow if it falls back to the dist-tree scan."),
    lang: str = Query("en", description="Language code (hive `lang` partition)."),
    n: int = Query(1, description="N-gram size (1 = unigrams, 2 = bigrams)"),
    weight: Optional[str] = Query(None, description=_WEIGHT_DESC),
    sparkline_dataset: str = Query("sparklines", description="Registry dataset_id for the precomputed term-bucketed sparklines (default: 'sparklines'). Empty falls back to the dist-tree scan."),
    db: AsyncSession = Depends(get_session),
):
    """Per-date time series for a single n-gram term.

    Returns counts, rank, and frequency under the chosen weight for each date.

    **Fast path**: point lookup on the term's hash bucket in the sparkline
    precompute (~tens of ms). **Slow fallback**: year-pruned scan of the dist
    tree for terms outside the precomputed vocabulary (or when no sparkline
    dataset is registered).
    """
    ngrams_obj = await get_latest_entry(db, "bluesky", "ngrams")
    if not ngrams_obj:
        raise HTTPException(status_code=404, detail="'bluesky/ngrams' dataset not found")

    select_cols = _series_cols(ngrams_obj, weight)
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
        sparkline_obj = await get_latest_entry(db, "bluesky", sparkline_dataset)
    if sparkline_obj:
        def _fast():
            with get_duckdb_client().timed_connect() as conn:
                return _fetch_sparkline(conn, sparkline_obj, select_cols, [type], n, lang,
                                        date_filter, date_params)
        with timed("fast_query", "sparkline bucket read"):
            series_rows = await run_blocking(_fast)

    # ── Slow fallback: dist-tree scan ──
    if not series_rows:
        year_filter, year_params = year_pruning(date_params)
        glob_pattern = f"{base_path}/*.parquet"

        def _slow():
            with handle_query_error("bluesky/ngrams"):
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
    window: int = Query(365, description="Number of days to look back from date. 0 = full history — cheap on the sparkline fast path, slow if it falls back to the dist-tree scan."),
    lang: str = Query("en", description="Language code (hive `lang` partition)."),
    n: int = Query(1, description="N-gram size (1 = unigrams, 2 = bigrams)"),
    weight: Optional[str] = Query(None, description=_WEIGHT_DESC),
    sparkline_dataset: str = Query("sparklines", description="Registry dataset_id for the precomputed term-bucketed sparklines (default: 'sparklines'). Empty falls back to the dist-tree scan."),
    db: AsyncSession = Depends(get_session),
):
    """Batch time series lookup for multiple terms in a single request.

    Returns a map of term -> time series. Ideal for fetching sparklines for all
    terms in an RTD wordshift comparison at once. Uses the sparkline precompute
    (hash-bucket point lookups) when registered; falls back to the dist-tree scan.
    """
    ngrams_obj = await get_latest_entry(db, "bluesky", "ngrams")
    if not ngrams_obj:
        raise HTTPException(status_code=404, detail="'bluesky/ngrams' dataset not found")

    select_cols = _series_cols(ngrams_obj, weight)
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
        sparkline_obj = await get_latest_entry(db, "bluesky", sparkline_dataset)
    if sparkline_obj:
        def _fast():
            with get_duckdb_client().timed_connect() as conn:
                return _fetch_sparkline(conn, sparkline_obj, select_cols, type_list, n, lang,
                                        date_filter, date_params)
        with timed("fast_query", "sparkline bucket read"):
            rows = await run_blocking(_fast)

    # ── Slow fallback: dist-tree scan ──
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
                        log.info("bluesky/term-series/batch: no partition data for %s", type_list)
                    else:
                        log.warning("bluesky/term-series/batch: partition scan failed: %s", exc)
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
