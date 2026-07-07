"""
Wikimedia endpoints — Wikipedia n-grams, revision histories, and term time series.
"""

import logging
from typing import Optional
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from ..core.database import get_session
from ..core.duckdb_client import get_duckdb_client, run_blocking
from ..core.query_utils import (
    build_hive_path, handle_query_error, is_data_missing, latest_from_manifest,
    resolve_entity,
)
from ..core.registry_utils import get_latest_entry
from ..core.term_series import (
    bucket_files, build_date_filter, fetch_sparkline_rows, log_fast_path_miss,
    ngrams_context, run_top_ngrams, series_entry, validated_dims,
)
from ..core.timing import timed
from . import openapi_docs as docs

log = logging.getLogger(__name__)

router = APIRouter()


def _fetch_top_articles(
    conn, top_articles_obj, terms, local_id, n, date_condition, date_params,
) -> dict:
    """Fetch top contributing articles for *terms*.

    Returns ``{(ngram, date_str): [[url, score], ...]}``, reading only the
    hash-bucket files that can contain the requested terms.

    Missing article files are expected (the dataset may not be materialised
    yet) and yield an empty dict. Any other failure is logged: a silently
    empty result usually means a stale hash_bucket config routing to the
    wrong shard, which is indistinguishable from "no data" without a log line.
    """
    if not top_articles_obj or not terms:
        return {}
    terms = sorted(terms)
    files = bucket_files(top_articles_obj, terms, local_id, n)
    file_list = ", ".join(f"'{f}'" for f in files)
    placeholders = ", ".join(["?"] * len(terms))
    try:
        rows = conn.execute(
            f"""
            SELECT ngram, date, article_url, score
            FROM read_parquet([{file_list}])
            WHERE ngram IN ({placeholders})
              AND {date_condition}
            ORDER BY ngram, date, article_rank
            """,
            [*terms, *date_params],
        ).fetchall()
    except Exception as exc:
        if is_data_missing(exc):
            log.info(
                "top_articles files missing for entity=%s n=%s; returning no articles",
                local_id, n,
            )
        else:
            log.warning(
                "top_articles lookup failed for entity=%s n=%s "
                "(check hash_bucket config vs on-disk shards): %s",
                local_id, n, exc,
            )
        return {}

    articles: dict = {}
    for ngram, dt, url, score in rows:
        articles.setdefault((ngram, str(dt)), []).append(
            [url, float(score) if score else 0.0]
        )
    return articles


# ── top-ngrams ─────────────────────────────────────────────────────────────────

@router.get(
    "/top-ngrams",
    openapi_extra=docs.WIKIMEDIA_GET_TOP_NGRAMS,
)
async def get_top_ngrams(
    dates: str = Query(default="2024-11-01,2024-11-07"),
    dates2: Optional[str] = Query(default=None),
    locations: str = Query(default="wikidata:Q30", description="Entity ID (e.g. 'wikidata:Q30') or local ID (e.g. 'en')"),
    granularity: str = Query(default="daily"),
    n: int = Query(default=1, description="N-gram size (1 = unigrams, 2 = bigrams). Only used when endpoint_schema.ngram_sizes is set."),
    limit: int = Query(default=100),
    db: AsyncSession = Depends(get_session),
):
    """Get top Wikipedia n-grams."""
    dataset_obj = await get_latest_entry(db, "wikimedia", "ngrams")
    if not dataset_obj:
        raise HTTPException(status_code=404, detail="'wikimedia/ngrams' dataset not found")

    extra = validated_dims(dataset_obj, {"granularity": granularity, "ngram_size": n})
    em = await resolve_entity(db, "wikimedia", "ngrams", locations)

    return await run_top_ngrams(
        dataset_obj, "wikimedia/ngrams", em.local_id, dates, dates2, extra, limit,
        metadata={"granularity": granularity, "location": locations},
    )


# ── revisions ──────────────────────────────────────────────────────────────────

