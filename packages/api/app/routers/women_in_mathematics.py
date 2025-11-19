# packages/api/app/routers/women_in_mathematics.py

"""
Women in Mathematics dataset routes
"""

from fastapi import APIRouter, HTTPException
from app.models.women_in_mathematics import (
    Author,
    DatasetSubmission,
    IngestRequest,
    Ngrams
)
from storywrangler.text import TextProcessor


router = APIRouter(
    prefix="/api/women-in-math",
    tags=["women-in-math"]
)


@router.post("")
async def submit_dataset(dataset: DatasetSubmission):
    """Submit women-in-math dataset metadata"""
    # Entity IDs already validated by Pydantic
    # TODO: save to database
    
    return {
        "status": "success",
        "dataset_id": "women-in-math",
        "authors": len(dataset.authors)
    }


@router.get("")
async def get_dataset():
    """Get dataset metadata"""
    # TODO: load from database
    return {
        "dataset_id": "women-in-math",
        "name": "Women in Mathematics",
        "specification_version": "0.0.1"
    }


@router.get("/authors")
async def list_authors():
    """List all authors"""
    # TODO: load from database
    return {"authors": []}


@router.get("/authors/{entity_id:path}")
async def get_author(entity_id: str) -> Author:
    """Get specific author by entity_id"""
    # TODO: load from database
    pass


@router.post("/ingest")
async def ingest_text(request: IngestRequest):
    """Ingest biography text for n-gram extraction"""
    
    # TODO: verify entity exists
    
    # Extract n-grams
    processor = TextProcessor()
    ngrams = processor.extract_ngrams(request.text, max_n=3)
    
    # TODO: save to database
    
    return {
        "status": "success",
        "entity_id": request.entity_id,
        "ngrams_extracted": len(ngrams)
    }


@router.get("/ngrams")
async def get_dataset_ngrams(n: int = 1, limit: int = 100):
    """Get top n-grams across all biographies"""
    # TODO: aggregate from database
    pass


@router.get("/authors/{entity_id:path}/ngrams")
async def get_author_ngrams(entity_id: str, n: int = 1) -> Ngrams:
    """Get n-grams for specific author"""
    # TODO: load from database
    pass