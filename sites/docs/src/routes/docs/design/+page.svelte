<script lang="ts">
	import * as Code from '$lib/components/ui/code';
	import * as Table from '$lib/components/ui/table';

	const duckdbExample = `import duckdb
duckdb.sql("SELECT * FROM read_parquet('/netfiles/compethicslab/babynames/**/*.parquet')")`;
</script>

<h1>Design & architecture</h1>

<p class="lead">
	Key design decisions behind the platform. This section grows as decisions are made and stabilized.
</p>

<h2>External vs. managed datasets</h2>

<p>
	By default, data stays with the submitter. The platform stores metadata only — a pointer to
	wherever the data lives on institutional storage. This preserves data sovereignty and avoids
	duplicating TB-scale datasets.
</p>

<p>
	<strong>Managed datasets</strong> are the opt-in alternative. When a student leaves without a
	successor, or when a dataset is small and stable enough, VCSI can take custody and move the data
	to platform-controlled storage.
</p>

<Table.Root>
	<Table.Header>
		<Table.Row>
			<Table.Head class="w-44"></Table.Head>
			<Table.Head>External <span class="text-muted-foreground font-normal">(default)</span></Table.Head>
			<Table.Head>Managed <span class="text-muted-foreground font-normal">(opt-in)</span></Table.Head>
		</Table.Row>
	</Table.Header>
	<Table.Body>
		<Table.Row>
			<Table.Cell class="font-medium">Data location</Table.Cell>
			<Table.Cell>Submitter's institutional storage</Table.Cell>
			<Table.Cell><code>/netfiles/vcsi/warehouse/</code> or PostgreSQL</Table.Cell>
		</Table.Row>
		<Table.Row>
			<Table.Cell class="font-medium">Storage owner</Table.Cell>
			<Table.Cell>Submitting group</Table.Cell>
			<Table.Cell>VCSI</Table.Cell>
		</Table.Row>
		<Table.Row>
			<Table.Cell class="font-medium">API-down fallback</Table.Cell>
			<Table.Cell>✓ DuckDB reads directly from <code>data_location</code></Table.Cell>
			<Table.Cell>✓ if on netfiles; depends on storage choice if on VM</Table.Cell>
		</Table.Row>
		<Table.Row>
			<Table.Cell class="font-medium"><code>storage_risk</code></Table.Cell>
			<Table.Cell><code>institutional</code> · <code>cloud</code> · <code>personal</code></Table.Cell>
			<Table.Cell><code>managed</code></Table.Cell>
		</Table.Row>
		<Table.Row>
			<Table.Cell class="font-medium">Typical trigger</Table.Cell>
			<Table.Cell>Registration via <code>submit.py</code></Table.Cell>
			<Table.Cell>Succession (<code>status: needs_successor</code>) or explicit request</Table.Cell>
		</Table.Row>
		<Table.Row>
			<Table.Cell class="font-medium">Best for</Table.Cell>
			<Table.Cell>Active datasets owned by a research group</Table.Cell>
			<Table.Cell>Historical, stable datasets; datasets whose author has left</Table.Cell>
		</Table.Row>
	</Table.Body>
</Table.Root>

<p>
	Managed ingestion has three paths: <strong>static clone</strong> (copy parquet files, update
	<code>data_location</code>), <strong>pipeline adoption</strong> (clone the source repo, schedule
	via Dagster), or <strong>PostgreSQL ingest</strong> (for very small, highly-queried datasets where
	DuckDB can still query via the PostgreSQL scanner extension). For now all datasets are expected to
	be external.
</p>

<h2>Platform down → data still accessible</h2>

<p>
	For external datasets, data lives on institutionally-managed storage (netfiles, shared object
	storage). If the API is unreachable, groups can still query their data directly via DuckDB +
	<code>data_location</code>:
</p>

<Code.Root code={duckdbExample} lang="python">
	<Code.CopyButton />
</Code.Root>

<h2>Entity mapping</h2>

<p>
	The <code>entity_mapping</code> field maps dataset-local column values to canonical identifiers
	from the <a href="https://github.com/vermont-complex-systems/Storywrangler-Specification">Storywrangler Specification</a>.
	Entities are submitted inline in <code>register()</code> and stored in the platform's PostgreSQL
	<code>entity_mappings</code> table — no separate adapter files needed.
</p>

<p>
	The SDK validates all <code>entity_id</code> values against the specification before making any
	network call. Malformed identifiers are rejected locally.
</p>

<h2>Medallion tiers</h2>

<p>The registry uses Bronze / Silver / Gold tiers adapted for a federated academic setting:</p>

<Table.Root>
	<Table.Header>
		<Table.Row>
			<Table.Head class="w-24">Tier</Table.Head>
			<Table.Head>What it is</Table.Head>
			<Table.Head class="w-52">Registered?</Table.Head>
		</Table.Row>
	</Table.Header>
	<Table.Body>
		<Table.Row>
			<Table.Cell class="font-semibold">Bronze</Table.Cell>
			<Table.Cell>Raw dumps, external APIs, source files</Table.Cell>
			<Table.Cell>No — referenced as source URLs only</Table.Cell>
		</Table.Row>
		<Table.Row>
			<Table.Cell class="font-semibold">Silver</Table.Cell>
			<Table.Cell>Standardized, entity-mapped, ready for cross-group use</Table.Cell>
			<Table.Cell>Yes</Table.Cell>
		</Table.Row>
		<Table.Row>
			<Table.Cell class="font-semibold">Gold</Table.Cell>
			<Table.Cell>Derived outputs — embeddings, models, predictions</Table.Cell>
			<Table.Cell>Yes, with <code>derived_from: [...]</code></Table.Cell>
		</Table.Row>
	</Table.Body>
</Table.Root>

<p>
	Each group owns their Bronze → Silver pipeline. Silver is what gets registered. Gold is everything
	built on top of Silver, potentially by a completely different group.
</p>

<h2>Project boundaries</h2>

<p>
	<strong>complex-stories-dev</strong> is a pure SvelteKit frontend. The registry and instruments
	live in <strong>storywrangler</strong> (<code>packages/api/</code>). Complex Stories is a
	first-party consumer of storywrangler-api — it calls the same endpoints any external group would,
	with no special privileges.
</p>
