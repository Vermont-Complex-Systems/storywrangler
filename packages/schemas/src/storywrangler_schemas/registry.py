"""
Storywrangler dataset registry schemas — single source of truth.

Both backend/app and packages/sdk import from here. Neither owns a copy.

Field responsibilities (see DatasetCreate for full detail):
  endpoint_schema : output shape only — {"type": "types-counts", "type_column": "ngram"}
  transform       : query slice axes — {"time_dimension": "date", "filter_dimensions": ["sex"]}
  entity_mapping  : entity identity — {"local_id_column": "location", "entity_namespace": "wikidata"}
  manifest        : coverage index (never query-time) — {"availability": {...}, "partition_index": [...]}
"""

from importlib.metadata import PackageNotFoundError, version as pkg_version
from typing import Dict, List, Literal, Optional, Union
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
            "Coverage summary for the registry UI. Never read at query time. "
            "Can be submitter-provided (arbitrary shape) or auto-derived — both are merged.\n\n"
            "**Submitter-provided** — any summary stats relevant to your dataset:\n\n"
            '```json\n{"stats": {"articles": 4059, "total_revisions": 776598, '
            '"earliest": "2019-12-08T23:12:10Z", "latest": "2026-03-07T00:01:09Z"}}\n```\n\n'
            "**Auto-derived** — when `transform.time_dimension` is set, `parquet_introspect` "
            "computes min/max of the time column per entity and partition dimension at "
            "registration time. Entity-first format:\n\n"
            '```json\n{"United States": {"daily": {"min": "2024-01-01", "max": "2026-04-20"}}}\n```\n\n'
            "For datasets without entity_mapping:\n\n"
            '```json\n{"daily": {"min": "2024-01-01", "max": "2026-04-20"}}\n```\n\n'
            "If both are present, auto-derived keys are merged into the submitter-provided dict."
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

    ``type-documents``
        Provenance: ``(type, date) → ranked [(document, score)]``. Not queried
        on its own — attached to a term-series response via ``?include=<role>``
        (or ``?include=all``), resolved through ``lineage.derived_from``.
        Declares doc_column / score_column / order_column (and type_column for
        the type it is keyed by), plus an optional ``role`` name.

    Physical orientation
        A ``types-counts`` corpus is often served by two physical forms with
        independent lifecycles: a **time-first** (date-partitioned) tree and a
        **type-first** (hash-bucketed) sparkline. ``orientation`` declares which
        one this registration is; the platform pairs them via
        ``lineage.derived_from`` (see the field docs).

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
    count_column: Optional[Union[str, List[str]]] = Field(
        None,
        description=(
            "Column holding the numeric measure to aggregate. "
            "Defaults to 'counts' for types-counts, 'count' for time-series. "
            "Declare only when different from the default. A list declares a "
            "menu of selectable measures — the first is the default; callers "
            "pick others per request via the endpoint's `weight` parameter "
            "(e.g. reddit's comments/submissions/all × score/controversy/"
            "unweighted columns)."
        ),
    )
    rank_column: Optional[Union[str, List[str]]] = Field(
        None,
        description=(
            "Companion rank column(s) a per-type time series returns alongside "
            "the count. A scalar is one canonical rank used for every `weight` "
            "(e.g. reddit's pipeline-side `rank`, which does not track the "
            "selected measure). A list must be parallel to `count_column` — the "
            "rank for each measure, indexed by the chosen `weight` (e.g. "
            "bluesky's `rank`/`rank_all`). Omit when the dataset has no "
            "precomputed rank; the series then carries counts only."
        ),
    )
    freq_column: Optional[Union[str, List[str]]] = Field(
        None,
        description=(
            "Companion normalized-frequency column(s), same scalar-or-parallel-"
            "list rule as `rank_column`. A list is indexed by the chosen "
            "`weight`. Omit when the dataset has no precomputed frequency."
        ),
    )
    orientation: Optional[Literal["time-first", "type-first"]] = Field(
        None,
        description=(
            "types-counts only. Physical layout of this form of the corpus. "
            "`time-first` (the default when omitted) is date-partitioned — it "
            "feeds top-ngrams / allotax / rtd / wordshift and the term-series "
            "slow fallback. `type-first` is hash-bucketed by type — the "
            "term-series fast-path (sparkline) companion. Declare `type-first` "
            "on a sparkline dataset whose `lineage.derived_from` names the "
            "primary time-first dataset, so term-series resolves it without a "
            "query param."
        ),
    )
    role: Optional[str] = Field(
        None,
        description=(
            "type-documents only. Short name for this provenance companion "
            "(e.g. 'articles', 'subreddits'). A term-series request attaches it "
            "with `?include=<role>` (or `?include=all`), resolved through "
            "`lineage.derived_from` — no raw dataset id in the query surface. "
            "Omit to be addressable only by dataset id (deprecated)."
        ),
    )
    doc_column: Optional[str] = Field(
        None,
        description=(
            "type-documents only. Column holding the source-document identifier "
            "(e.g. 'article_url'). A type-documents dataset maps (type, date) → a "
            "ranked list of these documents; a term-series request attaches them "
            "via `?include=<role>` (falling back to `?include=<dataset_id>`)."
        ),
    )
    score_column: Optional[str] = Field(
        None,
        description=(
            "type-documents only. Column holding each document's contribution "
            "score (e.g. 'score')."
        ),
    )
    order_column: Optional[str] = Field(
        None,
        description=(
            "type-documents only. Column the ranked documents are ordered by "
            "within a (type, date) (e.g. 'article_rank'). Defaults to "
            "`score_column` descending when omitted."
        ),
    )

    @model_validator(mode="after")
    def validate_companion_columns(self) -> "EndpointSchemaConfig":
        """List-form rank/freq must be parallel to a list count_column.

        A scalar companion is always allowed (one canonical column for every
        weight). A list companion only makes sense per-measure, so it requires
        count_column to be a list of the same length.
        """
        menu_len = len(self.count_column) if isinstance(self.count_column, list) else None
        for name in ("rank_column", "freq_column"):
            val = getattr(self, name)
            if not isinstance(val, list):
                continue
            if menu_len is None:
                raise ValueError(
                    f"{name} is a list but count_column is not; a per-measure "
                    f"{name} requires count_column to be a parallel list. Use a "
                    "scalar for a single canonical column."
                )
            if len(val) != menu_len:
                raise ValueError(
                    f"{name} has {len(val)} entries but count_column has "
                    f"{menu_len}; a list companion must be parallel to count_column."
                )
        return self

    @model_validator(mode="after")
    def validate_orientation_and_role(self) -> "EndpointSchemaConfig":
        """Scope orientation to types-counts and role to type-documents.

        Orientation describes a types-counts form's physical layout (time-first
        vs type-first); type-documents is inherently type-first, so it takes no
        orientation. `role` names a type-documents provenance companion for
        `?include=`, so it is meaningless on any other type.
        """
        if self.orientation is not None and self.type != "types-counts":
            raise ValueError(
                "orientation applies only to types-counts datasets "
                "(type-documents is inherently type-first)."
            )
        if self.role is not None and self.type != "type-documents":
            raise ValueError("role applies only to type-documents datasets.")
        return self


