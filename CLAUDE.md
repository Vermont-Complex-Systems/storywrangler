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
| `level_order` | What is the on-disk hive nesting order? | Yes — exact path construction |
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

For `parquet_hive`, most of the transform is auto-discovered from the hive directory
tree at registration time. The minimal submission only requires declaring which column
is the time dimension:

```python
{
  "time_dimension": "date",
}
```

All other hive levels are auto-discovered and classified:
- Levels matching `entity_mapping.local_id_column` → entity
- Levels matching `time_dimension` → time
- Levels matching `hash_bucket` (string column name) → hash_bucket
- Everything else → partition (gets auto-default from first on-disk value)

Optional fields:
- `filter_dimensions`: non-hive columns inside parquet files where omitting = aggregate
  over all values. E.g. `["sex"]` — omitting sex returns all names.
- `partition_dimensions`: override auto-discovered defaults when needed.
  E.g. `{"granularity": "daily"}` forces the default instead of alphabetically-first.

Query-time defaults come from `level_order.default_value` (stored at registration).
Helper functions `get_partition_defaults()` and `get_queryable_dims()` in
`core/query_utils.py` provide the query layer's view — they read from `level_order`
first, falling back to `transform.partition_dimensions` for pre-migration datasets.

Neither field includes the entity column — that is handled by `entity_mapping.local_id_column`.

### `transform.hash_bucket` — content-sharded partition routing

**Submission format** — just the column name:

```python
"ngram_bucket"
```

**Stored format** — auto-derived at registration by `_derive_bucket_config()`:

```python
{"column": "ngram_bucket", "default_count": 1, "overrides": {"United States": {"1": 16, "2": 32}}}
```

The submitter declares only which hive partition column holds the bucket ID.
At registration, `_derive_bucket_config()` walks the directory tree, counts
bucket directories per entity × partition combination, and derives
`default_count` (mode of all counts) and `overrides` (entity/partition
combos that differ from the default). The full config dict replaces the
string in the stored `transform.hash_bucket` before persisting.

The query layer computes the bucket at request time:

    bucket = (mmh3.hash(term, seed=0) & 0x7FFFFFFF) % count

- `& 0x7FFFFFFF` clears the sign bit (mmh3 returns signed int32; bucket IDs must be >= 0).
- Seed 0 matches DuckDB/DuckLake's `murmur3_32()` default.
- Bucket count is per-dataset registration (e.g. US gets 32, smaller countries get 16).
- `default_count` is the fallback when no override matches.
- `overrides` is a nested dict: `entity → {partition_dim_value → count}`.
  Resolution: `overrides[entity][str(dim_value)]` → `default_count`.
- Not listed in `partition_dimensions` — hash buckets are routing-only, not query axes.
  A model validator enforces that `hash_bucket` does not appear in
  `partition_dimensions` keys.
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

# parquet_hive (with level_order — exact-depth wildcard path)
read_parquet('{data_location}/*/*/*/*.parquet', hive_partitioning=true)

# parquet_hive (without level_order — recursive glob fallback)
read_parquet('{data_location}/**/*.parquet', hive_partitioning=true)
```

When `level_order` is populated, `_path_expr()` builds a fixed-depth wildcard
path (one `/*` per level) instead of the recursive `/**/*.parquet` glob. This
avoids NFS directory walking overhead.

For routers that need exact partition paths (sparklines, RTD), `build_hive_path()`
constructs paths from level_order with concrete values for each level. Falls back
to `None` when level_order is absent, signalling the caller to use legacy path logic.

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

### `level_order` — hive nesting order (derived, query-time)

The single source of truth for a `parquet_hive` dataset's directory structure.
Derived at registration time, included in default GET responses.

```json
[
  {"column": "ngram_size",  "type": "partition", "default_value": 1},
  {"column": "granularity", "type": "partition", "default_value": "daily"},
  {"column": "country",     "type": "entity",    "default_value": "Afghanistan"},
  {"column": "date",        "type": "time",      "default_value": "2020-01-01"}
]
```

**Type tags:** `partition` (undeclared hive levels or partition_dimensions key),
`entity` (entity_mapping.local_id_column), `hash_bucket` (transform.hash_bucket),
`time` (time_dimension), `filter` (filter_dimensions item).

**`default_value`:** The first on-disk value (sorted alphabetically) for each level.
If `partition_dimensions` declares an override, that wins. Type-coerced against
`filter_values` at registration (string `"1"` → int `1` when filter_values has ints).

**Computed by:** `validate_and_build_level_order()` in `parquet_introspect.py`.
`_discover_levels()` walks one branch of the hive tree, returning both column names
and first values. Undeclared levels default to type `"partition"`. Registration
fails with 422 if:
- Any declared `partition_dimensions` key or `hash_bucket` column is missing on disk
- `partition_dimensions` key order doesn't match the on-disk nesting order

**Used by:**
- `build_hive_path()` — exact partition paths at query time
- `get_partition_defaults()` — query-time default injection
- `get_queryable_dims()` — list of filterable columns
- Default GET response — human-readable summary of the full hive structure

**Backward compatibility:** null means "use glob fallback." All helpers fall back to
`transform.partition_dimensions` when `level_order` is absent.

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
