<script lang="ts">
	import { Snippet } from '$lib/components/ui/snippet';
	import PipelineDiagram from '$lib/components/PipelineDiagram.svelte';
</script>

<h1>Introduction</h1>

<p>
	Storywrangler is a research data registry for computational social science, built for a federated
	ecosystem of academic groups.
</p>

<p>
	Research groups register their datasets here — where they live, who owns them, what they contain,
	what they were derived from. The platform validates canonical identifiers at registration, tracks
	lineage across groups, and serves instruments (allotaxonometer, wordshift) to consumers like
	<a href="https://complexstories.uvm.edu">Complex Stories</a>.
</p>

<PipelineDiagram />

<h2>What the registry is</h2>

<p>
	The registry is a <strong>metadata catalog</strong> — it stores pointers to data, not data itself.
	Data stays on institutionally-managed storage. If the API is unreachable, groups can still query
	their data directly via DuckDB + <code>data_location</code>.
</p>

<h2>What registering gives you</h2>

<p>
	Short version below. For the full argument — including why the right framing is attribution
	infrastructure, not governance — see <a href="/docs/why-register">Why register?</a>
</p>

<ul>
	<li>
		<strong>Lineage</strong> — <code>derived_from</code> links outputs to inputs across groups; the
		registry can tell you what breaks if a Silver dataset changes schema
	</li>
	<li>
		<strong>Discoverability</strong> — other groups can find and build on your data without
		coordinating directly with you
	</li>
	<li>
		<strong>Ownership and succession</strong> — when a student leaves, the institute can take
		custody and hand off to the next person; datasets don't disappear with their author
	</li>
	<li>
		<strong>Attribution</strong> — every <code>derived_from</code> reference is a machine-readable
		citation; groups building on your data appear in your impact record
	</li>
	<li>
		<strong>Instrument access</strong> — datasets with compatible <code>endpoint_schemas</code>
		become queryable by instruments developed at the Vermont Complex Systems Institute, including
		the allotaxonometer and wordshift. These tools work against any conforming dataset without
		custom integration.
	</li>
	<li>
		<strong>Fine-grained access control</strong> — sensitive datasets can be shared selectively.
		Specific partner groups or collaborators can be granted access at different granularities:
		aggregate query results only, a filtered row subset, or full direct access. No dataset needs
		to be all-or-nothing.
	</li>
</ul>

<h2>Quick start</h2>

<Snippet text="uv add storywrangler-sdk" />

<p>
	Then write a <code>submit.py</code> — typically 50–100 lines. See
	<a href="/docs/register">Registering a dataset</a> for examples. Registration is an upsert — safe
	to re-run as data or metadata changes.
</p>

<h2>Data tiers</h2>

<p>
	The registry uses the medallion architecture from industry data platforms, adapted for a federated
	academic setting:
</p>

<table>
	<thead>
		<tr>
			<th>Tier</th>
			<th>What it is</th>
			<th>Registered?</th>
		</tr>
	</thead>
	<tbody>
		<tr>
			<td>Bronze</td>
			<td>Raw dumps, external source files</td>
			<td>No (referenced as source URLs)</td>
		</tr>
		<tr>
			<td>Silver</td>
			<td>Standardized, entity-mapped, registered</td>
			<td>Yes</td>
		</tr>
		<tr>
			<td>Gold</td>
			<td>Derived outputs — embeddings, models, predictions</td>
			<td>Yes, with <code>derived_from</code></td>
		</tr>
	</tbody>
</table>

<p>
	Each group owns their Bronze → Silver pipeline. Silver is what gets registered. Gold is everything
	built on top of Silver, potentially by a completely different group.
</p>

<h2>Standards compliance</h2>

<p>
	This platform follows the
	<a href="/docs/specification">Storywrangler Specification v0.0.1</a>. Identifiers are validated
	against the specification at registration time. Malformed identifiers are rejected before the
	dataset reaches Silver.
</p>
