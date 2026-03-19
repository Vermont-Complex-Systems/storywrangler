<h1>Wikimedia pipeline</h1>

<p class="lead">
	A full walkthrough of the Wikimedia ngram dataset: from raw dump to Silver registration to
	live allotaxonometry queries on Complex Stories. Uses <code>parquet_hive</code> — the reference
	implementation for groups writing partitioned files to netfiles.
</p>

<p>This case study will cover the complete arc of a production dataset in the registry:</p>

<ul>
	<li>Fetching and parsing Wikimedia page-view dumps (Bronze)</li>
	<li>
		Normalising to a Hive-partitioned parquet layout — <code>date=YYYY-MM-DD/country=XX/</code>
		— and stamping entity mappings (Silver)
	</li>
	<li>
		Writing <code>submit.py</code> with <code>parquet_hive</code>: manually scanning partition
		keys and computing statistics, then calling <code>register()</code> with
		<code>entity_mapping</code> and <code>endpoint_schemas</code>
	</li>
	<li>Querying the dataset live through the allotaxonometer on Complex Stories</li>
</ul>

<p>
	<em>Coming soon.</em> The Wikimedia pipeline is the reference implementation for the platform.
	Documentation will be written alongside the pipeline as it stabilises.
</p>
