"""
Wikimedia endpoints — Wikipedia n-grams, revision histories, and term time series.
"""

import hashlib
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from ..core.database import get_session
from ..core.duckdb_client import get_duckdb_client
from ..core.query_utils import handle_query_error, load_system, parse_dates, resolve_entity
from ..core.registry_utils import get_latest_entry
from ..core.timing import timed

router = APIRouter()


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
    dataset_obj = await get_latest_entry(db, "wikimedia", "ngrams")
    if not dataset_obj:
        raise HTTPException(status_code=404, detail="'wikimedia/ngrams' dataset not found")

    fv = dataset_obj.filter_values or {}
    tr = dataset_obj.transform or {}
    partition_dims = (tr.get("partition_dimensions") or tr.get("filter_dimensions") or []) if tr else []

    # Validate granularity against pre-introspected distinct values (if declared)
    if "granularity" in partition_dims:
        valid = fv.get("granularity", [])
        if valid and granularity not in valid:
            raise HTTPException(
                status_code=400,
                detail=f"granularity must be one of {sorted(valid)}",
            )

    # Validate n against pre-introspected ngram_size values (if declared)
    if "ngram_size" in partition_dims:
        valid_n = fv.get("ngram_size", [])
        if valid_n and n not in valid_n:
            raise HTTPException(
                status_code=400,
                detail=f"n must be one of {sorted(valid_n)}",
            )

    em = await resolve_entity(db, "wikimedia", "ngrams", locations)

    # Build filter_vals: include granularity and ngram_size if declared as partition dims.
    extra: dict = {}
    if "granularity" in partition_dims:
        extra["granularity"] = granularity
    if "ngram_size" in partition_dims:
        extra["ngram_size"] = n

    with handle_query_error("wikimedia/ngrams"):
        conn = get_duckdb_client().connect()
        dr1 = parse_dates(dates)
        sys1 = load_system(conn, dataset_obj, em.local_id, dr1, extra, limit)
        formatted1 = [{"types": t, "counts": c} for t, c in zip(sys1["types"], sys1["counts"])]

        if dates2:
            dr2 = parse_dates(dates2)
            sys2 = load_system(conn, dataset_obj, em.local_id, dr2, extra, limit)
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
    rev_dataset = await get_latest_entry(db, "wikimedia", "revisions")
    if not rev_dataset:
        raise HTTPException(status_code=404, detail="'wikimedia/revisions' dataset not found")

    with handle_query_error(f"wikimedia/revisions/{identifier}"):
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

def _entity_base_path(dataset_obj, local_id, filter_vals):
    """Build the Hive path up to the entity level (no date).

    Used for DuckDB glob patterns in the slow-path daily partition fallback.
    """
    entity_col = (dataset_obj.entity_mapping or {}).get("local_id_column")
    path = dataset_obj.data_location
    for dim, val in filter_vals.items():
        path += f"/{dim}={quote(str(val), safe='')}"
    if entity_col and local_id is not None:
        path += f"/{entity_col}={quote(str(local_id), safe='')}"
    return path


def _latest_from_manifest(dataset_obj, local_id, granularity=None):
    """Read the latest available date from manifest.availability.

    Availability is keyed by local_id (entity column value) with
    per-granularity min/max — populated at registration time by
    parquet_introspect.  Returns None if not available.
    """
    availability = (dataset_obj.manifest or {}).get("availability", {})
    if not availability:
        return None
    if local_id is not None and local_id in availability:
        entry = availability[local_id]
    elif local_id is None:
        entry = availability
    else:
        return None
    # entry is either {"min":..,"max":..} or {"daily": {"min":..,"max":..}, ...}
    if granularity and isinstance(entry, dict) and granularity in entry:
        return entry[granularity].get("max")
    if isinstance(entry, dict) and "max" in entry:
        return entry["max"]
    return None


