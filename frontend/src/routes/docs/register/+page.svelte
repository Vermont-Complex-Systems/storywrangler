<script lang="ts">
	import * as Code from '$lib/components/ui/code';

	const skeleton = `from storywrangler.registry import register

register({
    # ── Identity ──────────────────────────────────────────────────────
    "catalog":    "vcsi",          # producer org; vcsi is the default
    "domain":     "your-lab",      # top-level namespace (lab or project name)
    "dataset_id": "your-dataset",  # unique within the domain

    # ── Location ──────────────────────────────────────────────────────
    "data_location": "/netfiles/yourlab/dataset/",
    "data_format":   "parquet_hive",  # parquet | parquet_hive | duckdb | ducklake

    # ── Format-specific metadata ───────────────────────────────────────
    "format_config": {
        # tables_metadata, ducklake_data_path, partitioning, availability go here
        # (parquet_hive: tables_metadata + partitioning;
        #  ducklake:     tables_metadata + ducklake_data_path)
    },

    # ── Entity mapping (optional) ─────────────────────────────────────
    # Declares which column holds filter-dimension entities (countries,
    # researchers, topics). Omit if your dataset has no crosslinkable
    # dimensions. See "Entity mapping" section below.
    "entity_mapping": {
        "local_id_column": "country",
    },
    "entities": [
        {
            "local_id":    "united_states",   # value in your column
            "entity_id":   "wikidata:Q30",     # canonical identifier
            "entity_name": "United States",
            "entity_ids":  ["iso:US"],          # additional aliases
        },
    ],

    # ── Provenance ────────────────────────────────────────────────────
    "lineage": {
        "sources": {
            "main": {"your-source": "https://example.org/data/"},
        },
        "derived_from": [],             # ["domain/dataset_id"] if built on Silver data
        "consumers":    [],             # downstream users, stories, or scripts
    },

    # ── Ownership ─────────────────────────────────────────────────────
    "ownership": {
        "owner_group":  "your-lab",
        "contact":      "you@uvm.edu",
        "storage_risk": "institutional",  # managed | institutional | cloud | personal
    },

    # ── Instrument contract (optional) ────────────────────────────────
    # Required if you want this dataset queryable by allotaxonometer,
    # wordshift, or other instruments. Declares what query types it supports.
    "endpoint_schema": {
        "type": "types-counts",
        "time_dimension": "year",
        "filter_dimensions": ["country"],  # optional categorical filter columns
    },
})`;
</script>

<h1>Registering a dataset</h1>

<p>
	Registration is an upsert — safe to re-run as data or metadata changes. The SDK validates all
	<code>entity_id</code> values against the
	<a href="/docs/specification">Storywrangler-Specification</a> before making any network call.
	Malformed identifiers are rejected locally before anything reaches the server.
</p>

<h2>The submit.py structure</h2>

<p>
	A <code>submit.py</code> is a single call to <code>register()</code> with a Python dict. The
	dict has five logical groups of fields:
</p>

<ul>
	<li><strong>Identity</strong> — the two-part namespace key: <code>domain/dataset_id</code></li>
	<li>
		<strong>Location</strong> — where the data lives and in what format. The registry stores a
		pointer; it never copies the data.
	</li>
	<li>
		<strong>Format config</strong> — storage-format-specific metadata: file paths, partitioning
		scheme, coverage ranges. What the API needs to locate and query the data.
	</li>
	<li>
		<strong>Provenance</strong> — the <code>lineage</code> object: where raw data came from
		(<code>sources</code>), which registered datasets it was built on (<code>derived_from</code>),
		and known downstream consumers (<code>consumers</code>).
	</li>
	<li>
		<strong>Ownership</strong> — who maintains it and how durable the storage is
		(<code>storage_risk</code>).
	</li>
</ul>

<p>Two optional fields unlock additional platform features:</p>

<ul>
	<li>
		<strong>Entity mapping</strong> — maps dataset-local column values to canonical IDs
		(e.g. <code>wikidata:Q30</code>). Optional — instruments work without it via
		<code>filter_dimensions</code>, but entity mapping makes your dataset composable with
		others that share the same namespace. See below.
	</li>
	<li>
		<strong>Endpoint schema</strong> — declares what query types the dataset supports, so
		instruments can determine compatibility without hardcoding dataset-specific logic.
	</li>
</ul>

<Code.Root code={skeleton} lang="python">
	<Code.CopyButton />
