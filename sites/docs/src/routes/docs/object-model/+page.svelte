<script lang="ts">
	import * as Table from '$lib/components/ui/table';

	const hierarchy = `Registry
└── Domain             wikimedia · babynames · open-academic-analytics
    └── Dataset        ngrams · ego-authors · coauthors
        ├── Schema     column definitions and types
        ├── Entities   dimension vocabularies (entity_mapping)
        └── Endpoints  instrument contracts (endpoint_schemas)`;
</script>

<h1>Object model</h1>

<p>
	The registry organises objects in a namespace hierarchy. Each level scopes the one below it.
	Today the hierarchy is two levels deep; a third catalog level is planned for multi-group
	deployments.
</p>

<pre class="not-prose bg-muted rounded-lg p-4 font-mono text-sm leading-relaxed overflow-auto">{hierarchy}</pre>

<h2>Namespace levels</h2>

<Table.Root>
	<Table.Header>
		<Table.Row>
			<Table.Head class="w-28">Level</Table.Head>
			<Table.Head class="w-20">Status</Table.Head>
			<Table.Head class="w-52">Example</Table.Head>
			<Table.Head>What it represents</Table.Head>
		</Table.Row>
	</Table.Header>
	<Table.Body>
		<Table.Row>
			<Table.Cell class="font-semibold">Catalog</Table.Cell>
			<Table.Cell><span class="text-amber-600 dark:text-amber-400 text-xs">partial</span></Table.Cell>
			<Table.Cell><code>vcsi</code></Table.Cell>
			<Table.Cell>
				Producer identity — which organisation or group registered this namespace. The
				<code>catalog</code> field exists and defaults to <code>"vcsi"</code>. Not yet part of
				the primary key; namespace isolation across groups deferred to a future migration.
			</Table.Cell>
		</Table.Row>
		<Table.Row>
			<Table.Cell class="font-semibold">Domain</Table.Cell>
			<Table.Cell><span class="text-green-600 dark:text-green-400 text-xs">active</span></Table.Cell>
			<Table.Cell><code>wikimedia</code>, <code>babynames</code></Table.Cell>
			<Table.Cell>
				Subject area or research project. Groups own a domain; all datasets under it share an
				access and governance boundary.
			</Table.Cell>
		</Table.Row>
		<Table.Row>
			<Table.Cell class="font-semibold">Dataset</Table.Cell>
			<Table.Cell><span class="text-green-600 dark:text-green-400 text-xs">active</span></Table.Cell>
			<Table.Cell><code>ngrams</code>, <code>ego-authors</code></Table.Cell>
			<Table.Cell>
				A single registered data asset. Addressed as <code>domain/dataset_id</code>. Carries
				schema, lineage, entity mappings, and endpoint contracts.
			</Table.Cell>
		</Table.Row>
	</Table.Body>
</Table.Root>

<h2>Inside a dataset</h2>

<p>
	Each dataset carries several sub-objects that together form its full contract with the platform.
</p>

<Table.Root>
	<Table.Header>
		<Table.Row>
			<Table.Head class="w-36">Object</Table.Head>
			<Table.Head class="w-40">Registry field</Table.Head>
			<Table.Head>Purpose</Table.Head>
		</Table.Row>
	</Table.Header>
	<Table.Body>
		<Table.Row>
			<Table.Cell class="font-semibold">Schema</Table.Cell>
			<Table.Cell><code>data_schema</code></Table.Cell>
			<Table.Cell>
				Column names, types, and descriptions. Enables other groups to understand and query the
				dataset without reading the source code.
			</Table.Cell>
		</Table.Row>
		<Table.Row>
			<Table.Cell class="font-semibold">Entities</Table.Cell>
			<Table.Cell><code>entity_mapping</code></Table.Cell>
			<Table.Cell>
				Dimension vocabulary for filter and group-by dimensions (countries, researchers, topics).
				Maps dataset-local column values to canonical identifiers from the Storywrangler
				Specification. Omit for datasets with no cross-group dimensions.
			</Table.Cell>
		</Table.Row>
		<Table.Row>
			<Table.Cell class="font-semibold">Endpoints</Table.Cell>
			<Table.Cell><code>endpoint_schemas</code></Table.Cell>
			<Table.Cell>
				Instrument contracts — which query types (<code>types-counts</code>, etc.) this dataset
				supports, and along which time and entity dimensions. Instruments check this field to
				determine compatibility at query time.
			</Table.Cell>
		</Table.Row>
		<Table.Row>
			<Table.Cell class="font-semibold">Lineage</Table.Cell>
			<Table.Cell><code>derived_from</code>, <code>produced_by</code>, <code>consumers</code></Table.Cell>
			<Table.Cell>
				Dependency graph edges. <code>derived_from</code> points to upstream datasets;
				<code>consumers</code> is an opt-in list of known downstream users. Together they enable
				blast-radius estimation when a schema changes.
			</Table.Cell>
		</Table.Row>
		<Table.Row>
			<Table.Cell class="font-semibold">Provenance</Table.Cell>
			<Table.Cell><code>sources</code></Table.Cell>
			<Table.Cell>
				Raw data origins — external URLs and snapshot dates. Not registered as datasets themselves
				(Bronze tier), but recorded here for reproducibility.
			</Table.Cell>
		</Table.Row>
		<Table.Row>
			<Table.Cell class="font-semibold">Ownership</Table.Cell>
			<Table.Cell><code>owner_group</code>, <code>contact</code>, <code>status</code>, <code>storage_risk</code></Table.Cell>
			<Table.Cell>
				Who is responsible, how to reach them, whether the dataset is active or needs a
				successor, and how durable the underlying storage is.
			</Table.Cell>
		</Table.Row>
	</Table.Body>
</Table.Root>

<p>
	See the <a href="/docs/reference">Field reference</a> for the full list of fields and their types.
</p>
