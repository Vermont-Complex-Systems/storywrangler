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
    """How to map canonical entity IDs (e.g. Wikidata QIDs) to dataset-local identifiers."""

    table: Optional[str] = Field(
        None,
        description="DuckLake table name holding the adapter (ducklake format only)",
    )
    path: Optional[str] = Field(
        None,
        description="Absolute path to the adapter parquet file (parquet_hive format only)",
    )
    local_id_column: str = Field(
        ...,
        description="Column in the adapter that holds the dataset-local identifier",
    )
    entity_id_column: str = Field(
        ...,
        description="Column in the adapter that holds the canonical entity ID, e.g. 'wikidata:Q30'",
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
    data_format: Literal["parquet_hive", "duckdb", "ducklake"] = Field(
        "parquet_hive",
        description="Storage format.",
    )
    description: Optional[str] = Field(
        None,
        description="Human-readable description of the dataset",
    )
    tables_metadata: Optional[Dict[str, List[str]]] = Field(
        None,
        description=(
            "Maps logical table names to lists of file paths. "
            "Keys must match physical directory names under data_location (parquet_hive), "
            "or table names inside the lake (ducklake). "
            "Example: {\"daily\": [], \"weekly\": [], \"monthly\": []}"
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
    entity_mapping: Optional[EntityMappingConfig] = Field(
        None,
        description="Entity ID resolution config. Required for geo/entity filtering endpoints.",
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