@router.get(
    "/revisions",
    openapi_extra=docs.WIKIMEDIA_LIST_REVISION_ARTICLES,
)
async def list_revision_articles(
    min_revisions: int = Query(default=1, description="Minimum revision count filter"),
    limit: int = Query(default=100, description="Max articles to return"),
    db: AsyncSession = Depends(get_session),
):
    """List articles with extracted revision histories.

    Uses the pre-computed article_index from manifest.partition_index,
    populated at registration time by the submit script.
    """
    rev_dataset = await get_latest_entry(db, "wikimedia", "revisions")
    if not rev_dataset:
        raise HTTPException(status_code=404, detail="'wikimedia/revisions' dataset not found")

    article_index = rev_dataset.partition_index or []
    if not article_index:
        raise HTTPException(status_code=500, detail="Missing partition_index. Please re-register with partition_index set.")

    articles = [a for a in article_index if a["revision_count"] >= min_revisions][:limit]
    return {"articles": articles, "total": len(articles)}


@router.get(
    "/revisions/{identifier}",
    openapi_extra=docs.WIKIMEDIA_GET_REVISION_DELTAS,
)
async def get_revision_deltas(
    identifier: str,
    db: AsyncSession = Depends(get_session),
):
    """Delta-encoded revision history for one article.

    Returns one entry per revision. The first revision (revision_idx=0) contains
    the full token map. Subsequent revisions contain only changed tokens
    (value 0 = token removed).
    """
    rev_dataset = await get_latest_entry(db, "wikimedia", "revisions")
    if not rev_dataset:
        raise HTTPException(status_code=404, detail="'wikimedia/revisions' dataset not found")

    # Percent-encode the path-level value (same convention as build_hive_path):
    # neutralises SQL-string breakout (') and path traversal (../) in one step.
    safe_identifier = quote(identifier, safe="")

    def _query():
        with handle_query_error(f"wikimedia/revisions/{identifier}"):
            with get_duckdb_client().timed_connect() as conn:
                return conn.execute(f"""
                WITH ordered AS (
                    SELECT *,
                        ROW_NUMBER() OVER (ORDER BY revision_id::BIGINT) - 1 AS rev_seq,
                        json(ngram_counts)::MAP(VARCHAR, INTEGER) AS m
                    FROM read_parquet('{rev_dataset.data_location}/identifier={safe_identifier}/*.parquet')
                ),
                curr AS (
                    SELECT rev_seq,
                           unnest(map_keys(m)) AS token,
                           unnest(map_values(m)) AS curr_count
                    FROM ordered
                ),
                prev AS (
                    SELECT rev_seq + 1 AS rev_seq,
                           unnest(map_keys(m)) AS token,
                           unnest(map_values(m)) AS prev_count
                    FROM ordered
                ),
                diffs AS (
                    SELECT COALESCE(c.rev_seq, p.rev_seq) AS rev_seq,
                           COALESCE(c.token, p.token) AS token,
                           COALESCE(c.curr_count, 0) AS new_count
                    FROM curr c
                    FULL OUTER JOIN prev p
                        ON c.rev_seq = p.rev_seq AND c.token = p.token
                    WHERE prev_count IS NULL
                       OR curr_count IS NULL
                       OR curr_count != prev_count
                ),
                delta_agg AS (
                    SELECT rev_seq,
                           json_group_object(token, new_count) AS delta
                    FROM diffs
                    GROUP BY rev_seq
                )
                SELECT o.revision_id,
                       o.name,
                       o.date_modified,
                       o.revision_comment,
                       o.categories,
                       COALESCE(d.delta, '{{}}') AS token_diff
                FROM ordered o
                LEFT JOIN delta_agg d ON o.rev_seq = d.rev_seq
                ORDER BY o.rev_seq
            """).fetchall()

    rows = await run_blocking(_query)

    if not rows:
        raise HTTPException(status_code=404, detail=f"No revisions found for identifier {identifier}")

    return {
        "revisions": [
            {
                "revision_id": r[0],
                "name": r[1],
                "date_modified": r[2],
                "revision_comment": r[3],
                "categories": r[4],
                "token_diff": r[5],
            }
            for r in rows
        ]
    }


# ── term-series ───────────────────────────────────────────────────────────────