@router.get(
    "/term-series",
    openapi_extra={
        "responses": {
            "200": {
                "description": "Successful response",
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {
                                "type": {
                                    "type": "string",
                                    "description": "The n-gram term that was looked up (echoed back).",
                                },
                                "latest_available_date": {
                                    "type": "string",
                                    "format": "date",
                                    "description": "Most recent date with data for this entity (YYYY-MM-DD). Use this to default the date picker in the UI.",
                                },
                                "series": {
                                    "type": "array",
                                    "description": "Time series entries, one per date, sorted chronologically.",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "date": {"type": "string", "format": "date", "description": "Date (YYYY-MM-DD)"},
                                            "counts": {"type": "integer", "description": "Total weighted page-view count for this term on this date (sum across all Wikipedia articles containing the term)"},
                                            "rank": {"type": "integer", "description": "Rank by page-view count on this date (1 = most viewed term). 0 means not ranked."},
                                            "top_articles": {
                                                "type": "array",
                                                "description": "Top 10 Wikipedia articles contributing most page views to this term on this date. Only present when include_articles=true. Each entry is [url, score]. Empty array if no article data is available for this term on this date.",
                                                "items": {
                                                    "type": "array",
                                                    "prefixItems": [
                                                        {"type": "string", "description": "Full Wikipedia article URL"},
                                                        {"type": "number", "description": "Contribution score (higher = more page views attributed to this article for the term)"},
                                                    ],
                                                },
                                            },
                                        },
                                    },
                                },
                            },
                        },
                        "examples": {
                            "with_articles": {
                                "summary": "Term with top articles (include_articles=true, default)",
                                "value": {
                                    "type": "Trump",
                                    "latest_available_date": "2026-04-20",
                                    "series": [
                                        {
                                            "date": "2026-04-19",
                                            "counts": 41964675,
                                            "rank": 487,
                                            "top_articles": [
                                                ["https://en.wikipedia.org/wiki/Donald_Trump", 255.07],
                                                ["https://en.wikipedia.org/wiki/Donald_Trump_Jr.", 127.83],
                                                ["https://en.wikipedia.org/wiki/Lara_Trump", 123.68],
                                            ],
                                        },
                                        {
                                            "date": "2026-04-20",
                                            "counts": 45655115,
                                            "rank": 455,
                                            "top_articles": [
                                                ["https://en.wikipedia.org/wiki/Donald_Trump", 282.65],
                                                ["https://en.wikipedia.org/wiki/Kash_Patel", 168.08],
                                                ["https://en.wikipedia.org/wiki/Vanessa_Trump", 136.84],
                                            ],
                                        },
                                    ],
                                },
                            },
                            "without_articles": {
                                "summary": "Sparkline only (include_articles=false)",
                                "value": {
                                    "type": "Trump",
                                    "latest_available_date": "2026-04-20",
                                    "series": [
                                        {"date": "2026-04-19", "counts": 41964675, "rank": 487},
                                        {"date": "2026-04-20", "counts": 45655115, "rank": 455},
                                    ],
                                },
                            },
                        },
                    }
                },
            }
        },
        "x-performance": {
            "fast_path": "~20-70ms for terms in the precomputed vocabulary (~65K terms including top 10K by rank + RTD-divergent terms)",
            "slow_fallback": "~3-5s for arbitrary terms not in the vocabulary (scans daily partition files)",
            "sparkline_only": "~20ms with include_articles=false (skips the articles file entirely)",
        },
        "x-frontend-notes": {
            "term_case_sensitivity": "Terms are case-sensitive. 'COVID' and 'covid' are different lookups. The sparkline vocabulary stores original case from Wikipedia page views.",
            "include_articles_usage": "Set include_articles=false when rendering sparkline charts without article tooltips (2x faster). Only request articles when the user hovers/clicks to see contributing Wikipedia pages.",
            "top_articles_coverage": "top_articles is populated for all vocabulary terms (~65K) on all dates. Empty array means the source data had no articles for that term on that date.",
            "window_0_means_full_history": "window=0 (default) returns the full available date range (~570 days). Use window=30 or window=90 for recent data.",
            "empty_series": "If the term has no data at all, series will be an empty array.",
        },
    },
)
async def term_series(
    entity: str = Query(..., description="Global entity ID, e.g. 'wikidata:Q30'"),
    type: str = Query(..., description="The n-gram term to look up, e.g. 'Trump'. Case-sensitive."),
    date: Optional[str] = Query(None, description="End date (YYYY-MM-DD). Defaults to latest available."),
    window: int = Query(0, description="Number of days to look back from date. 0 = full history."),
    granularity: str = Query("daily", description="Hive granularity: daily | weekly | monthly"),
    n: int = Query(1, description="N-gram size (1 = unigrams, 2 = bigrams)"),
    include_articles: bool = Query(True, description="Include top_articles in response (set false for sparkline-only, ~2x faster)"),
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

    # Build entity_path for slow-path fallback (daily partition scan)
    ngrams_tr = ngrams_obj.transform or {}
    partition_map = (ngrams_tr.get("partition_dimensions") or {})
    if isinstance(partition_map, list):
        partition_map = {dim: None for dim in partition_map}
    ngrams_filter_vals: dict = {}
    if "granularity" in partition_map:
        ngrams_filter_vals["granularity"] = granularity
    if "ngram_size" in partition_map:
        ngrams_filter_vals["ngram_size"] = n
    entity_path = _entity_base_path(ngrams_obj, local_id, ngrams_filter_vals)

    with timed("discover", "Latest date from manifest"):
        latest_date = _latest_from_manifest(ngrams_obj, local_id, granularity)

    if not date:
        if not latest_date:
            return JSONResponse(
                status_code=404,
                content={"detail": "No data found for this entity", "latest_available_date": None},
            )
        date = latest_date

    try:
        end = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date: {date}")

    if window > 0:
        start = end - timedelta(days=window)
        start_str = start.strftime("%Y-%m-%d")
    else:
        start_str = None

    date_filter = "date BETWEEN ? AND ?" if start_str else "date <= ?"
    date_params = [start_str, date] if start_str else [date]

    # ── Fast path: sequential point lookups on sorted Parquet files ──
    sparkline_rows = []
    with timed("registry", "Sparkline registry lookup"):
        sparkline_obj = await get_latest_entry(db, "wikimedia", "sparklines")
        top_articles_obj = await get_latest_entry(db, "wikimedia", "top_articles_ngrams")

    if sparkline_obj:
        encoded_country = quote(str(local_id), safe="")
        sparkline_path = f"{sparkline_obj.data_location}/ngram_size={n}/country={encoded_country}/data_0.parquet"

        with timed("fast_query", "DuckDB sparkline + articles read"):
            conn = get_duckdb_client().connect()
            sparkline_rows = conn.execute(
                f"""
                SELECT date, pv_count, pv_rank, pv_freq
                FROM read_parquet('{sparkline_path}')
                WHERE ngram = ? AND {date_filter}
                ORDER BY date
                """,
                [type, *date_params],
            ).fetchall()

            articles_by_date: dict = {}
            if sparkline_rows and include_articles and top_articles_obj:
                try:
                    bucket = hashlib.md5(type.encode("utf-8")).hexdigest()[0]
                    articles_base = f"{top_articles_obj.data_location}/ngram_size={n}/country={encoded_country}"
                    art_rows = conn.execute(
                        f"""
                        SELECT date, article_url, score
                        FROM read_parquet('{articles_base}/*/data_0.parquet', hive_partitioning=true)
                        WHERE ngram_bucket = ? AND ngram = ? AND {date_filter}
                        ORDER BY date, article_rank
                        """,
                        [bucket, type, *date_params],
                    ).fetchall()
                    for row in art_rows:
                        articles_by_date.setdefault(str(row[0]), []).append(
                            [row[1], float(row[2]) if row[2] else 0.0]
                        )
                except Exception:
                    pass  # articles files may not exist yet

    # ── Slow path: scan daily partitions (fallback for terms not in sparkline) ──
    if not sparkline_rows:
        with timed("slow_query", "DuckDB daily partition scan"):
            conn = get_duckdb_client().connect()
            glob_pattern = f"{entity_path}/date=*/data_0.parquet"

            if include_articles:
                slow_rows = conn.execute(
                    f"""
                    SELECT date, pv_count, pv_rank, pv_freq, top_articles
                    FROM read_parquet('{glob_pattern}', hive_partitioning=true)
                    WHERE ngram = ? AND {date_filter}
                    ORDER BY date
                    """,
                    [type, *date_params],
                ).fetchall()
            else:
                slow_rows = conn.execute(
                    f"""
                    SELECT date, pv_count, pv_rank, pv_freq
                    FROM read_parquet('{glob_pattern}', hive_partitioning=true)
                    WHERE ngram = ? AND {date_filter}
                    ORDER BY date
                    """,
                    [type, *date_params],
                ).fetchall()

            series = []
            for row in slow_rows:
                entry = {
                    "date": str(row[0]),
                    "counts": int(row[1]) if row[1] else 0,
                    "rank": int(row[2]) if row[2] else 0,
                    "freq": float(row[3]) if row[3] else 0.0,
                }
                if include_articles:
                    top_articles = []
                    if row[4]:
                        for article in row[4]:
                            if len(article) >= 2:
                                try:
                                    top_articles.append([article[0], float(article[1])])
                                except (ValueError, TypeError):
                                    top_articles.append([article[0], 0.0])
                    entry["top_articles"] = top_articles
                series.append(entry)

            return {
                "type": type,
                "latest_available_date": latest_date,
                "series": series,
            }

    # ── Assemble response from fast path results ──
    series = []
    for row in sparkline_rows:
        date_str = str(row[0])
        entry = {
            "date": date_str,
            "counts": int(row[1]) if row[1] else 0,
            "rank": int(row[2]) if row[2] else 0,
            "freq": float(row[3]) if row[3] else 0.0,
        }
        if include_articles:
            entry["top_articles"] = articles_by_date.get(date_str, [])
        series.append(entry)

    return {
        "type": type,
        "latest_available_date": latest_date,
        "series": series,
    }


@router.get(
    "/term-series/batch",
    openapi_extra={
        "responses": {
            "200": {
                "description": "Successful response",
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {
                                "results": {
                                    "type": "object",
                                    "description": "Map of term → time series. Keys are the requested terms (in request order). Each value is an array of date entries identical to the /term-series series format.",
                                    "additionalProperties": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "date": {"type": "string", "format": "date"},
                                                "counts": {"type": "integer"},
                                                "rank": {"type": "integer"},
                                                "top_articles": {
                                                    "type": "array",
                                                    "description": "Only present when include_articles=true.",
                                                    "items": {
                                                        "type": "array",
                                                        "prefixItems": [
                                                            {"type": "string"},
                                                            {"type": "number"},
                                                        ],
                                                    },
                                                },
                                            },
                                        },
                                    },
                                },
                                "latest_available_date": {
                                    "type": "string",
                                    "format": "date",
                                    "description": "Most recent date with data for this entity.",
                                },
                            },
                        },
                        "examples": {
                            "batch_with_articles": {
                                "summary": "Batch lookup (include_articles=true)",
                                "value": {
                                    "results": {
                                        "Trump": [
                                            {"date": "2026-04-20", "counts": 45655115, "rank": 455, "top_articles": [["https://en.wikipedia.org/wiki/Donald_Trump", 282.65]]},
                                        ],
                                        "COVID": [
                                            {"date": "2026-04-20", "counts": 775676, "rank": 19105, "top_articles": []},
                                        ],
                                    },
                                    "latest_available_date": "2026-04-20",
                                },
                            },
                            "batch_sparkline_only": {
                                "summary": "Batch sparkline only (include_articles=false)",
                                "value": {
                                    "results": {
                                        "Trump": [{"date": "2026-04-20", "counts": 45655115, "rank": 455}],
                                        "COVID": [{"date": "2026-04-20", "counts": 775676, "rank": 19105}],
                                    },
                                    "latest_available_date": "2026-04-20",
                                },
                            },
                        },
                    }
                },
            }
        },
        "x-performance": {
            "fast_path": "~20-200ms depending on number of terms (all in precomputed vocabulary)",
            "mixed_path": "If some terms are in vocabulary and some aren't, fast terms return in ~50ms and slow terms add ~3-5s",
            "sparkline_only": "~20-40ms with include_articles=false",
        },
        "x-frontend-notes": {
            "typical_usage": "Used to fetch sparklines for multiple terms at once, e.g. all terms from an RTD wordshift comparison. Pass the wordshift types as comma-separated values.",
            "missing_terms": "Terms not found in any data source return an empty array in results. All requested terms always appear as keys.",
            "same_schema_as_single": "Each entry in results[term] has the same shape as entries in the /term-series series array.",
        },
    },
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

    ngrams_tr = ngrams_obj.transform or {}
    partition_map = (ngrams_tr.get("partition_dimensions") or {})
    if isinstance(partition_map, list):
        partition_map = {dim: None for dim in partition_map}
    ngrams_filter_vals: dict = {}
    if "granularity" in partition_map:
        ngrams_filter_vals["granularity"] = granularity
    if "ngram_size" in partition_map:
        ngrams_filter_vals["ngram_size"] = n
    entity_path = _entity_base_path(ngrams_obj, local_id, ngrams_filter_vals)
    latest_date = _latest_from_manifest(ngrams_obj, local_id, granularity)

    if not date:
        if not latest_date:
            return JSONResponse(
                status_code=404,
                content={"detail": "No data found for this entity", "latest_available_date": None},
            )
        date = latest_date

    try:
        end = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date: {date}")

    if window > 0:
        start = end - timedelta(days=window)
        start_str = start.strftime("%Y-%m-%d")
    else:
        start_str = None

    type_list = [t.strip() for t in types.split(",") if t.strip()]
    if not type_list:
        raise HTTPException(status_code=400, detail="types parameter must contain at least one term")

    placeholders = ", ".join(["?"] * len(type_list))
    date_filter = "AND date BETWEEN ? AND ?" if start_str else "AND date <= ?"
    date_params = [start_str, date] if start_str else [date]

    # Articles date filter: when articles_dates is provided, fetch articles
    # only for those specific dates (e.g. the two allotax comparison dates)
    # instead of the full sparkline window.
    if articles_dates:
        art_date_list = [d.strip() for d in articles_dates.split(",") if d.strip()]
        art_placeholders = ", ".join(["?"] * len(art_date_list))
        art_date_filter = f"AND date IN ({art_placeholders})"
        art_date_params = art_date_list
    else:
        art_date_filter = date_filter
        art_date_params = date_params

    # ── Fast path: sequential point lookups on sorted Parquet files ──
    # Sparkline/article precomputed data is daily-only; skip for weekly/monthly.
    sparkline_rows = []
    articles_by_key: dict = {}  # (ngram, date_str) -> [[url, score], ...]
    found_terms: set = set()
    use_fast_path = granularity == "daily"

    if use_fast_path:
        with timed("registry", "Sparkline registry lookup"):
            sparkline_obj = await get_latest_entry(db, "wikimedia", "sparklines")
            top_articles_obj = await get_latest_entry(db, "wikimedia", "top_articles_ngrams")
    else:
        sparkline_obj = None
        top_articles_obj = None

    if sparkline_obj:
        encoded_country = quote(str(local_id), safe="")
        sparkline_path = f"{sparkline_obj.data_location}/ngram_size={n}/country={encoded_country}/data_0.parquet"

        with timed("fast_query", "DuckDB sparkline + articles read"):
            conn = get_duckdb_client().connect()
            try:
                sparkline_rows = conn.execute(
                    f"""
                    SELECT ngram, date, pv_count, pv_rank, pv_freq
                    FROM read_parquet('{sparkline_path}')
                    WHERE ngram IN ({placeholders})
                      {date_filter}
                    ORDER BY ngram, date
                    """,
                    [*type_list, *date_params],
                ).fetchall()

                found_terms = {row[0] for row in sparkline_rows}

                if include_articles and found_terms and top_articles_obj:
                    try:
                        # Compute which buckets contain our terms, then pass all
                        # matching bucket files as a list so DuckDB can parallelise I/O
                        # (critical on NFS where sequential file opens are expensive).
                        buckets = {hashlib.md5(t.encode("utf-8")).hexdigest()[0] for t in found_terms}
                        articles_base = f"{top_articles_obj.data_location}/ngram_size={n}/country={encoded_country}"
                        bucket_files = [f"{articles_base}/ngram_bucket={b}/data_0.parquet" for b in buckets]
                        file_list = ", ".join(f"'{f}'" for f in bucket_files)
                        found_placeholders = ", ".join(["?"] * len(found_terms))
                        art_rows = conn.execute(
                            f"""
                            SELECT ngram, date, article_url, score
                            FROM read_parquet([{file_list}])
                            WHERE ngram IN ({found_placeholders})
                              {art_date_filter}
                            ORDER BY ngram, date, article_rank
                            """,
                            [*list(found_terms), *art_date_params],
                        ).fetchall()
                        for row in art_rows:
                            key = (row[0], str(row[1]))
                            articles_by_key.setdefault(key, []).append(
                                [row[2], float(row[3]) if row[3] else 0.0]
                            )
                    except Exception:
                        pass  # articles files may not exist yet
            except Exception:
                sparkline_rows = []
                found_terms = set()

    # ── Slow path: daily partition fallback for missing terms ──
    missing_terms = [t for t in type_list if t not in found_terms]
    slow_results: dict = {}
    if missing_terms:
        with timed("slow_query", "DuckDB daily partition scan"):
            conn = get_duckdb_client().connect()
            glob_pattern = f"{entity_path}/date=*/data_0.parquet"
            slow_placeholders = ", ".join(["?"] * len(missing_terms))

            if include_articles and use_fast_path:
                # top_articles column only exists in daily partition files
                slow_rows = conn.execute(
                    f"""
                    SELECT ngram, date, pv_count, pv_rank, pv_freq, top_articles
                    FROM read_parquet('{glob_pattern}', hive_partitioning=true)
                    WHERE ngram IN ({slow_placeholders})
                      {date_filter}
                    ORDER BY ngram, date
                    """,
                    [*missing_terms, *date_params],
                ).fetchall()
            else:
                slow_rows = conn.execute(
                    f"""
                    SELECT ngram, date, pv_count, pv_rank, pv_freq
                    FROM read_parquet('{glob_pattern}', hive_partitioning=true)
                    WHERE ngram IN ({slow_placeholders})
                      {date_filter}
                    ORDER BY ngram, date
                    """,
                    [*missing_terms, *date_params],
                ).fetchall()

            art_date_set = set(art_date_list) if articles_dates else None
            for row in slow_rows:
                ngram = row[0]
                date_str = str(row[1])
                entry = {
                    "date": date_str,
                    "counts": int(row[2]) if row[2] else 0,
                    "rank": int(row[3]) if row[3] else 0,
                    "freq": float(row[4]) if row[4] else 0.0,
                }
                if include_articles and use_fast_path:
                    # Only parse articles for requested dates (daily only)
                    if art_date_set is None or date_str in art_date_set:
                        top_articles = []
                        if row[5]:
                            for article in row[5]:
                                if len(article) >= 2:
                                    try:
                                        top_articles.append([article[0], float(article[1])])
                                    except (ValueError, TypeError):
                                        top_articles.append([article[0], 0.0])
                        entry["top_articles"] = top_articles
                    else:
                        entry["top_articles"] = []
                slow_results.setdefault(ngram, []).append(entry)

    # ── Merge results ──
    results: dict = {t: [] for t in type_list}
    for row in sparkline_rows:
        ngram = row[0]
        date_str = str(row[1])
        entry = {
            "date": date_str,
            "counts": int(row[2]) if row[2] else 0,
            "rank": int(row[3]) if row[3] else 0,
            "freq": float(row[4]) if row[4] else 0.0,
        }
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

    encoded_country = quote(str(local_id), safe="")
    path = f"{rtd_obj.data_location}/ngram_size={n}/country={encoded_country}/data_0.parquet"

    with timed("query", "DuckDB precomputed RTD read"):
        conn = get_duckdb_client().connect()
        with handle_query_error("wikimedia/precomputed_rtd"):
            rows = conn.execute(
                f"""
                SELECT ngram, date, date_delta, divergence, alpha, granularity
                FROM read_parquet('{path}')
                WHERE date = ? AND date_delta = ? AND granularity = ? AND alpha = ?
                ORDER BY ABS(divergence) DESC
                LIMIT ?
                """,
                [date, date_delta, granularity, alpha, limit],
            ).fetchall()

    return {
        "data": [
            {
                "type": r[0],
                "date": str(r[1]),
                "date_delta": r[2],
                "divergence": r[3],
                "alpha": r[4],
                "granularity": r[5],
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