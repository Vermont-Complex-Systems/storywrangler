<script lang="ts">
	import Markdown from 'svelte-exmarkdown';
	import { gfmPlugin } from 'svelte-exmarkdown/gfm';
	import rehypeSlug from 'rehype-slug';
	import rehypeAutolinkHeadings from 'rehype-autolink-headings';
	import type { Element } from 'hast';
	import MarkdownLink from './MarkdownLink.svelte';

	let { md }: { md: string } = $props();

	// "#" appended after each heading; visible on heading hover (styles below).
	const anchorContent: Element = {
		type: 'element',
		tagName: 'span',
		properties: { className: ['heading-anchor'], ariaHidden: 'true' },
		children: [{ type: 'text', value: '#' }]
	};

	// Custom <a> renderer forces a full page load for +server.ts endpoint links.
	const plugins = [
		gfmPlugin(),
		{ rehypePlugin: rehypeSlug },
		{
			rehypePlugin: [
				rehypeAutolinkHeadings,
				{
					behavior: 'append',
					properties: { className: ['heading-anchor-link'], ariaLabel: 'Link to this section' },
					content: anchorContent
				}
			] satisfies import('unified').Pluggable
		},
		{ renderer: { a: MarkdownLink } }
	];
</script>

<Markdown {md} {plugins} />

<style>
	/* Anchors render inside <Markdown>, so Svelte scoping needs :global(). */
	:global(a.heading-anchor-link) {
		margin-left: 0.35em;
		color: var(--muted-foreground);
		text-decoration: none;
		opacity: 0;
		transition: opacity 0.15s ease;
	}
	:global(:is(h1, h2, h3, h4, h5, h6):hover > a.heading-anchor-link),
	:global(a.heading-anchor-link:focus-visible) {
		opacity: 1;
	}
</style>