@router.get(
    "/term-series",
    openapi_extra=docs.WIKIMEDIA_TERM_SERIES,
)
async def term_series(
    entity: str = Query(..., description="Global entity ID, e.g. 'wikidata:Q30'"),
    type: str = Query(..., description="The n-gram term to look up, e.g. 'Trump'. Case-sensitive."),
    date: Optional[str] = Query(None, description="End date (YYYY-MM-DD). Defaults to latest available."),
    window: int = Query(0, description="Number of days to look back from date. 0 = full history."),
    granularity: str = Query("daily", description="Hive granularity: daily | weekly | monthly"),
    n: int = Query(1, description="N-gram size (1 = unigrams, 2 = bigrams)"),
    include_articles: bool = Query(True, description="Include top_articles in response (set false for sparkline-only, ~2x faster)"),
    sparkline_dataset: str = Query("sparklines", description="Registry dataset_id for the sparkline precomputed data (default: 'sparklines')."),
    db: AsyncSession = Depends(get_session),
):
    """Per-date time series for a single n-gram term within one entity (country).

    Returns counts, rank, and optionally top contributing Wikipedia articles for each date.

    **Fast path** (~20-70ms): point lookups on precomputed sorted Parquet files for ~65K vocabulary terms.
    **Slow fallback** (~3-5s): daily partition scan for arbitrary terms not in the precomputed vocabulary.
    Set `include_articles=false` for sparkline-only responses (~20ms, no top_articles field).
    """
    # Resolve entity via ngrams dataset (shared entity mappings)
    with timed("resolve", "Entity resolution"):
        ngrams_obj = await get_latest_entry(db, "wikimedia", "ngrams")
        if not ngrams_obj:
            raise HTTPException(status_code=404, detail="'wikimedia/ngrams' dataset not found")
        local_id = (await resolve_entity(db, "wikimedia", "ngrams", entity)).local_id

    _, entity_path = ngrams_context(
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

    # ── Fast path: sequential point lookups on sorted Parquet files ──
    series_rows = []
    articles: dict = {}  # (ngram, date_str) -> [[url, score], ...]
    with timed("registry", "Sparkline registry lookup"):
        sparkline_obj = await get_latest_entry(db, "wikimedia", sparkline_dataset)
        top_articles_obj = await get_latest_entry(db, "wikimedia", "top_articles_ngrams")

    if sparkline_obj:
        def _fast():
            with get_duckdb_client().timed_connect() as conn:
                rows = fetch_sparkline_rows(
                    conn, sparkline_obj, [type], local_id, n,
                    date_filter, date_params, "wikimedia/term-series",
                )
                arts: dict = {}
                if rows and include_articles:
                    arts = _fetch_top_articles(
                        conn, top_articles_obj, [type], local_id, n,
                        date_filter, date_params,
                    )
                return rows, arts

        with timed("fast_query", "DuckDB sparkline + articles read"):
            series_rows, articles = await run_blocking(_fast)

    # ── Slow path: partition scan (fallback for terms not in sparkline) ──
    if not series_rows:
        glob_pattern = f"{entity_path}/data_0.parquet"

        def _slow():
            with handle_query_error("wikimedia/ngrams"):
                with get_duckdb_client().timed_connect() as conn:
                    rows = conn.execute(
                        f"""
                        SELECT ngram, date, pv_count, pv_rank, pv_freq
                        FROM read_parquet('{glob_pattern}', hive_partitioning=true)
                        WHERE ngram = ? AND {date_filter}
                        ORDER BY date
                        """,
                        [type, *date_params],
                    ).fetchall()
                    arts: dict = {}
                    if rows and include_articles:
                        arts = _fetch_top_articles(
                            conn, top_articles_obj, [type], local_id, n,
                            date_filter, date_params,
                        )
                    return rows, arts

        with timed("slow_query", "DuckDB partition scan"):
            series_rows, articles = await run_blocking(_slow)

    series = []
    for row in series_rows:
        date_str = str(row[1])
        entry = series_entry(date_str, row[2], row[3], row[4])
        if include_articles:
            entry["top_articles"] = articles.get((row[0], date_str), [])
        series.append(entry)

    return {
        "type": type,
        "latest_available_date": latest_date,
        "series": series,
    }


@router.get(
    "/term-series/batch",
    openapi_extra=docs.WIKIMEDIA_TERM_SERIES_BATCH,
)
async def term_series_batch(
    entity: str = Query(..., description="Global entity ID, e.g. 'wikidata:Q30'"),
    types: str = Query(..., description="Comma-separated n-gram terms, e.g. 'Trump,COVID,the'. Case-sensitive."),
    date: Optional[str] = Query(None, description="End date (YYYY-MM-DD). Defaults to latest available."),
    window: int = Query(0, description="Number of days to look back from date. 0 = full history."),
    granularity: str = Query("daily", description="Hive granularity: daily | weekly | monthly"),
    n: int = Query(1, description="N-gram size (1 = unigrams, 2 = bigrams)"),
    include_articles: bool = Query(True, description="Include top_articles in response (set false for sparkline-only, ~2x faster)"),
    articles_dates: Optional[str] = Query(None, description="Comma-separated dates to fetch articles for (e.g. '2025-06-05,2026-01-21'). When set, top_articles are only included for these dates instead of the full window. Sparkline data is unaffected."),
    sparkline_dataset: str = Query("sparklines", description="Registry dataset_id for the sparkline precomputed data (default: 'sparklines')."),
    db: AsyncSession = Depends(get_session),
):
    """Batch time series lookup for multiple terms in a single request.

    Returns a map of term → time series. Ideal for fetching sparklines for all terms
    in an RTD wordshift comparison at once.

    **Fast path** (~20-200ms): point lookups on precomputed sorted Parquet files.
    **Slow fallback** (~3-5s per missing term): daily partition scan for terms not in the precomputed vocabulary.
    Set `include_articles=false` for sparkline-only responses (~2x faster).
    Use `articles_dates` to restrict top_articles to specific dates (e.g. the two allotax comparison dates).
    """
    ngrams_obj = await get_latest_entry(db, "wikimedia", "ngrams")
    if not ngrams_obj:
        raise HTTPException(status_code=404, detail="'wikimedia/ngrams' dataset not found")
    local_id = (await resolve_entity(db, "wikimedia", "ngrams", entity)).local_id

    _, entity_path = ngrams_context(
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

    # Articles date filter: when articles_dates is provided, fetch articles
    # only for those specific dates (e.g. the two allotax comparison dates)
    # instead of the full sparkline window.
    if articles_dates:
        art_date_list = [d.strip() for d in articles_dates.split(",") if d.strip()]
        art_placeholders = ", ".join(["?"] * len(art_date_list))
        art_date_filter = f"date IN ({art_placeholders})"
        art_date_params = art_date_list
    else:
        art_date_filter = date_filter
        art_date_params = date_params

    # ── Fast path: sequential point lookups on sorted Parquet files ──
    # Sparkline/article precomputed data is daily-only; skip for weekly/monthly.
    sparkline_rows = []
    articles_by_key: dict = {}  # (ngram, date_str) -> [[url, score], ...]
    use_fast_path = granularity == "daily"

    if use_fast_path:
        with timed("registry", "Sparkline registry lookup"):
            sparkline_obj = await get_latest_entry(db, "wikimedia", sparkline_dataset)
            top_articles_obj = await get_latest_entry(db, "wikimedia", "top_articles_ngrams")
    else:
        sparkline_obj = None
        top_articles_obj = None

    if sparkline_obj:
        def _fast():
            with get_duckdb_client().timed_connect() as conn:
                rows = fetch_sparkline_rows(
                    conn, sparkline_obj, type_list, local_id, n,
                    date_filter, date_params, "wikimedia/term-series/batch",
                )
                arts: dict = {}
                found = {row[0] for row in rows}
                if include_articles and found:
                    arts = _fetch_top_articles(
                        conn, top_articles_obj, found, local_id, n,
                        art_date_filter, art_date_params,
                    )
                return rows, arts

        with timed("fast_query", "DuckDB sparkline + articles read"):
            sparkline_rows, articles_by_key = await run_blocking(_fast)

    found_terms = {row[0] for row in sparkline_rows}

    # ── Slow path: partition fallback for missing terms ──
    missing_terms = [t for t in type_list if t not in found_terms]
    slow_results: dict = {}
    if missing_terms:
        glob_pattern = f"{entity_path}/data_0.parquet"
        slow_placeholders = ", ".join(["?"] * len(missing_terms))

        def _slow():
            with get_duckdb_client().timed_connect() as conn:
                try:
                    rows = conn.execute(
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
                        log.info("wikimedia/term-series/batch: no partition data for %s", missing_terms)
                    else:
                        log.warning("wikimedia/term-series/batch: partition scan failed: %s", exc)
                    return [], {}
                arts: dict = {}
                if rows and include_articles and use_fast_path:
                    arts = _fetch_top_articles(
                        conn, top_articles_obj, {row[0] for row in rows}, local_id, n,
                        art_date_filter, art_date_params,
                    )
                return rows, arts

        with timed("slow_query", "DuckDB partition scan"):
            slow_rows, slow_articles = await run_blocking(_slow)

        for row in slow_rows:
            ngram, date_str = row[0], str(row[1])
            entry = series_entry(date_str, row[2], row[3], row[4])
            if include_articles and use_fast_path:
                entry["top_articles"] = slow_articles.get((ngram, date_str), [])
            slow_results.setdefault(ngram, []).append(entry)

    # ── Merge results ──
    results: dict = {t: [] for t in type_list}
    for row in sparkline_rows:
        ngram, date_str = row[0], str(row[1])
        entry = series_entry(date_str, row[2], row[3], row[4])
        if include_articles:
            entry["top_articles"] = articles_by_key.get((ngram, date_str), [])
        results[ngram].append(entry)
    for ngram, entries in slow_results.items():
        results[ngram] = entries

    return {
        "results": results,
        "latest_available_date": latest_date,
    }


# ── precomputed-rtd ───────────────────────────────────────────────────────────

@router.get("/precomputed-rtd")
async def precomputed_rtd(
    entity: str = Query(..., description="Global entity ID, e.g. 'wikidata:Q30'"),
    date: str = Query(..., description="Reference date (YYYY-MM-DD)"),
    date_delta: int = Query(1, description="Days between the two compared systems"),
    granularity: str = Query("daily", description="Granularity: daily | weekly | monthly"),
    n: int = Query(1, description="N-gram size (1 = unigrams, 2 = bigrams)"),
    alpha: float = Query(0.17, description="RTD alpha parameter"),
    limit: int = Query(200, description="Top N terms by absolute divergence"),
    db: AsyncSession = Depends(get_session),
):
    """Precomputed Rank Turbulence Divergence for a single entity and date.

    Returns the top divergent terms between two consecutive time periods,
    sorted by absolute divergence descending.
    """
    with timed("registry", "RTD registry lookup"):
        rtd_obj = await get_latest_entry(db, "wikimedia", "precomputed_rtd")
        if not rtd_obj:
            raise HTTPException(status_code=404, detail="'wikimedia/precomputed_rtd' dataset not found")
        local_id = (await resolve_entity(db, "wikimedia", "ngrams", entity)).local_id

    path = build_hive_path(
        rtd_obj,
        filter_vals={"ngram_size": n, "alpha": alpha},
        entity_value=local_id,
        glob_suffix="/data_0.parquet",
    )

    def _query():
        with get_duckdb_client().timed_connect() as conn:
            with handle_query_error("wikimedia/precomputed_rtd"):
                return conn.execute(
                    f"""
                    SELECT ngram, divergence
                    FROM read_parquet('{path}')
                    WHERE date = ? AND date_delta = ? AND granularity = ?
                    ORDER BY ABS(divergence) DESC
                    LIMIT ?
                    """,
                    [date, date_delta, granularity, limit],
                ).fetchall()

    with timed("query", "DuckDB precomputed RTD read"):
        rows = await run_blocking(_query)

    return {
        "data": [
            {
                "type": r[0],
                "date": date,
                "date_delta": date_delta,
                "divergence": r[1],
                "alpha": alpha,
                "granularity": granularity,
            }
            for r in rows
        ],
        "metadata": {
            "entity": entity,
            "date": date,
            "date_delta": date_delta,
            "granularity": granularity,
            "n": n,
            "alpha": alpha,
        },
    }
