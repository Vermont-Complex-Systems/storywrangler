<h1>Why register?</h1>

<p class="lead">
	Registration is not a compliance checkbox. It is the citation infrastructure that lets a
	dataset survive its author.
</p>

<h2>The framing problem</h2>

<p>
	Academic groups don't think in terms of "data products," "upstream consumers," or "SLAs."
	Framing registration as governance overhead will be ignored. The right framing is
	<strong>attribution infrastructure</strong> — something academics already care about deeply.
</p>

<table>
	<thead>
		<tr>
			<th>Avoid saying</th>
			<th>Say instead</th>
		</tr>
	</thead>
	<tbody>
		<tr><td>Downstream consumers</td><td>Future collaborators</td></tr>
		<tr><td>Data governance</td><td>FAIR principles for your dataset</td></tr>
		<tr><td>Schema stability</td><td>Can someone reproduce your results in 5 years?</td></tr>
		<tr><td>Data contract</td><td>Your data surviving your PhD</td></tr>
		<tr><td>Lineage graph</td><td>The citation trail for your dataset</td></tr>
		<tr><td>Business-level aggregates</td><td>What goes in your methods section</td></tr>
	</tbody>
</table>

<h2>Your submit.py is a machine-readable methods section</h2>

<p>When you write a methods section you already describe:</p>

<ol>
	<li>Where the raw data came from → <code>sources</code> (URL + snapshot date + checksum)</li>
	<li>How you processed it → <code>produced_by</code> (git SHA of the code that ran)</li>
	<li>What derived variables you computed → <code>derived_from</code> (which Silver datasets you built on)</li>
</ol>

<p>
	Every <code>submit.py</code> automates what goes in the methods section. The payoff: a machine
	can traverse the full dependency graph and tell you in 2030 exactly which Wikipedia dump a
	2025 paper's topic classifications came from. That's reproducibility, not governance.
</p>

<h2>Registration = being cited</h2>

<p>
	When a CS or ML group registers Gold outputs with
	<code>derived_from: ["wikimedia/ngrams"]</code>, the registry records a machine-readable
	citation. The original team gains visibility into who is building on their work — evidence
	of impact for grant applications — without the two groups ever coordinating directly.
</p>

<p>
	Every <code>derived_from</code> reference is a citation. Groups building on your data appear
	in your impact record automatically.
</p>

<h2>The minimum ask</h2>

<p>Onboarding is three steps:</p>

<ol>
	<li><code>uv add storywrangler-sdk</code></li>
	<li>
		Write a <code>submit.py</code> — typically 50–100 lines. See
		<a href="/docs/register">Registering a dataset</a> for examples.
	</li>
	<li>
		Run <code>python submit.py</code> once per data update. Registration is an upsert — safe
		to re-run as data or metadata changes.
	</li>
</ol>

<p>
	The registry never touches the data. Groups keep full control of their pipelines and storage.
	The only thing that changes is that the dataset is now discoverable, citable, and succession-ready.
</p>

<h2>Beyond FAIR</h2>

<p>
	Funding agencies require FAIR-compliant data management plans. This platform satisfies FAIR,
	but FAIR is passive — it describes properties a dataset should have, not mechanisms to enforce
	them. What this platform adds:
</p>

<ul>
	<li>
		<strong>Enforcement at registration</strong> — canonical identifiers are validated by the
		SDK, not just recommended. A dataset with malformed ORCIDs is rejected before it reaches
		Silver.
	</li>
	<li>
		<strong>Provenance as a first-class field</strong> — <code>derived_from</code> and
		<code>produced_by</code> turn the methods section of a paper into a machine-readable
		dependency graph.
	</li>
	<li>
		<strong>Succession</strong> — ownership fields and a transfer endpoint mean a dataset can
		outlive the student who built it. FAIR says nothing about this.
	</li>
</ul>

<h2>The urgency</h2>

<p>
	The window to capture institutional knowledge is narrow. Every cohort that graduates takes
	with them the provenance of the datasets they built — which dump, which mapping, why that
	partition scheme. The registry is most valuable if populated <em>before</em> each departure,
	not after.
</p>
