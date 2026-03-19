<script lang="ts">
	import * as Code from '$lib/components/ui/code';
	import * as Table from '$lib/components/ui/table';

	const endpointExample = `{
    "type": "types-counts",
    "time_dimension": "date",
    "entity_dimensions": ["country"]
}`;
</script>

<h1>Field reference</h1>

<p>All fields accepted by <code>register()</code>.</p>

<Table.Root>
	<Table.Header>
		<Table.Row>
			<Table.Head class="w-44">Field</Table.Head>
			<Table.Head class="w-20">Type</Table.Head>
			<Table.Head class="w-14">Req</Table.Head>
			<Table.Head>Description</Table.Head>
		</Table.Row>
	</Table.Header>
	<Table.Body>
		<Table.Row>
			<Table.Cell><code>catalog</code></Table.Cell>
			<Table.Cell>string</Table.Cell>
			<Table.Cell></Table.Cell>
			<Table.Cell>Producer identity — organisation or group registering this dataset. Defaults to <code>"vcsi"</code>. Enables future 3-level namespace <code>catalog.domain.dataset_id</code>.</Table.Cell>
		</Table.Row>
		<Table.Row>
			<Table.Cell><code>domain</code></Table.Cell>
			<Table.Cell>string</Table.Cell>
			<Table.Cell>✓</Table.Cell>
			<Table.Cell>Namespace group (<code>wikimedia</code>, <code>babynames</code>, …)</Table.Cell>
		</Table.Row>
		<Table.Row>
			<Table.Cell><code>dataset_id</code></Table.Cell>
			<Table.Cell>string</Table.Cell>
			<Table.Cell>✓</Table.Cell>
			<Table.Cell>Identifier within the domain</Table.Cell>
		</Table.Row>
		<Table.Row>
			<Table.Cell><code>data_location</code></Table.Cell>
			<Table.Cell>string</Table.Cell>
			<Table.Cell>✓</Table.Cell>
			<Table.Cell>Absolute path or connection string to data on institutional storage</Table.Cell>
		</Table.Row>
		<Table.Row>
			<Table.Cell><code>data_format</code></Table.Cell>
			<Table.Cell>string</Table.Cell>
			<Table.Cell>✓</Table.Cell>
			<Table.Cell><code>parquet_hive</code> · <code>ducklake</code> · <code>duckdb</code></Table.Cell>
		</Table.Row>
		<Table.Row>
			<Table.Cell><code>format_config</code></Table.Cell>
			<Table.Cell>object</Table.Cell>
			<Table.Cell></Table.Cell>
			<Table.Cell>
				Storage-format-specific metadata. Sub-fields:
				<code>data_schema</code> (<code>{'{col: {type, description}}'}</code>),
				<code>tables_metadata</code> (table name → file path list),
				<code>ducklake_data_path</code> (ducklake only),
				<code>partitioning</code> (partition scheme and availability).
			</Table.Cell>
		</Table.Row>
		<Table.Row>
			<Table.Cell><code>entity_mapping</code></Table.Cell>
			<Table.Cell>object</Table.Cell>
			<Table.Cell></Table.Cell>
			<Table.Cell>
				Schema declaration for entity ID resolution: <code>{'{entity_type, local_id_column}'}</code>.
				Omit for datasets with no cross-group filter dimensions.
			</Table.Cell>
		</Table.Row>
		<Table.Row>
			<Table.Cell><code>entities</code></Table.Cell>
			<Table.Cell>array</Table.Cell>
			<Table.Cell></Table.Cell>
			<Table.Cell>
				Entity mapping rows to upsert: <code>{`[{local_id, entity_id, entity_name, entity_ids?}]`}</code>.
				Maps dataset-local column values to canonical identifiers. Required when
				<code>entity_mapping</code> is set.
			</Table.Cell>
		</Table.Row>
		<Table.Row>
			<Table.Cell><code>sources</code></Table.Cell>
			<Table.Cell>object</Table.Cell>
			<Table.Cell></Table.Cell>
			<Table.Cell>Raw data provenance keyed by dimension: <code>{`{dim: {name: url | url[]}}`}</code></Table.Cell>
		</Table.Row>
		<Table.Row>
			<Table.Cell><code>endpoint_schemas</code></Table.Cell>
			<Table.Cell>array</Table.Cell>
			<Table.Cell></Table.Cell>
			<Table.Cell>Query types this dataset supports (instrument contract)</Table.Cell>
		</Table.Row>
		<Table.Row>
			<Table.Cell><code>ownership</code></Table.Cell>
			<Table.Cell>object</Table.Cell>
			<Table.Cell></Table.Cell>
			<Table.Cell>
				Ownership and succession: <code>owner_group</code> (lab/group),
				<code>contact</code> (email or handle),
				<code>status</code> (<code>active</code> · <code>needs_successor</code> · <code>archived</code>),
				<code>storage_risk</code> (<code>managed</code> · <code>institutional</code> · <code>cloud</code> · <code>personal</code>).
			</Table.Cell>
		</Table.Row>
		<Table.Row>
			<Table.Cell><code>lineage</code></Table.Cell>
			<Table.Cell>object</Table.Cell>
			<Table.Cell></Table.Cell>
			<Table.Cell>
				<code>derived_from</code> (<code>["domain/dataset_id"]</code> — upstream datasets),
				<code>produced_by</code> (git SHA, script path, or Dagster asset key),
				<code>consumers</code> (opt-in list of downstream users for blast-radius estimation).
			</Table.Cell>
		</Table.Row>
	</Table.Body>
