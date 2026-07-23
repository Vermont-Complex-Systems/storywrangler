"""
Wikimedia endpoints — revision histories, precomputed RTD, and semantic time series.
"""

import json
import logging
from typing import Optional
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from ..core.database import get_session
from ..core.duckdb_client import get_duckdb_client, run_blocking
from ..core.duckdb_query import build_hive_path, handle_query_error
from ..core.query_utils import resolve_entity
from ..core.registry_utils import get_latest_entry
from ..core.timing import timed
from . import openapi_docs as docs

log = logging.getLogger(__name__)

router = APIRouter()


# ── revisions ──────────────────────────────────────────────────────────────────

@router.get(
    "/revisions",
    openapi_extra={**docs.WIKIMEDIA_LIST_REVISION_ARTICLES, "x-dataset": "revisions"},
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
    openapi_extra={**docs.WIKIMEDIA_GET_REVISION_DELTAS, "x-dataset": "revisions"},
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


# ── precomputed-rtd ───────────────────────────────────────────────────────────

@router.get("/precomputed-rtd", openapi_extra={"x-dataset": "precomputed_rtd"})
async def precomputed_rtd(
    entity: str = Query(..., description="Global entity ID, e.g. 'wikidata:Q30'"),
    date: str = Query(..., description="Reference date (YYYY-MM-DD)"),
    date_delta: int = Query(1, description="Days between the two compared systems"),
    granularity: str = Query("daily", description="Granularity: daily | weekly | monthly"),
    ngram_size: Optional[int] = Query(None, description="N-gram size (1 = unigrams, 2 = bigrams) — the registered column name."),
    n: int = Query(1, description="Deprecated alias for ngram_size."),
    alpha: float = Query(0.17, description="RTD alpha parameter"),
    limit: int = Query(200, description="Top N terms by absolute divergence"),
    db: AsyncSession = Depends(get_session),
):
    """Precomputed Rank Turbulence Divergence for a single entity and date.

    Returns the top divergent terms between two consecutive time periods,
    sorted by absolute divergence descending.
    """
    n = ngram_size if ngram_size is not None else n
    with timed("registry", "RTD registry lookup"):
        rtd_obj = await get_latest_entry(db, "wikimedia", "precomputed_rtd")
        if not rtd_obj:
            raise HTTPException(status_code=404, detail="'wikimedia/precomputed_rtd' dataset not found")
        local_id = (await resolve_entity(db, "wikimedia", "ngrams", entity)).local_id

    path = build_hive_path(
        rtd_obj,
        filter_vals={"ngram_size": n, "alpha": alpha},
        entity_value=local_id,
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


# ── semantic-timeseries ───────────────────────────────────────────────────────

@router.get("/semantic-timeseries", openapi_extra={"x-dataset": "semantic-timeseries"})
async def semantic_timeseries(
    country: str = Query("United States", description="Country name as stored in the data (e.g. 'United States'), or 'All' for the global pageview-weighted corpus"),
    db: AsyncSession = Depends(get_session),
):
    """Daily lexicon-scored time series for one country's pageview-weighted corpus.

    Returns the full history: one entry per day with the labMT happiness score
    (avg_happs), ousiometric power/danger/structure scores, and the
    pageview-weighted word-count denominators behind each average.
    """
    dataset_obj = await get_latest_entry(db, "wikimedia", "semantic-timeseries")
    if not dataset_obj:
        raise HTTPException(status_code=404, detail="'wikimedia/semantic-timeseries' dataset not found")

    def _query():
        # handle_query_error translates DuckDB failures into API errors:
        # timeout → 504, missing data file → 404, anything else → a 500
        # that doesn't leak filesystem paths.
        with handle_query_error("wikimedia/semantic-timeseries"):
            # timed_connect hands this request its own cursor on the shared
            # connection (parquet metadata stays cached across requests) and
            # interrupts the query after 120s — the timeout the 504 refers to.
            with get_duckdb_client().timed_connect() as conn:
                cur = conn.execute(
                    f"""
                    SELECT * REPLACE (strftime(date, '%Y-%m-%d') AS date)
                    FROM read_parquet('{dataset_obj.data_location}')
                    WHERE country = ?
                    ORDER BY date
                    """,
                    [country],
                )
                columns = [d[0] for d in cur.description]
                return [dict(zip(columns, row)) for row in cur.fetchall()]

    # DuckDB is blocking: run_blocking moves the query to a bounded worker
    # pool so a slow read doesn't stall every other request on the API.
    return await run_blocking(_query)


# ── semantic-ngrams ───────────────────────────────────────────────────────────

@router.get("/semantic-ngrams", openapi_extra={"x-dataset": "semantic-ngrams"})
async def semantic_ngrams(
    country: str = Query("United States", description="Country name as stored in the data (e.g. 'United States'), or 'All' for the global pageview-weighted corpus"),
    date: str = Query(..., description="Date (YYYY-MM-DD)"),
    granularity: str = Query("daily", description="daily, weekly, or monthly"),
    db: AsyncSession = Depends(get_session),
):
    """Per-word labMT counts for one country and day — the word shift graph's input.

    Returns the row for (country, date): the daily lexicon scores plus `count`,
    a map of labMT word → pageview-weighted count for every labMT word that
    appeared that day.
    """
    dataset_obj = await get_latest_entry(db, "wikimedia", "semantic-ngrams")
    if not dataset_obj:
        raise HTTPException(status_code=404, detail="'wikimedia/semantic-ngrams' dataset not found")

    # build_hive_path pins the exact partition leaf from the registered
    # level_order — one directory read instead of globbing the tree over NFS.
    # country is passed both ways so the path resolves whether or not the
    # registration declared entity_mapping (level type entity vs partition).
    path = build_hive_path(
        dataset_obj,
        entity_value=country,
        filter_vals={"granularity": granularity, "country": country},
    )
    if not path:
        raise HTTPException(
            status_code=500,
            detail="'wikimedia/semantic-ngrams' has no level_order — register it with data_format='parquet_hive'",
        )

    def _query():
        with handle_query_error("wikimedia/semantic-ngrams"):
            with get_duckdb_client().timed_connect() as conn:
                cur = conn.execute(
                    f"""
                    SELECT *
                    FROM read_parquet('{path}', hive_partitioning=true)
                    WHERE date = ?
                    """,
                    [date],
                )
                columns = [d[0] for d in cur.description]
                return [dict(zip(columns, row)) for row in cur.fetchall()]

    rows = await run_blocking(_query)

    # count is stored as a JSON string; return it as a real object so the
    # frontend reads word counts directly (and avoids double-encoding).
    for entry in rows:
        if isinstance(entry.get("count"), str):
            entry["count"] = json.loads(entry["count"])
    return rows
