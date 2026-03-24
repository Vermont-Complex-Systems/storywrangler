"""
Wikimedia endpoints — Wikipedia n-grams and revision histories.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..core.database import get_session
from ..core.duckdb_client import get_duckdb_client
from ..core.query_utils import load_system, resolve_entity
from ..models.registry import RegistryEntry

router = APIRouter()

_WikimediaEntry = select(RegistryEntry).where(RegistryEntry.domain == "wikimedia")


# ── top-ngrams ─────────────────────────────────────────────────────────────────

@router.get(
    "/top-ngrams",
    openapi_extra={
        "responses": {
            "200": {
                "description": "Successful response",
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {
                                "data": {
                                    "type": "array",
                                    "description": "N-gram frequency entries sorted by count descending.",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "types": {"type": "string", "description": "The n-gram string"},
                                            "counts": {"type": "integer", "description": "Total occurrence count over the date range"},
                                        },
                                    },
                                },
                                "metadata": {
                                    "type": "object",
                                    "description": "Request metadata echoed back",
                                    "properties": {
                                        "granularity": {"type": "string", "description": "Granularity used (daily/weekly/monthly)"},
                                        "location": {"type": "string", "description": "Entity ID used"},
                                    },
                                },
                            },
                        },
                        "example": {
                            "data": [
                                {"types": "the", "counts": 12345678},
                                {"types": "of", "counts": 9876543},
                                {"types": "a", "counts": 8234567},
                            ],
                            "metadata": {"granularity": "daily", "location": "wikidata:Q30"},
                        },
                    }
                },
            }
        }
    },
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
    result = await db.execute(_WikimediaEntry.where(RegistryEntry.dataset_id == "ngrams"))
    dataset_obj = result.scalar_one_or_none()
    if not dataset_obj:
        raise HTTPException(status_code=404, detail="'wikimedia/ngrams' dataset not found")

    ep = dataset_obj.endpoint_schema or {}
    granularities = ep.get("granularities", {})
    if granularity not in granularities:
        raise HTTPException(
            status_code=400,
            detail=f"granularity must be one of {sorted(granularities)}",
        )

    ngram_sizes = ep.get("ngram_sizes")
    if ngram_sizes is not None and n not in ngram_sizes:
        raise HTTPException(
            status_code=400,
            detail=f"n must be one of {ngram_sizes}",
        )

    em = await resolve_entity(db, "wikimedia", "ngrams", locations)

    def parse_dr(s: str) -> List[str]:
        parts = s.split(",")
        return [parts[0], parts[0]] if len(parts) == 1 else [parts[0], parts[1]]

    try:
        conn = get_duckdb_client().connect()
        dr1 = parse_dr(dates)
        sys1 = load_system(conn, dataset_obj, em.local_id, dr1, {}, granularity, limit, n=n)
        formatted1 = [{"types": t, "counts": c} for t, c in zip(sys1["types"], sys1["counts"])]

        if dates2:
            dr2 = parse_dr(dates2)
            sys2 = load_system(conn, dataset_obj, em.local_id, dr2, {}, granularity, limit, n=n)
            formatted2 = [{"types": t, "counts": c} for t, c in zip(sys2["types"], sys2["counts"])]
            key1 = dr1[0] if dr1[0] == dr1[1] else f"{dr1[0]}_{dr1[1]}"
            key2 = dr2[0] if dr2[0] == dr2[1] else f"{dr2[0]}_{dr2[1]}"
            return {
                key1: formatted1,
                key2: formatted2,
                "metadata": {"granularity": granularity, "location": locations},
            }

        return {
            "data": formatted1,
            "metadata": {"granularity": granularity, "location": locations},
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query execution failed: {str(e)}")


# ── revisions ──────────────────────────────────────────────────────────────────

@router.get(
    "/revisions",
    openapi_extra={
        "responses": {
            "200": {
                "description": "Successful response",
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {
                                "articles": {
                                    "type": "array",
                                    "description": "Articles with extracted revision histories",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "identifier": {"type": "string", "description": "Article identifier (slug)"},
                                            "revision_count": {"type": "integer", "description": "Number of revisions extracted"},
                                        },
                                    },
                                },
                                "total": {"type": "integer", "description": "Total number of matching articles returned"},
                            },
                        },
                        "example": {
                            "articles": [
                                {"identifier": "Cat", "revision_count": 142},
                                {"identifier": "Dog", "revision_count": 98},
                            ],
                            "total": 2,
                        },
                    }
                },
            }
        }
    },
)
async def list_revision_articles(
    min_revisions: int = Query(default=1, description="Minimum revision count filter"),
    limit: int = Query(default=100, description="Max articles to return"),
    db: AsyncSession = Depends(get_session),
):
    """List articles with extracted revision histories.

    Uses the pre-computed article_index from format_config.partitioning,
    populated at registration time by the submit script.
    """
    result = await db.execute(_WikimediaEntry.where(RegistryEntry.dataset_id == "revisions"))
    rev_dataset = result.scalar_one_or_none()
    if not rev_dataset:
        raise HTTPException(status_code=404, detail="'wikimedia/revisions' dataset not found")

    fc = rev_dataset.format_config or {}
    article_index = fc.get("partitioning", {}).get("article_index", [])
    if not article_index:
        raise HTTPException(status_code=500, detail="Missing article_index in format_config. Please re-register.")

    articles = [a for a in article_index if a["revision_count"] >= min_revisions][:limit]
    return {"articles": articles, "total": len(articles)}


@router.get(
    "/revisions/{identifier}",
    openapi_extra={
        "responses": {
            "200": {
                "description": "Successful response",
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {
                                "revisions": {
                                    "type": "array",
                                    "description": "Ordered revision history (oldest first). First entry is the full token map; subsequent entries contain only changed tokens.",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "revision_id": {"type": "string", "description": "Wikipedia revision ID"},
                                            "name": {"type": "string", "description": "Article title"},
                                            "date_modified": {"type": "string", "description": "ISO 8601 modification date"},
                                            "revision_comment": {"type": "string", "description": "Edit summary"},
                                            "categories": {"type": "array", "description": "List of article categories"},
                                            "token_diff": {"type": "string", "description": "JSON-encoded delta map: token → new count (0 = removed)"},
                                        },
                                    },
                                },
                            },
                        },
                        "example": {
                            "revisions": [
                                {
                                    "revision_id": "1234567890",
                                    "name": "Cat",
                                    "date_modified": "2024-01-15",
                                    "revision_comment": "/* Breeds */ Added Persian section",
                                    "categories": ["Cats", "Mammals", "Pets"],
                                    "token_diff": '{"cat": 3, "breed": 5, "persian": 1}',
                                }
                            ]
                        },
                    }
                },
            }
        }
    },
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
    result = await db.execute(_WikimediaEntry.where(RegistryEntry.dataset_id == "revisions"))
    rev_dataset = result.scalar_one_or_none()
    if not rev_dataset:
        raise HTTPException(status_code=404, detail="'wikimedia/revisions' dataset not found")

    try:
        conn = get_duckdb_client().connect()
        rows = conn.execute(f"""
            WITH ordered AS (
                SELECT *,
                    ROW_NUMBER() OVER (ORDER BY revision_id::BIGINT) - 1 AS rev_seq,
                    json(ngram_counts)::MAP(VARCHAR, INTEGER) AS m
                FROM read_parquet('{rev_dataset.data_location}/identifier={identifier}/*.parquet')
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")

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
