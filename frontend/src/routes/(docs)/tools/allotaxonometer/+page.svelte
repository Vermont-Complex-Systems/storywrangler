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
