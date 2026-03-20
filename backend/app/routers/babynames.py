"""
Babynames API endpoints.
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

_BabynamesEntry = select(RegistryEntry).where(RegistryEntry.domain == "babynames")


@router.get("/ngrams")
async def get_babynames_top_ngrams(
    dates: str = Query(default="1991,1993", description="Year range for system 1. Single value '1991' or range '1991,1993'"),
    dates2: Optional[str] = Query(default=None, description="Optional second year range for temporal comparison"),
    locations: str = Query(default="wikidata:Q30", description="Global entity ID, e.g. 'wikidata:Q30' (United States)"),
    sex: Optional[str] = Query(default="M", description="Sex filter: M | F | None to omit"),
    limit: int = Query(default=100),
    db: AsyncSession = Depends(get_session),
):
    """Get top baby names with optional temporal comparison.
    """
    result = await db.execute(_BabynamesEntry.where(RegistryEntry.dataset_id == "ngrams"))
    dataset_obj = result.scalar_one_or_none()
    if not dataset_obj:
        raise HTTPException(status_code=404, detail="'babynames/ngrams' dataset not found")

    em = await resolve_entity(db, "babynames", "ngrams", locations)

    def parse_dr(s: str) -> List[str]:
        parts = s.split(",")
        return [parts[0], parts[0]] if len(parts) == 1 else [parts[0], parts[1]]

    filter_vals = {"sex": sex} if sex else {}

    try:
        conn = get_duckdb_client().connect()
        dr1 = parse_dr(dates)
        sys1 = load_system(conn, dataset_obj, em.local_id, dr1, filter_vals, None, limit)
        formatted1 = [{"types": t, "counts": c} for t, c in zip(sys1["types"], sys1["counts"])]

        if dates2:
            dr2 = parse_dr(dates2)
            sys2 = load_system(conn, dataset_obj, em.local_id, dr2, filter_vals, None, limit)
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
