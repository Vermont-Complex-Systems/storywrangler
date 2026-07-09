# scisciDB pipeline

scisciDB is a pipeline for studying the science of science at scale. It ingests metadata from Semantic Scholar and OpenAlex — over 200 million papers — and pre-aggregates them into compact, queryable parquet files. The goal: let researchers explore publication trends by field of study, venue, topic, and metric type through Storywrangler's time-series endpoint, then drill down to select subsets of texts for deeper analysis.

## From raw data to pre-aggregated parquet

The raw data lives in DuckLake (DuckDB + PostgreSQL metadata catalog) on VACC institutional storage. The pipeline, orchestrated by Dagster, runs on SLURM and pre-computes dimensional aggregations. Instead of querying 200M paper rows at request time, we materialize compact cross-tabs:

- **field-venue-metrics**: S2 field of study x venue x year x metric_type x count
- **field-topic-metrics**: S2 field of study x OpenAlex primary topic x year x metric_type x count

Each is written as hive-partitioned parquet (partitioned by `field`), so DuckDB prunes to a single directory when filtering by field.

```sql
WITH base AS (
    SELECT
        list_filter(s2fieldsofstudy, x -> x.source = 's2-fos-model')[1].category AS field,
        venue, year, has_abstract, has_fulltext
    FROM s2_papers
    WHERE s2fieldsofstudy IS NOT NULL
      AND year IS NOT NULL AND year BETWEEN 1900 AND 2025
)
SELECT field, year, venue, 'total' AS metric_type, COUNT(*) AS count
FROM base WHERE field IS NOT NULL
GROUP BY field, year, venue

UNION ALL

SELECT field, year, venue, 'has_abstract' AS metric_type, COUNT(*) AS count
FROM base WHERE field IS NOT NULL AND has_abstract = true
GROUP BY field, year, venue

UNION ALL

SELECT field, year, venue, 'has_fulltext' AS metric_type, COUNT(*) AS count
FROM base WHERE field IS NOT NULL AND has_fulltext = true
GROUP BY field, year, venue
```

The `metric_type` dimension is synthetic — it doesn't exist in the raw data. The pipeline creates it by unioning total, has_abstract, and has_fulltext counts. This avoids computing these at query time.

## The time-series endpoint

Unlike `types-counts` (which returns a ranked bag of tokens), `time-series` returns tabular rows from a flexible GROUP BY query. The caller chooses which dimensions to group by and which to filter on.

```
# Field trends over time
GET /scisciDB/metrics?group_by=field,year&metric_type=total

# Drill into one field's venues
GET /scisciDB/metrics?group_by=venue,year&field=Computer+Science&metric_type=total

# Compare metric types
GET /scisciDB/metrics?group_by=year,metric_type&field=Computer+Science

# Multi-value filter (top venues)
GET /scisciDB/metrics?group_by=venue,year&venue=Nature,Science,PLOS+ONE&metric_type=total
```

The same endpoint serves all these queries — `group_by` controls the SELECT and GROUP BY, while filter params become WHERE clauses. Multi-value filters (comma-separated) generate IN clauses.

## Registration

Once the parquet files are on disk, a submit script registers them with the Storywrangler API. The registration declares the endpoint type, column names, and query axes.

```python
register({
    "catalog": "vcsi",
    "domain": "scisciDB",
    "dataset_id": "field-venue-metrics",
    "data_location": "/netfiles/compethicslab/scisciDB/field-venue-metrics",
    "data_format": "parquet_hive",
    "description": "Precomputed paper counts by S2 field, venue, year, and metric type.",
    "endpoint_schema": {
        "type": "time-series",
        "count_column": "count",
    },
    "transform": {
        "time_dimension": "year",
        "filter_dimensions": ["field", "venue"],
        # metric_type is a hive partition level — auto-discovered with default "has_abstract"
        # (alphabetically first). The query layer injects this default when callers omit it.
    },
    "lineage": {
        "sources": {"semantic_scholar": {"s2_papers": "https://api.semanticscholar.org/datasets/v1/release/"}},
        "repo": "https://github.com/jstonge/scisciDB",
    },
    "ownership": {
        "owner_group": "compethicslab",
        "contact": "compstorylab@uvm.edu",
    },
})
```

Key fields in the registration:

- **`endpoint_schema.type = "time-series"`** tells the router to use `load_time_series()` instead of `load_system()`
- **`filter_dimensions`** (field, venue) are non-hive columns safe to omit — omitting aggregates over all values
- **`metric_type`** is a hive partition level, auto-discovered from the directory structure. The query layer injects a default when callers omit it, preventing accidental double-counting
- Adding a new dataset (e.g. field-topic-metrics) is just another registration — same endpoint, same router, zero new code

## types-counts vs time-series

Storywrangler supports two endpoint types, each suited to a different analytical workflow:

- **types-counts**: Returns `{types: [...], counts: [...]}` — a ranked distribution. Used by `/allotax` to compare two systems via rank-turbulence divergence. The query is always: GROUP BY type_column, ORDER BY count DESC.
- **time-series**: Returns `[{col1: v, ..., count: n}]` — tabular rows from a flexible GROUP BY. The caller picks the dimensions. Used for exploration, trend analysis, and drill-down before selecting subsets of texts.

Both share the same infrastructure: registry-driven column names, WHERE clause generation from filter params, hive partition pruning. The difference is the query shape and what consumers do with the result.
