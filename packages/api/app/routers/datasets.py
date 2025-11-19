# packages/api/app/routers/datasets.py

"""
Core dataset routes
"""

from fastapi import APIRouter

router = APIRouter(
    prefix="/api",
    tags=["datasets"]
)


@router.get("/datasets")
async def list_datasets():
    """List all available datasets"""
    # TODO: load from database
    return {
        "datasets": [
            {
                "id": "women-in-math",
                "name": "Women in Mathematics",
                "description": "Biographical data of women mathematicians",
                "specification_version": "0.0.1"
            }
        ]
    }