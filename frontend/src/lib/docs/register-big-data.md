# Registering big data

Flat parquet is right up to a few gigabytes — don't partition small data. Past that, and once queries slice into the whole (one country, one granularity, one date range), switch `data_format` to `parquet_hive`: DuckDB then prunes partitions from directory names instead of opening files.

This page covers the two at-scale declarations: hive-partitioned storage and hash-bucketed partitions. The field-by-field registration basics are in [registering a dataset](/register); the pipeline-side craft — choosing partition keys, sizing files — is in [building a pipeline](/pipelines).

## Hive-partitioned storage

Set `data_format` to `parquet_hive` to enable [hive_partitioning](https://duckdb.org/docs/current/data/partitioning/hive_partitioning). All hive partition levels are auto-discovered from the directory structure — you only need to declare `time_dimension`. `data_location` points to the root of the hive tree:

```bash
wikigrams/                          ← data_location
  ngram_size=1/
    granularity=daily/
      country=United%20States/
        date=2024-01-01/data.parquet
```

```json
{
    "catalog": "vcsi",
    "domain":     "wikimedia",
    "dataset_id": "ngrams",
    "data_format":   "parquet_hive",
    "data_location": "/netfiles/wikimedia_snapshots/wikigrams",
    "description":   "Wikipedia n-gram frequencies by country and date.",
    "endpoint_schema": {
        "type":         "types-counts",
        "type_column":  "ngram",
        "count_column": "pv_count"
    },
    "transform": {"time_dimension": "date"},
    "ownership": {"owner_group": "vcsi", "contact": "compstorylab@uvm.edu"},
    "lineage":   {"repo": "https://gitlab.com/compstorylab/wikipedia-parsing"}
}
```

`type_column` and `count_column` declare the data's non-default column names — declare around the data rather than renaming it. Note what is *not* declared: the `ngram_size`, `granularity`, and `country` levels are auto-discovered from the tree at registration, and callers reach the time dimension through the standardized `?dates=` parameter. The `entities` list is truncated here — the real one has ~100 rows, one per Wikipedia language edition.

At query time, known values (entity, partition defaults) are pinned directly in the path, while the time level gets a wildcard and is filtered via `WHERE`. DuckDB only opens the matching files — no directory scanning:

```sql
FROM read_parquet(
  'ngram_size=1/granularity=daily/country=United%20States/date=*/*.parquet',
  hive_partitioning=true
)
WHERE date BETWEEN '2024-10-01' AND '2024-10-31'
```

Auto-discovered partition levels become regular query params with server-injected defaults:

```bash
curl "https://storywrangler.uvm.edu/storywrangler/allotax\
  ?domain=wikimedia&dataset=ngrams\
  &entity=wikidata:Q30&entity2=wikidata:Q145\
  &dates=2024-10-01,2024-10-31&dates2=2024-10-01,2024-10-31\
  &granularity=daily"
```

### Gotchas

- **Every directory level must be `col=val/`.** Non-hive names (`1grams/`, `daily/`) are not supported anywhere in the tree. Level discovery follows hive-named entries only — a level without one ends the walk, and whatever sits below it is invisible to the platform. Values with spaces or special characters are URL-encoded on disk (`country=United%20States`); DuckDB's partitioned writes do this automatically.
- **`data_location` is the root, not a partition.** Point it at the directory directly above the first `col=val/` level. One level too deep and every derived level, default, and pinned path shifts.
- **Nothing else lives under the root.** The query layer builds fixed-depth wildcard paths (one `/*` per level), so stray directories, scratch files, or loose parquet at the wrong depth break reads. The tree must also be uniform — same keys, same nesting order, same depth on every branch: discovery walks a single branch and assumes it represents the whole tree.
- **Time values must sort chronologically as text.** The time level doesn't have to be a calendar date — plain integers (`year=1990`) work — but availability bounds and partition pruning compare directory values as strings, so use zero-padded ISO dates (`date=2024-01-01`, never `date=2024-1-1`). Callers' `?dates=` values are cast to the column's actual type before the `BETWEEN`.
- **A 200 is not proof the tree was read.** Introspection failures (unreachable path, empty tree) are logged, not raised — registration succeeds and queries fail later. After registering, `GET /registry/{domain}/{dataset_id}` and confirm `level_order` and `manifest.availability` came back populated; empty means the walk failed.

## Hash-bucketed partitions

The previous example is *date-first*: fast for loading all terms in a time window. For *term-first* lookups (e.g. a sparkline for a single word across all dates), `transform.hash_bucket` adds a content-sharded partition level — each term is hashed to a bucket, so the query layer reads exactly one file:

```
sparklines/                          ← data_location
  country=United%20States/
    ngram_bucket=0/data.parquet        ← terms hashed to bucket 0
    ngram_bucket=1/data.parquet
    ...
    ngram_bucket=15/data.parquet       ← 16 buckets for the US
```

The hash *is* the index. The tempting alternative for term-first lookups is sorting terms into range files with an index sidecar mapping term ranges to filenames. That design costs an extra read per query to consult the index, and the sidecar sits inside the data tree where every glob picks it up as data. With a hash bucket the routing table is a function instead of a file: the pipeline computes `bucket = hash(term) % count` when writing, the query layer computes the same expression when reading, and they agree on where every term lives without storing or consulting any lookup structure.

> **Why murmur3?** The hash must be fast, stable across every writer and reader, and available in every language a pipeline might use. `assign_bucket()` uses murmur3-32 with seed 0 and the sign bit cleared, matching DuckDB and DuckLake's built-in `murmur3_32()` — so buckets written by a DuckLake pipeline, a plain parquet writer, and the query layer all land identically. The implementation lives in one place (`storywrangler_schemas.hashing`, re-exported by the SDK as `storywrangler.hashing`); never reimplement it in a pipeline.

You only declare the column name — the server auto-derives bucket counts by counting the bucket directories on disk, per partition combination:

```json
{
    "catalog": "vcsi",
    "domain": "wikimedia",
    "dataset_id": "sparklines",
    "data_location": "/netfiles/compethicslab/wikimedia/sparklines",
    "data_format": "parquet_hive",
    "description": "Precomputed per-term sparkline time series (counts + rank) across all dates.",
    "entity_mapping": {"local_id_column": "country", "entity_namespace": "wikidata"},
    "entities": [
        {"local_id": "United States",  "entity_id": "wikidata:Q30",  "entity_name": "United States"},
        {"local_id": "United Kingdom", "entity_id": "wikidata:Q145", "entity_name": "United Kingdom"}
    ],
    "transform": {
        "time_dimension": "date",
        "hash_bucket": "ngram_bucket"
    },
    "lineage": {
        "repo": "https://github.com/Vermont-Complex-Systems/wikipedia-parsing",
        "derived_from": ["wikimedia/ngrams"]
    },
    "ownership": {"owner_group": "vcsi", "contact": "compstorylab@uvm.edu"}
}
```

`lineage.derived_from` records that the sparklines are computed from `wikimedia/ngrams` — the two datasets are linked in the dependency graph.

In your transform step, use `assign_bucket()` from the SDK (same hash function as the query layer):

```python
from storywrangler.hashing import assign_bucket

# In your transform step — assign each row to a bucket
bucket = assign_bucket(term="hello world", num_buckets=16)
# → row goes into ngram_bucket={bucket}/data.parquet
```

At query time, the API hashes the term and reads only the matching bucket file:

```sql
FROM read_parquet('sparklines/country=United%20States/ngram_bucket=7/data.parquet')
WHERE ngram = 'hello world'
ORDER BY date
```

Bucket counts can differ per combination — shard big partitions harder (United States at 32 while small countries keep 16; a large language at 64 while tiny ones need 1). Registration counts the bucket directories in every combination and stores a default plus overrides, keyed by the combination's level values in tree order:

```json
{"column": "ngram_bucket", "default_count": 16, "overrides": {"1/United States": 32}}
```

This works with or without an entity level — a dataset partitioned only by `n=` and `lang=` gets keys like `"1/en"`:

```
ngrams_ts/                           ← data_location
  n=1/
    lang=en/
      ngram_bucket=0/data.parquet
      ...
      ngram_bucket=63/data.parquet     ← 64 buckets for English
    lang=gn/
      ngram_bucket=0/data.parquet      ← 1 bucket is enough for Guaraní
  n=2/
    ...
```

```json
{"column": "ngram_bucket", "default_count": 1, "overrides": {"1/en": 64, "2/en": 64}}
```

### Gotchas

- **Never reimplement the hash.** A pipeline that buckets with a different function or seed produces a tree that registers cleanly and misroutes every term — indistinguishable from "no data" at query time. Always `assign_bucket()`.
- **Re-shard and re-register are a pair.** The query layer resolves the modulus from the counts recorded at registration. If a rebuild changes any combination's bucket count and the dataset is not re-registered, terms silently route to the wrong bucket.
- **Nothing but data in bucket directories.** Anything named `*.parquet` under a bucket level is read as data — index files, manifests, and markers must live outside the tree or use a different extension.
- **Sort rows by term within each bucket.** The bucket bounds which file is read; the in-file sort lets parquet row groups prune within it, which is what keeps large buckets fast.

## Case studies

The [Wikimedia pipeline](/case-studies/wikimedia) shows what a complete `submit.py` looks like for `parquet_hive`: raw Wikipedia dump → silver n-gram frequencies, partitioned by country, granularity, and date.
