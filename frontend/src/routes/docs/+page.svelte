<script lang="ts">
	import { Snippet } from '$lib/components/ui/snippet';
	import SimpleDiagram from '$lib/components/SimpleDiagram.svelte';
</script>

<h1>Introduction</h1>

<p>
	Storywrangler is a research data registry for computational social science, built for a federated
	ecosystem of academic groups. It is meant to reduce friction between all kinds of datasets and complex systems instruments developped at the <a href="https://vermontcomplexsystems.org/">Vermont Complex Systems Institute</a>. 
</p>


<SimpleDiagram />

<p>
	In this example, the submitter declare in the JSON body that the dataset conforms to the <code>types-counts</code> endpoint schema (see available <a href="/docs/reference#endpoint-schema">endpoint-schema</a>), with filterable columns <code>sex</code> and <code>country</code>. Upon registering, the platform will lookup the submitted dataset to the provided <code>data_location</code>, enforcing the contract. If accepted, the allotaxonometer instrument will just know how to work with it. The instrument is callable from <code>/storywrangler/allotax</code> endpoint and work out of the box.
</p>

<p>
	The registry offers a <a href="https://docs.databricks.com/aws/en/data-governance/">data governance</a> solution to challenges met in academia. As opposed to industry, academia is composed by research groups with full autonomy over their research methods and tools. Academia is also characterized by high turnover, where graduate students who develop tools and data pipeline come and go. This allows for creativity, but imped research groups ability to build reliable and maintainable data pipelines with interoperable set of tools.
</p>

<p>To solve this, the registry is encoding in its infrastructure the following:</p>

<ul>
	<li>
		<strong>Lineage</strong> — links outputs to inputs across groups; the registry can tell you what breaks if a Silver dataset changes schema
	</li>
	<li>
		<strong>Ownership and succession</strong> — when a student leaves, the institute can take
		custody and hand off to the next person; datasets don't disappear with their author
	</li>
	<li>
		<strong>Attribution</strong> — your <code>submit.py</code> is a machine-readable methods
		section. Every <code>derived_from</code> reference is a citation; groups building on your
		data appear in your impact record automatically, without either group coordinating directly
	</li>
	<li>
		<strong>Fine-grained access control</strong> — sensitive datasets can be shared selectively.
		Specific partner groups or collaborators can be granted access at different granularities:
		aggregate query results only, a filtered row subset, or full direct access. No dataset needs
		to be all-or-nothing.
	</li>
</ul>

<p>The registry is also geared to <strong>discoverability</strong> so that  other groups can find and build on your data without coordinating directly with you. </p>


<h2>How does it work?</h2>

<p>
	The registry is a <strong>metadata catalog</strong>, loosely inspired by things like the <a href="https://www.unitycatalog.io/">Unity Catalogs</a>. When registered as <a href="/docs/design">external datasets</a>, it simply stores pointers to data, not the data itself. That is, we build an API that keeps tracks of the whereabouts of the data - where they live, who owns them, what they contain, what they were derived from. If our API is unreachable, groups can still query their data directly.
</p>

<p>
	Every dataset is addressed as three-levle namespace; <code>catalog/domain/dataset_id</code> — e.g.
	<code>vcsi/wikimedia/ngrams</code> or <code>compstorylab/babynames/ngrams</code>. We can also can manage datasets, where we run and ensure data maintainability over long term, if necessary.
</p>


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
