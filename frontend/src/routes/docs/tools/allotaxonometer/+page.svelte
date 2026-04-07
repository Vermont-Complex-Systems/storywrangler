<h1>Allotaxonometry</h1>

<p>
	A suite of instruments for comparing two ranked lists — word frequencies, name counts, topic
	distributions — across time, place, or any declared dimension. Includes the allotaxonometer
	and wordshift.
</p>

<h2>Allotaxonometer</h2>

<p>
	The allotaxonometer measures rank-turbulence divergence (RTD) between two ranked lists and
	produces a contribution breakdown: which elements shifted the most, and in which direction.
	The visual output is an allotaxonograph — a mirror plot showing the top drivers of the
	divergence.
</p>

<p>
	The core calculations are implemented in
	<a href="https://github.com/Vermont-Complex-Systems/allotaxonometer-core">allotaxonometer-core</a>,
	a Rust crate that handles the RTD computation. The web instruments call this crate via
	WebAssembly.
</p>

<h2>Wordshift</h2>

<p>
	Wordshift decomposes the difference in average word score (sentiment, frequency, or any
	per-word signal) between two text collections into word-level contributions — which words
	drove the change, through increased or decreased usage, and whether they pulled the score up
	or down.
</p>
