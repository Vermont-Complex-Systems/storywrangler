"""
Babynames API endpoints.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from ..core.database import get_session
from ..core.duckdb_client import get_duckdb_client
from ..core.query_utils import load_system, parse_dates, resolve_entity
from ..core.registry_utils import get_latest_entry

router = APIRouter()


@router.get(
    "/ngrams",
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
                                    "description": "Baby name frequency entries sorted by count descending.",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "types": {"type": "string", "description": "The baby name"},
                                            "counts": {"type": "integer", "description": "Number of babies given this name in the date range"},
                                        },
                                    },
                                },
                                "metadata": {
                                    "type": "object",
                                    "description": "Request metadata echoed back",
                                    "properties": {
                                        "location": {"type": "string", "description": "Entity ID used"},
                                        "sex": {"type": "string", "description": "Sex filter applied (M, F, or null)"},
                                    },
                                },
                            },
                        },
                        "example": {
                            "data": [
                                {"types": "James", "counts": 85234},
                                {"types": "John", "counts": 79102},
                                {"types": "Robert", "counts": 75680},
                            ],
                            "metadata": {"location": "wikidata:Q30", "sex": "M"},
                        },
                    }
                },
            }
        }
    },
)
async def get_babynames_top_ngrams(
    dates: str = Query(default="1991,1993", description="Year range for system 1. Single value '1991' or range '1991,1993'"),
    dates2: Optional[str] = Query(default=None, description="Optional second year range for temporal comparison"),
    locations: str = Query(default="wikidata:Q30", description="Entity ID (e.g. 'wikidata:Q30') or local ID (e.g. 'united_states')"),
    sex: Optional[str] = Query(default="M", description="Sex filter: M | F | None to omit"),
    limit: int = Query(default=100),
    db: AsyncSession = Depends(get_session),
):
    """Get top baby names with optional temporal comparison.
    """
    dataset_obj = await get_latest_entry(db, "babynames", "ngrams")
    if not dataset_obj:
        raise HTTPException(status_code=404, detail="'babynames/ngrams' dataset not found")

    em = await resolve_entity(db, "babynames", "ngrams", locations)

    filter_vals = {"sex": sex} if sex else {}

    try:
        conn = get_duckdb_client().connect()
        dr1 = parse_dates(dates)
        sys1 = load_system(conn, dataset_obj, em.local_id, dr1, filter_vals, limit)
        formatted1 = [{"types": t, "counts": c} for t, c in zip(sys1["types"], sys1["counts"])]

        if dates2:
            dr2 = parse_dates(dates2)
            sys2 = load_system(conn, dataset_obj, em.local_id, dr2, filter_vals, limit)
            formatted2 = [{"types": t, "counts": c} for t, c in zip(sys2["types"], sys2["counts"])]
            key1 = dr1[0] if dr1[0] == dr1[1] else f"{dr1[0]}-{dr1[1]}"
            key2 = dr2[0] if dr2[0] == dr2[1] else f"{dr2[0]}-{dr2[1]}"
            return {
                key1: formatted1,
                key2: formatted2,
                "metadata": {"location": locations, "sex": sex},
            }

        return {
            "data": formatted1,
            "metadata": {"location": locations, "sex": sex},
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query execution failed: {str(e)}")
