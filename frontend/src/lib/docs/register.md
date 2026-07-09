# Registering a dataset

The simplest use case of registering your dataset is to get access to VCSI instruments, such as the [allotaxonometer](/tools/allotaxonometer), which can then be served anywhere on the web. In this case, your submitted dataset must fulfil the instrument requirements you want to access (e.g. the allotaxonometer requires a `types-counts` endpoint schema — see the instrument page). It should also be part of an accepted domain (`GET /registry/domains` lists them). By default, endpoints can go in the `guest` domain, but specifying a domain helps cluster related datasets and improves discovery.

Registration starts minimal and progressively adds capabilities along three axes:

<!-- RegistrationFlowchart -->

The rest of this page walks through each path, starting from the minimal working registration. `types-counts` is the endpoint type for any rank-frequency distribution: a column of token values and a column of counts. At least one comparison axis is required — without one the API rejects the registration, since the allotaxonometer has no way to distinguish system 1 from system 2. `filter_dimensions` are categorical axes that serve as that comparison axis: the allotaxonometer compares `?town=Arlington vs ?town2=Addison`. At query time, omitting the parameter aggregates over all its values.

```python
from storywrangler import Storywrangler

client = Storywrangler()
client.registry.register({
    # ── Identity ──────────────────────────────────────────────────────
    "catalog":    "verso",
    "domain":     "vt-zoning-atlas",
    "dataset_id": "ngrams",

    # ── Location ──────────────────────────────────────────────────────
    "data_location": "/data/vt-zoning/ngrams.parquet",
    "data_format":   "parquet",
    "description":   "Word frequencies from Vermont zoning bylaws by town.",

    # ── Instrument contract ────────────────────────────────────────────
    # types-counts: a column of token values and a column of counts.
    # filter_dimensions are categorical axes exposed as query parameters.
    "endpoint_schema": {"type": "types-counts"},
    "transform":       {"filter_dimensions": ["town"]},

    "ownership": {"owner_group": "verso", "contact": "verso@uvm.edu"},
    "lineage":   {
        "repo": "https://github.com/Vermont-Complex-Systems/vt-zoning-atlas"
    },
})
```

Once registered, each `filter_dimensions` entry becomes a bare query parameter on the allotaxonometer. Comparing Arlington vs Addison:

```bash
curl "https://storywrangler.uvm.edu/storywrangler/allotax\
  ?domain=vt-zoning-atlas&dataset=ngrams\
  &town=Arlington&town2=Addison"
```

Without any entity mapping, we adopt the convention of simply incrementing provided filter dimensions when querying the API, e.g. `town` and `town2`.

## Providing entity mapping

Drop `filter_dimensions` and add `entity_mapping` instead. The SDK validates all `entity_id` values locally before anything reaches the server. This also standardizes the API parameter: regardless of what the local column is called (`town`, `geo`, `country`…), callers always use `?entity=` and `?entity2=` — accepting either a canonical ID (`wikidata:Q675558`) or the raw local value (`Arlington`):

```diff
- "transform": {"filter_dimensions": ["town"]},

+ "entity_mapping": {"local_id_column": "town", "entity_namespace": "wikidata"},
+ "entities": [
+     {"local_id": "Arlington", "entity_id": "wikidata:Q675558", "entity_name": "Arlington, Vermont"},
+     {"local_id": "Addison",   "entity_id": "wikidata:Q353095", "entity_name": "Addison, Vermont"},
+     # ... one row per town
+ ],
```

The corresponding curl command:

```bash
curl "https://storywrangler.uvm.edu/storywrangler/allotax\
  ?domain=vt-zoning-atlas&dataset=ngrams\
  &entity=wikidata:Q675558&entity2=wikidata:Q353095"
```

By analogy to `filter_dimension`, the API now expects `entity` and `entity2` keys but values can either be the standardized or local identifiers.

## Adding a time axis

`transform.time_dimension` opens a date-range axis for `BETWEEN` queries. The meaningful comparisons are same location across two time ranges (e.g. US 1990 vs US 2020), or same time range across two locations (e.g. US 2020 vs Quebec 2020). When `time_dimension` is set, the platform auto-populates `manifest.availability` at registration time — computing min/max date coverage per entity, so the UI knows valid ranges without querying the data.

Start without entity mapping: `geo` stays in `filter_dimensions` and callers pass raw local IDs directly — `?geo=united_states` — with no namespace resolution. The manifest is keyed by the same local IDs.

```python
from storywrangler import Storywrangler

client = Storywrangler()
client.registry.register({
    "catalog":    "vcsi",
    "domain":     "babynames",
    "dataset_id": "ngrams",
    "data_location": "/data/babynames/ngrams.parquet",
    "data_format":   "parquet",
    "description":   "Baby names by popularity, year, and location.",
    "endpoint_schema": {"type": "types-counts"},
    "transform": {
        "filter_dimensions": ["year", "sex", "geo"],  # year is exact-match only: ?year=1990
    },
    "ownership": {"owner_group": "vcsi", "contact": "compstorylab@uvm.edu"},
    "lineage":   {"repo": "https://github.com/Vermont-Complex-Systems/babynames"},
})
```

