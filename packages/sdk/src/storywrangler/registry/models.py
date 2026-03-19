"""
Pydantic models mirroring the backend DatasetCreate / EntityMappingConfig.

These are the client-side counterparts of the models defined in:
  complex-stories-dev/backend/app/routers/registry.py

Keeping these in sync with the backend is the submitter's contract.
When the backend adds or changes a field, update here too — the SDK
will then raise a ValidationError at submission time rather than
returning a 422 from the API.
"""

from typing import Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field, model_validator

from ..validation.endpoints import EndpointValidator


class EntityMappingConfig(BaseModel):
    """Schema declaration for entity ID resolution.

    Describes entity_type and local_id_column. The actual mapping rows (local_id →
    entity_id) are submitted separately via the 'entities' field in DatasetCreate or
    via the POST /admin/registry/{domain}/{dataset_id}/entities batch endpoint.
    """

    entity_type: str = Field(
        ...,
        description="Entity identifier system (e.g. 'wikidata', 'orcid', 'ror')",
    )
    local_id_column: str = Field(
        ...,
        description="Column in the dataset holding the dataset-local identifier",
    )


class EntityRow(BaseModel):
    """One row in the entity mapping table."""

    local_id: str = Field(
        ...,
        description="Dataset-local identifier (e.g. country code, author ID)",
    )
    entity_id: str = Field(
        ...,
        description="Canonical entity ID conforming to the entity_type format (e.g. 'wikidata:Q30')",
    )
    entity_name: str = Field(
        ...,
        description="Human-readable name for the entity",
    )
    entity_ids: Optional[List[str]] = Field(
        None,
        description="Alternate identifiers (e.g. ['iso:US', 'local:babynames:united_states'])",
    )


class FormatConfig(BaseModel):
    """Storage-format-specific metadata.

    parquet_hive: tables_metadata + partitioning
    ducklake:     tables_metadata + ducklake_data_path + data_schema + partitioning
    duckdb:       (no subfields needed)

    Adapter parquet paths for query-time DuckDB JOINs go in
    tables_metadata['adapter'], unifying both parquet_hive and ducklake.
    """

    tables_metadata: Optional[Dict[str, List[str]]] = Field(
        None,
        description=(
            "Maps logical table names to lists of file paths. "
            "Keys must match physical directory names under data_location (parquet_hive), "
            "or table names inside the lake (ducklake). "
            "Include 'adapter' key for entity-mapping parquet files used in query-time JOINs. "
            "Example: {\"daily\": [], \"weekly\": [], \"monthly\": [], \"adapter\": []}"
        ),
    )
    ducklake_data_path: Optional[str] = Field(
        None,
        description="ducklake only. Path to the DuckLake catalog .duckdb file",
    )
    data_schema: Optional[Dict[str, str]] = Field(
        None,
        description="Column name → DuckDB type. e.g. {\"ngram\": \"VARCHAR\", \"count\": \"BIGINT\"}",
    )
    partitioning: Optional[Dict] = Field(
        None,
        description="Partitioning scheme. e.g. {\"keys\": [\"date\", \"country\"], \"granularity\": \"daily\"}",
    )
    availability: Optional[Dict] = Field(
        None,
        description="Coverage metadata. e.g. {\"daily\": {\"available\": {\"Q30\": {\"min\": \"2010-01-01\", \"max\": \"2024-12-31\"}}}} or {\"available\": [\"town_a\", \"town_b\"]} for snapshot data.",
    )


class EndpointSchemaConfig(BaseModel):
    """Describes one endpoint type this dataset supports and how to query it.

    Separates three kinds of dimensions:
    - time_dimension: the column used to slice by time (e.g. 'date', 'year')
    - entity_dimensions: columns resolved via entity_mapping into the shared canonical
      entity namespace (e.g. 'country' → wikidata:Q30). These enable cross-dataset
      interoperability.
    - filter_dimensions: local categorical filters not in the shared entity space
      (e.g. 'sex' in babynames). Useful for querying but not cross-dataset interoperable.
    """

    type: str = Field(
        ...,
        description="Endpoint type name from the Storywrangler specification, e.g. 'types-counts'",
    )
    time_dimension: Optional[str] = Field(
        None,
        description=(
            "Column name used to slice by time. "
            "Common values: 'date' (daily), 'week', 'month', 'year', 'timestamp'. "
            "Must match a partition key or column in the dataset."
        ),
    )
    entity_dimensions: Optional[List[str]] = Field(
        None,
        description=(
            "Column names resolved via entity_mapping into the shared canonical entity namespace. "
            "These dimensions are interoperable across datasets that share the same entity vocabulary. "
            "Example: ['country'] when country values map to wikidata QIDs."
        ),
    )
    filter_dimensions: Optional[List[str]] = Field(
        None,
        description=(
            "Local categorical filter columns not in the shared entity namespace. "
            "Useful for querying within a dataset but not cross-dataset interoperable. "
            "Example: ['sex'] in babynames (values: 'M', 'F')."
        ),
    )


