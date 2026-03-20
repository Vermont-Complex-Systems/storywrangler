"""
Storywrangler dataset registry schemas — single source of truth.

Both backend/app and packages/sdk import from here. Neither owns a copy.

Three cases for endpoint_schema (see EndpointSchemaConfig):
  - No time axis   : {"type": "types-counts"}
  - Time column    : {"type": "types-counts", "time_dimension": "year", "filter_dimensions": ["sex"]}
  - Hive-partitioned: {"type": "types-counts", "type_column": "ngram", "count_column": "pv_count",
                       "granularities": {"daily": "date", "weekly": "week", "monthly": "month"}}
"""

from typing import Dict, List, Literal, Optional, Union
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from .standards import Standards

_SUPPORTED_ENDPOINT_TYPES: frozenset[str] = frozenset(Standards.ENDPOINT_SCHEMAS)


class EntityMappingConfig(BaseModel):
    """Declares how a dataset-local column maps to canonical entity IDs (e.g. Wikidata QIDs). Actual mapping rows are submitted via the `entities` field or the batch upsert endpoint."""

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
        description="Canonical entity ID (e.g. 'wikidata:Q30')",
    )
    entity_name: str = Field(
        ...,
        description="Human-readable name for the entity",
    )
    entity_ids: Optional[List[str]] = Field(
        None,
        description="Alternate identifiers (e.g. ['iso:US', 'local:babynames:united_states'])",
    )

    @field_validator("entity_id")
    @classmethod
    def validate_entity_id_format(cls, v: str) -> str:
        if not Standards.valid_entity_id(v):
            raise ValueError(
                f"Unrecognized entity_id format: '{v}'. "
                f"Supported namespaces: wikidata, orcid, ror, ipeds, doi, isbn, local. "
                f"See {Standards.spec_url('31-entity-identifiers')} for the full spec."
            )
        return v


class FormatConfig(BaseModel):
    """Storage-format-specific metadata. Pass only the fields relevant to your `data_format` — `parquet` and `duckdb` can submit `{}`. See [format reference](/docs/specification#storage-formats)."""

    tables_metadata: Optional[Dict[str, List[str]]] = Field(
        None,
        description=(
            "Maps logical table names to lists of parquet file paths. "
            "Examples: `{\"daily\": [\"2024-01-01.parquet\", ...], \"adapter\": [\"states.parquet\"]}`. "
            "Use the `adapter` key for entity-mapping parquet files loaded at query time. "
            "See [format reference](/docs/specification#storage-formats)."
        ),
    )
    ducklake_data_path: Optional[str] = Field(
        None,
        description=(
            "`ducklake` format only. Absolute path to the DuckLake catalog `.duckdb` file. "
            "Example: `/data/wikimedia/catalog.duckdb`. "
            "See [format reference](/docs/specification#storage-formats)."
        ),
    )
    partitioning: Optional[Dict] = Field(
        None,
        description=(
            "Hive-partitioning scheme for `parquet_hive` datasets. "
            "Example: `{\"keys\": [\"date\", \"country\"]}`. "
            "See [format reference](/docs/specification#storage-formats)."
        ),
    )
    availability: Optional[Dict] = Field(
        None,
        description=(
            "Coverage metadata keyed by granularity then entity. "
            "Example: `{\"daily\": {\"available\": {\"wd:Q30\": {\"min\": \"2010-01-01\", \"max\": \"2024-12-31\"}}}}`. "
            "Used by the query layer to validate date-range requests."
        ),
    )


class OwnershipConfig(BaseModel):
    """Ownership and succession metadata."""

    owner_group: Optional[str] = Field(
        None,
        description="Lab or research group (e.g. 'compethicslab', 'vcsi').",
    )
    contact: Optional[str] = Field(
        None,
        description="Email or GitHub handle of the current maintainer.",
    )
    status: Optional[str] = Field(
        "active",
        description="Lifecycle state: active | needs_successor | archived.",
    )
    storage_risk: Optional[str] = Field(
        None,
        description="Durability signal: managed | institutional | cloud | personal.",
    )


class LineageConfig(BaseModel):
    """Lineage metadata for a dataset: `sources` (external raw URLs), `derived_from` (intra-registry upstream datasets), `consumers` (downstream stories or scripts), and `repo` (producing pipeline URL)."""

    sources: Optional[Dict[str, Dict[str, Union[str, List[str]]]]] = Field(
        None,
        description=(
            "External raw data URLs keyed by dimension then location. "
            "e.g. {\"geo\": {\"US\": \"https://ssa.gov/...\"}}. "
            "Used by the validate-sources endpoint."
        ),
    )
    derived_from: Optional[List[str]] = Field(
        None,
        description="Intra-registry upstream datasets as 'domain/dataset_id' (e.g. ['wikimedia/ngrams']).",
    )
    consumers: Optional[List[str]] = Field(
        None,
        description="Downstream users — stories, tools, or scripts that depend on this dataset.",
    )
    repo: Optional[str] = Field(
        None,
        description="Git repository URL for the pipeline that produced this dataset. e.g. `https://github.com/org/repo`.",
    )


