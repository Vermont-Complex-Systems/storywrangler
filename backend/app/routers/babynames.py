"""
Babynames API endpoints.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from ..core.database import get_session
from ..core.query_utils import resolve_entity
from ..core.registry_utils import get_latest_entry
from ..core.term_series import run_top_ngrams
from . import openapi_docs as docs

router = APIRouter()


@router.get(
    "/top-ngrams",
    openapi_extra={**docs.BABYNAMES_GET_BABYNAMES_TOP_NGRAMS, "x-dataset": "ngrams"},
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

    return await run_top_ngrams(
        dataset_obj, "babynames/ngrams", em.local_id, dates, dates2,
        {"sex": sex} if sex else {}, limit,
        metadata={"location": locations, "sex": sex},
        range_sep="-",
    )
