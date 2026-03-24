# Storywrangler SDK

Entity and taxonomy validation for Storywrangler.

## Standards

This package implements validation rules defined in the [Storywrangler Specification](https://github.com/vermont-complex-systems/Storywrangler-Specification).

**Current version:** v0.0.1

See [versions/0.0.1.md](https://github.com/vermont-complex-systems/Storywrangler-Specification/blob/main/versions/0.0.1.md) for specification details.

## Installation
```bash
pip install storywrangler-sdk
```

## Usage
```python
from storywrangler.validation import EntityValidator

validator = EntityValidator()

# Validate Wikidata Q-code (Spec: Section 3.1.1)
validator.validate_wikidata("wikidata:Q937")  # True

# Validate ORCID (Spec: Section 3.1.2)
validator.validate_orcid("orcid:0000-0002-1825-0097")  # True

# Validate OpenAlex entity (Spec: Section 3.1.x — author, work, institution, …)
validator.validate_openalex("openalex:A5002034958")  # True — author
validator.validate_openalex("openalex:W2741809807")  # True — work
validator.validate_openalex("openalex:I26873012")    # True — institution

# Validate any entity ID
validator.validate("ror:05qghxh33")  # True
```

## Supported Namespaces

| Namespace   | Format example                  | Entity types                           |
|-------------|---------------------------------|----------------------------------------|
| `wikidata`  | `wikidata:Q937`                 | People, places, concepts, …            |
| `orcid`     | `orcid:0000-0002-1825-0097`     | Researchers                            |
| `openalex`  | `openalex:A5002034958`          | Authors (A), Works (W), Institutions (I), Concepts (C), Sources (S), Funders (F), Publishers (P) |
| `ror`       | `ror:05qghxh33`                 | Research organisations                 |
| `ipeds`     | `ipeds:231174`                  | US higher-ed institutions              |
| `doi`       | `doi:10.1038/nature12373`       | Published works                        |
| `isbn`      | `isbn:978-3-16-148410-0`        | Books                                  |
| `local`     | `local:<any-string>`            | Dataset-local identifiers (no global lookup) |

## Entity Mapping

### `entity_namespace` — declaring identifier type

When registering a dataset, the `entity_mapping.entity_namespace` field tells the
platform what kind of entity the local-ID column holds. This enables two things:

1. **Cross-dataset joins** — the platform can follow namespace edges
   (`openalex:A → openalex:I → wikidata:Q`) to join datasets that are keyed on
   different identifier systems.
2. **Automatic entity resolution** — columns that already contain globally-typed
   values (OpenAlex URLs, DOIs, ORCID iDs) do **not** need an explicit `entities`
   list; the platform derives the canonical `local_id` from the namespace prefix
   alone.

**Pattern 1 — opaque local keys** (explicit entity rows required):
```python
# Column holds e.g. town names; a lookup table is needed
client.registry.register({
    "domain": "babynames",
    "dataset_id": "names",
    "entity_mapping": {
        "local_id_column": "state",
        "entity_namespace": "wikidata",   # what kind of entity each state maps to
    },
    "entities": [
        {"local_id": "VT", "entity_id": "wikidata:Q16551", "entity_name": "Vermont"},
        ...
    ],
})
```

**Pattern 2 — global-identifier column** (no entity rows needed):
```python
# Column already holds OpenAlex author URLs — entity_namespace is sufficient
client.registry.register({
    "domain": "open-academic-analytics",
    "dataset_id": "papers",
    "entity_mapping": {
        "local_id_column": "ego_author_id",   # stores https://openalex.org/A…
        "entity_namespace": "openalex",
    },
    # no "entities" list required
})
```

The platform's `resolve_entity` endpoint uses the namespace to derive the stored URL
from a canonical ID without requiring explicit entity rows:
```
openalex:A5002034958  →  https://openalex.org/A5002034958
doi:10.1038/nature    →  https://doi.org/10.1038/nature
```

### `EntityGraph` — cross-namespace edges

The backend maintains an `entity_graph` table (PostgreSQL adjacency list) that stores
directed edges between canonical entity IDs:

```
subject_id  --[predicate]-->  object_id
```

Supported predicates:

| Predicate        | Meaning                                        | Example                                        |
|------------------|------------------------------------------------|------------------------------------------------|
| `affiliated_with` | Author belongs to institution                 | `openalex:A… → openalex:I26873012`             |
| `same_as`         | Cross-namespace identity                      | `openalex:I26873012 → wikidata:Q1068`          |
| `country`         | Institution is in country                     | `openalex:I26873012 → wikidata:Q30`            |
| `broader`         | Concept hierarchy                             | `openalex:C… → openalex:C…`                    |

These edges enable multi-hop traversal, for example joining OAA authors with a
babynames dataset keyed on Wikidata country:

```
openalex:A5002034958
  --affiliated_with--> openalex:I26873012   (UVM)
  --same_as----------> wikidata:Q1068        (UVM on Wikidata)
  --country----------> wikidata:Q30          (United States)
  ↕ shared wikidata:Q30
babynames/names  (entity_mapping.entity_namespace = "wikidata")
```

**API endpoints:**
```
GET  /registry/entity-graph/path?from_id=openalex:A5002034958&to_namespace=wikidata
GET  /registry/entity-graph/neighbors?entity_id=openalex:I26873012
POST /admin/registry/entity-graph          # upsert edges (admin)
```

## Standards Compliance

This SDK implements [Storywrangler Specification v0.0.1](https://github.com/vermont-complex-systems/Storywrangler-Specification/blob/main/versions/0.0.1.md).

All validators follow the format requirements and validation algorithms defined in the specification.
