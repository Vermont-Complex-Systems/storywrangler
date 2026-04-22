<script lang="ts">
	import * as Code from '$lib/components/ui/code';

	const pipelineSQL = `WITH base AS (
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
GROUP BY field, year, venue`;

	const apiCalls = `# Field trends over time
GET /scisciDB/metrics?group_by=field,year&metric_type=total

# Drill into one field's venues
GET /scisciDB/metrics?group_by=venue,year&field=Computer+Science&metric_type=total

# Compare metric types
GET /scisciDB/metrics?group_by=year,metric_type&field=Computer+Science

# Multi-value filter (top venues)
GET /scisciDB/metrics?group_by=venue,year&venue=Nature,Science,PLOS+ONE&metric_type=total`;

	const registrationPayload = `register({
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
        "partition_dimensions": {"metric_type": "total"},
    },
    "lineage": {
        "sources": {"semantic_scholar": {"s2_papers": "https://api.semanticscholar.org/datasets/v1/release/"}},
        "repo": "https://github.com/jstonge/scisciDB",
    },
    "ownership": {
        "owner_group": "compethicslab",
        "contact": "compstorylab@uvm.edu",
    },
})`;
</script>

<h1>scisciDB pipeline</h1>

<p>
	scisciDB is a pipeline for studying the science of science at scale. It ingests metadata from
	Semantic Scholar and OpenAlex — over 200 million papers — and pre-aggregates them into compact,
	queryable parquet files. The goal: let researchers explore publication trends by field of study,
	venue, topic, and metric type through Storywrangler's time-series endpoint, then drill down to
	select subsets of texts for deeper analysis.
</p>

<h2>From raw data to pre-aggregated parquet</h2>

<p>
	The raw data lives in DuckLake (DuckDB + PostgreSQL metadata catalog) on VACC institutional
	storage. The pipeline, orchestrated by Dagster, runs on SLURM and pre-computes dimensional
	aggregations. Instead of querying 200M paper rows at request time, we materialize compact
	cross-tabs:
</p>

<ul>
	<li>
		<strong>field-venue-metrics</strong>: S2 field of study x venue x year x metric_type x count
	</li>
	<li>
		<strong>field-topic-metrics</strong>: S2 field of study x OpenAlex primary topic x year x
		metric_type x count
	</li>
</ul>

<p>
	Each is written as hive-partitioned parquet (partitioned by <code>field</code>), so DuckDB prunes
	to a single directory when filtering by field.
</p>

<Code.Root code={pipelineSQL} lang="sql">
	<Code.CopyButton />
</Code.Root>

<p>
	The <code>metric_type</code> dimension is synthetic — it doesn't exist in the raw data. The
	pipeline creates it by unioning total, has_abstract, and has_fulltext counts. This avoids
	computing these at query time.
</p>

<h2>The time-series endpoint</h2>

<p>
	Unlike <code>types-counts</code> (which returns a ranked bag of tokens),
	<code>time-series</code> returns tabular rows from a flexible GROUP BY query. The caller chooses
	which dimensions to group by and which to filter on.
</p>

<Code.Root code={apiCalls} lang="http">
	<Code.CopyButton />
</Code.Root>

<p>
	The same endpoint serves all these queries — <code>group_by</code> controls the SELECT and GROUP
	BY, while filter params become WHERE clauses. Multi-value filters (comma-separated) generate IN
	clauses.
</p>

<h2>Registration</h2>

<p>
	Once the parquet files are on disk, a submit script registers them with the Storywrangler API. The
	registration declares the endpoint type, column names, and query axes.
</p>

<Code.Root code={registrationPayload} lang="python">
	<Code.CopyButton />
</Code.Root>

<p>Key fields in the registration:</p>

<ul>
	<li>
		<strong><code>endpoint_schema.type = "time-series"</code></strong> tells the router to use
		<code>load_time_series()</code> instead of <code>load_system()</code>
	</li>
	<li>
		<strong><code>filter_dimensions</code></strong> (field, venue) are safe to omit — omitting
		aggregates over all values
	</li>
	<li>
		<strong><code>partition_dimensions</code></strong> (metric_type) with default
		<code>"total"</code> prevents accidental double-counting when the caller doesn't specify a
		metric type
	</li>
	<li>
		Adding a new dataset (e.g. field-topic-metrics) is just another registration — same endpoint,
		same router, zero new code
	</li>
</ul>

<h2>types-counts vs time-series</h2>

<p>
	Storywrangler supports two endpoint types, each suited to a different analytical workflow:
</p>

<ul>
	<li>
		<strong>types-counts</strong>: Returns <code>{`{types: [...], counts: [...]}`}</code> — a
		ranked distribution. Used by <code>/allotax</code> to compare two systems via rank-turbulence
		divergence. The query is always: GROUP BY type_column, ORDER BY count DESC.
	</li>
	<li>
		<strong>time-series</strong>: Returns
		<code>{`[{col1: v, ..., count: n}]`}</code> — tabular rows from a flexible GROUP BY. The
		caller picks the dimensions. Used for exploration, trend analysis, and drill-down before
		selecting subsets of texts.
	</li>
</ul>

<p>
	Both share the same infrastructure: registry-driven column names, WHERE clause generation from
	filter params, hive partition pruning. The difference is the query shape and what consumers do
	with the result.
</p>
