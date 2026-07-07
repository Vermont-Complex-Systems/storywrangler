"""
Reddit endpoints — subreddit n-grams and term time series.
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from ..core.database import get_session
from ..core.duckdb_client import get_duckdb_client, run_blocking
from ..core.query_utils import (
    handle_query_error, is_data_missing, latest_from_manifest, resolve_entity,
)
from ..core.registry_utils import get_latest_entry
from ..core.term_series import (
    build_date_filter, fetch_sparkline_rows, ngrams_context, run_top_ngrams,
    series_entry, validated_dims,
)
from ..core.timing import timed
from . import openapi_docs as docs

log = logging.getLogger(__name__)

router = APIRouter()


# ── top-ngrams ────────────────────────────────────────────────────────────────

@router.get(
    "/top-ngrams",
    openapi_extra=docs.REDDIT_GET_TOP_NGRAMS,
)
async def get_top_ngrams(
    dates: str = Query(default="2024-11-01,2024-11-07"),
    dates2: Optional[str] = Query(default=None),
    entity: str = Query(default="AskReddit", description="Subreddit name or global entity ID"),
    granularity: str = Query(default="daily"),
    n: int = Query(default=1, description="N-gram size (1 = unigrams, 2 = bigrams)."),
    limit: int = Query(default=100),
    db: AsyncSession = Depends(get_session),
):
    """Get top Reddit n-grams for a subreddit."""
    dataset_obj = await get_latest_entry(db, "reddit", "ngrams")
    if not dataset_obj:
        raise HTTPException(status_code=404, detail="'reddit/ngrams' dataset not found")

    extra = validated_dims(dataset_obj, {"granularity": granularity, "ngram_size": n})
    em = await resolve_entity(db, "reddit", "ngrams", entity)

    return await run_top_ngrams(
        dataset_obj, "reddit/ngrams", em.local_id, dates, dates2, extra, limit,
        metadata={"granularity": granularity, "entity": entity},
    )


# ── term-series ───────────────────────────────────────────────────────────────

@router.get(
    "/term-series",
    openapi_extra=docs.REDDIT_TERM_SERIES,
)
async def term_series(
    type: str = Query(..., description="The n-gram term to look up. Case-sensitive."),
    entity: Optional[str] = Query(None, description="Entity ID (optional). When omitted, no entity filtering is applied."),
    date: Optional[str] = Query(None, description="End date (YYYY-MM-DD). Defaults to latest available."),
    window: int = Query(0, description="Number of days to look back from date. 0 = full history."),
    granularity: str = Query("daily", description="Hive granularity: daily | weekly | monthly"),
    n: int = Query(1, description="N-gram size (1 = unigrams, 2 = bigrams)"),
    db: AsyncSession = Depends(get_session),
):
    """Per-date time series for a single n-gram term.

    Returns counts and rank for each date.
    Entity is optional — when omitted, queries across all entities.
    """
    with timed("resolve", "Entity resolution"):
        ngrams_obj = await get_latest_entry(db, "reddit", "ngrams")
        if not ngrams_obj:
            raise HTTPException(status_code=404, detail="'reddit/ngrams' dataset not found")
        local_id = None
        if entity:
            local_id = (await resolve_entity(db, "reddit", "ngrams", entity)).local_id

    _, base_path = ngrams_context(
        ngrams_obj, local_id, {"granularity": granularity, "ngram_size": n})

    with timed("discover", "Latest date from manifest"):
        latest_date = latest_from_manifest(ngrams_obj, local_id, granularity)

    if not date:
        if not latest_date:
            return JSONResponse(
                status_code=404,
                content={"detail": "No data found for this entity", "latest_available_date": None},
            )
        date = latest_date

    date_filter, date_params = build_date_filter(date, window)

    # ── Sparkline fast path (when sparklines dataset is registered) ──
    series_rows = []
    with timed("registry", "Sparkline registry lookup"):
        sparkline_obj = await get_latest_entry(db, "reddit", "sparklines")

    if sparkline_obj:
        def _fast():
            with get_duckdb_client().timed_connect() as conn:
                return fetch_sparkline_rows(
                    conn, sparkline_obj, [type], local_id, n,
                    date_filter, date_params, "reddit/term-series",
                )

        with timed("fast_query", "DuckDB sparkline read"):
            series_rows = await run_blocking(_fast)

    # ── Slow path: scan daily partitions ──
    if not series_rows:
        glob_pattern = f"{base_path}/date=*/data_0.parquet"

        def _slow():
            with handle_query_error("reddit/ngrams"):
                with get_duckdb_client().timed_connect() as conn:
                    return conn.execute(
                        f"""
                        SELECT ngram, date, pv_count, pv_rank, pv_freq
                        FROM read_parquet('{glob_pattern}', hive_partitioning=true)
                        WHERE ngram = ? AND {date_filter}
                        ORDER BY date
                        """,
                        [type, *date_params],
                    ).fetchall()

        with timed("slow_query", "DuckDB daily partition scan"):
            series_rows = await run_blocking(_slow)

    return {
        "type": type,
        "latest_available_date": latest_date,
        "series": [series_entry(str(row[1]), row[2], row[3], row[4]) for row in series_rows],
    }


# ── term-series/batch ────────────────────────────────────────────────────────

@router.get("/term-series/batch")
async def term_series_batch(
    types: str = Query(..., description="Comma-separated n-gram terms, e.g. 'trump,covid,the'. Case-sensitive."),
    entity: Optional[str] = Query(None, description="Entity ID (optional). When omitted, no entity filtering is applied."),
    date: Optional[str] = Query(None, description="End date (YYYY-MM-DD). Defaults to latest available."),
    window: int = Query(0, description="Number of days to look back from date. 0 = full history."),
    granularity: str = Query("daily", description="Hive granularity: daily | weekly | monthly"),
    n: int = Query(1, description="N-gram size (1 = unigrams, 2 = bigrams)"),
    db: AsyncSession = Depends(get_session),
):
    """Batch time series lookup for multiple terms in a single request.

    Returns a map of term -> time series. Ideal for fetching sparklines for all
    terms in an RTD wordshift comparison at once.

    Entity is optional — when omitted, queries across all entities.
    """
    ngrams_obj = await get_latest_entry(db, "reddit", "ngrams")
    if not ngrams_obj:
        raise HTTPException(status_code=404, detail="'reddit/ngrams' dataset not found")

    local_id = None
    if entity:
        local_id = (await resolve_entity(db, "reddit", "ngrams", entity)).local_id

    _, base_path = ngrams_context(
        ngrams_obj, local_id, {"granularity": granularity, "ngram_size": n})
    latest_date = latest_from_manifest(ngrams_obj, local_id, granularity)

    if not date:
        if not latest_date:
            return JSONResponse(
                status_code=404,
                content={"detail": "No data found for this entity", "latest_available_date": None},
            )
        date = latest_date

    date_filter, date_params = build_date_filter(date, window)

    type_list = [t.strip() for t in types.split(",") if t.strip()]
    if not type_list:
        raise HTTPException(status_code=400, detail="types parameter must contain at least one term")

    # ── Fast path: sparkline bucket lookups ──
    sparkline_rows = []
    sparkline_obj = await get_latest_entry(db, "reddit", "sparklines")

    if sparkline_obj:
        def _fast():
            with get_duckdb_client().timed_connect() as conn:
                return fetch_sparkline_rows(
                    conn, sparkline_obj, type_list, local_id, n,
                    date_filter, date_params, "reddit/term-series/batch",
                )

        with timed("fast_query", "DuckDB sparkline batch read"):
            sparkline_rows = await run_blocking(_fast)

    found_terms = {row[0] for row in sparkline_rows}

    # ── Slow path: daily partition fallback for missing terms ──
    missing_terms = [t for t in type_list if t not in found_terms]
    slow_results: dict = {}
    if missing_terms:
        glob_pattern = f"{base_path}/date=*/data_0.parquet"
        slow_placeholders = ", ".join(["?"] * len(missing_terms))

        def _slow():
            with get_duckdb_client().timed_connect() as conn:
                try:
                    return conn.execute(
                        f"""
                        SELECT ngram, date, pv_count, pv_rank, pv_freq
                        FROM read_parquet('{glob_pattern}', hive_partitioning=true)
                        WHERE ngram IN ({slow_placeholders})
                          AND {date_filter}
                        ORDER BY ngram, date
                        """,
                        [*missing_terms, *date_params],
                    ).fetchall()
                except Exception as exc:
                    # Batch semantics: terms with no data return empty arrays,
                    # so a missing partition is fine — but log real errors.
                    if is_data_missing(exc):
                        log.info("reddit/term-series/batch: no partition data for %s", missing_terms)
                    else:
                        log.warning("reddit/term-series/batch: partition scan failed: %s", exc)
                    return []

        with timed("slow_query", "DuckDB daily partition scan"):
            slow_rows = await run_blocking(_slow)

        for row in slow_rows:
            slow_results.setdefault(row[0], []).append(
                series_entry(str(row[1]), row[2], row[3], row[4]))

    # ── Merge results ──
    results: dict = {t: [] for t in type_list}
    for row in sparkline_rows:
        results[row[0]].append(series_entry(str(row[1]), row[2], row[3], row[4]))
    for ngram, entries in slow_results.items():
        results[ngram] = entries

    return {
        "results": results,
        "latest_available_date": latest_date,
    }
