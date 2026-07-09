<script lang="ts">
	import MarkdownDoc from '$lib/components/MarkdownDoc.svelte';
	import { doc_components, marker_pattern } from '$lib/docs-components';

	let { data } = $props();

	// Split on registered `<!-- Name -->` markers; the capture group makes
	// odd indices component names and even indices markdown segments.
	const segments = $derived(data.md.split(marker_pattern));
</script>

{#each segments as segment, i (i)}
	{#if i % 2 === 1}
		{@const Embed = doc_components[segment]}
		<Embed />
	{:else if segment.trim()}
		<MarkdownDoc md={segment} />
	{/if}
{/each}
