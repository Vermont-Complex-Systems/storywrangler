# Storywrangler — Architecture Notes for Claude

Decisions made during development. Read this before suggesting schema or query changes.

---

## Data formats: parquet only

Storywrangler accepts exactly two storage formats from submitters:

- `parquet` — single file or flat directory
- `parquet_hive` — hive-partitioned directory tree (all partition levels use `col=val` naming)

**Why not ducklake or duckdb:** Both were dropped because at query time they resolved
to `read_parquet()` anyway. DuckLake catalogs were bypassed; duckdb with `table_files`
was just parquet under a path convention. No legacy formats are tolerated.

---

## parquet_hive convention: full `col=val` at every level

For `parquet_hive`, **every partition level must follow hive naming** (`col=val/`).
Non-hive directory names like `1grams/` or `daily/` are not supported.

`data_location` must be the **root** of the hive tree — the directory directly above the
first `col=val/` level. Example layout:
```
/data/ngrams/                        ← data_location points here
  ngram_size=1/
    granularity=daily/
      location=en/
        date=2024-01-01/data.parquet
```

**Why:** DuckDB's `hive_partitioning=true` then handles partition pruning automatically
for any combination of WHERE conditions. No manual path construction in the codebase.
All filtering is uniform WHERE clauses for both `parquet` and `parquet_hive`.

**Performance:** DuckDB reads partition values from directory names (not file contents)
for filter_dimensions introspection and for pruning. This is equivalent to manual glob
construction but generalises to any partition structure and any filter combination.

---

## DatasetCreate field responsibilities

Each top-level field answers a distinct question. Do not conflate them.

| Field | Question | Used at query time? |
|---|---|---|
| `data_location` | Where is the data on disk? | Yes — embedded in `read_parquet()` |
| `data_format` | How is the data laid out? | Yes — selects query strategy |
| `endpoint_schema` | What does the API return? | Yes — column names only |
| `transform` | What axes can callers slice on? | Yes — WHERE clause columns |
| `entity_mapping` | How to resolve entity identifiers? | Yes — entity column + namespace |
| `manifest` | What data exists (coverage/partition index)? | No — UI/discovery only |
| `ownership` | Who owns this? | No — governance only |
| `lineage` | Where did it come from? | No — provenance only |

### `endpoint_schema` — output shape only

```python
{"type": "types-counts", "type_column": "ngram", "count_column": "pv_count"}
```

Only three fields: endpoint type and the column names for types and counts.
No time dimension, no filter dimensions, no granularities, no ngram_sizes here.

### `transform` — query slice axes

```python
{
  "time_dimension":       "date",
  "filter_dimensions":    ["sex"],                                       # categorical, safe to omit
  "partition_dimensions": {"granularity": "daily", "ngram_size": 1},    # dict: col → safe default
}
```

- `time_dimension`: the column for `WHERE time_col BETWEEN ? AND ?`.
- `filter_dimensions`: categorical columns where omitting = aggregate over all values (valid).
  E.g. omitting `sex` returns all names.
- `partition_dimensions`: dict where keys are columns that are unsafe to omit (mixing them
  would produce nonsensical aggregations, e.g. daily + weekly + monthly). Values are the safe
  defaults injected automatically when the caller omits the parameter (`None` = no safe default,
  caller must always provide). Distinct values for both `filter_dimensions` and
  `partition_dimensions` are **auto-introspected** at registration into `filter_values`.

Neither field includes the entity column — that is handled by `entity_mapping.local_id_column`.

### `transform.hash_bucket` — content-sharded partition routing

```python
{"column": "ngram_bucket", "counts": {"default": 16, "United States/1": 16, "United States/2": 32}}
```

Declares that the dataset distributes rows across hive partition directories
named `{column}={0..count-1}` by a murmur3_32 hash of the entity/type column.
The query layer computes the bucket at request time:

    bucket = (mmh3.hash(term, seed=0) & 0x7FFFFFFF) % count

- `& 0x7FFFFFFF` clears the sign bit (mmh3 returns signed int32; bucket IDs must be >= 0).
- Seed 0 matches DuckDB/DuckLake's `murmur3_32()` default.
- `counts` is either a single int (uniform) or a dict mapping slash-separated
  partition values to counts. The `"default"` key is the fallback.
  Key convention: `entity_value/partition_dim1_value/partition_dim2_value/...`
  where entity comes from `entity_mapping.local_id_column` and partition dims
  follow `partition_dimensions` dict order (e.g. `"United States/1"` for
  country + ngram_size). No extra `key_dimensions` field needed — the key
  order is already implied by the existing schema declarations.
