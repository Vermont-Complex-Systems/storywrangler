"""
Storywrangler dataset registry schemas — single source of truth.

Both backend/app and packages/sdk import from here. Neither owns a copy.

Field responsibilities (see DatasetCreate for full detail):
  endpoint_schema : output shape only — {"type": "types-counts", "type_column": "ngram"}
  transform       : query slice axes — {"time_dimension": "date", "filter_dimensions": ["granularity", "ngram_size"]}
  entity_mapping  : entity identity — {"local_id_column": "location", "entity_namespace": "wikidata"}
  manifest        : coverage index (never query-time) — {"availability": {...}, "partition_index": [...]}
"""

from importlib.metadata import PackageNotFoundError, version as pkg_version
from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from .standards import Standards


def _get_schema_version() -> str:
    try:
        return pkg_version("storywrangler-schemas")
    except PackageNotFoundError:
        return "unknown"

_SUPPORTED_ENDPOINT_TYPES: frozenset[str] = frozenset(Standards.ENDPOINT_SCHEMAS)


_KNOWN_NAMESPACES: frozenset[str] = Standards.NAMESPACES


class EntityMappingConfig(BaseModel):
    """Declares how a dataset-local column maps to canonical entity IDs.

    Two usage patterns:

    1. **Opaque local keys** — column holds non-standard values (e.g. state abbreviation,
       snake_case name) that need a lookup table.  Provide `entities` rows to supply
       the local_id → entity_id mappings.  `entity_namespace` is optional but recommended
       so the platform knows what kind of entity the column represents.

    2. **Global-identifier column** — column already holds values from a recognised
       namespace (e.g. DOIs, OpenAlex author URLs, ORCID iDs).  Set `entity_namespace`
       to declare the namespace; the `entities` list is then optional — useful only
       when you also want display names stored, or when the stored format differs from
       the canonical ID format (e.g. full URLs vs `openalex:A...`).

    `entity_namespace` is the prerequisite for cross-dataset entity graph traversal:
    it tells the platform which resolution rules and external APIs apply (OpenAlex,
    Wikidata SPARQL, ORCID, …) so entities can be enriched and joined across datasets.
    """

    local_id_column: str = Field(
        ...,
        description="Column in the dataset holding the dataset-local identifier.",
    )
    entity_namespace: Optional[str] = Field(
        None,
        description=(
            "Canonical namespace for identifiers in `local_id_column`. "
            "Declares the entity type for discovery, enrichment, and cross-dataset "
            "graph traversal — e.g. the platform can follow openalex:A → openalex:I → "
            "wikidata:Q to join OAA authors with a babynames dataset keyed on Wikidata. "
            f"Supported: {', '.join(sorted(_KNOWN_NAMESPACES))}. "
            "See §3.1 of the Storywrangler Specification."
        ),
    )

    @field_validator("entity_namespace")
    @classmethod
    def validate_entity_namespace(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if v not in _KNOWN_NAMESPACES:
            raise ValueError(
                f"Unknown entity_namespace '{v}'. "
                f"Supported: {', '.join(sorted(_KNOWN_NAMESPACES))}. "
                f"See {Standards.spec_url('31-entity-identifiers')} for the full spec."
            )
        return v


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
                f"Supported namespaces: wikidata, orcid, openalex, ror, ipeds, doi, isbn, local. "
                f"See {Standards.spec_url('31-entity-identifiers')} for the full spec."
            )
        return v


class ManifestConfig(BaseModel):
    """Coverage index — pre-computed metadata about what data exists in this dataset.

    Borrowed from Apache Iceberg's concept of a manifest: a pre-computed record of
    partition bounds and file-level statistics. Never read at query time — used only
    for discovery, UI display, and SDK consumers.

    Leave empty for most datasets. Populated at registration time by the submit script.

    - `availability`: time/entity coverage summary (babynames, wikimedia/ngrams)
    - `partition_index`: enumerable partition list with per-partition stats (wikimedia/revisions)

    See [format reference](/docs/specification#storage-formats).
    """

    availability: Optional[Dict] = Field(
        None,
        description=(
            "Time coverage summary for display in the registry UI and for computing "
            "valid date ranges (e.g. the /rtd endpoint requires explicit dates). "
            "Auto-populated by parquet_introspect at registration time when "
            "transform.time_dimension is set. Never read at query time for data loading. "
            "Entity-first, keyed by local_id (or entity_id), with per-granularity min/max — "
            '`{"United States": {"daily": {"min": "2024-01-01", "max": "2026-04-20"}, '
            '"weekly": {"min": "2024-09-30", "max": "2026-04-13"}}}`; '
            "for datasets without entity_mapping (global): "
            '`{"daily": {"min": "2024-01-01", "max": "2026-04-20"}}`.'
        ),
    )
    partition_index: Optional[List[Dict]] = Field(
        None,
        description=(
            "`parquet_hive` only. Enumerable list of partition values with optional per-partition stats. "
            "Stored separately and excluded from summary registry responses to keep them fast. "
            'Example: `[{"identifier": "Cat", "revision_count": 142, "first_edit": "2001-01-01"}]`.'
        ),
    )


