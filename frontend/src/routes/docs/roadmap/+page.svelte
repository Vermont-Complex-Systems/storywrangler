<h1>Roadmap</h1>

<p class="lead">
	What the registry does today, what is missing, and what is planned. This page exists so
	potential adopters can see the gaps honestly rather than discovering them after onboarding.
</p>

<h2>Current state</h2>

<p>
	The registry today is a metadata catalog: it stores pointers to datasets, validates their
	format at registration, and serves them to instruments. The core read/write path is
	operational. What is missing is mostly the connective tissue — lineage, ownership, resilience,
	and enforcement.
</p>

<table>
	<thead>
		<tr>
			<th>Area</th>
			<th>Today</th>
			<th>Gap</th>
			<th>Priority</th>
		</tr>
	</thead>
	<tbody>
		<tr>
			<td>Dataset registration</td>
			<td>Working</td>
			<td>—</td>
			<td>—</td>
		</tr>
		<tr>
			<td>Lineage</td>
			<td>Field exists in schema</td>
			<td>Not enforced; no traversal API</td>
			<td>P2</td>
		</tr>
		<tr>
			<td>Ownership &amp; succession</td>
			<td><code>ownership</code> field in schema</td>
			<td>Transfer endpoint and policy not yet implemented</td>
			<td>P1</td>
		</tr>
		<tr>
			<td>Identifier enforcement</td>
			<td>Format accepted as string</td>
			<td>Malformed IDs reach Silver undetected</td>
			<td>P1 (via SDK)</td>
		</tr>
		<tr>
			<td>Endpoint schema contract</td>
			<td>Field populated</td>
			<td>Not validated at query time</td>
			<td>P2</td>
		</tr>
		<tr>
			<td>Catalog resilience</td>
			<td>PostgreSQL only</td>
			<td>Catalog unreachable when API is down</td>
			<td>P3</td>
		</tr>
		<tr>
			<td>Column descriptions</td>
			<td><code>&#123;col: type&#125;</code> only</td>
			<td>No human-readable field documentation</td>
			<td>P4</td>
		</tr>
		<tr>
			<td>Gold layer</td>
			<td>Not registered</td>
			<td>Derived artifacts and ML outputs are invisible</td>
			<td>P5</td>
		</tr>
	</tbody>
</table>

<h2>P1 — Ownership and succession</h2>

<p>
	When a student leaves, their dataset registration persists but institutional knowledge is lost.
	There is no mechanism for the institute to take custody and hand off to a new maintainer.
</p>

<p>
	The <code>ownership</code> field is now part of the <code>Dataset</code> model and registration
	payload. Four sub-fields, submitted as <code>{'"ownership": {...}'}</code>:
</p>

<ul>
	<li>
		<code>owner_group</code> — lab or research group (<code>"compethicslab"</code>,
		<code>"VCSI"</code>)
	</li>
	<li><code>contact</code> — email or GitHub handle of the current maintainer</li>
	<li>
		<code>status</code> — <code>active</code> | <code>needs_successor</code> |
		<code>archived</code>
	</li>
	<li>
		<code>storage_risk</code> — durability signal:
		<code>managed</code> &gt; <code>institutional</code> &gt; <code>cloud</code> &gt;
		<code>personal</code>. Datasets on <code>personal</code> or <code>cloud</code> storage
		automatically flag <code>needs_successor</code>.
	</li>
</ul>

<p>
	Paired with a <code>PATCH /admin/registry/{'{domain}'}/{'{dataset_id}'}/transfer</code> endpoint
	to change ownership. This is also the on-ramp for promoting a dataset to managed hosting when a
	student leaves without handing off.
</p>

<h2>P2 — Lineage</h2>

<p>
	The registry knows where data lives but not where it came from or what depends on it. A schema
	change in <code>wikimedia/ngrams</code> currently has unknown blast radius.
</p>

<p>Three fields to add:</p>

<ul>
	<li>
		<code>derived_from</code> — list of <code>domain/dataset_id</code> references this dataset
		was built from (<code>["wikimedia/ngrams", "wikimedia/revisions"]</code>)
	</li>
	<li>
		<code>produced_by</code> — pipeline or script that generated this dataset (git SHA, Dagster
		asset key, or script path)
	</li>
	<li>
		<code>consumers</code> — opt-in list of known downstream users (stories, tools, partner
		groups) that would otherwise be invisible. Dataset-to-dataset downstream lineage is
		computable by inverting <code>derived_from</code>; <code>consumers</code> covers what that
		query cannot see.
	</li>
</ul>

<p>
	Paired with <code>GET /registry/{'{domain}'}/{'{dataset_id}'}/dependents</code> — lists all
	datasets that declare <code>derived_from</code> containing this one. Enables impact analysis
	before schema changes without a graph database: simple list traversal is sufficient at this
	scale.
