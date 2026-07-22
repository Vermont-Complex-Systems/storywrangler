<script lang="ts">
	import AllotaxDemo from '$lib/components/AllotaxDemo.svelte';
	import * as Code from '$lib/components/ui/code';

	const installCode = `npm install allotaxonometer-ui`;

	const usageCode = `<script>
  import { Dashboard, Allotaxonograph } from 'allotaxonometer-ui';

  // sys1, sys2: ranked [{ types, counts }] lists — e.g. the two systems from
  // GET /wikimedia/top-ngrams?dates=2024-11-06&dates2=2025-09-10
  const graph = new Allotaxonograph();
  graph.setAlpha(0.58);                        // rank-turbulence alpha
  graph.updateData(sys1, sys2, ['2024-11-06', '2025-09-10']);
<\/script>

<!-- graph.dat is reactive; it fills in once the WASM finishes computing -->
{#if graph.dat}
  <Dashboard
    dat={graph.dat}
    barData={graph.barData}
    balanceData={graph.balanceData}
    maxlog10={graph.maxlog10}
    divnorm={graph.rtd?.normalization ?? 1}
    title={['2024-11-06', '2025-09-10']}
    alpha={0.58}
  />
{/if}`;

	const wordshiftInstallCode = `pip install wordshift`;

	const wordshiftUsageCode = `import wordshift

# type2freq_1, type2freq_2: {word: frequency} maps, e.g. two days of ranked
# n-grams from GET /wikimedia/top-ngrams
result = wordshift.weighted_avg_shift(
    type2freq_1, type2freq_2,
    lexicon="labMT_English",   # bundled labMT happiness lexicon
    top_n=50,                  # cap the returned per-word entries
)

result["entries"][:5]          # the words that drove the sentiment change`;
</script>

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
	Below, it compares English Wikipedia (US) on two days of very different collective attention —
	<strong>election day</strong> (2024-11-06) and the <strong>Charlie Kirk</strong> assassination
	(2025-09-10) — computed live in your browser from the API's ranked n-grams. The diamond plots
	every n-gram by its rank on each day; the wordshift ranks the terms that drove the two days apart.
</p>

<AllotaxDemo />

<p>
	That figure is the <a href="https://www.npmjs.com/package/allotaxonometer-ui">allotaxonometer-ui</a>
	npm package — the same Svelte components you can drop into your own app. Install it:
</p>

<Code.Root code={installCode} lang="bash" hideLines={true}>
	<Code.CopyButton />
</Code.Root>

<p>
	Feed it two ranked type/count lists (for example the two systems returned by
	<code>GET /wikimedia/top-ngrams</code>), then render the dashboard:
</p>

<Code.Root code={usageCode} lang="svelte">
	<Code.CopyButton />
</Code.Root>

<p>
	The core rank-turbulence-divergence math lives in
	<a href="https://github.com/Vermont-Complex-Systems/allotaxonometer-core">allotaxonometer-core</a>,
	a Rust crate the package calls via WebAssembly.
</p>

<h2>Wordshift</h2>

<p>
	Wordshift decomposes the difference in average word score (sentiment, frequency, or any
	per-word signal) between two text collections into word-level contributions — which words
	drove the change, through increased or decreased usage, and whether they pulled the score up
	or down.
</p>

<p>
	The reference implementation is the <a href="https://pypi.org/project/wordshift/">wordshift</a>
	Python package, usable directly in scripts and notebooks. Install it:
</p>

<Code.Root code={wordshiftInstallCode} lang="bash" hideLines={true}>
	<Code.CopyButton />
</Code.Root>

<p>
	Give it two <code>{'{word: frequency}'}</code> maps and a bundled labMT lexicon; it returns each
	word's signed contribution to the change in average sentiment, plus the component sums a shift
	graph needs:
</p>

<Code.Root code={wordshiftUsageCode} lang="python">
	<Code.CopyButton />
</Code.Root>

<p>
	On the platform you do not have to fetch and feed the two systems yourself.
	<code>GET /storywrangler/wordshift</code> (or <code>wiki.wordshift(...)</code> in the SDK)
	resolves the dataset, loads both date-or-entity systems, and runs the shift server-side, the same
	way <code>/rtd</code> does for divergence.
</p>

<p>
	The core math lives in
	<a href="https://github.com/Vermont-Complex-Systems/wordshift-core">wordshift-core</a>, a Rust
	crate, mirroring the allotaxonometer's <code>allotaxonometer-core</code>.
</p>