</Code.Root>

<h2>Entity mapping</h2>

<p>
	The <code>entity_mapping</code> field covers <strong>filter-dimension entities</strong> — things a
	caller can GROUP BY or FILTER ON in an instrument query. It is not for measured values. Person
	names are the content of babynames, not its dimensions; Wikipedia article titles are the content
	of ngrams, not dimensions.
</p>

<p>Adapter vocabularies are always bounded by entity type:</p>

<table>
	<thead>
		<tr>
			<th>Entity type</th>
			<th>Typical count</th>
		</tr>
	</thead>
	<tbody>
		<tr><td>Countries / territories</td><td>11–200</td></tr>
		<tr><td>Researchers / ORCID holders</td><td>hundreds to tens of thousands</td></tr>
		<tr><td>Topics / fields (controlled vocabulary)</td><td>hundreds</td></tr>
		<tr><td>Wikipedia articles, person names</td><td>millions — never an adapter vocabulary</td></tr>
	</tbody>
</table>

<p>
	The SDK batches large entity lists automatically (~2,000 per request). See the
	<a href="/docs/reference#entity-types">Field reference</a> for all supported
	<code>entity_id</code> namespace prefixes (<code>wikidata</code>, <code>orcid</code>,
	<code>ror</code>, etc.).
</p>

<h2>Choosing a storage format</h2>

<p>
	The registry accommodates four <code>data_format</code> values. The right choice depends on how
	your group manages its data, not on what the platform prefers.
</p>

<table>
	<thead>
		<tr>
			<th>Format</th>
			<th>Best for</th>
			<th><code>submit.py</code> complexity</th>
		</tr>
	</thead>
	<tbody>
		<tr>
			<td><code>ducklake</code></td>
			<td>Groups already running a DuckLake catalog</td>
			<td>Medium — must query DuckLake metadata tables for file paths and coverage, but no manual directory scanning</td>
		</tr>
		<tr>
			<td><code>parquet_hive</code></td>
			<td>Groups that drop files on netfiles and want to keep it simple</td>
			<td>Medium — must manually scan partitions and compute statistics</td>
		</tr>
		<tr>
			<td><code>duckdb</code></td>
			<td>Small, stable, managed datasets (survey snapshots, historical records)</td>
			<td>Low — single file, no partitioning</td>
		</tr>
		<tr>
			<td><code>parquet</code></td>
			<td>Single flat parquet file, no partitioning or catalog</td>
			<td>Low — simplest case; no format_config sub-fields needed</td>
		</tr>
	</tbody>
</table>

<p>
	<strong>DuckLake</strong> — if your group already uses DuckLake, <code>submit.py</code> reads
	file paths and coverage from the catalog's metadata tables rather than scanning directories
	manually. The tradeoff is operational overhead — you need a running DuckLake catalog. If your
	group is not already comfortable with DuckLake, starting with <code>parquet_hive</code> and
	migrating later is a reasonable path.
</p>

<p>
	<strong>parquet_hive</strong> — the most common choice for groups that produce data via a pipeline
	and write the output to netfiles. No catalog, no schema inference — the adapter scans the
	partition layout and computes statistics explicitly.
</p>

<h3>Why the registry itself is not DuckLake</h3>

<p>
	The registry is a mutable operational store — rows are frequently updated as ownership transfers,
	status changes, and metadata is enriched. DuckLake's time-travel is efficient precisely because
	parquet files are immutable; frequent small updates fight against this model. PostgreSQL with
	Alembic migrations is the right shape for a catalog of this kind.
</p>

<p>
	The resilience benefit DuckLake would provide — catalog queryable without the API — is covered by
	the planned <a href="/docs/roadmap#p3--catalog-resilience">parquet snapshot export (P3)</a>.
</p>

<h2>Case studies</h2>

<p>
	Two reference pipelines show what a complete <code>submit.py</code> looks like in practice, each
	with a different storage format:
</p>

<ul>
	<li>
		<a href="/docs/case-studies/wikimedia">Wikimedia pipeline</a> — <code>parquet_hive</code>.
		Raw Wikipedia dump → Silver n-gram frequencies, partitioned by date and country.
	</li>
	<li>
		<a href="/docs/case-studies/babynames">Babynames pipeline</a> — <code>ducklake</code>.
		SSA + Québec birth records managed via a DuckLake catalog; shows how the catalog eliminates
		manual partition scanning.
	</li>
</ul>