class DatasetCreate(BaseModel):
    """Registration payload for a dataset backend.

    The (domain, dataset_id) pair must be unique. Registration is an upsert:
    safe to re-run after data or metadata changes.

    Mirrors DatasetCreate in complex-stories-dev/backend/app/routers/registry.py.
    """

    dataset_id: str = Field(
        ...,
        description="Short identifier, unique within domain. e.g. 'ngrams', 'revisions'",
    )
    domain: str = Field(
        ...,
        description="Owning service or router. e.g. 'wikimedia', 'storywrangler', 'babynames'",
    )
    data_location: str = Field(
        ...,
        description="Absolute path to the root of the dataset on disk, or connection string",
    )
    data_format: Literal["parquet", "parquet_hive", "duckdb", "ducklake"] = Field(
        "parquet_hive",
        description="Storage format. Use 'parquet' for a single flat file, 'parquet_hive' for partitioned directories.",
    )
    description: Optional[str] = Field(
        None,
        description="Human-readable description of the dataset",
    )
    format_config: Optional[FormatConfig] = Field(
        None,
        description=(
            "Storage-format-specific metadata. "
            "parquet_hive: tables_metadata + partitioning. "
            "ducklake: tables_metadata + ducklake_data_path + data_schema + partitioning. "
            "Adapter parquet paths go in tables_metadata['adapter']."
        ),
    )
    entity_mapping: Optional[EntityMappingConfig] = Field(
        None,
        description="Schema declaration for entity ID resolution. Required when entity_dimensions are declared.",
    )
    entities: Optional[List[EntityRow]] = Field(
        None,
        description=(
            "Entity mapping rows to upsert into the entity_mappings table. "
            "Each row maps a dataset-local ID to a canonical entity ID. "
            "Can also be submitted separately via POST /admin/registry/{domain}/{dataset_id}/entities."
        ),
    )
    sources: Optional[Dict[str, Dict[str, Union[str, List[str]]]]] = Field(
        None,
        description=(
            "Source URLs for provenance and HTTP validation. "
            "Outer key is a logical dimension (e.g. 'main' for single-source, 'geo' for geography-organized). "
            "Inner key is a name within that dimension. Value is a URL string or list of URLs. "
            "Example: {\"main\": {\"enwiki\": \"https://dumps.wikimedia.org/other/enterprise_html/\"}}"
        ),
    )
    endpoint_schemas: Optional[List[EndpointSchemaConfig]] = Field(
        None,
        description=(
            "Endpoint types this dataset supports, with their query dimensions. "
            "Each entry declares a response format type plus the time, entity, and filter "
            "dimensions available for querying. Data shape validation happens in prepare.py."
        ),
    )
    catalog: Optional[str] = Field(
        "vcsi",
        description="Producer identity — the organisation or group registering this dataset. Defaults to 'vcsi'.",
    )
    ownership: Optional[Dict] = Field(
        None,
        description="Ownership and succession metadata: {owner_group, contact, status, storage_risk}.",
    )
    lineage: Optional[Dict] = Field(
        None,
        description="Lineage metadata: {derived_from, produced_by, consumers}.",
    )

    @model_validator(mode="after")
    def validate_endpoint_schema_names(self) -> "DatasetCreate":
        if not self.endpoint_schemas:
            return self
        validator = EndpointValidator()
        known = set(validator.list_supported_endpoints())
        unknown = [c.type for c in self.endpoint_schemas if c.type not in known]
        if unknown:
            raise ValueError(
                f"Unknown endpoint type(s): {unknown}. "
                f"Supported: {sorted(known)}"
            )
        return self
