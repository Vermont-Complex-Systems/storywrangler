# Storywrangler SDK

Dataset registration client, entity validation, and project scaffolding for Storywrangler.

Implements the [Storywrangler Specification v0.0.3](https://github.com/vermont-complex-systems/Storywrangler-Specification/blob/main/versions/0.0.3.md).

## Installation
```bash
pip install storywrangler
```

## Quick Start

### 1. Scaffold a new dataset project

```bash
# Flat parquet
uvx storywrangler new my-dataset --format parquet

# Hive-partitioned parquet
uvx storywrangler new my-dataset --format parquet_hive

# With snakemake instead of make
uvx storywrangler new my-dataset --format parquet_hive --orchestrator snakemake
```

This generates the project structure:

```
my-dataset/
  config/entities.yaml      # entity mappings (local_id → canonical ID)
  extract/src/scrape.py     # download raw data
  transform/src/process.py  # process into parquet
  adapter/submit.py         # register with the platform
  tests/                    # entity coverage tests
  Makefile                  # or Snakefile
```

### 2. Configure and register

```bash
cd my-dataset
cp .env.example .env        # fill in DATASET_ID, DOMAIN, DATA_PATH, API_KEY
uv sync
# Edit adapter/submit.py, config/entities.yaml
make submit
```

### 3. Or register programmatically

```python
from storywrangler import Storywrangler

client = Storywrangler()  # reads API_KEY from env

client.registry.register({
    "catalog": "vcsi",
    "domain": "babynames",
    "dataset_id": "names",
    "data_location": "/data/babynames",
    "data_format": "parquet_hive",
    "description": "US baby name frequencies by state, sex, and year.",
    "endpoint_schema": {"type": "types-counts"},
    "transform": {"time_dimension": "year"},
    "entity_mapping": {"local_id_column": "state", "entity_namespace": "wikidata"},
    "entities": [
        {"local_id": "VT", "entity_id": "wikidata:Q16551", "entity_name": "Vermont"},
        # ...
    ],
    "ownership": {"owner_group": "vcsi", "contact": "compstorylab@uvm.edu"},
    "lineage": {"repo": "https://github.com/org/babynames"},
})
```

## Registration Schema

The registration payload (`DatasetCreate`) is defined in [Specification §3.7](https://github.com/vermont-complex-systems/Storywrangler-Specification/blob/main/versions/0.0.3.md#37-dataset-registration-schema).

### Required fields

| Field | Description |
|---|---|
| `catalog` | Producer identity (organisation or group) |
| `domain` | Owning service or router (e.g. `wikimedia`, `babynames`) |
| `dataset_id` | Short identifier, unique within domain |
| `data_location` | Path to data on disk (string or list of strings) |
| `data_format` | `parquet` or `parquet_hive` |
| `description` | Human-readable description |
| `ownership` | `{owner_group, contact}` |
| `lineage` | `{repo}` at minimum |

### Storage formats

- **`parquet`** — single file, flat directory, or explicit file list. All filtering via WHERE clauses.
- **`parquet_hive`** — directory tree with `col=val/` at every level. Partition levels are **auto-discovered** at registration time — you only declare `time_dimension` and optionally `hash_bucket`.

### Key optional fields

| Field | Purpose |
|---|---|
| `endpoint_schema` | Output shape: `types-counts` (rank distributions) or `time-series` (tabular GROUP BY) |
| `transform` | Query axes: `time_dimension`, `filter_dimensions` (non-hive columns), `hash_bucket` |
| `entity_mapping` | Maps a local column to canonical entity IDs (see below) |
| `entities` | Entity rows: `{local_id, entity_id, entity_name}` |
| `manifest` | Coverage metadata (auto-derived — don't compute manually) |
| `version` | `"latest"` (default, mutable) or semver like `"1.0.0"` (immutable) |

### Auto-derived at registration

The server computes these from the data — submitters should not set them:
- `data_schema` — column names and types
- `level_order` — hive nesting order with type tags and defaults
- `manifest.availability` — time/entity coverage ranges
- `filter_values` — distinct values per filter dimension
- `hash_bucket` config — bucket counts per entity

## Entity Mapping

### `entity_namespace` — declaring identifier type

`entity_mapping.entity_namespace` tells the platform what kind of entity the
local-ID column holds. This enables cross-dataset joins and automatic entity
resolution.

**Pattern 1 — opaque local keys** (entity rows required):
```python
# Column holds state abbreviations — a lookup table maps them to Wikidata
{
    "entity_mapping": {"local_id_column": "state", "entity_namespace": "wikidata"},
    "entities": [
        {"local_id": "VT", "entity_id": "wikidata:Q16551", "entity_name": "Vermont"},
    ],
}
```

**Pattern 2 — global-identifier column** (no entity rows needed):
```python
# Column already holds OpenAlex author URLs
{
    "entity_mapping": {"local_id_column": "ego_author_id", "entity_namespace": "openalex"},
    # no "entities" list required — the platform derives canonical IDs from the namespace
}
```

## Instruments

The SDK wraps the platform's analytical endpoints so you can call them from Python without building HTTP requests.

### Allotaxonometer

Compare two type-frequency systems using rank-turbulence divergence:

```python
result = client.instrument.allotax(
    domain="wikimedia", dataset="ngrams",
    entity="wikidata:Q30", entity2="wikidata:Q145",
    dates="2024-10-01,2024-10-31",
    alpha=1.0,
)
# result keys: normalization, delta_sum, diamond_counts, wordshift, balance, meta
```

Filter dimensions are passed as keyword arguments:

```python
result = client.instrument.allotax(
    domain="babynames", dataset="ngrams",
    dates="1925", dates2="2025",
    sex="M", sex2="F",
)
```

### RTD (lightweight)

Fast date-vs-date wordshift (no diamond plot):

```python
result = client.instrument.rtd(
    entity="wikidata:Q30",
    dates="2026-02-17", dates2="2026-02-10",
)
# result keys: wordshift, alpha, meta
```

For the underlying computation without the platform, use the [`allotax`](https://pypi.org/project/allotax/) package directly.

## Hash Bucket Assignment

For datasets with content-sharded partitions (`transform.hash_bucket`), use `assign_bucket()` to partition files consistently with the query layer:

```python
from storywrangler.hashing import assign_bucket

# In your transform step — assign each row to a bucket directory
bucket = assign_bucket(term="hello world", num_buckets=16)
# → writes to ngram_bucket={bucket}/data.parquet
```

This uses murmur3_32 (seed 0) with a sign-bit mask, matching DuckDB's built-in `murmur3_32()` default. Both the backend query router and pipeline code import from the same source — `storywrangler_schemas.hashing` — ensuring bucket assignments are always consistent.

## Entity Validation

```python
from storywrangler.validation import EntityValidator

validator = EntityValidator()

validator.validate_wikidata("wikidata:Q937")          # True
validator.validate_orcid("orcid:0000-0002-1825-0097")  # True
validator.validate_openalex("openalex:A5002034958")     # True
validator.validate("ror:05qghxh33")                     # True (any namespace)
```

### Supported Namespaces

| Namespace   | Format example                  | Entity types                           |
|-------------|---------------------------------|----------------------------------------|
| `wikidata`  | `wikidata:Q937`                 | People, places, concepts, …            |
| `orcid`     | `orcid:0000-0002-1825-0097`     | Researchers                            |
| `openalex`  | `openalex:A5002034958`          | Authors (A), Works (W), Institutions (I), Concepts (C), Sources (S), Funders (F), Publishers (P) |
| `ror`       | `ror:05qghxh33`                 | Research organisations                 |
| `ipeds`     | `ipeds:231174`                  | US higher-ed institutions              |
| `doi`       | `doi:10.1038/nature12373`       | Published works                        |
| `isbn`      | `isbn:978-3-16-148410-0`        | Books                                  |
| `local`     | `local:<any-string>`            | Dataset-local identifiers              |

## Entity Graph (Beta)

The backend maintains an entity graph — a directed adjacency list of edges between
canonical entity IDs. This enables multi-hop traversal across namespaces.

```
openalex:A5002034958
  --affiliated_with--> openalex:I26873012   (UVM)
  --same_as----------> wikidata:Q1068        (UVM on Wikidata)
  --country----------> wikidata:Q30          (United States)
```

**Supported predicates:** `affiliated_with`, `same_as`, `country`, `broader`

**API endpoints:**
```
GET  /registry/entity-graph/path?from_id=openalex:A5002034958&to_namespace=wikidata
GET  /registry/entity-graph/neighbors?entity_id=openalex:I26873012
POST /admin/registry/entity-graph          # upsert edges (admin)
```

## Standards Compliance

This SDK implements [Storywrangler Specification v0.0.3](https://github.com/vermont-complex-systems/Storywrangler-Specification/blob/main/versions/0.0.3.md).

All validators follow the format requirements and validation algorithms defined in the specification.
