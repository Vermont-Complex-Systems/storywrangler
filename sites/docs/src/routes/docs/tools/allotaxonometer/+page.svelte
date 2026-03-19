<h1>Allotaxonometry</h1>

<p class="lead">
	A suite of instruments for comparing two ranked lists — word frequencies, name counts, topic
	distributions — across time or context. Includes the allotaxonometer and wordshift.
</p>

<h2>Allotaxonometer</h2>

<p>
	The allotaxonometer measures rank-turbulence divergence between two ranked lists and produces
	a contribution breakdown: which elements shifted the most, and in which direction. The visual
	output is an allotaxonograph — a mirror plot showing the top drivers of the divergence.
</p>

<p>
	The core calculations are implemented in
	<a href="https://github.com/Vermont-Complex-Systems/allotaxonometer-core">allotaxonometer-core</a>,
	a Rust crate that handles the rank-turbulence divergence computation. The web instruments call
	this crate via WebAssembly.
</p>

<h2>Wordshift</h2>

<p>
	Wordshift decomposes the difference in average word score (sentiment, frequency, or any
	per-word signal) between two text collections into word-level contributions — which words
	drove the change, through increased or decreased usage, and whether they pulled the score up
	or down.
</p>

<h2>Dataset requirements</h2>

<p>
	To be queryable by allotaxonometry instruments, a dataset must declare a compatible
	<code>endpoint_schemas</code> entry. At minimum:
</p>

<ul>
	<li><code>type: "types-counts"</code></li>
	<li>A <code>time_dimension</code> along which two slices can be selected</li>
	<li>Optionally, <code>entity_dimensions</code> for filtering by country, researcher, etc.</li>
</ul>

<h2>Status</h2>

<p>
	In development at the Vermont Complex Systems Institute. Documentation will expand as the
	instruments stabilise.
</p>
