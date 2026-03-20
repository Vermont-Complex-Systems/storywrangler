<script lang="ts">
	import * as Code from '$lib/components/ui/code';

	const minimalEndpoint = `# Minimal endpoint_schema to unlock allotaxonometry
"endpoint_schema": {
    "type": "types-counts",
    "time_dimension": "year",   # or "granularities" for parquet_hive
}`;

	const callPatterns = `# entity vs entity (same time, different place)
GET /storywrangler/allotax
  ?domain=wikimedia&dataset=ngrams
  &entity=wikidata:Q30&entity2=wikidata:Q145
  &dates=2024-10&dates2=2024-10
  &granularity=daily

# time vs time (same entity, different period)
GET /storywrangler/allotax
  ?domain=babynames&dataset=babynames
  &entity=wikidata:Q30
  &dates=1990&dates2=1980

# filter-only (no entity_mapping — pass raw column values)
GET /storywrangler/allotax
  ?domain=babynames&dataset=babynames-simple
  &geo=US&geo2=CA&sex=F&sex2=F
  &dates=1990&dates2=1980`;
</script>

<h1>Allotaxonometry</h1>

<p>
	A suite of instruments for comparing two ranked lists — word frequencies, name counts, topic
	distributions — across time, place, or any declared dimension. Includes the allotaxonometer
	and wordshift.
</p>

<h2>Allotaxonometer</h2>

<p>
	The allotaxonometer measures rank-turbulence divergence (RTD) between two ranked lists and
	produces a contribution breakdown: which elements shifted the most, and in which direction.
	The visual output is an allotaxonograph — a mirror plot showing the top drivers of the
	divergence.
</p>

<p>
	The core calculations are implemented in
	<a href="https://github.com/Vermont-Complex-Systems/allotaxonometer-core">allotaxonometer-core</a>,
	a Rust crate that handles the RTD computation. The web instruments call this crate via
	WebAssembly.
</p>

<h2>Wordshift</h2>

<p>
	Wordshift decomposes the difference in average word score (sentiment, frequency, or any
	per-word signal) between two text collections into word-level contributions — which words
	drove the change, through increased or decreased usage, and whether they pulled the score up
	or down.
</p>

<h2>Making a dataset queryable</h2>

<p>
	Any registered dataset with <code>endpoint_schema.type = "types-counts"</code> is
	automatically queryable by allotaxonometry instruments. No custom integration is needed — the
	endpoint is driven entirely by the registered metadata.
</p>

<Code.Root code={minimalEndpoint} lang="python">
	<Code.CopyButton />
</Code.Root>

<p>Optional fields that unlock additional query patterns:</p>

<ul>
	<li>
		<code>time_dimension</code> — column for WHERE-based time filtering. Required for time vs
		time comparisons on flat (non-hive) datasets.
	</li>
	<li>
		<code>granularities</code> — for <code>parquet_hive</code> datasets. Maps subdirectory
		granularity to time column: <code>{`{"daily": "date", "monthly": "month"}`}</code>.
	</li>
	<li>
		<code>filter_dimensions</code> — local categorical columns a caller can filter on
		(e.g. <code>["sex"]</code> in babynames, <code>["geo"]</code> for a dataset without
		entity mapping).
	</li>
	<li>
		<code>type_column</code> / <code>count_column</code> — declare when your parquet files
		use non-default column names (defaults are <code>types</code> and <code>counts</code>).
	</li>
</ul>

<h2>Call patterns</h2>

<p>
	The <code>/storywrangler/allotax</code> endpoint compares any two systems that differ on at
	least one dimension. Systems are specified by combining <code>entity</code>,
	<code>dates</code>, and filter dimension parameters:
</p>

<Code.Root code={callPatterns} lang="http">
	<Code.CopyButton />
</Code.Root>

<p>
	Datasets with <a href="/docs/case-studies/wikimedia#the-difference-entity-mapping-makes">entity mapping</a>
	accept canonical Wikidata IDs (<code>wikidata:Q30</code>) — the endpoint resolves them to the
	dataset's internal column values at query time. Datasets without entity mapping accept raw
	column values directly via <code>filter_dimensions</code>.
</p>

<h2>Status</h2>

<p>
	In development at the Vermont Complex Systems Institute. Documentation will expand as the
	instruments stabilise.
</p>
