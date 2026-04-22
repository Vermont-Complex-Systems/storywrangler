<script lang="ts">
	import * as Code from '$lib/components/ui/code';

  import diagram from '$lib/assets/simple-diagram.png?enhanced';
  
	// Step 1 — types-counts with filter_dimensions only. No entity axis, no time.
	// The allotaxonometer can compare ?town=Arlington vs ?town2=Addison.
	const step1 = `from storywrangler import Storywrangler

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
})`;

	// Curl preview for Step 1 — filter_dimensions become bare query parameters.
	const step1curl = `curl "https://storywrangler.uvm.edu/storywrangler/allotax\\
  ?domain=vt-zoning-atlas&dataset=ngrams\\
  &town=Arlington&town2=Addison"`;

	// Step 2 — diff: entity_mapping replaces filter_dimensions.
	const step1b = `- "transform": {"filter_dimensions": ["town"]},

+ "entity_mapping": {"local_id_column": "town", "entity_namespace": "wikidata"},
+ "entities": [
+     {"local_id": "Arlington", "entity_id": "wikidata:Q675558", "entity_name": "Arlington, Vermont"},
+     {"local_id": "Addison",   "entity_id": "wikidata:Q353095", "entity_name": "Addison, Vermont"},
+     # ... one row per town
+ ],`;

	// Curl preview for Step 2 — entity IDs instead of raw filter values.
	const step1bcurl = `curl "https://storywrangler.uvm.edu/storywrangler/allotax\\
  ?domain=vt-zoning-atlas&dataset=ngrams\\
  &entity=wikidata:Q675558&entity2=wikidata:Q353095"`;

	// Step 3 — babynames: year/sex/geo all as plain filter_dimensions (starting state).
	const step2 = `from storywrangler import Storywrangler

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
})`;

	// Curl preview for filter-only version — year as exact match.
	const step2curl = `curl "https://storywrangler.uvm.edu/storywrangler/allotax\\
  ?domain=babynames&dataset=ngrams\\
  &year=1990&year2=2020\\
  &geo=united_states&sex=F"`;

	// Diff: move year to time_dimension, add manifest.availability.
	const step2time = `  "transform": {
-     "filter_dimensions": ["year", "sex", "geo"],
+     "filter_dimensions": ["sex", "geo"],
+     "time_dimension":    "year",
  },

+ "manifest": {
+     "availability": {
+         "united_states": {"min": 1880, "max": 2022},
+         "quebec":        {"min": 1980, "max": 2022},
+     }
+ },`;

	// Step 3b — diff: remove geo from filter_dimensions, add entity_mapping, upgrade manifest keys.
	const step2b = `- "filter_dimensions": ["sex", "geo"],
+ "filter_dimensions": ["sex"],

  "manifest": {
      "availability": {
-         "united_states": {"min": 1880, "max": 2022},
-         "quebec":        {"min": 1980, "max": 2022},
+         "wikidata:Q30":  {"min": 1880, "max": 2022},
+         "wikidata:Q176": {"min": 1980, "max": 2022},
      }
  },

+ "entity_mapping": {"local_id_column": "geo", "entity_namespace": "wikidata"},
+ "entities": [
+     {"local_id": "united_states", "entity_id": "wikidata:Q30",  "entity_name": "United States"},
+     {"local_id": "quebec",        "entity_id": "wikidata:Q176", "entity_name": "Quebec"},
+ ],`;

	// Curl preview — canonical entity IDs after adding entity_mapping.
	const step3curl = `curl "https://storywrangler.uvm.edu/storywrangler/allotax\\
  ?domain=babynames&dataset=ngrams\\
  &entity=wikidata:Q30\\
  &dates=1990&dates2=2020\\
  &sex=F"`;

	// Step 4 — wikimedia: parquet_hive + partition_dimensions + non-default column names.
	const step4 = `from storywrangler import Storywrangler

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
        "type_column":  "ngram",     # non-override when column name differs
        "count_column": "pv_count",  # non-default
    },
    "transform": {
        "time_dimension": "date",      # hive partition key; callers use ?dates= (standardized)
        # partition_dimensions: a dict, not a list.
        # Keys are columns unsafe to mix (daily + monthly = nonsense aggregation).
        # Values are the safe defaults injected when the caller omits the param.
        "partition_dimensions": {"granularity": "daily", "ngram_size": 1},
    },
    "entity_mapping": {"local_id_column": "country", "entity_namespace": "wikidata"},
    "entities": [
        {"local_id": "United States",  "entity_id": "wikidata:Q30",  "entity_name": "United States"},
        {"local_id": "United Kingdom", "entity_id": "wikidata:Q145", "entity_name": "United Kingdom"},
        # … ~100 Wikipedia language editions
    ],

    "ownership": {"owner_group": "vcsi", "contact": "compstorylab@uvm.edu"},
    "lineage":   {"repo": "https://github.com/Vermont-Complex-Systems/..."},
})`;

	// DuckDB translation for Step 4 — what the API runs internally per system.
	const step4duckdb = `FROM read_parquet('1grams/ngram_size=1/**/*.parquet', hive_partitioning=true)
WHERE country     = 'United States'    -- entity_mapping.local_id_column
  AND date BETWEEN ? AND ?             -- time_dimension
  AND granularity = 'daily'            -- partition_dimensions (default injected)`;

	// Curl preview for Step 4 — partition_dimensions passed as regular query params.
	const step4curl = `curl "https://storywrangler.uvm.edu/storywrangler/allotax\\
  ?domain=wikimedia&dataset=ngrams\\
  &entity=wikidata:Q30&entity2=wikidata:Q145\\
  &dates=2024-10-01,2024-10-31&dates2=2024-10-01,2024-10-31\\
  &granularity=daily"`;
