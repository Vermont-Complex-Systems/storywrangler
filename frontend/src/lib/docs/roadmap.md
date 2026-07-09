# Roadmap

What the registry does today, what is missing, and what is planned. This page exists so potential adopters can see the gaps honestly rather than discovering them after onboarding.

## Current state

The registry today is a metadata catalog: it stores pointers to datasets, validates their format at registration, and serves them to instruments. The core read/write path is operational. What is missing is mostly the connective tissue — lineage, ownership, resilience, and enforcement.

| Area | Today | Gap | Priority |
| --- | --- | --- | --- |
| Dataset registration | Working | — | — |
| Lineage | Field exists in schema | Not enforced; no traversal API | P2 |
| Ownership & succession | `ownership` field in schema | Transfer endpoint and policy not yet implemented | P1 |
| Identifier enforcement | Format accepted as string | Malformed IDs reach Silver undetected | P1 (via SDK) |
| Endpoint schema contract | Field populated | Not validated at query time | P2 |
| Catalog resilience | PostgreSQL only | Catalog unreachable when API is down | P3 |
| Column descriptions | `{col: type}` only | No human-readable field documentation | P4 |
| Gold layer | Not registered | Derived artifacts and ML outputs are invisible | P5 |
| Storage backend | netfiles (institutional NFS) | Slow reads; UVM-only access; blocks immutable Frozen DuckLake snapshots | Planned |

## P1 — Ownership and succession

When a student leaves, their dataset registration persists but institutional knowledge is lost. There is no mechanism for the institute to take custody and hand off to a new maintainer.

The `ownership` field is now part of the `Dataset` model and registration payload. Four sub-fields, submitted as `"ownership": {...}`:

- `owner_group` — lab or research group (`"compethicslab"`, `"VCSI"`)
- `contact` — email or GitHub handle of the current maintainer
- `status` — `active` | `needs_successor` | `archived`
- `storage_risk` — durability signal: `managed` > `institutional` > `cloud` > `personal`. Datasets on `personal` or `cloud` storage automatically flag `needs_successor`.

Paired with a `PATCH /admin/registry/{domain}/{dataset_id}/transfer` endpoint to change ownership. This is also the on-ramp for promoting a dataset to managed hosting when a student leaves without handing off.

## P2 — Lineage

The registry knows where data lives but not where it came from or what depends on it. A schema change in `wikimedia/ngrams` currently has unknown blast radius.

Three fields to add:

- `derived_from` — list of `domain/dataset_id` references this dataset was built from (`["wikimedia/ngrams", "wikimedia/revisions"]`)
- `produced_by` — pipeline or script that generated this dataset (git SHA, Dagster asset key, or script path)
- `consumers` — opt-in list of known downstream users (stories, tools, partner groups) that would otherwise be invisible. Dataset-to-dataset downstream lineage is computable by inverting `derived_from`; `consumers` covers what that query cannot see.

Paired with `GET /registry/{domain}/{dataset_id}/dependents` — lists all datasets that declare `derived_from` containing this one. Enables impact analysis before schema changes without a graph database: simple list traversal is sufficient at this scale.

## P3 — Catalog resilience

If PostgreSQL is down, `GET /registry/` is unreachable. Groups lose discoverability even though their data is physically accessible.

Proposed fix: a scheduled export job that writes the full registry to a parquet snapshot on netfiles:

```
/netfiles/compethicslab/registry/
  snapshots/date=YYYY-MM-DD/registry.parquet
  latest.parquet
```

Groups can then query the catalog directly via DuckDB without going through the API.

## P4 — Column descriptions

`data_schema` today is `{column: type}` only. No descriptions, no sensitivity flags. This limits discoverability for researchers who don't know what `rank` or `cnt` means in the ngrams schema.

Proposed extension — backward compatible, old format detected and migrated on read:

```json
{
  "rank": {"type": "BIGINT", "description": "Frequency rank of the n-gram on this date"},
  "cnt":  {"type": "BIGINT", "description": "Raw occurrence count"},
  "freq": {"type": "DOUBLE", "description": "Normalized frequency (cnt / total tokens)"}
}
```

## P5 — Gold layer registration

Derived datasets and ML artifacts are currently unregistered. There is no way to know which version of `wikimedia/ngrams` a given embedding was built from, or what stories depend on what Gold artifacts.

No separate model registry is needed at this scale. Gold artifacts register via the same `submit.py` pattern, with `derived_from` pointing to their Silver inputs:

| Asset | `data_format` | `derived_from` |
| --- | --- | --- |
| `wikimedia/article-embeddings` | `parquet_hive` | `["wikimedia/revisions"]` |
| `wikimedia/topic-classifier` | `duckdb` | `["wikimedia/article-embeddings"]` |
| `wikimedia/ngram-topics` | `parquet_hive` | `["wikimedia/ngrams", "wikimedia/topic-classifier"]` |

A trained model is just another registered dataset whose `data_location` points to model weights on netfiles. If model versioning becomes critical, that is when to reconsider.

### Managed datasets

