# Allotaxonometer

The allotaxonometer compares two ranked lists — word frequencies, name counts, topic distributions — across time, place, or any declared dimension.

It measures rank-turbulence divergence (RTD) between the two lists and produces a contribution breakdown: which elements shifted the most, and in which direction. The visual output is an allotaxonograph — a mirror plot showing the top drivers of the divergence.

Below, it compares English Wikipedia (US) on two days of very different collective attention — **election day** (2024-11-06) and the **Charlie Kirk** assassination (2025-09-10) — computed live in your browser from the API's ranked n-grams. The diamond plots every n-gram by its rank on each day; the wordshift ranks the terms that drove the two days apart.

<!-- AllotaxDemo -->

That figure is the [allotaxonometer-ui](https://www.npmjs.com/package/allotaxonometer-ui) npm package — the same Svelte components you can drop into your own app. Install it:

```bash
npm install allotaxonometer-ui
```

Feed it two ranked type/count lists (for example the two systems returned by `GET /storywrangler/top-ngrams`), then render the dashboard:

```svelte
<script>
  import { Dashboard, Allotaxonograph } from 'allotaxonometer-ui';

  // sys1, sys2: ranked [{ types, counts }] lists — e.g. the two systems from
  // GET /storywrangler/top-ngrams?domain=wikimedia&dates=2024-11-06&dates2=2025-09-10
  const graph = new Allotaxonograph();
  graph.setAlpha(0.58);                        // rank-turbulence alpha
  graph.updateData(sys1, sys2, ['2024-11-06', '2025-09-10']);
</script>

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
{/if}
```

The core rank-turbulence-divergence math lives in [allotaxonometer-core](https://github.com/Vermont-Complex-Systems/allotaxonometer-core), a Rust crate the package calls via WebAssembly.

The companion instrument, [wordshift](/tools/wordshift), decomposes *why* two lists diverge into per-word contributions.
