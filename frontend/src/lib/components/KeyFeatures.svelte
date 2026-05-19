<script lang="ts">
</script>

{#snippet iconCorpora()}
	<path stroke-linecap="round" stroke-linejoin="round" d="M13.19 8.688a4.5 4.5 0 0 1 1.242 7.244l-4.5 4.5a4.5 4.5 0 0 1-6.364-6.364l1.757-1.757m13.35-.622 1.757-1.757a4.5 4.5 0 0 0-6.364-6.364l-4.5 4.5a4.5 4.5 0 0 0 1.242 7.244" />
{/snippet}

{#snippet iconLineage()}
	<path stroke-linecap="round" stroke-linejoin="round" d="M7.217 10.907a2.25 2.25 0 1 0 0 2.186m0-2.186c.18.324.283.696.283 1.093s-.103.77-.283 1.093m0-2.186 9.566-5.314m-9.566 7.5 9.566 5.314m0 0a2.25 2.25 0 1 0 3.935 2.186 2.25 2.25 0 0 0-3.935-2.186Zm0-12.814a2.25 2.25 0 1 0 3.933-2.185 2.25 2.25 0 0 0-3.933 2.185Z" />
{/snippet}

{#snippet iconInstruments()}
	<path stroke-linecap="round" stroke-linejoin="round" d="M11.42 15.17 17.25 21A2.652 2.652 0 0 0 21 17.25l-5.877-5.877M11.42 15.17l2.496-3.03c.317-.384.74-.626 1.208-.766M11.42 15.17l-4.655 5.653a2.548 2.548 0 1 1-3.586-3.586l5.654-4.654m5.65-4.65 3.029-2.497a.532.532 0 0 1 .765.766L12.873 9.63M11.42 15.17l1.453-1.453" />
{/snippet}

{#snippet iconInterop()}
	<path stroke-linecap="round" stroke-linejoin="round" d="m3.75 13.5 10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75Z" />
{/snippet}

{#snippet iconGovernance()}
	<path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75 11.25 15 15 9.75m-3-7.036A11.959 11.959 0 0 1 3.598 6 11.99 11.99 0 0 0 3 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285Z" />
{/snippet}

{#snippet iconDiscover()}
	<path stroke-linecap="round" stroke-linejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
{/snippet}

<div class="not-prose mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
	{#each [
		{
			icon: iconInstruments,
			color: 'purple',
			title: 'Instrument-driven endpoints',
			body: 'The allotaxonometer and other VCSI tools become available the moment a dataset is registered. The schema contract is the wiring — no per-dataset integration work required.',
		},
		{
			icon: iconInterop,
			color: 'purple',
			title: 'Performance-Oriented',
			body: 'Built on Parquet and DuckDB to scale from megabytes to terabytes. Columnar storage, partition pruning, and in-process analytical queries keep latency low without infrastructure overhead.',
		},
		{
			icon: iconCorpora,
			color: 'purple',
			title: 'Interoperability by Design',
			body: 'Datasets declare their query axes and output shape once. The platform bridges heterogeneous identifier namespaces — Wikidata, OpenAlex, local IDs — through a unified entity graph.',
		},
		{
			icon: iconGovernance,
			color: 'orange',
			title: 'Selective Sharing & Succession',
			body: 'Fine-grained access control means datasets that cannot be fully open can still be shared: expose aggregate results only, a filtered row subset, or full access per collaborator. Ownership succession ensures datasets survive student turnover.',
		},
		{
			icon: iconDiscover,
			color: 'orange',
			title: 'Discoverable Analysis',
			body: "Search the registry to find datasets that are already instrument-ready. The schema contract tells you not just where the data lives, but what analyses are immediately available — discovery and reproducibility are the same guarantee.",
		},
		{
			icon: iconLineage,
			color: 'orange',
			title: 'Lineage & Impact',
			body: 'Downstream groups that build on your data register their dependency in the registry. Their work appears in your impact record automatically — research credit propagates without either group coordinating directly.',
		},
	] as card (card.title)}
		<div class="border-border rounded-lg border p-5 flex flex-col gap-3">
			<div class={[
				'flex h-9 w-9 items-center justify-center rounded-md',
				card.color === 'purple'
					? 'bg-purple-100 dark:bg-purple-950 text-purple-600 dark:text-purple-400'
					: 'bg-orange-100 dark:bg-orange-950 text-orange-600 dark:text-orange-400'
			]}>
				<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="h-5 w-5" aria-hidden="true">
					{@render card.icon()}
				</svg>
			</div>
			<p class="text-foreground text-sm font-semibold">{card.title}</p>
			<p class="text-muted-foreground text-sm leading-relaxed">{card.body}</p>
		</div>
	{/each}
</div>
