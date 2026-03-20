<script lang="ts">
	import * as Code from '$lib/components/ui/code';
	import PipelineDiagram from '$lib/components/PipelineDiagram.svelte';

	const ngramsPayload = `register({
    "catalog":       "vcsi",
    "domain":        "wikimedia",
    "dataset_id":    "ngrams",
    "data_location": "/netfiles/compethicslab/wikimedia/1grams",
    "data_format":   "parquet_hive",
    "description":   "Wikipedia n-gram frequencies by country and date",

    # ── What shape it has ─────────────────────────────────────────────
    "format_config": {
        "tables_metadata": {"ngrams": ["/netfiles/.../daily/...", ...]},
        "partitioning": {"keys": ["date", "country"]},
    },
    "endpoint_schema": {
        "type":         "types-counts",
        "type_column":  "ngram",     # non-default column name
        "count_column": "pv_count",  # non-default column name
        "granularities": {"daily": "date", "weekly": "week", "monthly": "month"},
    },

    # ── What entities exist ───────────────────────────────────────────
    "entity_mapping": {
        "local_id_column": "country",   # raw value in parquet: "United States"
    },
    "entities": [
        {"local_id": "United States", "entity_id": "wikidata:Q30",  "entity_name": "United States"},
        {"local_id": "United Kingdom", "entity_id": "wikidata:Q145", "entity_name": "United Kingdom"},
        # … ~100 Wikipedia language editions
    ],

    # ── Provenance and ownership ──────────────────────────────────────
    "lineage": {
        "sources": {"main": {"enwiki": "https://dumps.wikimedia.org/other/enterprise_html/"}},
        "derived_from": [],
    },
    "ownership": {
        "owner_group":  "vcsi",
        "contact":      "compstorylab@uvm.edu",
        "storage_risk": "institutional",
    },
})`;

	const filterOnlyCall = `# filter-only (no entity_mapping — pass raw column values directly)
GET /storywrangler/allotax
  ?domain=babynames&dataset=babynames-simple
  &geo=US&geo2=CA&sex=F&sex2=F
  &dates=1990&dates2=1980`;

	const entityMappedCall = `# entity-mapped (canonical ID resolved to local column value at query time)
GET /storywrangler/allotax
  ?domain=wikimedia&dataset=ngrams
  &entity=wikidata:Q30&entity2=wikidata:Q145
  &dates=2024-10-01,2024-10-31&dates2=2024-10-01,2024-10-31
  &granularity=daily`;
</script>

<h1>Wikimedia pipeline</h1>

<p>
	Wikipedia n-gram frequencies: raw page-view dumps → Silver parquet_hive → live allotaxonometry
	on Complex Stories. Reference implementation for groups writing Hive-partitioned files to shared
	storage.
</p>

<PipelineDiagram />

<h2>The registration process</h2>

<p>
	You have a dataset — a table of (type, count) pairs, possibly sliced by time, geography, or other
	dimensions. You register it by telling the API:
</p>

<ul>
	<li><strong>Where the data lives</strong> — a file path (parquet, ducklake, etc.)</li>
	<li>
		<strong>What shape it has</strong> — which column is the "type", which is the "count", what
		time column exists, what other dimensions can be filtered on
	</li>
	<li><strong>What format</strong> — flat parquet, hive-partitioned, ducklake, etc.</li>
</ul>

<p>
	That's enough for the <code>/allotax</code> endpoint to load and compare any two slices of your
	data. The wikimedia ngrams registration adds entity mapping on top of that minimum.
</p>

<Code.Root code={ngramsPayload} lang="python">
	<Code.CopyButton />
</Code.Root>

<p>
	Two things this dataset declares beyond the minimum: non-default column names
	(<code>ngram</code>, <code>pv_count</code>) and a hive granularity map
	(<code>daily/weekly/monthly</code>). Both are read by the allotax endpoint at query time.
</p>

<h2>What you gain by registering entities</h2>

<p>
	Without entities, callers pass raw column values directly — <code>?geo=US&amp;geo2=CA</code>. It
	works, but the API treats them as opaque strings.
</p>

<Code.Root code={filterOnlyCall} lang="http">
	<Code.CopyButton />
</Code.Root>

<p>
	With entities, you map your local IDs to a shared namespace (e.g. Wikidata). This buys you:
</p>

<ul>
	<li>
		<strong>Cross-dataset queries</strong> — "United States" means the same thing in babynames,
		wikimedia, and storywrangler ngrams. A frontend can let users pick an entity once and query
		all datasets.
	</li>
	<li>
		<strong>Discovery</strong> — the registry knows which entities exist in your dataset, their
		names, aliases (<code>iso:US</code>), and date coverage. A UI can populate a dropdown without
		hitting your data.
	</li>
	<li>
		<strong>Provenance</strong> — you can attach source URLs and availability ranges per entity,
		so users know where each slice came from and how far back it goes.
	</li>
</ul>

<p>
	The call pattern changes accordingly — instead of a raw column value, the caller passes a
	canonical ID:
</p>

<Code.Root code={entityMappedCall} lang="http">
	<Code.CopyButton />
</Code.Root>

<p>
	In short: filter-only is quick to submit; entities make your dataset a first-class citizen that
	composes with others.
</p>
