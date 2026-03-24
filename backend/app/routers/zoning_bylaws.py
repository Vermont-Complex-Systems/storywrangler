"""
Zoning bylaws API endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..core.database import get_session
from ..core.duckdb_client import get_duckdb_client
from ..core.query_utils import load_system, resolve_entity
from ..models.registry import RegistryEntry

router = APIRouter()

_ZoningBylawsEntry = select(RegistryEntry).where(RegistryEntry.domain == "vt-zoning-atlas")


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
                                    "description": "Top words in the town's zoning bylaw, sorted by frequency descending.",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "types": {"type": "string", "description": "Word token"},
                                            "counts": {"type": "integer", "description": "Frequency count of the word"},
                                        },
                                    },
                                },
                                "metadata": {
                                    "type": "object",
                                    "description": "Request metadata echoed back",
                                    "properties": {
                                        "location": {"type": "string", "description": "Entity ID used"},
                                    },
                                },
                            },
                        },
                        "example": {
                            "data": [
                                {"types": "the", "counts": 4394},
                                {"types": "of", "counts": 2559},
                                {"types": "and", "counts": 1956},
                            ],
                            "metadata": {"location": "Arlington"},
                        },
                    }
                },
            }
        }
    },
)
async def get_zoning_bylaws_ngrams(
    locations: str = Query(default="Arlington", description="Town name (e.g. 'Arlington') or Wikidata entity ID (e.g. 'wikidata:Q675558')"),
    limit: int = Query(default=100),
    db: AsyncSession = Depends(get_session),
):
    """Get top words from a town's zoning bylaw."""
    result = await db.execute(_ZoningBylawsEntry.where(RegistryEntry.dataset_id == "ngrams"))
    dataset_obj = result.scalar_one_or_none()
    if not dataset_obj:
        raise HTTPException(status_code=404, detail="'vt-zoning-atlas/ngrams' dataset not found")

    em = await resolve_entity(db, "vt-zoning-atlas", "ngrams", locations)

    try:
        conn = get_duckdb_client().connect()
        sys1 = load_system(conn, dataset_obj, em.local_id, None, {}, None, limit)
        formatted = [{"types": t, "counts": c} for t, c in zip(sys1["types"], sys1["counts"])]
        return {
            "data": formatted,
            "metadata": {"location": locations},
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query execution failed: {str(e)}")
