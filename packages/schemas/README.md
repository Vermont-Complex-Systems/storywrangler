# storywrangler-schemas

Shared Pydantic schemas for the [Storywrangler](https://github.com/vermont-complex-systems/storywrangler) platform. Both the backend API and the `storywrangler` SDK import from this package — neither owns a copy of the models.

Implements the [Storywrangler Specification v0.0.3](https://github.com/vermont-complex-systems/Storywrangler-Specification/blob/main/versions/0.0.3.md).

## Installation

```bash
pip install storywrangler-schemas
```

Most users should install `storywrangler` instead, which includes this package as a dependency.

## What's inside

### Registry models (`storywrangler_schemas.registry`)

| Model | Purpose |
|---|---|
| `DatasetCreate` | Full registration payload (domain, format, transform, entity mapping, lineage, ...) |
| `EndpointSchemaConfig` | Output shape declaration (`types-counts`, `time-series`) |
| `TransformConfig` | Query slice axes (time dimension, filter dimensions, hash bucket) |
| `EntityMappingConfig` | Entity ID resolution config (local column + namespace) |
| `EntityRow` | One row in the entity mapping table |
| `ManifestConfig` | Coverage index (availability, partition index) |
| `OwnershipConfig` | Owner group, contact, lifecycle status |
| `LineageConfig` | Sources, upstream datasets, pipeline repo, archival DOI |

### Hash bucket assignment (`storywrangler_schemas.hashing`)

Canonical `murmur3_32` hash function shared between the backend query layer and data pipelines:

```python
from storywrangler_schemas.hashing import assign_bucket

bucket = assign_bucket("hello", num_buckets=16)  # deterministic int in [0, 16)
```

### Standards (`storywrangler_schemas.standards`)

Entity ID validation, namespace registry, and spec URL helpers.
