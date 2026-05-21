"""
Reddit endpoints — subreddit n-grams and term time series.
"""

from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from ..core.database import get_session
from ..core.duckdb_client import get_duckdb_client
from ..core.query_utils import (
    assign_bucket, build_hive_path, entity_base_path, get_bucket_config,
    get_queryable_dims, handle_query_error, latest_from_manifest, load_system,
    parse_dates, resolve_bucket_count, resolve_entity,
)
from ..core.registry_utils import get_latest_entry
from ..core.timing import timed

router = APIRouter()


# ── top-ngrams ────────────────────────────────────────────────────────────────

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
                                        "entity": {"type": "string", "description": "Entity ID used"},
                                    },
                                },
                            },
                        },
                        "example": {
                            "data": [
                                {"types": "the", "counts": 12345678},
                                {"types": "of", "counts": 9876543},
                            ],
                            "metadata": {"granularity": "daily", "entity": "AskReddit"},
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

    fv = dataset_obj.filter_values or {}
    queryable = get_queryable_dims(dataset_obj)

    if "granularity" in queryable:
        valid = fv.get("granularity", [])
        if valid and granularity not in valid:
            raise HTTPException(
                status_code=400,
                detail=f"granularity must be one of {sorted(valid)}",
            )

    if "ngram_size" in queryable:
        valid_n = fv.get("ngram_size", [])
        if valid_n and n not in valid_n:
            raise HTTPException(
                status_code=400,
                detail=f"n must be one of {sorted(valid_n)}",
            )

    em = await resolve_entity(db, "reddit", "ngrams", entity)

    extra: dict = {}
    if "granularity" in queryable:
        extra["granularity"] = granularity
    if "ngram_size" in queryable:
        extra["ngram_size"] = n

    with handle_query_error("reddit/ngrams"):
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
                "metadata": {"granularity": granularity, "entity": entity},
            }

        return {
            "data": formatted1,
            "metadata": {"granularity": granularity, "entity": entity},
        }


# ── shared term-series helpers ───────────────────────────────────────────────

def _resolve_ngrams_context(ngrams_obj, local_id, granularity, n):
    """Build filter_vals and base path for term-series queries."""
    _dim_values = {"granularity": granularity, "ngram_size": n}
    ngrams_dims = get_queryable_dims(ngrams_obj)
    ngrams_filter_vals: dict = {
        dim: _dim_values[dim] for dim in ngrams_dims if dim in _dim_values
    }
    base_path = entity_base_path(ngrams_obj, local_id, ngrams_filter_vals)
    return ngrams_filter_vals, base_path


def _build_date_filter(date_str, window):
    """Parse date/window into SQL filter clause and params."""
    try:
        end = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date: {date_str}")

    if window > 0:
        start = end - timedelta(days=window)
        start_str = start.strftime("%Y-%m-%d")
    else:
        start_str = None

    date_filter = "date BETWEEN ? AND ?" if start_str else "date <= ?"
    date_params = [start_str, date_str] if start_str else [date_str]
    return date_filter, date_params