</p>

<h2>P3 — Catalog resilience</h2>

<p>
	If PostgreSQL is down, <code>GET /registry/</code> is unreachable. Groups lose discoverability
	even though their data is physically accessible.
</p>

<p>
	Proposed fix: a scheduled export job that writes the full registry to a parquet snapshot on
	netfiles:
</p>

<pre
	class="not-prose bg-muted overflow-x-auto rounded-lg p-4 font-mono text-sm">/netfiles/compethicslab/registry/
  snapshots/date=YYYY-MM-DD/registry.parquet
  latest.parquet</pre>

<p>Groups can then query the catalog directly via DuckDB without going through the API.</p>

<h2>P4 — Column descriptions</h2>

<p>
	<code>data_schema</code> today is <code>&#123;column: type&#125;</code> only. No descriptions, no
	sensitivity flags. This limits discoverability for researchers who don't know what
	<code>rank</code> or <code>cnt</code> means in the ngrams schema.
</p>

<p>Proposed extension — backward compatible, old format detected and migrated on read:</p>

<pre class="not-prose bg-muted overflow-x-auto rounded-lg p-4 font-mono text-sm"
>&#123;
  "rank": &#123;"type": "BIGINT", "description": "Frequency rank of the n-gram on this date"&#125;,
  "cnt":  &#123;"type": "BIGINT", "description": "Raw occurrence count"&#125;,
  "freq": &#123;"type": "DOUBLE", "description": "Normalized frequency (cnt / total tokens)"&#125;
&#125;</pre>

<h2>P5 — Gold layer registration</h2>

<p>
	Derived datasets and ML artifacts are currently unregistered. There is no way to know which
	version of <code>wikimedia/ngrams</code> a given embedding was built from, or what stories
	depend on what Gold artifacts.
</p>

<p>
	No separate model registry is needed at this scale. Gold artifacts register via the same
	<code>submit.py</code> pattern, with <code>derived_from</code> pointing to their Silver inputs:
</p>

<table>
	<thead>
		<tr>
			<th>Asset</th>
			<th><code>data_format</code></th>
			<th><code>derived_from</code></th>
		</tr>
	</thead>
	<tbody>
		<tr>
			<td><code>wikimedia/article-embeddings</code></td>
			<td><code>parquet_hive</code></td>
			<td><code>["wikimedia/revisions"]</code></td>
		</tr>
		<tr>
			<td><code>wikimedia/topic-classifier</code></td>
			<td><code>duckdb</code></td>
			<td><code>["wikimedia/article-embeddings"]</code></td>
		</tr>
		<tr>
			<td><code>wikimedia/ngram-topics</code></td>
			<td><code>parquet_hive</code></td>
			<td><code>["wikimedia/ngrams", "wikimedia/topic-classifier"]</code></td>
		</tr>
	</tbody>
</table>

<p>
	A trained model is just another registered dataset whose <code>data_location</code> points to
	model weights on netfiles. If model versioning becomes critical, that is when to reconsider.
</p>

<h2>Open questions</h2>

<p>
	These are unresolved policy questions, not technical gaps. Documenting them here so
	collaborators can see what is still being decided.
</p>

<ul>
	<li>
		<strong>Should stories be registered assets?</strong> A story consuming
		<code>wikimedia/ngrams</code> is a downstream dependency. Tracking it would complete the
		lineage picture. But stories are frontend code, not data — the boundary is unclear.
	</li>
	<li>
		<strong>Storage class enforcement?</strong> Should the platform hard-reject registration of
		<code>personal</code> storage, or only warn? Hard enforcement reduces friction from bad
		registrations; soft warning may be ignored.
	</li>
	<li>
		<strong>Spec validation strictness.</strong> Format validation (regex + checksum) should be a
		hard reject at registration. Existence checks (live ORCID registry, Wikidata SPARQL) are
		expensive and should be warnings only. The spec already makes this distinction
		(<code>MUST</code> vs <code>SHOULD</code>).
	</li>
	<li>
		<strong>Who governs the registry?</strong> The succession mechanism will exist once P1 lands,
		but the policy is unresolved: who approves new registrations, holds admin access, and can
		archive or transfer a dataset when a student leaves without handing off? This needs a named
		role before external groups onboard.
	</li>
	<li>
		<strong>PII and data sensitivity.</strong> <code>storage_risk</code> covers durability but
		not sensitivity. Some datasets contain or are derived from identified individuals. Does the
		registry need a <code>sensitivity</code> field? Who determines classification, and does it
		gate access to <code>data_location</code>?
	</li>
</ul>
