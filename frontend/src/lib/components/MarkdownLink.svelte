<script lang="ts">
	import type { Snippet } from 'svelte';

	let {
		href = '',
		children,
		...rest
	}: { href?: string; children?: Snippet; [key: string]: unknown } = $props();

	// Endpoint routes (llms.txt, sections.json, …) are +server.ts responses, not
	// pages — SvelteKit's client-side nav to them fails, so force a full load.
	const reload = $derived(/\.(?:txt|json)(?:[?#]|$)/.test(href));
</script>

<a {href} {...rest} data-sveltekit-reload={reload ? '' : undefined}>{@render children?.()}</a>
