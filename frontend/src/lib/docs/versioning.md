# Versioning

Storywrangler uses two versioning layers with different purposes. Understanding when to use each prevents both over-engineering (archiving every pipeline run) and under-engineering (losing reproducibility when it matters).

## The two-layer model

Registration is designed for **daily use** — re-register freely whenever your pipeline runs. Versioned snapshots and archival are opt-in steps you take when reproducibility or citation is needed.

```
Dataset pipeline
  → parquet files land on disk
  → POST /register            ← frictionless, fast iteration

      ↓ when the interface contract changes

Registry snapshot (version="1.0.0")
  → immutable entry in the platform registry
  → reproducible queries against this interface contract

      ↓ when long-term preservation is needed

Dataverse / archival
  → DOI-bearing, externally citable
  → lineage.archival_doi recorded in the registry entry
```

## The `version` field

Every `DatasetCreate` payload carries a `version` field that defaults to `"latest"`:

```python
DatasetCreate(
    domain="babynames",
    dataset_id="ngrams",
    version="latest",   # default — the mutable development slot
    ...
)
```

### The mutable slot — `"latest"`

Re-registering with `version="latest"` always overwrites the existing entry. This is the default and requires no thought during active development. Pipeline re-runs, metadata corrections, and coverage updates all use this slot.

### Semver strings — immutable snapshots

Once you bump to a named version, that entry is **locked**. Re-registering the same version string returns `409 Conflict`.

```python
# Create an immutable snapshot
DatasetCreate(
    domain="babynames",
    dataset_id="ngrams",
    version="1.0.0",
    ...
)
```

The platform follows [Semantic Versioning](https://semver.org/). For datasets, the three increments map to interface changes rather than code changes:

| Increment | Trigger |
| --- | --- |
| **PATCH** `1.0.x` | Bug fix in processing — same schema, corrected values |
| **MINOR** `1.x.0` | New data added — new time range, new entities; old queries still work |
| **MAJOR** `x.0.0` | Breaking interface change — column renamed, `endpoint_schema` or `transform` axes changed |

A routine pipeline re-run that only adds new rows to existing parquet files does **not** require a version bump. The contract (schema, query axes, data location) is unchanged.

## The `schema_version` field

Every registration automatically records which version of `storywrangler-schemas` was in effect. This is the software–data version coupling recommended by the [Research Data Alliance versioning guidelines](https://zenodo.org/records/13743876): it records which registration contract was in effect so consumers know whether newer fields are available.

```python
# schema_version is auto-populated — do not set manually
DatasetCreate(
    ...
    # schema_version="1.0.0"  ← injected from importlib.metadata
)
```

## Inspecting versions

### List all versions for a dataset

```bash
GET /registry/babynames/ngrams/versions
```

```json
{
  "domain": "babynames",
  "dataset_id": "ngrams",
  "versions": [
    { "version": "latest",  "schema_version": "1.0.0", "created_at": "2025-03-01T..." },
    { "version": "1.1.0",   "schema_version": "1.0.0", "created_at": "2025-02-01T..." },
    { "version": "1.0.0",   "schema_version": "1.0.0", "created_at": "2025-01-01T..." }
  ],
  "total": 3
}
```

### Retrieve a specific version

```bash
GET /registry/babynames/ngrams?version=1.0.0
```

Omitting `?version` always returns the most recently registered entry.

## Platform component versions

The `/version` endpoint reports the runtime software stack:

```bash
GET /version
```

```json
{
  "api": "1.0.0",
  "schemas": "1.0.0",
  "duckdb": "1.1.3",
  "allotax": "0.3.1"
}
```

When using the allotaxonometer, the response `meta` block also includes `dataset_version` and `allotax_version` — so any result can be traced back to the exact data contract and computation engine that produced it.

## Archiving to Dataverse

When a versioned snapshot is ready for long-term preservation and citation, archive it in [Harvard Dataverse](https://dataverse.harvard.edu/) (or any DOI-issuing repository) and record the DOI in `lineage.archival_doi`:

```python
DatasetCreate(
    domain="babynames",
    dataset_id="ngrams",
    version="1.0.0",
    lineage=LineageConfig(
        repo="https://github.com/Vermont-Complex-Systems/babynames",
        archival_doi="10.7910/DVN/XXXXXX",   # set after archiving
    ),
    ...
)
```

The presence of `archival_doi` signals that this version's data is durably stored externally and is citable in publications. The registry entry remains the lightweight interface record; Dataverse holds the canonical, immutable data copy.
