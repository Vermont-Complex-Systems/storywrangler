"""
SQLModel ORM models for the dataset registry (metadata catalog).

These use the new "registry" and "registry_entity_mappings" tables, which live alongside
the legacy "datasets" and "entity_mappings" tables owned by complex-stories-dev.
The legacy tables are untouched — this new backend reads/writes only to "registry".
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, ForeignKeyConstraint, JSON, String
from sqlalchemy.sql import func
from sqlmodel import Field, SQLModel


class RegistryEntryBase(SQLModel):
    """Scalar fields shared between the ORM table and any derived schemas.

    The three-level namespace is: catalog.domain.dataset_id
      catalog    — producing organisation (e.g. 'vcsi')
      domain     — owning service (e.g. 'wikimedia', 'babynames')
      dataset_id — name within domain (e.g. 'ngrams', 'revisions')
    """

    catalog: str = "vcsi" 
    domain: str = Field(primary_key=True)
    dataset_id: str = Field(primary_key=True)
    data_location: str
    data_format: str = "parquet_hive"
    description: str = None


class RegistryEntry(RegistryEntryBase, table=True):
    """One entry in the dataset registry."""

    __tablename__ = "registry"

    # JSON columns — stored as plain dicts; Pydantic validation happens in DatasetCreate
    format_config: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    entity_mapping: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    endpoint_schema: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    ownership: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    lineage: Optional[dict] = Field(default=None, sa_column=Column(JSON))

    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now()),
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), onupdate=func.now()),
    )

    def __repr__(self) -> str:
        return f"<RegistryEntry(domain='{self.domain}', id='{self.dataset_id}', format='{self.data_format}')>"


class EntityMapping(SQLModel, table=True):
    """Entity mappings: dataset-local IDs ↔ canonical entity IDs (e.g. Wikidata QIDs)."""

    __tablename__ = "registry_entity_mappings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["domain", "dataset_id"],
            ["registry.domain", "registry.dataset_id"],
        ),
    )

    id: str = Field(
        sa_column=Column(String, primary_key=True),
        description="Composite key: domain:dataset_id:local_id",
    )
    domain: str
    dataset_id: str
    local_id: str
    entity_id: str           # canonical identifier, e.g. 'wikidata:Q30'
    entity_name: str
    entity_ids: Optional[list] = Field(default=None, sa_column=Column(JSON))
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now()),
    )

    def __repr__(self) -> str:
        return f"<EntityMapping(local='{self.local_id}', entity='{self.entity_id}')>"
