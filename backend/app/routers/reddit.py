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