</script>

<h1>Registering a dataset</h1>

<div class="not-prose my-8">
	<enhanced:img src={diagram} alt="Storywrangler platform diagram: a POST request with endpoint_schema, data_location, and data_format enters the Storywrangler Platform (a decision diamond), which validates schema and data availability, reads from File Storage below, and returns an allotax JSON response." class="w-full dark:invert" />
</div>


<p>
	The simplest use case of registering your dataset is to get access to VCSI instruments, such as
	the <a href="/tools/allotaxonometer">allotaxonometer</a>, which can then be served anywhere
	on the web. In this case, your submitted dataset must fulfil the instrument requirements you want
	to access (e.g. the allotaxonometer requires a <code>types-counts</code> endpoint schema — see
	the instrument page). It should also be part of an accepted domain. By default, endpoints can go
	in the <code>guest</code> domain, but specifying a domain helps cluster related datasets and
	improves discovery.
</p>

<p>
	The minimal working registration. <code>types-counts</code> is the endpoint type for any
	rank-frequency distribution: a column of token values and a column of counts. At least one
	comparison axis is required — without one the API rejects the registration, since the
	allotaxonometer has no way to distinguish system 1 from system 2.
	<code>filter_dimensions</code> are categorical axes that serve as that comparison axis:
	the allotaxonometer compares <code>?town=Arlington vs ?town2=Addison</code>. At query time,
	omitting the parameter aggregates over all its values.
</p>

<Code.Root code={step1} lang="python">
	<Code.CopyButton />
</Code.Root>

<p>Once registered, each <code>filter_dimensions</code> entry becomes a bare query parameter on the allotaxonometer. Comparing Arlington vs Addison:</p>

<Code.Root code={step1curl} lang="bash" hideLines={true}>
</Code.Root>

<p>Without any entity mapping, we adopt the convention of simply incrementing provided filter dimensions when querying the API, e.g. <code>town</code> and <code>town2</code>.</p>

<h2>Providing entity mapping</h2>

<p>
	Drop <code>filter_dimensions</code> and add <code>entity_mapping</code> instead. The SDK
	validates all <code>entity_id</code> values locally before anything reaches the server.
	This also standardizes the API parameter: regardless of what the local column is called
	(<code>town</code>, <code>geo</code>, <code>country</code>…), callers always use
	<code>?entity=</code> and <code>?entity2=</code> — accepting either a canonical ID
	(<code>wikidata:Q675558</code>) or the raw local value (<code>Arlington</code>):
