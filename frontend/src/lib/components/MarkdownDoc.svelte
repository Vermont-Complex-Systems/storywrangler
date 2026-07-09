<script lang="ts">
	import Markdown from 'svelte-exmarkdown';
	import { gfmPlugin } from 'svelte-exmarkdown/gfm';
	import rehypeSlug from 'rehype-slug';

	let { md }: { md: string } = $props();

	const plugins = [gfmPlugin(), { rehypePlugin: rehypeSlug }];
</script>

<Markdown {md} {plugins} />