</Table.Root>

<h2>Entity types</h2>

<p>
	<code>entity_mapping.entity_type</code> is the <strong>identifier system</strong> used for
	the entity IDs in this dataset — not a semantic category. The SDK validates each
	<code>entity_id</code> format against the declared type using the
	<a href="https://github.com/vermont-complex-systems/Storywrangler-Specification"
		>Storywrangler Specification</a
	>.
</p>

<Table.Root>
	<Table.Header>
		<Table.Row>
			<Table.Head class="w-36">Value</Table.Head>
			<Table.Head class="w-44">ID format</Table.Head>
			<Table.Head>Use for</Table.Head>
		</Table.Row>
	</Table.Header>
	<Table.Body>
		<Table.Row>
			<Table.Cell><code>wikidata</code></Table.Cell>
			<Table.Cell><code>wikidata:Q…</code></Table.Cell>
			<Table.Cell>Countries, regions, concepts, events — anything with a Wikidata entry</Table.Cell>
		</Table.Row>
		<Table.Row>
			<Table.Cell><code>orcid</code></Table.Cell>
			<Table.Cell><code>orcid:0000-…</code></Table.Cell>
			<Table.Cell>Academic authors and researchers</Table.Cell>
		</Table.Row>
		<Table.Row>
			<Table.Cell><code>ror</code></Table.Cell>
			<Table.Cell><code>ror:…</code></Table.Cell>
			<Table.Cell>Research institutions</Table.Cell>
		</Table.Row>
		<Table.Row>
			<Table.Cell><code>doi</code></Table.Cell>
			<Table.Cell><code>doi:10.…</code></Table.Cell>
			<Table.Cell>Published works with DOIs</Table.Cell>
		</Table.Row>
		<Table.Row>
			<Table.Cell><code>local</code></Table.Cell>
			<Table.Cell><code>local:corpus:id</code></Table.Cell>
			<Table.Cell>Entities with no standard identifier; document why</Table.Cell>
		</Table.Row>
	</Table.Body>
</Table.Root>

<h2>Endpoint schemas</h2>

<p>
	The <code>endpoint_schemas</code> field declares what query types a dataset supports — the contract
	between the catalog and instruments (allotaxonometer, wordshift, etc.). An instrument checks this
	field at query time to determine compatibility.
</p>

<Code.Root code={endpointExample} lang="json">
	<Code.CopyButton />
</Code.Root>
