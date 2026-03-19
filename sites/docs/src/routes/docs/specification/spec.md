# Storywrangler Entity Standards v1.0

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
   - [Adapter Submission Contract](#37-adapter-submission-contract)
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
- Endpoint response schemas required for interoperability
- Adapter submission contract (registration payload schema)

This specification does NOT define:
- Internal data formats
- Processing algorithms

### 1.2 Terminology

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in RFC 2119.

---

## 2. Definitions

### Entity
A distinguishable person, place, organization, concept, event, or work referenced in a corpus.

### Entity Identifier
A persistent, unique identifier from a recognized identifier system (Wikidata, ORCID, ROR, DOI, ISBN).

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
- Preferred over Wikidata for researchers with publications

---

#### 3.1.3 ROR (Research Organization Registry)

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


#### 3.1.4 IPEDS (Integrated Postsecondary Education Data System)

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

#### 3.1.5 DOI (Digital Object Identifier)

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

#### 3.1.6 ISBN (International Standard Book Number)

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

**Note:** Microsoft Academic Graph was retired in 2021. Use OpenAlex Concepts API for current field mappings and validation.

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
1. ORCID (if academic/researcher with publications)
2. Wikidata Q-code (otherwise)

**For organizations:**
1. ROR (if research institution, preferred for international interoperability)
2. IPEDS (if US higher education institution)
3. Wikidata Q-code (otherwise)

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

This section defines required schemas for standardized API endpoints across Storywrangler datasets.

#### 3.6.1 Top N-Grams Endpoint

All datasets implementing a "top-ngrams" endpoint MUST conform to the following schema:

**Required Columns:**
- `types` (VARCHAR): The n-gram text content
- `counts` (INTEGER): Frequency count for the n-gram

**Example Query Response:**
```json
[
  {"types": "John", "counts": 1234},
  {"types": "Mary", "counts": 987},
  {"types": "Michael", "counts": 856}
]
```

**Column Requirements:**
- Column names MUST be exactly `types` and `counts`
- `types` MUST be a text/varchar data type
- `counts` MUST be an integer data type
- Response MUST return data as a JSON array
- Results SHOULD be ordered by count in descending order

**Implementation Notes:**
- Optional filter parameters (year, location, sex, limit) are implementation-specific
- Aggregation and filtering logic is handled by individual adapters
- Response format MUST be lightweight (array only, no wrapper objects)

---

#### 3.6.2 Endpoint Schema Declaration

When registering a dataset, adapters declare which endpoint types the dataset supports and how its columns map to the standard dimensions. This declaration is part of the registration payload (see Section 3.7).

**`EndpointSchemaConfig` fields:**

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | string | REQUIRED | Endpoint type name. MUST be a value from the supported types list. Currently: `types-counts`. |
| `time_dimension` | string | optional | Column used for temporal slicing (e.g. `date`, `week`, `month`, `year`). |
| `entity_dimensions` | list[string] | optional | Columns whose values are canonical entity IDs resolvable via `entity_mapping`. |
| `filter_dimensions` | list[string] | optional | Local categorical filter columns not in shared entity space (e.g. `sex`, `language`). Not cross-dataset interoperable. |

**Validation rules:**
- `type` MUST be in the list of supported endpoint types (validated by the SDK before submission)
- `entity_dimensions` columns MUST be covered by `entity_mapping` if entity resolution is expected
- `filter_dimensions` values are dataset-local and carry no cross-dataset semantics

**Example:**
```json
{
  "type": "types-counts",
  "time_dimension": "date",
  "entity_dimensions": ["country"],
  "filter_dimensions": ["language"]
}
```

---

### 3.7 Adapter Submission Contract

This section defines the payload an adapter MUST send when registering a dataset with the Storywrangler registry. The SDK validates this payload locally before making any network call; a conforming payload will not produce a `422` error from the backend.

#### 3.7.1 Registration Payload Schema (`DatasetCreate`)

**Required fields:**

| Field | Type | Description |
|---|---|---|
| `dataset_id` | string | Short identifier for the dataset within its domain (e.g. `ngrams`, `revisions`). |
| `domain` | string | Owning service. MUST be one of the accepted domains (see §3.7.2). |
| `data_location` | string | Absolute path or connection string to the underlying data. |
| `data_format` | string | Storage format. MUST be one of: `parquet_hive`, `duckdb`, `ducklake`. Default: `parquet_hive`. |

**Optional fields:**

| Field | Type | Description |
|---|---|---|
| `description` | string | Human-readable description of the dataset. |
| `format_config` | `FormatConfig` | Storage-format-specific metadata. See below. |
| `entity_mapping` | `EntityMappingConfig` | Schema declaration for entity ID resolution (required when `entity_dimensions` are declared). See §3.7.3. |
| `entities` | list[`EntityRow`] | Entity mapping rows to upsert inline. Each row: `{local_id, entity_id, entity_name, entity_ids?}`. Can also be submitted separately via `POST /admin/registry/{domain}/{dataset_id}/entities`. |
| `endpoint_schemas` | list[`EndpointSchemaConfig`] | Endpoint types the dataset supports. See §3.6.2. |
| `sources` | object | Source URLs for provenance and validation. |
| `catalog` | string | Producer identity — the organisation or group registering this dataset (e.g. `vcsi`). Defaults to `vcsi`. Enables a future 3-level namespace `catalog.domain.dataset_id`. |
| `ownership` | object | Ownership and succession metadata: `{owner_group, contact, status, storage_risk}`. |
| `lineage` | object | Lineage metadata: `{derived_from, produced_by, consumers}`. |

**`FormatConfig` fields:**

| Field | Type | Applies to | Description |
|---|---|---|---|
| `tables_metadata` | object | parquet_hive, ducklake | Maps logical table names to file path lists. |
| `ducklake_data_path` | string | ducklake | Path to the DuckLake catalog `.duckdb` file. |
| `data_schema` | object | any | Column name → DuckDB type (e.g. `{"ngram": "VARCHAR", "count": "BIGINT"}`). |
| `partitioning` | object | parquet_hive, ducklake | Partitioning scheme (e.g. `{"keys": ["date", "country"], "granularity": "daily"}`). |

**`ownership` fields:** `owner_group` (lab/group), `contact` (email or GitHub handle), `status` (`active` \| `needs_successor` \| `archived`), `storage_risk` (`managed` \| `institutional` \| `cloud` \| `personal`).

**`lineage` fields:** `derived_from` (list of `"domain/dataset_id"` upstream refs), `produced_by` (git SHA, script path, or Dagster asset key), `consumers` (opt-in list of downstream users).

The composite key `(domain, dataset_id)` MUST be unique in the registry. Re-submitting an existing pair performs an upsert (UPDATE).

---

#### 3.7.2 Accepted Domains

The `domain` field MUST be a value recognized by the registry. The registry maintains the authoritative list of accepted domains; submissions with an unrecognized value MUST be rejected.

The current list is queryable via `GET /registry/domains` or the SDK's `list_domains()` helper. New domains are added through the governance process in §4.

---

#### 3.7.3 Entity Mapping Configuration (`EntityMappingConfig`)

Declares how a dataset-local identifier column maps to canonical entity IDs (defined in §3.1). Required when `entity_dimensions` are listed in an endpoint schema.

This is a **schema declaration only** — it describes the mapping structure, not the storage location. The actual mapping rows live in the `entity_mappings` table, submitted via the `entities` field in `DatasetCreate` or the batch endpoint `POST /admin/registry/{domain}/{dataset_id}/entities`.

| Field | Type | Required | Description |
|---|---|---|---|
| `entity_type` | string | REQUIRED | Entity identifier system (e.g. `wikidata`, `orcid`, `ror`). |
| `local_id_column` | string | REQUIRED | Column in the dataset holding the dataset-local ID. |

Entity IDs in submitted `entities` rows MUST conform to the format rules for the declared `entity_type` (§3.1).

---

#### 3.7.4 Validation Sequence

The SDK performs the following checks **before** sending the registration request:

1. Pydantic schema validation of the `DatasetCreate` model
2. `domain` membership check against accepted domains (§3.7.2)
3. Endpoint type names in `endpoint_schemas` validated against supported types (§3.6.2)
4. Entity ID format validation for any IDs in `entities` rows, validated against the declared `entity_type` (§3.1)

If any check fails, a `ValidationError` is raised locally. The backend performs the same domain and schema checks on receipt and returns `422` if the payload does not conform — this should not occur for SDK-submitted payloads but may occur for direct API calls.

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

### Version 0.0.3 (2026-03-16)

**Changed:**
- §3.7.1 `FormatConfig`: removed reference to `"adapter"` key in `tables_metadata`; adapter parquet for query-time JOINs is a legacy pattern superseded by the `entity_mappings` PostgreSQL table
- §3.7.3 `EntityMappingConfig`: removed reference to adapter parquet paths; entity rows are submitted via `entities` field or batch endpoint only

### Version 0.0.2 (2026-03-16)

**Added:**
- §1.1: Expanded scope to include endpoint response schemas and adapter submission contract; removed incorrect exclusion of API contracts
- §3.6.2: `EndpointSchemaConfig` — how adapters declare `time_dimension`, `entity_dimensions`, and `filter_dimensions` when registering
- §3.7: Adapter Submission Contract — full `DatasetCreate` registration payload schema, accepted domains, `EntityMappingConfig`, and SDK validation sequence; includes ownership fields (`owner_group`, `contact`, `status`, `storage_risk`), lineage fields (`derived_from`, `produced_by`, `consumers`), and `catalog` for future 3-level namespace

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