</p>

<Code.Root code={step1b} lang="diff" hideLines={true}>
</Code.Root>

<p>The corresponding curl command:</p>

<Code.Root code={step1bcurl} lang="bash" hideLines={true}>
</Code.Root>

<p>By analogy to <code>filter_dimension</code>, the API now expect <code>entity</code> and <code>entity2</code> keys but values can either be the standardized or local identifiers. </p>

<h2>Adding a time axis</h2>

<p>
	<code>transform.time_dimension</code> opens a date-range axis for <code>BETWEEN</code> queries.
	The meaningful comparisons are same location across two time ranges (e.g. US 1990 vs US 2020),
	or same time range across two locations (e.g. US 2020 vs Quebec 2020). This is also the first
	registration that populates <code>manifest.availability</code> — year coverage per location,
	letting the UI know valid ranges without querying the data.
</p>

<p>
	Start without entity mapping: <code>geo</code> stays in <code>filter_dimensions</code> and
	callers pass raw local IDs directly — <code>?geo=united_states</code> — with no namespace
	resolution. The manifest is keyed by the same local IDs.
</p>

<Code.Root code={step2} lang="python">
	<Code.CopyButton />
</Code.Root>

<p>And the corresponding curl command:</p>

<Code.Root code={step2curl} lang="bash" hideLines={true}>
</Code.Root>

<p>Moving <code>year</code> to <code>time_dimension</code> unlocks range queries and standardizes
the API parameter: regardless of the underlying column name (<code>year</code>, <code>date</code>…),
callers always use <code>?dates=</code> and <code>?dates2=</code>. <code>manifest.availability</code>
is optional — it tells the UI what years are valid without touching the data, but the endpoint
works without it:</p>

<Code.Root code={step2time} lang="diff" hideLines={true}>
</Code.Root>

<p>
	Adding <code>entity_mapping</code> promotes <code>geo</code> out of
	<code>filter_dimensions</code> and upgrades the manifest keys to canonical entity IDs:
</p>

<Code.Root code={step2b} lang="diff" hideLines={true}>
</Code.Root>

<p>The corresponding curl command:</p>

<Code.Root code={step3curl} lang="bash" hideLines={true}>
</Code.Root>

<h2>hive-partitioned storage</h2>

<p>
	The final form introduces <a href="https://duckdb.org/docs/current/data/partitioning/hive_partitioning">hive_partitioning</a> by specifying the `data_format`,  the relevant <code>partition_dimensions</code>. When using the hive partitioning strategy, <code>data_location</code> encodes the root of the hive tree:
</p>

<pre><code>1grams/                          ← data_location
  ngram_size=1/
    granularity=daily/
      country=United%20States/
        date=2024-01-01/data.parquet</code></pre>

<p>
	The subsequent directories below the data root should be of the form <code>col=val/</code> . This is geared towards performance, as duckdb will only read the relevant files when querying the data. This is particularly valuable in web apps where users could benefit from exploring arbitrary date ranges.
</p>

<Code.Root code={step4} lang="python">
	<Code.CopyButton />
</Code.Root>

<p>
	Each registration field maps directly to a clause in the DuckDB query the API runs per
	system — it really is that simple:
</p>

<Code.Root code={step4duckdb} lang="sql" hideLines={true}>
</Code.Root>

<p>
	That result set is handed to the instrument as-is. Partition dimensions are passed as regular
	query params — the platform validates them against the introspected <code>filter_values</code>
	and injects defaults for any omitted ones:
</p>

<Code.Root code={step4curl} lang="bash" hideLines={true}>
</Code.Root>

<h2>Case studies</h2>

<p>
	The <a href="/case-studies/wikimedia">Wikimedia pipeline</a> shows what a complete
	<code>submit.py</code> looks like for <code>parquet_hive</code>: raw Wikipedia dump → silver
	n-gram frequencies, partitioned by country, granularity, and date. Covers
	<code>transform.partition_dimensions</code> and <code>manifest.availability</code>.
</p>
