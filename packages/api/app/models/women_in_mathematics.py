# packages/api/app/models/women_in_mathematics.py

"""
Pydantic models for Women in Mathematics dataset
"""

from pydantic import BaseModel, field_validator
from typing import List, Optional
from storywrangler.validation import EntityValidator


class BiographicalData(BaseModel):
    birth_year: Optional[int] = None
    death_year: Optional[int] = None
    birthplace: Optional[str] = None
    field: str  # Wikidata field ID


class Author(BaseModel):
    """Author entity for women-in-math dataset"""
    entity_id: str
    entity_ids: Optional[List[str]] = None  # Alternate IDs
    entity_type: str = "person"
    confidence: float
    name: str
    biographical_data: BiographicalData
    
    @field_validator('entity_id')
    @classmethod
    def validate_entity_id(cls, v):
        validator = EntityValidator()
        if not validator.validate(v):
            raise ValueError(f'Invalid entity_id: {v}')
        return v
    
    @field_validator('entity_ids')
    @classmethod
    def validate_entity_ids(cls, v):
        if v is None:
            return v
        validator = EntityValidator()
        for eid in v:
            if not validator.validate(eid):
                raise ValueError(f'Invalid alternate entity_id: {eid}')
        return v


class DatasetSubmission(BaseModel):
    dataset_id: str = "women-in-math"
    name: str
    specification_version: str
    description: str
    authors: List[Author]


class IngestRequest(BaseModel):
    entity_id: str
    text: str


class Ngrams(BaseModel):
    ngram: List[str]
    count: List[int]