# Querying Datasets

The reliable way to query Storywrangler is discovery-first: read the registry
metadata, then construct queries from what it says actually exists. Never guess
entity IDs, granularities, or date ranges.

Here is the whole flow at a glance — list the catalog, then pull two terms' time
series and plot them, straight from the live API:

<!-- LiveDemo -->

## Step 1 — discover datasets

```
GET /registry/                     → all datasets (latest version each)
GET /registry/{domain}/{dataset}   → one dataset's metadata
```

The per-dataset response contains everything needed to build a valid query:

- **`level_order`** — the on-disk hive nesting, in order, with a type tag and
  default per level:
  ```json
  [
    {"column": "ngram_size",  "type": "partition", "default_value": 1},
    {"column": "granularity", "type": "partition", "default_value": "daily"},
    {"column": "country",     "type": "entity",    "default_value": "Afghanistan"},
    {"column": "date",        "type": "time",      "default_value": "2020-01-01"}
  ]
  ```
  Levels typed `partition` or `filter` are the dimensions you may pass as query
  parameters; omitted ones fall back to `default_value`.
- **`filter_values`** — the valid values per dimension, introspected from the
  data itself (e.g. `{"ngram_size": [1, 2], "granularity": ["daily", "weekly"]}`).
  A value outside this list returns an empty result, not an error.
- **`manifest.availability`** — min/max time coverage per entity and
  granularity. Check it before requesting a date range:
  ```json
  {"United States": {"daily": {"min": "2024-01-01", "max": "2026-04-20"}}}
  ```
- **`endpoint_schema`** — the output shape: endpoint type (e.g. `types-counts`)
  and which columns hold types and counts.

## Step 2 — resolve entities

Entity identifiers are namespaced (`wikidata:Q30` = United States). To map
human names or local IDs to canonical entity IDs:

```
GET /registry/{domain}/{dataset}/adapter
→ [{"local_id": "united_states", "entity_id": "wd:Q30", "entity_name": "United States", ...}]
```

## Step 3 — query an instrument

Each domain router exposes some subset of these instruments (see the per-domain
endpoint reference sections for exact paths, parameters, and response shapes):

- **Top n-grams** — highest-count types for an entity over a date range.
  Returns `{"data": [{"types": ..., "counts": ...}], "metadata": {...}}`.
- **Term series** — a per-term time series (date, counts, rank). Wikimedia's
  variant can include the top contributing Wikipedia articles per date.
  Batch variants accept comma-separated terms.
- **Allotaxonometer** — rank-turbulence divergence between two systems
  (two entities, two date ranges, or both), computed in Rust. Returns the
  diamond-plot histogram, wordshift contributions, and divergence metrics.
  System-2 parameters use a `2` suffix (`entity2`, `dates2`, `sex2`, ...).

With the SDK, the dataset-scoped client wires the discovery steps together:

```python
wiki = client.dataset("wikimedia", "ngrams")
wiki.filters                      # step 1: what can I slice on?
wiki.availability                 # step 1: what dates exist?
wiki.allotax(entity="wikidata:Q30", entity2="wikidata:Q145",
             dates="2026-05-01", dates2="2026-05-01",
             ngram_size=1, granularity="daily")
```

## Performance guidance

- **Term lookups are case-sensitive.** `COVID` and `covid` are different terms.
- **Wikimedia term-series has a fast and a slow path.** Terms in the
  precomputed vocabulary (~65K terms) return in tens of milliseconds; arbitrary
  terms fall back to scanning daily partition files (~3–5 s). Prefer vocabulary
  terms for interactive use.
- **Skip what you don't need.** Omitting `include=` (the default) is roughly 2×
  faster than `include=articles`; only request articles when the user drills in.
- **Window the series.** Omit `dates` for full history; pass a narrow range like
  `dates=2024-10-01,2024-12-31` when only recent data is needed.
- **Batch when comparing terms.** The batch term-series endpoint fetches many
  sparklines in one request; missing terms come back as empty arrays, never
  errors.
- The `Server-Timing` response header breaks down where query time went.

## Error semantics

Structured error codes on the `detail` object:

- `404 DATA_NOT_AVAILABLE` — the dataset is registered but its files are not on
  this server.
- `500 QUERY_FAILED` — the query itself failed; check parameters against
  `filter_values`.
- `504 QUERY_TIMEOUT` — the query exceeded the time limit; narrow the date
  range or use a coarser granularity.

An empty `data`/`series` array with a 200 status usually means the filter
values were valid types but matched nothing — re-check `filter_values` and
`availability`.
