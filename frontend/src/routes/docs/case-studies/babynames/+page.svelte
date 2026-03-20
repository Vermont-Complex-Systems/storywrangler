<h1>Babynames pipeline</h1>

<p class="lead">
	A full walkthrough of the babynames dataset: SSA and Québec birth records managed via a DuckLake
	catalog, registered as a Silver dataset with geographic entity mapping. Uses
	<code>ducklake</code> — the reference implementation for groups running their own lakehouse.
</p>

<p>This case study will cover:</p>

<ul>
	<li>
		Sourcing birth record data from the US Social Security Administration and the Québec civil
		registry (Bronze)
	</li>
	<li>
		Managing the dataset in DuckLake — how the catalog provides schema, file paths, and
		snapshots automatically, simplifying <code>submit.py</code>
	</li>
	<li>
		Writing <code>submit.py</code> with <code>ducklake</code>: what the adapter reads from the
		catalog versus what it declares manually, and how entity mapping works for a small geographic
		vocabulary (US + Québec)
	</li>
	<li>Contrast with <code>parquet_hive</code>: what the DuckLake adapter omits that a Hive adapter must do manually</li>
</ul>

<p>
	<em>Coming soon.</em> The babynames pipeline is the reference implementation for DuckLake-backed
	datasets. Documentation will be written alongside the pipeline as it stabilises.
</p>
