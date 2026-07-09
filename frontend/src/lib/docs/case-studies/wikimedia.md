# Wikimedia pipeline

The Wikipedia enterprise dump comprises over 100Gb of compressed files, daily. Arguably, it counts as "big data" by academic standards. As is often the case, it is not just about size; one needs to extract the data from the raw html, making some decisions along the way about what should stay and what should go. Typically, this involves deciding what you count as content and what is boilerplate. Some insights only come from experimentation from downstream tasks. In our case, our downstream products included counting ngrams of varying sizes (e.g. words, bigrams, trigrams), before feeding that to our instruments that build on principles of heavy-tail distributions.

This pipeline is also a story about how large data problems have become tractable on accessible hardware. Crunching 1 TB of n-gram counts on a consumer laptop was unthinkable a decade ago; today it is routine, thanks to open formats like Apache Arrow and out-of-core execution engines like DuckDB. This case study follows the full Storywrangler workflow: we start with the pipeline itself, walk through how its outputs are registered with the platform using the `storywrangler` SDK, and then look at how the Storywrangler API serves over 500 GB of Parquet data from a SvelteKit application.

Here is what the allotaxonometer page of the app looks like:

<!-- DemoVideo -->

For context, on loading a pair of single days, it'll load two "types-counts" parquet files of around 300–400 MB each, access the `top N = types` (at first we do 100K, then 1M), before computing the rank turbulence divergence (RTD). You can think of RTD as something like entropy: a metric that surfaces which types in comparable systems have experienced the most turbulence, controlling for the heavy-tail nature of the system. Note that as we increase date ranges to 16 days (2 times 8 days), we are loading as many 300–400 MB files as there are days, summing around 4 GB of data without much hassle.

## The data pipeline

<!-- PipelineDiagram -->

This is how we go from 100Gb of daily dumps to about 165G of parquets for the daily level, hive partitioned on each date such that each file is about 300-400Mb. This is nice because duckdb knows how to skip days based on that hive partition, then within each file we sort based on types such that we can find the rank of a given type for a given time window.

## The registration process

You have a dataset — a table of (type, count) pairs, possibly sliced by time, geography, or other dimensions. You register it by telling the API:

- **Where the data lives** — a file path to parquet files
- **What shape it has** — which column is the "type", which is the "count", and what time column exists
- **What format** — flat parquet or hive-partitioned

That's enough for the `/allotax` endpoint to load and compare any two slices of your data. The wikimedia ngrams registration adds entity mapping on top of that minimum.

```python
register({
    "catalog": "vcsi",
    "domain": "wikimedia",
    "dataset_id": "ngrams",
    "data_location": "/netfiles/wikimedia_snapshots/wikigrams",
    "data_format": "parquet_hive",
    "description": "Wikipedia n-grams by frequency, date, and location with entity mappings and ranks",
    "entity_mapping": {
        "entity_namespace": "wikidata",
        "local_id_column": "country",
    },
    "entities": get_entities(),
    "endpoint_schema": {
        "type": "types-counts",
        "type_column": "ngram",
        "count_column": "pv_count",
    },
    "transform": {
        "time_dimension": "date",
        # Hive levels (ngram_size, granularity, country, date) are auto-discovered.
        # hash_bucket: "ngram_bucket",  # optional: content-sharded partition
    },
    "lineage": {
        "sources": {
            "url": "https://dumps.wikimedia.org/other/enterprise_html/"
        },
        "repo": "https://github.com/Vermont-Complex-Systems/wikipedia-parsing",
    },
    "ownership": {
        "owner_group": "vcsi",
        "contact": "compstorylab@uvm.edu"
    },
})
```

Two things this dataset declares beyond the minimum: non-default column names (`ngram`, `pv_count`) and entity mapping. Hive partition levels (ngram_size, granularity, country, date) are auto-discovered from the directory structure.

## What you gain by registering entities

Without entities, callers pass raw column values directly — `?geo=US&geo2=CA`. It works, but the API treats them as opaque strings.

```
# filter-only (no entity_mapping — pass raw column values directly)
GET /storywrangler/allotax
  ?domain=babynames&dataset=babynames-simple
  &geo=US&geo2=CA&sex=F&sex2=F
  &dates=1990&dates2=1980
```

With entities, you map your local IDs to a shared namespace (e.g. Wikidata). This buys you:

- **Cross-dataset queries** — "United States" means the same thing in babynames, wikimedia, and storywrangler ngrams. A frontend can let users pick an entity once and query all datasets.
- **Discovery** — the registry knows which entities exist in your dataset, their names, aliases (`iso:US`), and date coverage. A UI can populate a dropdown without hitting your data.
- **Provenance** — you can attach source URLs and availability ranges per entity, so users know where each slice came from and how far back it goes.

The call pattern changes accordingly — instead of a raw column value, the caller passes a canonical ID:

```
# entity-mapped (canonical ID resolved to local column value at query time)
GET /storywrangler/allotax
  ?domain=wikimedia&dataset=ngrams
  &entity=wikidata:Q30&entity2=wikidata:Q145
  &dates=2024-10-01,2024-10-31&dates2=2024-10-01,2024-10-31
  &granularity=daily
```

In short: filter-only is quick to submit; entities make your dataset a first-class citizen that composes with others.
