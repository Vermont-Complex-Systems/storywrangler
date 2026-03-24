
<h1>Registering a dataset</h1>


<h2>Specs-free registration</h2>

<p>
	The simplest use case of registering your dataset is to get access to VCSI instruments, such as the <a href="/docs/tools/allotaxonometer">alloxonometer</a>, which can then be served anywhere on the web. In this case, your submitted dataset must fullfil the  instrument requirements you want to access (e.g. allotaxonometers requires a <code>types-counts</code> endpoint schema, see instrument page). It should also be part of an accepted domain space. By default, endpoints can go in the <code>guest</code> domain space, but specifying a domain space help cluster together related endpoints and increase discovery. If you want to submit a new domain space, you can submit a PR (TODO: add template).
</p>

<p>
	If you simply want to make a programmatic use of our instruments, such as integrating the instruments in your codebase, you might be interested in running locally the equivalent packages we use on the platform (calling directly the Rust-backed <code>py-allotax</code> module, for instance). 
</p>

<h3>The submit.py structure</h3>

<p>
	A <code>submit.py</code> is a single call to <code>register()</code> with a Python dict. The dict has five logical groups of fields:
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

For the instrument part, we have the following fields:

<ul>
	<li>
		<code>filter_dimensions</code>
	</li>
	<li>
		<strong>Endpoint schema</strong> — declares what query types the dataset supports, so
		instruments can determine compatibility without hardcoding dataset-specific logic.
	</li>
</ul>

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

<h2>Specification-free registration, with accompanying endpoints</h2>

<!-- Pattern 1 — opaque local keys (explicit entity rows required):

The column holds values that have no intrinsic meaning outside the dataset — state abbreviations, snake_case names, internal IDs. The platform has no way to know what "VT" or "town_of_burlington" maps to without being told. You have to supply entity rows:


"entity_mapping": {"local_id_column": "state", "entity_namespace": "wikidata"},
"entities": [
    {"local_id": "VT", "entity_id": "wikidata:Q16551", "entity_name": "Vermont"},
    ...
] 
	
When a query comes in for wikidata:Q16551, resolve_entity looks it up in the registry_entity_mappings table and gets back local_id = "VT" to use in the SQL WHERE state = ?.

Pattern 2 — global-identifier column (no entity rows needed):

The column already holds values from a recognized namespace — specifically full URLs like https://openalex.org/A5002034958. There's a bijection between the canonical form (openalex:A5002034958) and what's stored in the column. The platform just needs to know the namespace to compute that mapping.

This is the _derive_local_id fallback added to resolve_entity in query_utils.py:


_NAMESPACE_URL_PREFIX = {
    "openalex": "https://openalex.org/",
    "doi":      "https://doi.org/",
}

# When no entity row is found, look up entity_namespace from the registry entry
# and derive the stored value directly:
# openalex:A5002034958  →  https://openalex.org/A5002034958

-->


<p>
	To serve any dataset to users, say you want the <code>ngrams</code> datasets to be available to all, an endpoint ought to be added to the platform. The process is straightforward (TODO: add template to do it), but that will need to go through a PR as we need to review it. 
</p>

<h2>Registering interoperable datasets</h2>

<p>
	Now, if you are interested in making your datasets interoperable with  the rest of the data on the platform, you will need to provide the mapping between your local identifiers and the global identifier namespace available on the platform and specified by the <a href="/docs/specification">Storywrangler-Specification</a>. We provide an SDK to validate the specification, facilitating the submission process. In this case, malformed identifiers are rejected locally before anything reaches the server.
</p>

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


<h3>The submit.py structure additional fields</h3>

<ul>
	<li>
		<strong>Entity mapping</strong> — maps dataset-local column values to canonical IDs
		(e.g. <code>wikidata:Q30</code>). 
	</li>
</ul>



<h2>Case studies</h2>

<p>
	Two reference pipelines show what a complete <code>submit.py</code> looks like in practice, each with a different storage format:
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
