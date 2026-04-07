"""
SQLModel ORM models for the dataset registry (metadata catalog).

These use the new "registry" and "registry_entity_mappings" tables, which live alongside
the legacy "datasets" and "entity_mappings" tables owned by complex-stories-dev.
The legacy tables are untouched — this new backend reads/writes only to "registry".
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Column, DateTime, JSON, String, UniqueConstraint
from sqlalchemy.sql import func
from sqlmodel import Field, SQLModel


class RegistryEntryBase(SQLModel):
    """Scalar fields shared between the ORM table and any derived schemas.

    The four-level identity is: catalog.domain.dataset_id@version
      catalog    — producing organisation (e.g. 'vcsi')
      domain     — owning service (e.g. 'wikimedia', 'babynames')
      dataset_id — name within domain (e.g. 'ngrams', 'revisions')
      version    — 'latest' (mutable) or semver string (immutable snapshot)
    """

    catalog: str = "vcsi"
    domain: str = Field(primary_key=True)
    dataset_id: str = Field(primary_key=True)
    version: str = Field(default="latest", primary_key=True)
    data_location: Optional[Any] = Field(default=None, sa_column=Column(JSON))
    data_format: str = "parquet_hive"
    description: str = None


class RegistryEntry(RegistryEntryBase, table=True):
    """One entry in the dataset registry."""

    __tablename__ = "registry"

    # JSON columns — stored as plain dicts; Pydantic validation happens in DatasetCreate
    manifest: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    entity_mapping: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    endpoint_schema: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    transform: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    ownership: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    lineage: Optional[dict] = Field(default=None, sa_column=Column(JSON))

    # Schema version — which storywrangler-schemas release governed this registration
    schema_version: Optional[str] = Field(default=None)

    # Derived at registration — never submitted, always backend-computed
    data_schema: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    filter_values: Optional[dict] = Field(default=None, sa_column=Column(JSON))

    # Partition index — submitted by owner for parquet_hive datasets with
    # enumerable partitions (e.g. wikimedia/revisions article list).
    # Excluded from summary registry responses via load_only.
    partition_index: Optional[list] = Field(default=None, sa_column=Column(JSON))

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
    """Entity mappings: dataset-local IDs ↔ canonical entity IDs (e.g. Wikidata QIDs).

    Version-agnostic: entity rows represent the canonical lookup table for a dataset
    identity (domain + dataset_id) across all versions. The FK to registry was removed
    because the registry PK is now (domain, dataset_id, version) — referential integrity
    is enforced at the application level in the registry router.
    """

    __tablename__ = "registry_entity_mappings"

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


class EntityGraph(SQLModel, table=True):
    """Cross-namespace entity relationships for dataset federation.

    Stores directed edges of the form:
        subject_id --[predicate]--> object_id

    Predicates (controlled vocabulary):
        affiliated_with — author belongs to institution   (openalex:A → openalex:I)
        same_as         — cross-namespace identity         (openalex:I → wikidata:Q)
        country         — institution is in country        (openalex:I → wikidata:Q)
        broader         — concept hierarchy                (openalex:C → openalex:C)

    Together these edges enable multi-hop graph traversal, e.g.:
        openalex:A5002034958
          --affiliated_with--> openalex:I26873012   (UVM)
          --same_as----------> wikidata:Q1068        (UVM on Wikidata)
          --country----------> wikidata:Q30          (United States)
          ↕ shared namespace
        babynames entity_id: wikidata:Q30

    source: who asserted this edge — "openalex" | "wikidata" | "manual"
    """

    __tablename__ = "entity_graph"
    __table_args__ = (
        UniqueConstraint("subject_id", "predicate", "object_id", name="uq_entity_graph_edge"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    subject_id: str = Field(index=True)    # e.g. "openalex:A5002034958"
    predicate: str                          # e.g. "affiliated_with"
    object_id: str = Field(index=True)     # e.g. "openalex:I26873012"
    source: str                             # e.g. "openalex"

    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now()),
    )

    def __repr__(self) -> str:
        return f"<EntityGraph('{self.subject_id}' --{self.predicate}--> '{self.object_id}')>"