class EndpointSchemaConfig(BaseModel):
    """Declares the query contract for a dataset: endpoint type, time axis, filter dimensions, and optional hive-partitioning. See [endpoint schema spec](/docs/specification#endpoint-schemas)."""

    type: str = Field(
        ...,
        description=(
            f"Endpoint type. Currently supported: `{'`, `'.join(sorted(_SUPPORTED_ENDPOINT_TYPES))}`. "
            "See [endpoint schema spec](/docs/specification#endpoint-schemas)."
        ),
    )
    time_dimension: Optional[str] = Field(
        None,
        description="Column for WHERE-based time filtering (non-hive). e.g. 'year'. Omit for hive-partitioned.",
    )
    granularities: Optional[Dict[str, str]] = Field(
        None,
        description="Hive-partitioned only. Maps subdirectory to time column. e.g. {\"daily\": \"date\"}",
    )
    type_column: Optional[str] = Field(
        None,
        description="Column holding token/type values. Defaults to 'types'. Declare only when different.",
    )
    count_column: Optional[str] = Field(
        None,
        description="Column holding frequency values. Defaults to 'counts'. Declare only when different.",
    )
    filter_dimensions: Optional[List[str]] = Field(
        None,
        description="Local categorical filter columns. e.g. ['sex'] in babynames.",
    )
    ngram_sizes: Optional[List[int]] = Field(
        None,
        description=(
            "Available n-gram sizes when the data is split into {n}grams/ subdirectories. "
            "e.g. [1, 2] → 1grams/ and 2grams/ under data_location. "
            "Omit for datasets with a single flat structure."
        ),
    )


class DatasetCreate(BaseModel):
    """Registration payload for a dataset backend.

    The (domain, dataset_id) pair must be unique. Registration is an upsert:
    safe to re-run after data or metadata changes.

    Minimal example (no time axis):
        DatasetCreate(
            dataset_id="zoning_bylaws", domain="Vermont-Zoning-Atlas",
            data_location="/data/vt/zoning_bylaws.parquet", data_format="parquet",
            entity_mapping={"entity_type": "wikidata", "local_id_column": "town"},
            endpoint_schema={"type": "types-counts"},
        )
    """


    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "catalog": "vcsi",
                    "domain": "babynames",
                    "dataset_id": "ngrams",
                    "data_location": "/data/babynames/names.parquet",
                    "data_format": "parquet",
                    "description": "US baby name frequencies by state, year, and sex.",
                    "format_config": {},
                    "endpoint_schema": {"type": "types-counts", "time_dimension": "year", "filter_dimensions": ["sex", "geo"]},
                    "ownership": {"owner_group": "vcsi", "contact": "compstorylab@uvm.edu", "storage_risk": "institutional"},
                    "lineage": {},
                }
            ]
        }
    )

    catalog: str = Field(
        ...,
        description="Producer identity — organisation or group registering this dataset.",
    )
    domain: str = Field(
        ...,
        description="Owning service or router. Examples: `wikimedia`, `storywrangler`, `babynames`. See [valid domains](/docs/api-reference/registry).",
    )
    dataset_id: str = Field(
        ...,
        description="Short identifier, unique within domain. e.g. 'ngrams', 'revisions'",
    )
    data_location: str = Field(
        ...,
        description="Absolute path to the root of the dataset on disk, or connection string",
    )
    data_format: Literal["parquet", "parquet_hive", "duckdb", "ducklake"] = Field(
        ...,
        description=(
            "Storage format. One of `parquet` (single file), `parquet_hive` (directory-partitioned), "
            "`duckdb` (embedded DB file), `ducklake` (DuckLake catalog). "
            "See [format reference](/docs/specification#storage-formats)."
        ),
    )
    description: str = Field(..., description="Human-readable description of the dataset")
    format_config: FormatConfig = Field(
        ...,
        description="Storage-format-specific metadata (tables_metadata, partitioning, availability, etc.)",
    )
    ownership: OwnershipConfig = Field(
        ...,
        description="Ownership and succession metadata.",
    )
    lineage: LineageConfig = Field(
        ...,
        description="Lineage metadata: upstream datasets, producing pipeline, downstream consumers.",
    )
    entity_mapping: Optional[EntityMappingConfig] = Field(
        None,
        description="Schema declaration for entity ID resolution (entity_type + local_id_column).",
    )
    entities: Optional[List[EntityRow]] = Field(
        None,
        description="Entity mapping rows to upsert. Can also be submitted via the batch entities endpoint.",
    )
    endpoint_schema: Optional[EndpointSchemaConfig] = Field(
        None,
        description="Query contract for this dataset. Declares endpoint type, time and filter dimensions.",
    )

    @model_validator(mode="after")
    def validate_endpoint_schema_type(self) -> "DatasetCreate":
        if not self.endpoint_schema:
            return self
        if self.endpoint_schema.type not in _SUPPORTED_ENDPOINT_TYPES:
            raise ValueError(
                f"Unknown endpoint type: '{self.endpoint_schema.type}'. "
                f"Supported: {sorted(_SUPPORTED_ENDPOINT_TYPES)}"
            )
        return self