class TransformConfig(BaseModel):
    """Query slice axes — how to filter the dataset at request time.

    For `parquet_hive`, the on-disk hive directory levels are auto-discovered
    at registration time. Each level is classified by matching it against the
    declarations here and in `entity_mapping`:

    - `entity_mapping.local_id_column` → entity level
    - `time_dimension` → time level
    - `hash_bucket` → hash bucket level
    - everything else → partition level (queryable, gets an auto-default)

    The discovered order and auto-defaults are stored in `level_order` — you
    do not need to declare partition columns.

    `filter_dimensions` is for non-hive columns inside parquet files (e.g. `sex`
    in babynames) where omitting the filter aggregates over all values.
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
            "Non-hive categorical filter columns where omitting the filter aggregates "
            "over all values (valid behaviour). E.g. `['sex']` — omitting sex returns "
            "all names. Not needed for hive partition levels — those are auto-discovered."
        ),
    )
    time_partitions: Optional[List[str]] = Field(
        None,
        description=(
            "Hive partition columns that subdivide the time_dimension into "
            "hierarchical components (e.g. ['year', 'month'] when time_dimension='date'). "
            "At query time, values are auto-derived from the requested dates — callers "
            "never need to pass year/month explicitly. Column names must match standard "
            "temporal components: year, month, day."
        ),
    )
    defaults: Optional[Dict[str, object]] = Field(
        None,
        description=(
            "Default value per queryable hive level, injected when the caller "
            "omits the parameter — e.g. {'lang': 'en', 'n': 1}. Overrides the "
            "auto-discovered default (the first on-disk value alphabetically — "
            "right for ngram_size=1/granularity=daily, wrong for language "
            "levels, where 'af' wins the alphabet). Each key must be a "
            "partition/filter hive level and each value must exist on disk; "
            "both are validated at registration. Undeclared levels keep the "
            "auto-discovered default."
        ),
    )
    hash_bucket: Optional[str] = Field(
        None,
        description=(
            "Hash-bucket column name for content-sharded datasets. "
            "Just the hive partition column holding the bucket ID "
            "(e.g. 'ngram_bucket'). Bucket counts per entity are "
            "auto-derived from the directory structure at registration time. "
            "Hash buckets are routing-only, not query axes."
        ),
    )
    hash_algorithm: Literal["murmur3_32"] = Field(
        "murmur3_32",
        description=(
            "Hash algorithm for bucket routing. Currently only murmur3_32 "
            "is supported. Pipelines MUST use storywrangler.hashing.assign_bucket() "
            "to ensure consistency with the query layer."
        ),
    )
    hash_seed: int = Field(
        0,
        description=(
            "Seed for the hash function. Seed 0 matches DuckDB's "
            "built-in murmur3_32() default."
        ),
    )

    @model_validator(mode="after")
    def _hash_params_require_bucket(self):
        """hash_algorithm/hash_seed only make sense when hash_bucket is set."""
        if self.hash_bucket is None:
            if self.hash_algorithm != "murmur3_32" or self.hash_seed != 0:
                raise ValueError(
                    "hash_algorithm and hash_seed require hash_bucket to be set."
                )
        return self


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
        description="Owning service or router. Examples: `wikimedia`, `storywrangler`, `babynames`. Query `GET /registry/domains` for the current list.",
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
            "same version string returns 409 Conflict.\n\n"
            "- **PATCH** — bug fixes (same schema, corrected values)\n"
            "- **MINOR** — new data (new time range, new entities — backward compatible)\n"
            "- **MAJOR** — breaking schema changes (column rename, endpoint_schema change)\n\n"
            "See https://semver.org/."
        ),
    )
    data_location: Union[str, List[str]] = Field(
        ...,
        description=(
            "Where to find the data. Three forms are supported for `parquet`:\n\n"
            "- Single file: `/data/babynames.parquet`\n"
            "- Flat directory: `/data/babynames/` (all `.parquet` files read)\n"
            "- File list: `[\"/data/f1.parquet\", \"/data/f2.parquet\"]` — "
            "use this when the pipeline manages multiple snapshot files (e.g. DuckLake) and "
            "you need to pin exactly the live files at submit time.\n\n"
            "For `parquet_hive`, provide the **root** of the hive partition tree — the directory "
            "directly above the first `col=val/` level (e.g. `/data/ngrams/` where subdirectories "
            "are `ngram_size=1/granularity=daily/…`). Do not point to a subdirectory.\n\n"
            "For `mongodb`, provide a non-secret locator — one of: `<database>/<collection>` "
            "(e.g. `1grams/en`, which the server samples to introspect); a Mongo host "
            "(e.g. `wranglerdb01a.uvm.edu:27017`) that signals where the data lives while a "
            "bespoke router owns the db/collection routing; or a `{placeholder}` routing "
            "template. Host and template forms require an explicit `data_schema` (no single "
            "collection to sample). The server's `MONGODB_URI` supplies the connection and "
            "credentials — never put credentials in the registry."
        ),
    )

    data_format: Literal["parquet", "parquet_hive", "mongodb"] = Field(
        ...,
        description=(
            "Storage format. One of `parquet` (single file or directory), "
            "`parquet_hive` (directory-partitioned by entity/time), or `mongodb` "
            "(pass-through: served from a live MongoDB collection — no hive "
            "introspection, level_order, or hash buckets; queries are equality "
            "filters + time range only). "
            "See [format reference](/docs/specification#storage-formats)."
        ),
    )
    description: str = Field(..., description="Human-readable description of the dataset")
    data_schema: Optional[Dict[str, str]] = Field(
        None,
        description=(
            "Column names → DuckDB type strings (e.g. `{'ngram': 'VARCHAR', 'pv_count': 'BIGINT'}`). "
            "When provided, this is the authoritative schema. "
            "When omitted, schema is auto-derived from the data files."
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
    def validate_mongodb_constraints(self) -> "DatasetCreate":
        """mongodb is a pass-through format: no hive machinery, no creds in the registry.

        data_location is a non-secret locator the router interprets. Three forms:
          - literal '<database>/<collection>' — the server samples it to introspect;
          - a Mongo host (e.g. 'wranglerdb01a.uvm.edu:27017') — a bespoke router owns
            the db/collection routing; needs an explicit data_schema;
          - a '{placeholder}' routing template — likewise needs data_schema.
        A connection URI or credentials must never appear here — those come from
        the server's MONGODB_URI.
        """
        if self.data_format != "mongodb":
            return self
        loc = self.data_location
        if not isinstance(loc, str) or not loc.strip():
            raise ValueError(
                "mongodb data_location must be a non-empty string: a host, "
                "'<database>/<collection>', or a '{placeholder}' routing template."
            )
        if "://" in loc or "@" in loc:
            raise ValueError(
                "mongodb data_location must not contain a connection URI or credentials — "
                "those come from the server's MONGODB_URI, never the registry. Use a host, "
                "'<database>/<collection>', or a '{placeholder}' routing template."
            )
        segments = [s for s in loc.strip("/").split("/") if s]
        is_concrete_collection = len(segments) == 2 and "{" not in loc
        if not is_concrete_collection and not self.data_schema:
            raise ValueError(
                "this mongodb data_location is a host or routing template, not a literal "
                "'<database>/<collection>', so the server cannot sample a collection to "
                "introspect — provide an explicit data_schema."
            )
        if self.transform and self.transform.hash_bucket is not None:
            raise ValueError(
                "transform.hash_bucket applies only to parquet_hive datasets "
                "(hash buckets route to partition directories, which mongodb does not have)."
            )
        return self

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