And the corresponding curl command:

```bash
curl "https://storywrangler.uvm.edu/storywrangler/allotax\
  ?domain=babynames&dataset=ngrams\
  &year=1990&year2=2020\
  &geo=united_states&sex=F"
```

Moving `year` to `time_dimension` unlocks range queries and standardizes the API parameter: regardless of the underlying column name (`year`, `date`…), callers always use `?dates=` and `?dates2=`. Availability is auto-derived at registration — it tells the UI what date ranges are valid per entity without touching the data:

```diff
  "transform": {
-     "filter_dimensions": ["year", "sex", "geo"],
+     "filter_dimensions": ["sex", "geo"],
+     "time_dimension":    "year",
  },
+ # availability is auto-populated at registration:
+ # {"united_states": {"min": 1880, "max": 2022}, "quebec": {"min": 1980, "max": 2022}}
```

Adding `entity_mapping` promotes `geo` out of `filter_dimensions`. Availability keys auto-upgrade to canonical entity IDs:

```diff
- "filter_dimensions": ["sex", "geo"],
+ "filter_dimensions": ["sex"],

+ "entity_mapping": {"local_id_column": "geo", "entity_namespace": "wikidata"},
+ "entities": [
+     {"local_id": "united_states", "entity_id": "wikidata:Q30",  "entity_name": "United States"},
+     {"local_id": "quebec",        "entity_id": "wikidata:Q176", "entity_name": "Quebec"},
+ ],
```

The corresponding curl command:

```bash
curl "https://storywrangler.uvm.edu/storywrangler/allotax\
  ?domain=babynames&dataset=ngrams\
  &entity=wikidata:Q30\
  &dates=1990&dates2=2020\
  &sex=F"
```

## Hive-partitioned storage

The final form introduces [hive_partitioning](https://duckdb.org/docs/current/data/partitioning/hive_partitioning) by setting `data_format` to `parquet_hive`. All hive partition levels are auto-discovered from the directory structure — you only need to declare `time_dimension`. `data_location` points to the root of the hive tree:

```
1grams/                          ← data_location
  ngram_size=1/
    granularity=daily/
      country=United%20States/
        date=2024-01-01/data.parquet
```

```python
from storywrangler import Storywrangler

client = Storywrangler()
client.registry.register({
    "domain":     "wikimedia",
    "dataset_id": "ngrams",
    # data_location is the root of the hive tree
    "data_location": "/netfiles/compethicslab/wikimedia/1grams",
    "data_format":   "parquet_hive",
    "description":   "Wikipedia n-gram frequencies by country and date.",
    "endpoint_schema": {
        "type":         "types-counts",
        "type_column":  "ngram",     # non-default column name
        "count_column": "pv_count",  # non-default
    },
    "transform": {
        "time_dimension": "date",      # hive partition key; callers use ?dates= (standardized)
        # All other hive levels (ngram_size, granularity, country) are auto-discovered
        # from the directory structure — no need to declare them.
    },
    "entity_mapping": {"local_id_column": "country", "entity_namespace": "wikidata"},
    "entities": [
        {"local_id": "United States",  "entity_id": "wikidata:Q30",  "entity_name": "United States"},
        {"local_id": "United Kingdom", "entity_id": "wikidata:Q145", "entity_name": "United Kingdom"},
        # … ~100 Wikipedia language editions
    ],

    "ownership": {"owner_group": "vcsi", "contact": "compstorylab@uvm.edu"},
    "lineage":   {"repo": "https://github.com/Vermont-Complex-Systems/..."},
})
```

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

You only declare the column name — the server auto-derives bucket counts per entity:

```python
from storywrangler import Storywrangler

client = Storywrangler()
client.registry.register({
    "catalog": "vcsi",
    "domain": "wikimedia",
    "dataset_id": "sparklines",
    "data_location": "/netfiles/compethicslab/wikimedia/sparklines",
    "data_format": "parquet_hive",
    "description": "Precomputed per-term sparkline time series (counts + rank) across all dates.",
    "entity_mapping": {"local_id_column": "country", "entity_namespace": "wikidata"},
    "entities": [
        {"local_id": "United States",  "entity_id": "wikidata:Q30",  "entity_name": "United States"},
        {"local_id": "United Kingdom", "entity_id": "wikidata:Q145", "entity_name": "United Kingdom"},
        # ...
    ],
    "transform": {
        "time_dimension": "date",
        "hash_bucket": "ngram_bucket",   # ← content-sharded partition
    },
    "lineage": {
        "repo": "https://github.com/Vermont-Complex-Systems/wikipedia-parsing",
        "derived_from": ["wikimedia/ngrams"],  # this dataset is derived from the ngrams pipeline
    },
    "ownership": {"owner_group": "vcsi", "contact": "compstorylab@uvm.edu"},
})
```

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

## Case studies

The [Wikimedia pipeline](/case-studies/wikimedia) shows what a complete `submit.py` looks like for `parquet_hive`: raw Wikipedia dump → silver n-gram frequencies, partitioned by country, granularity, and date.
