# Storywrangler Entity Standards v0.0.3

*v0.0.3 · 2026-04-19*

## Table of Contents

1. [Introduction](#1-introduction)
2. [Definitions](#2-definitions)
3. [Specification](#3-specification)
   - [Entity Identifier Systems](#31-entity-identifier-systems)
   - [Field Taxonomies](#32-field-taxonomies)
   - [Entity Mapping Requirements](#33-entity-mapping-requirements)
   - [Validation Rules](#34-validation-rules)
   - [Unresolved Entities](#35-unresolved-entities)
   - [API Endpoint Schemas](#36-api-endpoint-schemas)
   - [Dataset Registration Schema](#37-dataset-registration-schema)
4. [Extending the Standards](#4-extending-the-standards)
5. [Appendix A: Validation Algorithms](#appendix-a-validation-algorithms)
6. [Appendix B: Revision History](#appendix-b-revision-history)

---

## 1. Introduction

The Storywrangler Entity Standards define accepted entity identifier systems and field taxonomies to enable interoperability across datasets in the Storywrangler ecosystem.

### 1.1 Scope

This specification defines:
- Accepted entity identifier systems
- Accepted field taxonomy systems
- Format requirements for identifiers and classifications
- Validation rules
- Entity and field mapping requirements for adapters
- Dataset registration schema (storage formats, query axes, entity mapping, versioning)
- API endpoint schema contracts (`types-counts`, `time-series`)

This specification does NOT define:
- Internal query implementation (SQL generation, caching, routing)
- Processing algorithms
- API transport contracts (HTTP methods, status codes, pagination)

### 1.2 Terminology

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in RFC 2119.

---

## 2. Definitions

### Entity
A distinguishable person, place, organization, concept, event, or work referenced in a corpus.

### Entity Identifier
A persistent, unique identifier from a recognized identifier system (Wikidata, ORCID, OpenAlex, ROR, DOI, ISBN).

### Field Taxonomy
A classification system for organizing knowledge domains, academic disciplines, or subject areas.

### Adapter
Code component responsible for transforming pipeline outputs to include standardized entity identifiers and field classifications.

### Local Identifier
A corpus-specific identifier used when no standard identifier exists.

---

## 3. Specification

### 3.1 Entity Identifier Systems

#### 3.1.1 Wikidata Q-codes

**Namespace:** `wikidata`

**Format:** `wikidata:Q[0-9]+`

**Usage:** People, places, concepts, events, works, organizations.

**Resolution Base URL:** `https://www.wikidata.org/wiki/`

**External Specifications:**
- Wikidata Identifiers: https://www.wikidata.org/wiki/Wikidata:Identifiers
- Wikidata Data Model: https://www.mediawiki.org/wiki/Wikibase/DataModel

**Validation:**
- MUST match regular expression: `^wikidata:Q[0-9]+$`
- SHOULD verify entity exists in Wikidata

**When to use:**
- Default for all entities with Wikidata entries
- Required for concepts, places, events, works
- For people when ORCID is not available
- For organizations when ROR is not available

---

#### 3.1.2 ORCID

**Namespace:** `orcid`

**Format:** `orcid:[0-9]{4}-[0-9]{4}-[0-9]{4}-[0-9]{3}[0-9X]`

**Usage:** Academic authors, researchers, scholars.

**Resolution Base URL:** `https://orcid.org/`

**External Specifications:**
- ORCID Structure: https://support.orcid.org/hc/en-us/articles/360006897674

**Validation:**
- MUST match regular expression: `^orcid:[0-9]{4}-[0-9]{4}-[0-9]{4}-[0-9]{3}[0-9X]$`
- MUST pass ISO 7064 mod 11-2 checksum validation (see Appendix A.1)
- SHOULD verify ORCID is registered

**When to use:**
- REQUIRED for academic authors when available
- Preferred over OpenAlex and Wikidata for researchers with publications

---

#### 3.1.3 OpenAlex

**Namespace:** `openalex`

**Format:** `openalex:[AWICSFP][0-9]+`

**Usage:** Any entity type from the OpenAlex knowledge graph. The letter prefix encodes the entity type:

| Prefix | Entity type | Example |
|--------|-------------|---------|
| `A` | Author | `openalex:A5002034958` |
| `W` | Work (paper, preprint, book, dataset) | `openalex:W2741809807` |
| `I` | Institution | `openalex:I114027177` |
| `C` | Concept / field of study | `openalex:C41008148` |
| `S` | Source (journal, repository, conference) | `openalex:S1983995261` |
| `F` | Funder | `openalex:F4320332161` |
| `P` | Publisher | `openalex:P4310319965` |

**Resolution Base URL:** `https://openalex.org/`

**External Specifications:**
- OpenAlex API: https://docs.openalex.org/
- Author disambiguation: https://docs.openalex.org/api-entities/authors/author-disambiguation

**Validation:**
- MUST match regular expression: `^openalex:[AWICSFP][0-9]+$`
- SHOULD verify entity exists via OpenAlex API

**When to use:**
- Any dataset derived from OpenAlex
- Authors (`A`): when ORCID is unavailable; OpenAlex covers ~250M authors including those who have not self-registered
- Works (`W`): when DOI is unavailable (preprints, grey literature, books)
- Institutions (`I`): when ROR is unavailable
- Concepts (`C`): preferred over `mag:` namespace for field classifications (see §3.2.3)

**Notes:**
- OpenAlex IDs are algorithmically assigned; author records may occasionally merge or split as disambiguation improves
- OpenAlex is the actively maintained successor to Microsoft Academic Graph
- Unlike ORCID, OpenAlex IDs are not self-certified — ORCID remains the preferred identifier for authors when available

---

#### 3.1.4 ROR (Research Organization Registry)

**Namespace:** `ror`

**Format:** `ror:[a-z0-9]{9}`

**Usage:** Research organizations, universities, institutes.

**Resolution Base URL:** `https://ror.org/`

**External Specifications:**
- ROR Documentation: https://ror.readme.io/
- ROR API: https://ror.readme.io/docs/rest-api

**Validation:**
- MUST match regular expression: `^ror:[a-z0-9]{9}$`
- SHOULD verify ROR ID exists in registry

**When to use:**
- REQUIRED for research institutions when available
- Preferred over Wikidata for academic organizations


---


#### 3.1.5 IPEDS (Integrated Postsecondary Education Data System)

**Namespace:** `ipeds`

**Format:** `ipeds:[0-9]{6}`

**Usage:** US postsecondary education institutions (colleges, universities).

**Resolution Base URL:** `https://nces.ed.gov/collegenavigator/?id=`

**External Specifications:**
- IPEDS Overview: https://nces.ed.gov/ipeds/
- IPEDS Database: https://nces.ed.gov/ipeds/use-the-data

**Validation:**
- MUST match regular expression: `^ipeds:[0-9]{6}$`
- SHOULD verify IPEDS ID exists in NCES database

**When to use:**
- US higher education institutions
- Course catalog data
- Educational research datasets
- Use alongside ROR when both available

**Relationship to ROR:**
- Many US institutions have both IPEDS and ROR IDs
- IPEDS is US-specific, ROR is international
- Prefer ROR for international interoperability
- Include both when available

**Examples:**
- `ipeds:230764` (University of Vermont)
- `ipeds:166027` (MIT)
- `ipeds:110635` (Harvard University)

**Notes:**
- IPEDS IDs are 6-digit integers (with leading zeros preserved)
- Only covers US postsecondary institutions
- Maintained by National Center for Education Statistics (NCES)

---

#### 3.1.6 DOI (Digital Object Identifier)

**Namespace:** `doi`

**Format:** `doi:10.[0-9]{4,}/[^\s]+`

**Usage:** Published scholarly works, datasets, books with DOIs.

**Resolution Base URL:** `https://doi.org/`

**External Specifications:**
- DOI Handbook: https://www.doi.org/doi-handbook/
- DOI Resolution: https://dx.doi.org/

**Validation:**
- MUST match regular expression: `^doi:10\.[0-9]{4,}/[^\s]+$`
- SHOULD verify DOI resolves

**When to use:**
- REQUIRED for published papers, articles, datasets with DOIs
- Use alongside ORCID for author attribution
- Preferred over URLs for citing scholarly works


---

#### 3.1.7 ISBN (International Standard Book Number)

**Namespace:** `isbn`

**Format:** `isbn:[0-9]{13}` or `isbn:[0-9]{9}[0-9X]`

**Usage:** Books (both print and digital editions).

**Resolution Base URLs:**
- WorldCat: `https://www.worldcat.org/isbn/`
- Open Library: `https://openlibrary.org/isbn/`

**External Specifications:**
- ISBN International: https://www.isbn-international.org/
- ISBN Users' Manual: https://www.isbn-international.org/content/isbn-users-manual

**Validation:**
- MUST match one of:
  - ISBN-13: `^isbn:[0-9]{13}$`
  - ISBN-10: `^isbn:[0-9]{9}[0-9X]$`
- MUST pass checksum validation (see Appendix A.2)
- Hyphens MUST be removed before validation

**When to use:**
- REQUIRED for books with ISBNs
- Use ISBN-13 when both formats exist
- Reference books in course catalogs, literature corpora, citation contexts

**Notes:**
- ISBNs should be stored without hyphens
- ISBN-10 can be converted to ISBN-13 (prefix with 978)
- Different editions of same book have different ISBNs

---

### 3.2 Field Taxonomies

Field and subject classifications enable thematic organization and discovery across datasets. Multiple classification systems are accepted to accommodate domain-specific needs and address coverage gaps in general-purpose taxonomies.

**General Principle:** Adapters MUST provide at least one recognized taxonomy identifier. Adapters MAY provide multiple taxonomies for the same entity to enable cross-system mapping.

#### 3.2.1 Wikidata Fields

**Namespace:** `wikidata`

**Format:** `wikidata:Q{id}`

**Usage:** General-purpose field classifications across all domains.

**External Specifications:**
- Wikidata Academic Disciplines: https://www.wikidata.org/wiki/Q11862829
- SPARQL Query Service: https://query.wikidata.org/

**Validation:**
- MUST match regular expression: `^wikidata:Q[0-9]+$`
- SHOULD verify entity exists and represents an academic field or discipline

**When to use:**
- Default for general cross-domain classification
- When no domain-specific taxonomy applies
- For interdisciplinary topics well-represented in Wikidata

**Limitations:**
- May lack precision for specialized subfields
- Coverage gaps in emerging fields
- Potential geographic and language biases

---

#### 3.2.2 arXiv Categories

**Namespace:** `arxiv`

**Format:** `arxiv:{category}` or `arxiv:{archive}.{subject-class}`

**Usage:** Preprint classifications, particularly computer science, physics, mathematics, and quantitative fields.

**External Specifications:**
- arXiv Category Taxonomy: https://arxiv.org/category_taxonomy
- arXiv Subject Classifications: https://arxiv.org/help/api/user-manual

**Validation:**
- MUST match pattern: `^arxiv:[a-z-]+(\.[A-Z]{2})?$`
- SHOULD verify category exists in arXiv taxonomy

**When to use:**
- Papers from arXiv or similar preprint servers
- Computer science, physics, mathematics research
- When arXiv's fine-grained categories add precision

**Hierarchy:** arXiv categories have implicit two-level hierarchy (archive.subject-class). Adapters MAY encode this explicitly in metadata.

---

#### 3.2.3 Microsoft Academic Graph (MAG) Field IDs

**Namespace:** `mag`

**Format:** `mag:{id}`

**Usage:** Scholarly publications classified in Microsoft Academic Graph or OpenAlex.

**External Specifications:**
- OpenAlex Concepts: https://docs.openalex.org/api-entities/concepts
- MAG Field of Study (legacy): https://www.microsoft.com/en-us/research/project/academic/

**Validation:**
- MUST match pattern: `^mag:[0-9]+$`
- SHOULD verify field ID exists (via OpenAlex API)

**When to use:**
- Datasets derived from OpenAlex or legacy MAG
- When leveraging MAG's hierarchical field structure
- Papers with existing MAG classifications

**Note:** Microsoft Academic Graph was retired in 2021. For new datasets use `openalex:C...` (§3.1.3) instead of `mag:`. The `mag:` namespace is retained for backwards compatibility with existing data.

---

#### 3.2.4 Multiple Taxonomies

An entity MAY be classified using multiple taxonomy systems simultaneously.

**When to use multiple taxonomies:**
- Dataset originates from system with native classification (e.g., arXiv papers include arXiv categories)
- Enable cross-dataset queries by providing Wikidata mapping
- Preserve domain-specific precision while maintaining interoperability

**Format:**
```json
{
  "fields": [
    {"id": "arxiv:cs.CL", "primary": true, "confidence": 1.0},
    {"id": "wikidata:Q21198", "primary": false, "confidence": 0.8}
  ]
}
```

**Requirements:**
- At least one taxonomy MUST be marked as `primary`
- Confidence scores (0.0-1.0) SHOULD be provided when mapping is uncertain
- Adapters SHOULD document mapping methodology

---

#### 3.2.5 Local Field Classifications

When no standard taxonomy adequately represents a field, discipline, or subject area:

**Namespace:** `local`

**Format:** `local:{corpus_id}:{field_id}`

**Examples:**
- `local:indigenous-knowledge:traditional_medicine`
- `local:women-in-math:algebra_educators`

**Requirements:**
- MUST be used only when standard taxonomies have coverage gaps
- MUST document field definitions in dataset metadata
- SHOULD provide human-readable labels
- SHOULD attempt mapping to standard taxonomies
- MAY be upgraded to standard identifiers in future versions

---

#### 3.2.6 Cross-Taxonomy Mapping

Storywrangler provides utilities for mapping between taxonomy systems where feasible.

**Mapping guarantees:**
- Exact mappings provided where documented
- Approximate mappings provided with confidence scores
- No guarantee of perfect translation across all systems

**Query behavior:**
When querying by field, Storywrangler API:
1. Returns exact matches for specified taxonomy
2. MAY return approximate matches from other taxonomies
3. Includes confidence scores for cross-taxonomy matches

**Adapters are not required to provide mappings** - Storywrangler handles cross-taxonomy queries using internal mapping tables.

---

#### 3.2.7 Hierarchy and Relationships

Many taxonomies encode hierarchical relationships (broader/narrower fields).

**Approach:**
- Wikidata: Use SPARQL queries with `P279` (subclass of) relationships
- arXiv: Implicit hierarchy in archive.subject-class structure  
- MAG: Hierarchical field structure available via OpenAlex API

**Adapters are not required to explicitly encode hierarchy.** Storywrangler leverages native taxonomy structures for hierarchical queries.

**Optional:** Adapters MAY provide explicit hierarchy in metadata for clarity or performance optimization.

---

### 3.3 Entity Mapping Requirements

#### 3.3.1 Adapter Obligations

Adapters MUST:
1. Map entities to at least one standard identifier system
2. Validate identifier format using Section 3.1 specifications
3. Use priority rules defined in Section 3.3.2

Adapters SHOULD:
1. Verify identifiers exist in source registries
2. Provide confidence scores for mappings when uncertain
3. Document entity resolution methodology in pipeline code

#### 3.3.2 Priority Rules

When multiple identifier systems could apply:

**For people:**
1. ORCID (if academic/researcher — self-certified ground truth)
2. `openalex:A...` (if researcher with publications and no ORCID)
3. Wikidata Q-code (for scholars, public figures, or historical persons not in OpenAlex)

**For works:**
1. DOI (if available)
2. `openalex:W...` (for works without DOIs: preprints, grey literature, book chapters)
3. ISBN (if book)
4. Wikidata Q-code (otherwise)

**For organizations:**
1. ROR (if research institution, preferred for international interoperability)
2. IPEDS (if US higher education institution)
3. `openalex:I...` (if institution is in OpenAlex but lacks ROR)
4. Wikidata Q-code (otherwise)

**Note:** US higher education institutions SHOULD include both ROR and IPEDS when available.

**For published works:**
1. DOI (if available)
2. ISBN (if book)
3. Wikidata Q-code (otherwise)

**For concepts, places, events:**
1. Wikidata Q-code (required)

**For fields/subjects:**
- Use taxonomy most appropriate for dataset origin
- Multiple taxonomies MAY be provided (see Section 3.2.4)

#### 3.3.3 Multiple Identifiers

An entity MAY have multiple identifiers from different systems. When providing multiple identifiers:
- One MUST be designated as primary
- Others MAY be listed as alternatives
- Adapters SHOULD document why multiple identifiers are provided

---

### 3.4 Validation Rules

#### 3.4.1 Format Validation

All entity identifiers and field classifications MUST:
1. Include namespace prefix
2. Match the format specification for their system
3. Not include whitespace

#### 3.4.2 Existence Validation

Adapters SHOULD verify that identifiers exist in their source registries. When verification fails:
- MAY proceed with format-valid identifier
- SHOULD document validation status in metadata
- MUST NOT proceed if identifier format is invalid

---

### 3.5 Unresolved Entities

#### 3.5.1 Local Identifiers

When an entity cannot be mapped to a standard identifier system, adapters MAY use local identifiers.

**Namespace:** `local`

**Format:** `local:{corpus_id}:{local_id}`

Where:
- `{corpus_id}` is the corpus identifier
- `{local_id}` is a corpus-specific identifier

**Example:** `local:women-in-math:person_042`

**Constraints:**
- MUST be used only when no standard identifier exists
- SHOULD include confidence score indicating mapping quality
- MAY be upgraded to standard identifiers in future versions

#### 3.5.2 Documentation Requirements

When using local identifiers, adapters SHOULD document:
- Why no standard identifier exists
- Entity resolution attempts made
- Potential future resolution strategies

---

### 3.6 API Endpoint Schemas

This section defines the output schemas for standardized API endpoints. Each dataset declares its endpoint type via `endpoint_schema.type` (see §3.7.4). The endpoint type determines the response shape and column semantics.

#### 3.6.1 `types-counts`

A rank distribution: a bag of (type, count) pairs ordered by frequency. Used for rank-based comparisons such as rank-turbulence divergence.

**Default columns:**
- `types` (VARCHAR): The token, label, or type value
- `counts` (INTEGER): Frequency count

Datasets with non-default column names MUST declare them via `endpoint_schema.type_column` and `endpoint_schema.count_column` (see §3.7.4).

**Response format:** JSON array, ordered by count descending.

```json
[
  {"types": "John", "counts": 1234},
  {"types": "Mary", "counts": 987},
  {"types": "Michael", "counts": 856}
]
```

**Requirements:**
- Response MUST be a JSON array (no wrapper objects)
- Results MUST be ordered by count in descending order
- The type column MUST be a text/varchar data type
- The count column MUST be an integer data type

**Typical query axes:** entity, time range, categorical filters (e.g. sex, granularity). Filter parameters are dataset-specific, declared via `transform` (see §3.7.5).

---

#### 3.6.2 `time-series`

Tabular rows from a flexible GROUP BY query. The caller chooses which dimensions to group by and which to filter on. Used for trend analysis and exploratory drill-down.

**Default columns:**
- `count` (INTEGER): The numeric measure to SUM

The count column name MAY be overridden via `endpoint_schema.count_column`. There is no `type_column` for `time-series` — all non-count columns are grouping/filtering dimensions.

**Response format:** JSON array of row objects. Column names match the dataset schema.

```json
[
  {"field": "Computer Science", "year": 2020, "count": 142857},
  {"field": "Computer Science", "year": 2021, "count": 158432},
  {"field": "Physics", "year": 2020, "count": 98765}
]
```

**Requirements:**
- Response MUST be a JSON array of row objects
- Results SHOULD be ordered by the time dimension ascending
- The count column MUST be an integer data type
- The dataset MUST declare `transform.time_dimension`
- The dataset MUST declare at least one `transform.filter_dimensions` entry

**Query interface:** Callers specify `group_by` (which dimensions appear in the SELECT/GROUP BY) and filter parameters (which become WHERE clauses). Multi-value filters (comma-separated) generate IN clauses.

---

### 3.7 Dataset Registration Schema

This section defines the `DatasetCreate` object — the registration payload submitted to the Storywrangler registry. Registration is an upsert: safe to re-run after data or metadata changes. The `(domain, dataset_id, version)` tuple uniquely identifies a dataset entry.

#### 3.7.1 Overview

A registration declares:

1. **Where the data lives** — storage format and file path (`data_format`, `data_location`)
2. **What the API returns** — endpoint type and column names (`endpoint_schema`)
3. **How callers can slice the data** — time axis, categorical filters, hash buckets (`transform`)
4. **How entities are resolved** — local column → canonical identifier mapping (`entity_mapping`, `entities`)
5. **Who owns it and where it came from** — governance and provenance (`ownership`, `lineage`)
6. **What version it is** — mutable `latest` slot or immutable semver snapshots (`version`)

The registry auto-derives additional metadata at registration time:
- `data_schema` — column names and DuckDB types (from the parquet files)
- `level_order` — hive nesting order with type tags and defaults (from the directory structure)
- `manifest.availability` — time/entity coverage ranges (from the data)
- `filter_values` — enumerable distinct values per filter dimension (from the data)
- `hash_bucket` config — bucket counts per entity (from the directory structure)

#### 3.7.2 Required Fields

All registrations MUST include these fields:

| Field | Type | Description |
|---|---|---|
| `catalog` | string | Producer identity — organisation or group registering this dataset |
| `domain` | string | Owning service or router (e.g. `wikimedia`, `babynames`, `scisciDB`) |
| `dataset_id` | string | Short identifier, unique within domain (e.g. `ngrams`, `revisions`) |
| `data_location` | string or string[] | Path to the data on disk (see §3.7.3) |
| `data_format` | enum | Storage format: `parquet` or `parquet_hive` (see §3.7.3) |
| `description` | string | Human-readable description of the dataset |
| `ownership` | object | Ownership metadata (see §3.7.8) |
| `lineage` | object | Provenance metadata (see §3.7.8) |

#### 3.7.3 Storage Formats

Storywrangler accepts exactly two storage formats:

##### `parquet` — flat parquet

Single file, flat directory of files, or explicit file list.

`data_location` supports three forms:
- Single file: `/data/babynames.parquet`
- Flat directory: `/data/babynames/` (all `.parquet` files are read)
- File list: `["/data/f1.parquet", "/data/f2.parquet"]`

No directory structure is interpreted. All filtering is done via WHERE clauses on columns within the files.

##### `parquet_hive` — hive-partitioned parquet

Directory tree where **every partition level uses `col=val/` naming** (Apache Hive convention).

`data_location` MUST be the **root** of the hive tree — the directory directly above the first `col=val/` level.

```
/data/ngrams/                        ← data_location points here
  ngram_size=1/
    granularity=daily/
      country=United States/
        date=2024-01-01/
          data_0.parquet
```

**Requirements:**
- Every partition level MUST follow hive naming (`col=val/`)
- Non-hive directory names (e.g. `1grams/`, `daily/`) are NOT supported
- Partition levels are auto-discovered from the directory structure at registration time
- Each discovered level is classified by matching against declarations in `transform` and `entity_mapping` (see §3.7.6)

**Why hive-only:** DuckDB's `hive_partitioning=true` handles partition pruning automatically for any combination of WHERE conditions. This makes filtering uniform across both storage formats.

---

#### 3.7.4 Endpoint Schema

Declares what columns the API reads and returns. Describes the response structure only — query slicing belongs in `transform` (§3.7.5).

```json
{
  "type": "types-counts",
  "type_column": "ngram",
  "count_column": "pv_count"
}
```

| Field | Required | Description |
|---|---|---|
| `type` | REQUIRED | Endpoint type. MUST be one of: `types-counts`, `time-series`. See §3.6 |
| `type_column` | OPTIONAL | `types-counts` only. Column holding token/type values. Defaults to `types` |
| `count_column` | OPTIONAL | Column holding the numeric measure. Defaults to `counts` for `types-counts`, `count` for `time-series` |

Datasets that use the default column names (`types`/`counts` or `count`) MAY omit `type_column` and `count_column`.

**Constraints:**
- `types-counts` datasets MUST declare either `entity_mapping` or `transform.filter_dimensions` (there must be at least one axis to slice on)
- `time-series` datasets MUST declare `transform.time_dimension` and at least one `transform.filter_dimensions` entry

---

#### 3.7.5 Transform Configuration

Declares the query slice axes — how callers can filter the dataset at request time.

```json
{
  "time_dimension": "date",
  "filter_dimensions": ["sex"],
  "hash_bucket": "ngram_bucket"
}
```

| Field | Required | Description |
|---|---|---|
| `time_dimension` | OPTIONAL | Column name for time-range filtering (e.g. `year`, `date`). For `parquet_hive`, this is the hive partition column holding the time value |
| `filter_dimensions` | OPTIONAL | Non-hive categorical columns inside parquet files where omitting the filter aggregates over all values (e.g. `["sex"]`). NOT needed for hive partition levels — those are auto-discovered |
| `hash_bucket` | OPTIONAL | Hive partition column holding content-shard bucket IDs (e.g. `ngram_bucket`). Bucket counts per entity are auto-derived from the directory structure at registration. See §3.7.5.1 |
| `hash_algorithm` | OPTIONAL | Hash algorithm for bucket routing. Currently only `murmur3_32` is supported. Defaults to `murmur3_32` |
| `hash_seed` | OPTIONAL | Seed for the hash function. Defaults to `0` (matches DuckDB's `murmur3_32()` default) |

**For `parquet_hive` datasets:** Hive partition levels do NOT need to be declared. They are auto-discovered from the directory structure and stored in `level_order` (§3.7.6). The minimal `transform` submission for a hive dataset is:

```json
{"time_dimension": "date"}
```

##### 3.7.5.1 Hash Buckets

Hash buckets are content-sharded partitions used to split large datasets (e.g. n-gram files) into manageable file sizes. They are **routing-only** — not query axes, not exposed to end users.

**Submission format:** The submitter declares only the column name:

```json
"ngram_bucket"
```

**Derived config:** At registration, the platform walks the directory tree and derives:
- `default_count` — the modal bucket count across all entity × partition combinations
- `overrides` — entity/partition combinations that differ from the default

**Query-time routing:** The query layer computes the target bucket using murmur3 (seed 0):

```
bucket = (murmur3_32(term, seed=0) & 0x7FFFFFFF) % count
```

- `& 0x7FFFFFFF` clears the sign bit (murmur3 returns signed int32; bucket IDs MUST be ≥ 0)
- Seed 0 matches DuckDB's `murmur3_32()` default
- `count` is resolved per entity from the derived config
- `hash_algorithm` and `hash_seed` are stored in the schema for machine-readable contract declaration

**SDK function:** The SDK provides `storywrangler.hashing.assign_bucket(term, num_buckets)` — the canonical implementation of this algorithm. Pipelines MUST use this function (or an exact reimplementation) when partitioning files into bucket directories. This ensures consistency between data production and query-time routing.

---

#### 3.7.6 Level Order (Derived)

For `parquet_hive` datasets, the registry auto-discovers the on-disk hive nesting order at registration time and stores it as `level_order`. This is the single source of truth for the dataset's directory structure.

**Format:** Ordered array of level descriptors:

```json
[
  {"column": "ngram_size",  "type": "partition", "default_value": 1},
  {"column": "granularity", "type": "partition", "default_value": "daily"},
  {"column": "country",     "type": "entity",    "default_value": "Afghanistan"},
  {"column": "date",        "type": "time",      "default_value": "2020-01-01"}
]
```

**Type tags:** Each discovered hive level is classified by matching against declarations:

| Type | Source | Description |
|---|---|---|
| `partition` | undeclared hive levels | Queryable partition axis with auto-default |
| `entity` | `entity_mapping.local_id_column` | Entity resolution column |
| `hash_bucket` | `transform.hash_bucket` | Content-shard routing column |
| `time` | `transform.time_dimension` | Time-range filtering column |
| `filter` | `transform.filter_dimensions` | Non-hive filter appearing as hive level |

**`default_value`:** The first on-disk value (sorted alphabetically) for each level. Used by the query layer when a caller omits a partition parameter.

**Classification rules:**
- Levels matching `entity_mapping.local_id_column` → `entity`
- Levels matching `transform.time_dimension` → `time`
- Levels matching `transform.hash_bucket` → `hash_bucket`
- Levels matching a `transform.filter_dimensions` entry → `filter`
- All remaining levels → `partition` (with auto-default from first on-disk value)

**Registration validation:**
- Registration MUST fail with 422 if `transform.hash_bucket` names a column not found on disk

**Backward compatibility:** `level_order` is absent (`null`) for datasets registered before this feature was introduced. Query-time code MUST fall back to recursive glob patterns when `level_order` is absent.

---

#### 3.7.7 Entity Mapping

Declares how a dataset-local column maps to canonical entity identifiers from §3.1.

```json
{
  "local_id_column": "country",
  "entity_namespace": "wikidata"
}
```

| Field | Required | Description |
|---|---|---|
| `local_id_column` | REQUIRED | Column in the dataset holding the entity identifier |
| `entity_namespace` | OPTIONAL | Canonical namespace for the identifiers (see §3.1). Enables cross-dataset entity graph traversal |

**Two resolution patterns:**

1. **Opaque local keys** — the column holds non-standard values (e.g. country names, state abbreviations). The submitter provides `entities` rows mapping each `local_id` to a canonical `entity_id`. `entity_namespace` is RECOMMENDED.

2. **Global-identifier columns** — the column already holds values from a recognised namespace (e.g. OpenAlex author URLs, DOIs). Set `entity_namespace` to declare the namespace. Entity rows are OPTIONAL — useful only for display names or format normalization.

**Dual role in hive datasets:** For `parquet_hive`, `local_id_column` is both the entity resolution column AND the hive partition key. The directory level is `local_id_column=value/`. This is intentional — hive partitioning promotes a column to the path level; the name remains the column name.

**Entity rows:** Submitted inline as `entities` in the registration payload, or via a separate batch endpoint. Each row contains:

| Field | Required | Description |
|---|---|---|
| `local_id` | REQUIRED | Dataset-local identifier value |
| `entity_id` | REQUIRED | Canonical entity ID (MUST match a format from §3.1) |
| `entity_name` | REQUIRED | Human-readable name |
| `entity_ids` | OPTIONAL | Alternate identifiers (e.g. `["iso:US", "local:babynames:united_states"]`) |

**Auto-derivation:** If `entity_namespace` is omitted but `entities` rows are provided, the namespace is auto-derived from the entity_id prefixes when all rows share the same known namespace.

---

#### 3.7.8 Ownership and Lineage

##### Ownership

```json
{
  "owner_group": "vcsi",
  "contact": "compstorylab@uvm.edu",
  "status": "active"
}
```

| Field | Required | Description |
|---|---|---|
| `owner_group` | REQUIRED | Lab or research group identifier |
| `contact` | REQUIRED | Email or GitHub handle of the current maintainer |
| `status` | OPTIONAL | Lifecycle state: `active` (default), `needs_successor`, or `archived` |

##### Lineage

```json
{
  "sources": {"geo": {"united_states": "https://www.ssa.gov/..."}},
  "derived_from": ["wikimedia/ngrams"],
  "consumers": ["storywrangler/allotax"],
  "repo": "https://github.com/Vermont-Complex-Systems/babynames"
}
```

| Field | Required | Description |
|---|---|---|
| `repo` | REQUIRED | Git repository URL for the producing pipeline |
| `sources` | OPTIONAL | External raw data URLs, keyed by dimension then location |
| `derived_from` | OPTIONAL | Intra-registry upstream datasets as `domain/dataset_id` |
| `consumers` | OPTIONAL | Downstream users — stories, tools, or scripts |
| `archival_doi` | OPTIONAL | DOI from an archival system (e.g. Harvard Dataverse) for long-term preservation |

---

#### 3.7.9 Versioning

The `version` field controls dataset mutability:

- **`latest`** (default) — mutable development slot. Each re-registration overwrites the previous entry. Safe to re-register freely during development.
- **Semver strings** (e.g. `1.0.0`) — immutable snapshots. Re-registering the same version string MUST return 409 Conflict.

**Semver semantics:**
- **PATCH** — bug fixes (same schema, corrected values)
- **MINOR** — new data (new time range, new entities — backward compatible)
- **MAJOR** — breaking schema changes (column rename, endpoint_schema change)

Semver interpretation follows https://semver.org/.

---

#### 3.7.10 Manifest (Derived)

Pre-computed coverage metadata, never read at query time. Used for discovery, UI display, and SDK consumers. The name is borrowed from Apache Iceberg's concept of a manifest.

```json
{
  "availability": {
    "United States": {"daily": {"min": "2024-01-01", "max": "2026-04-20", "types": 2648755}},
    "Canada": {"daily": {"min": "2024-01-01", "max": "2026-04-20", "types": 1893002}}
  },
  "partition_index": [
    {"identifier": "Cat", "revision_count": 142, "first_edit": "2001-01-01"}
  ]
}
```

| Field | Derived? | Description |
|---|---|---|
| `availability` | Yes — auto-populated at registration | Time coverage summary: MIN/MAX of the time dimension, grouped by entity and partition dimensions. Entity-first format when `entity_mapping` is present; flat otherwise |
| `availability.*.types` | Yes — types-counts datasets only | Vocabulary size (distinct type count) at the latest available date, per entity × partition combination. A representative ceiling hint for `topN`-style parameters, not an exact figure for arbitrary date ranges |
| `partition_index` | No — submitter-provided | Enumerable partition list with optional per-partition stats. Stored separately from summary responses |

**`availability` auto-population:** When `transform.time_dimension` is set, the registry computes availability by scanning the data files at registration time. Submitters SHOULD NOT compute this manually. For datasets with `endpoint_schema.type = "types-counts"`, each availability leaf also gains a `types` count (best-effort — a leaf may hold bounds only if the count could not be read).

---

#### 3.7.11 Complete Examples

##### Minimal flat parquet (no time axis)

```json
{
  "catalog": "vcsi",
  "domain": "Vermont-Zoning-Atlas",
  "dataset_id": "zoning_bylaws",
  "data_location": "/data/vt/zoning_bylaws.parquet",
  "data_format": "parquet",
  "description": "Vermont municipal zoning bylaws.",
  "endpoint_schema": {"type": "types-counts"},
  "entity_mapping": {"local_id_column": "town", "entity_namespace": "wikidata"},
  "ownership": {"owner_group": "vcsi", "contact": "compstorylab@uvm.edu"},
  "lineage": {"repo": "https://github.com/Vermont-Complex-Systems/vt-zoning-atlas"}
}
```

##### Hive-partitioned with entity mapping and hash buckets (wikimedia ngrams)

```json
{
  "catalog": "vcsi",
  "domain": "wikimedia",
  "dataset_id": "ngrams",
  "data_location": "/netfiles/wikimedia_snapshots/wikigrams",
  "data_format": "parquet_hive",
  "description": "Wikipedia n-grams by frequency, date, and location.",
  "endpoint_schema": {
    "type": "types-counts",
    "type_column": "ngram",
    "count_column": "pv_count"
  },
  "transform": {
    "time_dimension": "date",
    "hash_bucket": "ngram_bucket"
  },
  "entity_mapping": {
    "local_id_column": "country",
    "entity_namespace": "wikidata"
  },
  "ownership": {"owner_group": "vcsi", "contact": "compstorylab@uvm.edu"},
  "lineage": {
    "sources": {"url": "https://dumps.wikimedia.org/other/enterprise_html/"},
    "repo": "https://github.com/Vermont-Complex-Systems/wikipedia-parsing"
  }
}
```

Hive levels auto-discovered: `ngram_size → granularity → country → date` (with `ngram_bucket` nested under `country`).

##### Time-series endpoint (scisciDB)

```json
{
  "catalog": "vcsi",
  "domain": "scisciDB",
  "dataset_id": "field-venue-metrics",
  "data_location": "/netfiles/compethicslab/scisciDB/field-venue-metrics",
  "data_format": "parquet_hive",
  "description": "Precomputed paper counts by S2 field, venue, year, and metric type.",
  "endpoint_schema": {
    "type": "time-series",
    "count_column": "count"
  },
  "transform": {
    "time_dimension": "year",
    "filter_dimensions": ["field", "venue"]
  },
  "ownership": {"owner_group": "compethicslab", "contact": "compstorylab@uvm.edu"},
  "lineage": {
    "sources": {"semantic_scholar": {"s2_papers": "https://api.semanticscholar.org/datasets/v1/release/"}},
    "repo": "https://github.com/jstonge/scisciDB"
  }
}
```

Hive level `metric_type` is auto-discovered as a `partition` level. The query layer injects its default value when callers omit it.

---

## 4. Extending the Standards

### 4.1 Proposing New Systems

To propose a new entity identifier system or field taxonomy:

1. Open GitHub Discussion in storywrangler-standards repository
2. Provide specification following format in Section 3:
   - Namespace
   - Format with regular expression
   - Usage description
   - Resolution base URL (if applicable)
   - External specifications
   - Validation rules
3. Demonstrate:
   - Persistent, stable identifiers
   - Open access for validation/resolution
   - Active governance
   - Community need (affected datasets)

### 4.2 Governance

The Technical Steering Committee reviews proposals quarterly.

**Approval criteria:**
- Majority vote from TSC
- Technical feasibility demonstrated
- Community need established
- Maintenance commitment identified

**Upon approval:**
1. Specification added to next minor version
2. Implementation in storywrangler-sdk required
3. Migration guide published
4. Announcement to community

---

## Appendix A: Validation Algorithms

### A.1 ORCID Checksum (ISO 7064 mod 11-2)

The final character of an ORCID identifier is a check digit calculated using the ISO 7064 mod 11-2 algorithm:

1. Remove the `orcid:` prefix and all hyphens
2. Take the first 15 digits
3. Initialize total = 0
4. For each digit:
   - total = (total + digit) × 2
5. remainder = total mod 11
6. result = (12 - remainder) mod 11
7. If result = 10, check digit is 'X', otherwise it is the string representation of result

The identifier is valid if the calculated check digit matches the final character.

---

### A.2 ISBN Checksum Validation

#### A.2.1 ISBN-13 Checksum

ISBN-13 uses a weighted sum modulo 10:

1. Remove `isbn:` prefix and all hyphens
2. Take all 13 digits
3. Multiply odd-position digits (1st, 3rd, 5th...) by 1
4. Multiply even-position digits (2nd, 4th, 6th...) by 3
5. Sum all results
6. Check digit = (10 - (sum mod 10)) mod 10

The ISBN is valid if the calculated check digit matches the 13th digit.

#### A.2.2 ISBN-10 Checksum

ISBN-10 uses modulo 11:

1. Remove `isbn:` prefix and all hyphens
2. Take first 9 digits
3. For each digit at position i (1-indexed):
   - Multiply digit by (11 - i)
4. Sum all results
5. remainder = sum mod 11
6. Check digit = 11 - remainder
7. If check digit = 10, use 'X'

The ISBN is valid if the calculated check digit matches the 10th character.

#### A.2.3 ISBN-10 to ISBN-13 Conversion

To convert ISBN-10 to ISBN-13:
1. Prefix with "978"
2. Take first 9 digits of ISBN-10
3. Calculate new ISBN-13 check digit using A.2.1

---

## Appendix B: Revision History

### Version 0.0.3 (2026-05-18)

**Added Dataset Registration Schema (§3.7):**
- Storage formats: `parquet` (flat) and `parquet_hive` (hive-partitioned with `col=val/` at every level)
- `endpoint_schema`: output shape declaration (`type`, `type_column`, `count_column`)
- `transform`: query slice axes (`time_dimension`, `filter_dimensions`, `hash_bucket`)
- `entity_mapping`: local column → canonical entity ID resolution (connects to §3.1)
- `level_order`: auto-derived hive nesting order with type tags and defaults
- `manifest`: auto-derived availability and submitter-provided partition_index
- `ownership` and `lineage`: governance and provenance metadata
- `version`: mutable `latest` slot and immutable semver snapshots
- Three complete registration examples (flat parquet, hive with entities, time-series)

**Expanded §3.6 API Endpoint Schemas:**
- Renamed §3.6.1 from "Top N-Grams Endpoint" to `types-counts` to match endpoint type name
- Added §3.6.2 `time-series` — tabular rows from flexible GROUP BY queries
- Documented custom column name declarations via `type_column` / `count_column`

**Updated §1.1 Scope:**
- Added dataset registration schema and endpoint schema contracts to "defines" list
- Refined "does NOT define" — "Internal data formats" → "Internal query implementation"

---

### Version 0.0.2 (2026-03-24)

**Added entity identifier systems:**
- OpenAlex (`openalex:[AWICSFP][0-9]+`) — covers all OpenAlex entity types: authors (A), works (W), institutions (I), concepts (C), sources (S), funders (F), publishers (P)

**Updated priority rules (§3.3.2):**
- People: ORCID > `openalex:A...` > Wikidata
- Works: DOI > `openalex:W...` > ISBN > Wikidata
- Organizations: ROR > IPEDS > `openalex:I...` > Wikidata

**Updated §3.2.3:** `mag:` namespace retained for backwards compatibility; new datasets should use `openalex:C...`

---

### Version 0.0.1 (2025-11-09)

Initial release.

**Included entity identifier systems:**
- Wikidata Q-codes
- ORCID
- ROR
- DOI
- ISBN

**Included field taxonomies:**
- Wikidata fields
- arXiv categories
- Microsoft Academic Graph (MAG) field IDs

**Initial governance:** Technical Steering Committee established