- Not listed in `partition_dimensions` — hash buckets are routing-only, not query axes.
- Helpers live in `core/query_utils.py`: `murmur_bucket()`, `get_bucket_config()`,
  `resolve_bucket_count()` — generic, usable by any router.

### `entity_mapping.local_id_column` — dual role (documented, not a bug)

For `parquet_hive`, `local_id_column` is both:
1. The column used in `WHERE entity_col = ?` (entity resolution)
2. The hive partition key — the directory is `entity_col=value/`

These are the same concept: "the column that identifies the entity in stored data."
Hive partitioning promotes a column to the path level; the name is still the column name.

### `manifest` — coverage index, borrowed from Apache Iceberg (never query-time)

Contains `availability` (time/entity ranges) and `partition_index` (enumerable
partition list with per-partition stats). Neither is read at query time.

The name is borrowed from Apache Iceberg: a pre-computed record of partition bounds
and file-level statistics — exactly what `availability` and `partition_index` are.

`availability` is **auto-populated by `parquet_introspect.py`** at registration time
when `transform.time_dimension` is set. It computes `MIN/MAX` of the time column
grouped by entity and partition dimensions. Entity-first format:
```json
{"United States": {"daily": {"min": "2024-01-01", "max": "2026-04-20"}, "weekly": {...}}}
```
For datasets without entity_mapping: `{"daily": {"min": ..., "max": ...}}`.

`partition_index` is submitter-provided, stored in a separate DB column (excluded
from summary responses via SQLAlchemy `load_only`) and re-injected into `manifest`
on `GET ?full=true`.

---

## Query layer: `load_system()` is format-agnostic

`load_system()` in `core/query_utils.py` uses identical WHERE-based logic for both
formats. The only difference is the FROM expression:

```python
# parquet
read_parquet('{data_location}')

# parquet_hive
read_parquet('{data_location}/**/*.parquet', hive_partitioning=true)
```

Callers (wikimedia, allotax routers) pass `granularity` and `ngram_size` as plain
entries in `filter_vals` — they are just WHERE clause values, not special cases.

---

## Validation: from `filter_values`, not from schema declarations

Routers validate `granularity` and `n` against `dataset_obj.filter_values` (a JSON
column populated at registration by `parquet_introspect.py`). This is authoritative
because it reflects what is actually in the data, not what a submitter declared.

If `filter_values` is empty (dataset not yet introspected), validation is skipped
and DuckDB will return an empty result for invalid values.

---

## `parquet_introspect.py` — registration-time only

Runs once on `POST /register`. Uses `hive_partitioning=true` for `parquet_hive` so:
- `DESCRIBE SELECT *` includes partition columns in `data_schema`
- `SELECT DISTINCT dim` reads from directory metadata, not file contents

Never raises — failures are logged and registration proceeds without derived fields.

---

## Transform boundary: server vs. frontend

`TransformConfig` declares **available axes** — what the dataset can be sliced on.
It does not declare rendering or aggregation preferences.

Rule of thumb:
- **Server-side**: anything requiring the full dataset (aggregation, WHERE pruning)
- **Query parameter**: things that vary per request (`?normalized=true` someday)
- **Frontend**: Observable Plot territory — sort, bin, window, stack, normalize on subset

Do not add more fields to `TransformConfig` unless they describe a new *axis* that
requires schema-level declaration (i.e., cannot be expressed as a query parameter).

---

## OAA (Open Academic Analytics)

Uses the same `read_parquet()` pattern as all other routers. Pipeline pre-materialises:
- `papers.parquet`, `coauthors.parquet`, `training.parquet`
- `authors.parquet` — pre-joined summary (one row per ego author)
- `embeddings.parquet` — papers filtered to those with UMAP coordinates

All registered under `domain="open-academic-analytics"`. Router resolves
`data_location` from the registry; no bespoke DuckDB connections.

`academic-research-groups` (faculty roster) is registered under `domain="datasets"`.

---

## SDK CLI (`storywrangler new`)

Scaffolds `parquet` or `parquet_hive` project templates only. `ducklake` and `duckdb`
format templates were removed. The generated `submit.py` uses the current `DatasetCreate`
structure: `endpoint_schema` for output shape, `transform` for slice axes.
