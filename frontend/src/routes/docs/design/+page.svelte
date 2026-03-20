<script lang="ts">
	import * as Table from '$lib/components/ui/table';
</script>

<h1>Design & architecture</h1>

<p>
	Key design decisions behind the platform. This section grows as decisions are made and
	stabilized.
</p>

<h2>External vs. managed datasets</h2>

<p>
	By default, data stays with the submitter. The platform stores metadata only — a pointer to
	wherever the data lives on institutional storage. This preserves data sovereignty and avoids
	duplicating TB-scale datasets.
</p>

<p>
	<strong>Managed datasets</strong> are the opt-in alternative. When a student leaves without a
	successor, or when a dataset is small and stable enough, VCSI can take custody and move the
	data to platform-controlled storage.
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
	<code>data_location</code>), <strong>pipeline adoption</strong> (clone the source repo,
	schedule via Dagster), or <strong>PostgreSQL ingest</strong> (for very small, highly-queried
	datasets where DuckDB can still query via the PostgreSQL scanner extension). For now all
	datasets are expected to be external.
</p>