class OwnershipConfig(BaseModel):
    """Ownership and succession metadata."""

    owner_group: str = Field(
        ...,
        description="Lab or research group (e.g. 'compethicslab', 'vcsi').",
    )
    contact: str = Field(
        ...,
        description="Email or GitHub handle of the current maintainer.",
    )
    status: str = Field(
        "active",
        description="Lifecycle state: active | needs_successor | archived.",
    )


class LineageConfig(BaseModel):
    """Lineage metadata for a dataset: `sources` (external raw URLs), `derived_from` (intra-registry upstream datasets), `consumers` (downstream stories or scripts), and `repo` (producing pipeline URL)."""

    sources: Optional[Dict[str, Dict[str, Union[str, List[str]]]]] = Field(
        None,
        description=(
            "External raw data URLs keyed by dimension then location. "
            "Used by the validate-sources endpoint. "
            "Example: "
            "{\"geo\": {"
            "\"united_states\": \"https://www.ssa.gov/oact/babynames/limits.html\", "
            "\"quebec\": \"https://www.donneesquebec.ca/recherche/dataset/banque-de-prenoms\""
            "}}."
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
    repo: str = Field(
        ...,
        description="Git repository URL for the pipeline that produced this dataset. e.g. `https://github.com/Vermont-Complex-Systems/babynames`.",
    )
    archival_doi: Optional[str] = Field(
        None,
        description=(
            "DOI assigned by an archival system (e.g. Harvard Dataverse) when this version "
            "was checkpointed for long-term preservation. Set this after archiving — it signals "
            "that the version is citable and its data is durably stored externally. "
            "Example: '10.7910/DVN/XXXXXX'."
        ),
    )


class EndpointSchemaConfig(BaseModel):
    """Output shape declaration — what columns the API reads and returns.

    Describes the response structure only; query slicing (time range, categorical
    filters, entity axis) belongs in TransformConfig.

    Supported types:

    ``types-counts``
        Rank distribution: ``{types: [...], counts: [...]}``.
        type_column (default 'types') holds token/label values.
        count_column (default 'counts') holds frequency values.
        Requires entity_mapping or transform.filter_dimensions.

    ``time-series``
        Tabular rows: ``[{dim1: v, ..., count: n}]``.
        count_column (default 'count') is the numeric measure to SUM.
        type_column is not used.
        Requires transform.time_dimension and at least one filter_dimension.

    See [endpoint schema spec](/docs/specification#endpoint-schemas).
    """

    type: str = Field(
        ...,
        description=(
            f"Endpoint type. Supported: `{'`, `'.join(sorted(_SUPPORTED_ENDPOINT_TYPES))}`. "
            "See [endpoint schema spec](/docs/specification#endpoint-schemas)."
        ),
    )
    type_column: Optional[str] = Field(
        None,
        description=(
            "types-counts only. Column holding token/type values. "
            "Defaults to 'types'. Declare only when different."
        ),
    )
    count_column: Optional[str] = Field(
        None,
        description=(
            "Column holding the numeric measure to aggregate. "
            "Defaults to 'counts' for types-counts, 'count' for time-series. "
            "Declare only when different from the default."
        ),
    )


class TransformConfig(BaseModel):
    """Query slice axes — how to filter the dataset at request time.

    Three orthogonal axes, all generating WHERE clauses at query time:
    - `time_dimension`: date-range filtering via BETWEEN.
    - `filter_dimensions`: categorical columns where omitting the filter is
      valid (aggregates over all values). E.g. omitting `sex` means all sexes.
    - `partition_dimensions`: columns where omitting the filter is INVALID —
      it would mix incompatible rows (e.g. daily + weekly + monthly summed).
      For `parquet_hive` these are the hive partition keys. Declare safe
      defaults in `partition_defaults`; they are injected automatically when
      the caller does not provide the parameter.

    `entity_mapping.local_id_column` is NOT listed here — it is the entity
    identity column and is handled separately.
    """

    time_dimension: Optional[str] = Field(
        None,
        description=(
            "Column for time-range filtering, e.g. 'year' or 'date'. "
            "For parquet_hive this is the hive partition column; "
            "all granularity levels must share the same column name."
        ),
    )
    filter_dimensions: Optional[List[str]] = Field(
        None,
        description=(
            "Categorical filter columns where omitting the filter aggregates over all values "
            "(valid behaviour). E.g. ['sex'] — omitting sex returns all names. "
            "Distinct values are auto-introspected at registration."
        ),
    )
    partition_dimensions: Optional[Dict[str, Any]] = Field(
        None,
        description=(
            "Storage partition key columns — filtering on these is performant because the "
            "query layer can prune at the storage level rather than scanning file contents. "
            "For parquet_hive, these map directly to hive directory levels (col=val/); "
            "DuckDB reads partition values from directory names and skips non-matching "
            "directories entirely. Future backends (e.g. database connections) may support "
            "analogous partition pruning. "
            "Keys are column names; values are safe defaults injected automatically when "
            "the caller omits the parameter (use None when no safe default exists). "
            "For datasets where mixing partition slices is semantically invalid "
            "(e.g. daily + weekly + monthly), providing defaults prevents accidental "
            "cross-partition aggregation. "
            "Distinct values are auto-introspected at registration. "
            "Example: {\"granularity\": \"daily\", \"ngram_size\": 1}."
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
            entity_mapping={"local_id_column": "town", "entity_namespace": "wikidata"},
            endpoint_schema={"type": "types-counts"},
            ownership={"owner_group": "vcsi", "contact": "compstorylab@uvm.edu"},
            lineage={"repo": "https://github.com/Vermont-Complex-Systems/vt-zoning-atlas"},
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
                    "endpoint_schema": {"type": "types-counts"},
                    "transform": {"time_dimension": "year", "filter_dimensions": ["sex"]},
                    "ownership": {"owner_group": "vcsi", "contact": "compstorylab@uvm.edu"},
                    "lineage": {"repo": "https://github.com/Vermont-Complex-Systems/babynames"},
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
    version: str = Field(
        "latest",
        description=(
            "Dataset version. `'latest'` (default) is the mutable development slot — "
            "safe to re-register freely; each re-registration overwrites the previous entry. "
            "Semver strings (e.g. `'1.0.0'`) create immutable snapshots: re-registering the "
            "same version string returns 409 Conflict. "
            "Increment PATCH for bug fixes (same schema, corrected values), "
            "MINOR for new data (new time range, new entities — backward compatible), "
            "MAJOR for breaking schema changes (column rename, endpoint_schema change). "
            "See https://semver.org/."
        ),
    )
    data_location: Union[str, List[str]] = Field(
        ...,
        description=(
            "Where to find the data. Three forms are supported for `parquet`:\n"
            "- Single file: `/data/babynames.parquet`\n"
            "- Flat directory: `/data/babynames/` (all `.parquet` files read)\n"
            "- File list: `[\"/data/f1.parquet\", \"/data/f2.parquet\"]` — "
            "use this when the pipeline manages multiple snapshot files (e.g. DuckLake) and "
            "you need to pin exactly the live files at submit time.\n"
            "For `parquet_hive`, provide the **root** of the hive partition tree — the directory "
            "directly above the first `col=val/` level (e.g. `/data/ngrams/` where subdirectories "
            "are `ngram_size=1/granularity=daily/…`). The query layer appends `/**/*.parquet` and "
            "enables hive partition pruning automatically. Do not point to a subdirectory."
        ),
    )

    data_format: Literal["parquet", "parquet_hive"] = Field(
        ...,
        description=(
            "Storage format. One of `parquet` (single file or directory) or "
            "`parquet_hive` (directory-partitioned by entity/time). "
            "See [format reference](/docs/specification#storage-formats)."
        ),
    )
    description: str = Field(..., description="Human-readable description of the dataset")
    data_schema: Optional[Dict[str, str]] = Field(
        None,
        description=(
            "Column names → DuckDB type strings (e.g. {'ngram': 'VARCHAR', 'pv_count': 'BIGINT'}). "
            "When provided, used as the authoritative schema — glob-based schema introspection "
            "is skipped. When omitted, schema is auto-derived from data files (all files must "
            "have consistent schemas or registration will be rejected)."
        ),
    )
    manifest: Optional[ManifestConfig] = Field(
        None,
        description="Coverage index: pre-computed availability and partition_index. Never read at query time.",
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
        description="Output shape: endpoint type and column names for types and counts.",
    )
    transform: Optional[TransformConfig] = Field(
        None,
        description="Query slice axes: time dimension and categorical filter columns.",
    )
    schema_version: str = Field(
        default_factory=_get_schema_version,
        description=(
            "Version of storywrangler-schemas used at registration time. "
            "Auto-populated — do not set manually. "
            "Records the software-data version coupling so consumers know which "
            "registration contract was in effect when this entry was created."
        ),
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

    @model_validator(mode="after")
    def derive_entity_namespace(self) -> "DatasetCreate":
        """Auto-derive entity_namespace from submitted entity rows when not declared.

        If entity_mapping is provided without entity_namespace but entity rows are
        submitted, infer the namespace from the entity_id prefixes. Requires all
        rows to share the same known namespace (e.g. all 'wikidata:Q...' → 'wikidata').
        """
        if not self.entity_mapping or self.entity_mapping.entity_namespace is not None:
            return self
        if not self.entities:
            return self
        prefixes = {
            e.entity_id.split(":")[0]
            for e in self.entities
            if ":" in e.entity_id
        }
        if len(prefixes) == 1:
            ns = prefixes.pop()
            if ns in _KNOWN_NAMESPACES:
                self.entity_mapping.entity_namespace = ns
        return self