When a student leaves without a successor, or when a dataset is small and stable enough, VCSI could take custody and move the data to platform-controlled storage. Managed ingestion would have three paths: **static clone** (copy parquet files, update `data_location`), **pipeline adoption** (clone the source repo, schedule via Dagster), or **PostgreSQL ingest** (for very small, highly-queried datasets). The `storage_risk: "managed"` value is reserved for this case.

### Internal tables

Some datasets are small enough and queried frequently enough that storing them as parquet files adds unnecessary indirection. The planned design is to allow a third storage class — **internal tables** — where data is ingested directly into the platform's PostgreSQL database and served without DuckDB. The registry entry would declare `data_format: "postgres"` and `data_location` would identify the table rather than a file path. The query layer would route to a PostgreSQL cursor instead of `read_parquet()`. No datasets currently use this path.

## Planned — Storage backend: netfiles → S3 and Frozen DuckLake

The current data serving path reads parquet files directly from netfiles, UVM's institutional NFS. This creates three compounding problems:

- **Performance.** netfiles is an archival system optimised for sequential writes, not the random column reads DuckDB issues at query time. Every API request pays the NFS latency tax.
- **Accessibility.** `data_location` paths are only reachable from UVM-networked machines. External collaborators and cloud compute cannot access the data without a VPN or an intermediary copy.
- **Frozen snapshots.** [Frozen DuckLake](https://ducklake.select/2025/10/24/frozen-ducklake/) snapshots reference parquet files by HTTP/S3 URL — they require the files to be HTTP-accessible. netfiles paths cannot be referenced this way, so versioned snapshots cannot freeze against them.

### What Frozen DuckLake actually is

A Frozen DuckLake is a tiny `.ducklake` file — a DuckDB database containing table schemas and pointers to parquet files stored in S3. It does **not** copy the data: the parquet files stay in place and the catalog freezes which exact files existed at that moment. The catalog file itself is kilobytes; the storage cost is negligible. Queries attach it like any DuckDB database:

```
ATTACH 'ducklake:s3://storywrangler-snapshots/babynames/ngrams/1.0.0.ducklake'
```

Because the catalog references S3 URLs and S3 object versioning prevents silent overwriting, a frozen snapshot is trustworthy in a way that a `data_location` pointer to a submitter's local disk is not: the submitter cannot accidentally break or mutate it.

### Migration path

The migration is submitter-driven and incremental — no flag day. DuckDB handles S3 URIs transparently; the query layer is unchanged. Submitters update one line in their `submit.py` and upload their parquet files to the platform S3 bucket:

```python
# before
data_location = "/netfiles/gsm-storywrangler/babynames/ngrams/"

# after
data_location = "s3://storywrangler-data/babynames/ngrams/"
```

The registry stores the new path; the API serves queries against S3 from that point forward. Existing netfiles registrations continue to work during transition.

### Frozen DuckLake on top

Once a dataset's `data_location` is an S3 URI, the platform can generate a frozen snapshot at version registration time automatically. At `POST /register` with a semver version string, the platform:

1. Enumerates all `.parquet` files at `data_location` (already done for introspection)
2. Calls `ducklake_add_data_files()` to register those S3 URLs in a `.ducklake` catalog
3. Uploads the catalog to `s3://storywrangler-snapshots/{domain}/{dataset_id}/{version}.ducklake`
4. Stores the URL in `RegistryEntry.ducklake_path` (already reserved in the schema)

Query layer change is minimal: versioned requests check `ducklake_path` and use `ATTACH 'ducklake:...'` instead of `read_parquet(s3://...)`. The `version="latest"` slot always reads the live `data_location` — no snapshot is generated for it.

### Cost

S3 Standard is approximately $0.023/GB/month, with S3 Intelligent-Tiering reducing cost further for infrequently accessed snapshot versions. For a typical research dataset in the tens of GB range, storage is $1–5/month. Request costs are negligible at academic traffic volumes. The `.ducklake` catalog files themselves are kilobytes — essentially free.

### Schema reservation

`RegistryEntry.ducklake_path` is already a nullable column in the registry schema. It is `null` for all current entries (netfiles-backed and `latest` versions). No existing queries are affected. When the migration lands, the column is populated automatically by the registration endpoint — submitters never set it.

## Open questions

These are unresolved policy questions, not technical gaps. Documenting them here so collaborators can see what is still being decided.

- **Should stories be registered assets?** A story consuming `wikimedia/ngrams` is a downstream dependency. Tracking it would complete the lineage picture. But stories are frontend code, not data — the boundary is unclear.
- **Storage class enforcement?** Should the platform hard-reject registration of `personal` storage, or only warn? Hard enforcement reduces friction from bad registrations; soft warning may be ignored.
- **Spec validation strictness.** Format validation (regex + checksum) should be a hard reject at registration. Existence checks (live ORCID registry, Wikidata SPARQL) are expensive and should be warnings only. The spec already makes this distinction (`MUST` vs `SHOULD`).
- **Who governs the registry?** The succession mechanism will exist once P1 lands, but the policy is unresolved: who approves new registrations, holds admin access, and can archive or transfer a dataset when a student leaves without handing off? This needs a named role before external groups onboard.
- **PII and data sensitivity.** `storage_risk` covers durability but not sensitivity. Some datasets contain or are derived from identified individuals. Does the registry need a `sensitivity` field? Who determines classification, and does it gate access to `data_location`?