# ── term-series ───────────────────────────────────────────────────────────────

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
                                    "description": "Most recent date with data for this entity.",
                                },
                                "series": {
                                    "type": "array",
                                    "description": "Time series entries, one per date, sorted chronologically.",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "date": {"type": "string", "format": "date"},
                                            "counts": {"type": "integer", "description": "Total count for this term on this date"},
                                            "rank": {"type": "integer", "description": "Rank by count on this date (1 = most frequent). 0 means not ranked."},
                                        },
                                    },
                                },
                            },
                        },
                        "example": {
                            "type": "trump",
                            "latest_available_date": "2026-04-20",
                            "series": [
                                {"date": "2026-04-19", "counts": 41964, "rank": 487},
                                {"date": "2026-04-20", "counts": 45655, "rank": 455},
                            ],
                        },
                    }
                },
            }
        },
    },
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

    ngrams_filter_vals, base_path = _resolve_ngrams_context(ngrams_obj, local_id, granularity, n)

    with timed("discover", "Latest date from manifest"):
        latest_date = latest_from_manifest(ngrams_obj, local_id, granularity)

    if not date:
        if not latest_date:
            return JSONResponse(
                status_code=404,
                content={"detail": "No data found for this entity", "latest_available_date": None},
            )
        date = latest_date

    date_filter, date_params = _build_date_filter(date, window)

    # ── Sparkline fast path (when sparklines dataset is registered) ──
    sparkline_rows = []
    with timed("registry", "Sparkline registry lookup"):
        sparkline_obj = await get_latest_entry(db, "reddit", "sparklines")

    if sparkline_obj:
        spark_hb = get_bucket_config(sparkline_obj)
        bucket = assign_bucket(type, resolve_bucket_count(spark_hb, local_id, n))
        sparkline_path = build_hive_path(
            sparkline_obj,
            filter_vals={"ngram_size": n},
            entity_value=local_id,
            bucket_value=bucket,
            glob_suffix="/data_0.parquet",
        )
        with timed("fast_query", "DuckDB sparkline read"):
            conn = get_duckdb_client().connect()
            try:
                sparkline_rows = conn.execute(
                    f"""
                    SELECT date, pv_count, pv_rank, pv_freq
                    FROM read_parquet('{sparkline_path}')
                    WHERE ngram = ? AND {date_filter}
                    ORDER BY date
                    """,
                    [type, *date_params],
                ).fetchall()
            except Exception:
                sparkline_rows = []

    # ── Slow path: scan daily partitions ──
    if not sparkline_rows:
        with timed("slow_query", "DuckDB daily partition scan"):
            conn = get_duckdb_client().connect()
            glob_pattern = f"{base_path}/date=*/data_0.parquet"

            with handle_query_error("reddit/ngrams"):
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
                series.append({
                    "date": str(row[0]),
                    "counts": int(row[1]) if row[1] else 0,
                    "rank": int(row[2]) if row[2] else 0,
                    "freq": float(row[3]) if row[3] else 0.0,
                })

            return {
                "type": type,
                "latest_available_date": latest_date,
                "series": series,
            }

    # ── Assemble response from fast path results ──
    series = []
    for row in sparkline_rows:
        series.append({
            "date": str(row[0]),
            "counts": int(row[1]) if row[1] else 0,
            "rank": int(row[2]) if row[2] else 0,
            "freq": float(row[3]) if row[3] else 0.0,
        })

    return {
        "type": type,
        "latest_available_date": latest_date,
        "series": series,
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

    ngrams_filter_vals, base_path = _resolve_ngrams_context(ngrams_obj, local_id, granularity, n)
    latest_date = latest_from_manifest(ngrams_obj, local_id, granularity)

    if not date:
        if not latest_date:
            return JSONResponse(
                status_code=404,
                content={"detail": "No data found for this entity", "latest_available_date": None},
            )
        date = latest_date

    date_filter, date_params = _build_date_filter(date, window)

    type_list = [t.strip() for t in types.split(",") if t.strip()]
    if not type_list:
        raise HTTPException(status_code=400, detail="types parameter must contain at least one term")

    placeholders = ", ".join(["?"] * len(type_list))

    # ── Fast path: sparkline bucket lookups ──
    sparkline_rows = []
    found_terms: set = set()

    sparkline_obj = await get_latest_entry(db, "reddit", "sparklines")

    if sparkline_obj:
        spark_hb = get_bucket_config(sparkline_obj)
        spark_n_buckets = resolve_bucket_count(spark_hb, local_id, n)
        spark_buckets = {assign_bucket(t, spark_n_buckets) for t in type_list}
        spark_bucket_files = [
            build_hive_path(
                sparkline_obj, filter_vals={"ngram_size": n},
                entity_value=local_id, bucket_value=b,
                glob_suffix="/data_0.parquet",
            )
            for b in spark_buckets
        ]
        spark_file_list = ", ".join(f"'{f}'" for f in spark_bucket_files)

        with timed("fast_query", "DuckDB sparkline batch read"):
            conn = get_duckdb_client().connect()
            try:
                sparkline_rows = conn.execute(
                    f"""
                    SELECT ngram, date, pv_count, pv_rank, pv_freq
                    FROM read_parquet([{spark_file_list}])
                    WHERE ngram IN ({placeholders})
                      AND {date_filter}
                    ORDER BY ngram, date
                    """,
                    [*type_list, *date_params],
                ).fetchall()
                found_terms = {row[0] for row in sparkline_rows}
            except Exception:
                sparkline_rows = []
                found_terms = set()

    # ── Slow path: daily partition fallback for missing terms ──
    missing_terms = [t for t in type_list if t not in found_terms]
    slow_results: dict = {}
    if missing_terms:
        with timed("slow_query", "DuckDB daily partition scan"):
            conn = get_duckdb_client().connect()
            glob_pattern = f"{base_path}/date=*/data_0.parquet"
            slow_placeholders = ", ".join(["?"] * len(missing_terms))

            try:
                slow_rows = conn.execute(
                    f"""
                    SELECT ngram, date, pv_count, pv_rank, pv_freq
                    FROM read_parquet('{glob_pattern}', hive_partitioning=true)
                    WHERE ngram IN ({slow_placeholders})
                      AND {date_filter}
                    ORDER BY ngram, date
                    """,
                    [*missing_terms, *date_params],
                ).fetchall()
            except Exception:
                slow_rows = []

            for row in slow_rows:
                ngram = row[0]
                slow_results.setdefault(ngram, []).append({
                    "date": str(row[1]),
                    "counts": int(row[2]) if row[2] else 0,
                    "rank": int(row[3]) if row[3] else 0,
                    "freq": float(row[4]) if row[4] else 0.0,
                })

    # ── Merge results ──
    results: dict = {t: [] for t in type_list}
    for row in sparkline_rows:
        ngram = row[0]
        results[ngram].append({
            "date": str(row[1]),
            "counts": int(row[2]) if row[2] else 0,
            "rank": int(row[3]) if row[3] else 0,
            "freq": float(row[4]) if row[4] else 0.0,
        })
    for ngram, entries in slow_results.items():
        results[ngram] = entries

    return {
        "results": results,
        "latest_available_date": latest_date,
    }
