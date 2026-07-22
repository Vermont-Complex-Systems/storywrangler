"""
Zoning bylaws API endpoints.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from ..core.database import get_session
from ..core.duckdb_client import get_duckdb_client, run_blocking
from ..core.duckdb_query import handle_query_error, load_system
from ..core.query_utils import resolve_entity
from ..core.registry_utils import get_latest_entry
from . import openapi_docs as docs

router = APIRouter()


@router.get(
    "/top-ngrams",
    openapi_extra={**docs.ZONING_BYLAWS_GET_ZONING_BYLAWS_NGRAMS, "x-dataset": "ngrams"},
)
async def get_zoning_bylaws_ngrams(
    entity: str = Query(default="Arlington", description="Town name (e.g. 'Arlington') or Wikidata entity ID (e.g. 'wikidata:Q675558')."),
    limit: int = Query(default=100),
    db: AsyncSession = Depends(get_session),
):
    """Get top words from a town's zoning bylaw."""
    dataset_obj = await get_latest_entry(db, "vt-zoning-atlas", "ngrams")
    if not dataset_obj:
        raise HTTPException(status_code=404, detail="'vt-zoning-atlas/ngrams' dataset not found")

    em = await resolve_entity(db, "vt-zoning-atlas", "ngrams", entity)

    def _query():
        with handle_query_error("vt-zoning-atlas/ngrams"):
            with get_duckdb_client().timed_connect() as conn:
                sys1 = load_system(conn, dataset_obj, em.local_id, None, {}, limit)
                formatted = [{"types": t, "counts": c} for t, c in zip(sys1["types"], sys1["counts"])]
                return {
                    "data": formatted,
                    "metadata": {"location": entity},
                }

    return await run_blocking(_query)
