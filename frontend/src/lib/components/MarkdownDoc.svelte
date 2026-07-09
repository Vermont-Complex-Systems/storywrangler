<script lang="ts">
	import Markdown from 'svelte-exmarkdown';
	import { gfmPlugin } from 'svelte-exmarkdown/gfm';
	import rehypeSlug from 'rehype-slug';
	import MarkdownLink from './MarkdownLink.svelte';

	let { md }: { md: string } = $props();

	// Custom <a> renderer forces a full page load for +server.ts endpoint links.
	const plugins = [gfmPlugin(), { rehypePlugin: rehypeSlug }, { renderer: { a: MarkdownLink } }];
</script>

<Markdown {md} {plugins} />
