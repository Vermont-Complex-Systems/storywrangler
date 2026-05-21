<script lang="ts">
	import Markdown from 'svelte-exmarkdown';
	import { gfmPlugin } from 'svelte-exmarkdown/gfm';
	import rehypeSlug from 'rehype-slug';
	import specContent from './spec.md?raw';

	const plugins = [gfmPlugin(), { rehypePlugin: rehypeSlug }];
</script>

<div class="not-prose mb-4 flex items-center gap-2">
	<span class="rounded-full border border-zinc-300 bg-zinc-100 px-2.5 py-0.5 font-mono text-xs text-zinc-700 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">
		v0.0.3
	</span>
	<span class="text-muted-foreground text-xs">2026-04-19</span>
</div>

<Markdown md={specContent} {plugins} />
