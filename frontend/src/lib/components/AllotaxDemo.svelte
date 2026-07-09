<script lang="ts">
	import { browser } from '$app/environment';
	import { onMount } from 'svelte';
	import { Dashboard, Allotaxonograph } from 'allotaxonometer-ui';
	// Real cached ngram distributions for the two spike days — regenerate with
	// scripts/fetch_demo_data.py. The allotaxonometer (WASM, via allotaxonometer-ui)
	// computes the rank-turbulence divergence in the browser.
	import allotaxData from '$lib/data/demo-allotax.json';

	const title = allotaxData.title as [string, string];
	const alpha = 0.58; // RTD alpha — adjust to taste.

	// The Dashboard lays out at a fixed size (diamond + wordshift ≈ 1200px wide).
	// Render it at that natural size and CSS-scale it down to the container width,
	// so the two panels stay side by side without horizontal scroll at any width.
	const NATURAL_W = 1200;
	const NATURAL_H = 815;
	let width = $state(NATURAL_W);
	const scale = $derived(Math.min(1, width / NATURAL_W));

	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	let allotax = $state<any>(null);

	onMount(() => {
		// Constructed here (not at module top) so SSR never touches the WASM init.
		const a = new Allotaxonograph();
		a.setAlpha(alpha);
		a.updateData(allotaxData.sys1, allotaxData.sys2, title);
		allotax = a;
	});
</script>

<div class="not-prose my-8 overflow-hidden rounded-xl border border-border bg-background p-4">
	<div bind:clientWidth={width}>
		{#if browser && allotax?.dat}
			<div
				class="mx-auto overflow-hidden"
				style="width: {NATURAL_W * scale}px; height: {NATURAL_H * scale}px;"
			>
				<div
					style="width: {NATURAL_W}px; height: {NATURAL_H}px; transform: scale({scale}); transform-origin: top left;"
				>
					<Dashboard
						dat={allotax.dat}
						barData={allotax.barData}
						balanceData={allotax.balanceData}
						maxlog10={allotax.maxlog10}
						divnorm={allotax.rtd?.normalization ?? 1}
						{title}
						{alpha}
						DashboardWidth={NATURAL_W}
						DashboardHeight={NATURAL_H}
						WordshiftWidth={400}
					/>
				</div>
			</div>
		{:else}
			<div class="text-muted-foreground flex h-64 items-center justify-center gap-2 text-sm">
				<span
					class="h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent"
				></span>
				Computing rank-turbulence divergence…
			</div>
		{/if}
	</div>
</div>
