<script lang="ts">
	import * as Code from '$lib/components/ui/code';

	const latestCode = `DatasetCreate(
    domain="babynames",
    dataset_id="ngrams",
    version="latest",   # default — the mutable development slot
    ...
)`;

	const snapshotCode = `# Create an immutable snapshot
DatasetCreate(
    domain="babynames",
    dataset_id="ngrams",
    version="1.0.0",
    ...
)`;

	const schemaVersionCode = `# schema_version is auto-populated — do not set manually
DatasetCreate(
    ...
    # schema_version="1.0.0"  ← injected from importlib.metadata
)`;

	const listVersionsBash = `GET /registry/babynames/ngrams/versions`;

	const listVersionsJson = `{
  "domain": "babynames",
  "dataset_id": "ngrams",
  "versions": [
    { "version": "latest",  "schema_version": "1.0.0", "created_at": "2025-03-01T..." },
    { "version": "1.1.0",   "schema_version": "1.0.0", "created_at": "2025-02-01T..." },
    { "version": "1.0.0",   "schema_version": "1.0.0", "created_at": "2025-01-01T..." }
  ],
  "total": 3
}`;

	const getVersionBash = `GET /registry/babynames/ngrams?version=1.0.0`;

	const platformVersionBash = `GET /version`;

	const platformVersionJson = `{
  "api": "1.0.0",
  "schemas": "1.0.0",
  "duckdb": "1.1.3",
  "allotax": "0.3.1"
}`;

	const archivalCode = `DatasetCreate(
    domain="babynames",
    dataset_id="ngrams",
    version="1.0.0",
    lineage=LineageConfig(
        repo="https://github.com/Vermont-Complex-Systems/babynames",
        archival_doi="10.7910/DVN/XXXXXX",   # set after archiving
    ),
    ...
)`;
</script>

<h1>Versioning</h1>

<p>
	Storywrangler uses two versioning layers with different purposes. Understanding when to use each
	prevents both over-engineering (archiving every pipeline run) and under-engineering (losing
	reproducibility when it matters).
</p>

<h2>The two-layer model</h2>

<p>Registration is designed for <strong>daily use</strong> — re-register freely whenever your pipeline runs. Versioned snapshots and archival are opt-in steps you take when reproducibility or citation is needed.</p>

<div class="not-prose my-6 rounded-lg border border-border bg-card p-5 font-mono text-xs leading-relaxed text-muted-foreground">
	<p><span class="text-foreground font-semibold">Dataset pipeline</span></p>
	<p class="pl-2">→ parquet files land on disk</p>
	<p class="pl-2">→ <code class="text-foreground">POST /register</code> ← frictionless, fast iteration</p>
	<p class="mt-3 pl-4 text-[10px]">↓ when the interface contract changes</p>
	<p class="mt-3"><span class="text-foreground font-semibold">Registry snapshot</span> <span class="text-orange-600 dark:text-orange-400">(version="1.0.0")</span></p>
	<p class="pl-2">→ immutable entry in the platform registry</p>
	<p class="pl-2">→ reproducible queries against this interface contract</p>
	<p class="mt-3 pl-4 text-[10px]">↓ when long-term preservation is needed</p>
	<p class="mt-3"><span class="text-foreground font-semibold">Dataverse / archival</span></p>
	<p class="pl-2">→ DOI-bearing, externally citable</p>
	<p class="pl-2">→ <code class="text-foreground">lineage.archival_doi</code> recorded in the registry entry</p>
</div>

<h2>The <code>version</code> field</h2>

<p>
	Every <code>DatasetCreate</code> payload carries a <code>version</code> field that defaults to
	<code>"latest"</code>:
</p>

<Code.Root lang="python" code={latestCode}>
	<Code.CopyButton />
</Code.Root>

<h3>The mutable slot — <code>"latest"</code></h3>

<p>
	Re-registering with <code>version="latest"</code> always overwrites the existing entry. This is
	the default and requires no thought during active development. Pipeline re-runs, metadata
	corrections, and coverage updates all use this slot.
</p>

<h3>Semver strings — immutable snapshots</h3>

<p>
	Once you bump to a named version, that entry is <strong>locked</strong>. Re-registering the same
	version string returns <code>409 Conflict</code>.
</p>

<Code.Root lang="python" code={snapshotCode}>
	<Code.CopyButton />
</Code.Root>

<p>
	The platform follows <a href="https://semver.org/">Semantic Versioning</a>. For datasets, the
	three increments map to interface changes rather than code changes:
</p>

<table>
	<thead>
		<tr>
			<th>Increment</th>
			<th>Trigger</th>
		</tr>
	</thead>
	<tbody>
		<tr>
			<td><strong>PATCH</strong> <code>1.0.x</code></td>
			<td>Bug fix in processing — same schema, corrected values</td>
		</tr>
		<tr>
			<td><strong>MINOR</strong> <code>1.x.0</code></td>
			<td>New data added — new time range, new entities; old queries still work</td>
		</tr>
		<tr>
			<td><strong>MAJOR</strong> <code>x.0.0</code></td>
			<td>Breaking interface change — column renamed, <code>endpoint_schema</code> or <code>transform</code> axes changed</td>
		</tr>
	</tbody>
</table>

<p>
	A routine pipeline re-run that only adds new rows to existing parquet files does <strong>not</strong>
	require a version bump. The contract (schema, query axes, data location) is unchanged.
</p>

<h2>The <code>schema_version</code> field</h2>

<p>
	Every registration automatically records which version of <code>storywrangler-schemas</code> was
	in effect. This is the software–data version coupling recommended by the
	<a href="https://zenodo.org/records/13743876">Research Data Alliance versioning guidelines</a>:
	it records which registration contract was in effect so consumers know whether newer fields are
	available.
</p>

<Code.Root lang="python" code={schemaVersionCode}>
	<Code.CopyButton />
</Code.Root>

<h2>Inspecting versions</h2>

<h3>List all versions for a dataset</h3>

<Code.Root lang="bash" code={listVersionsBash} hideLines={true}>
	<Code.CopyButton />
</Code.Root>

<Code.Root lang="json" code={listVersionsJson} />

<h3>Retrieve a specific version</h3>

<Code.Root lang="bash" code={getVersionBash} hideLines={true}>
	<Code.CopyButton />
</Code.Root>

<p>Omitting <code>?version</code> always returns the most recently registered entry.</p>

<h2>Platform component versions</h2>

<p>
	The <code>/version</code> endpoint reports the runtime software stack:
</p>

<Code.Root lang="bash" code={platformVersionBash} hideLines={true}>
	<Code.CopyButton />
</Code.Root>

<Code.Root lang="json" code={platformVersionJson} />

<p>
	When using the allotaxonometer, the response <code>meta</code> block also includes
	<code>dataset_version</code> and <code>allotax_version</code> — so any result can be traced back
	to the exact data contract and computation engine that produced it.
</p>

<h2>Archiving to Dataverse</h2>

<p>
	When a versioned snapshot is ready for long-term preservation and citation, archive it in
	<a href="https://dataverse.harvard.edu/">Harvard Dataverse</a> (or any DOI-issuing repository)
	and record the DOI in <code>lineage.archival_doi</code>:
</p>

<Code.Root lang="python" code={archivalCode}>
	<Code.CopyButton />
</Code.Root>

<p>
	The presence of <code>archival_doi</code> signals that this version's data is durably stored
	externally and is citable in publications. The registry entry remains the lightweight interface
	record; Dataverse holds the canonical, immutable data copy.
</p>
