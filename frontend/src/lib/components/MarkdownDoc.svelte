<script lang="ts">
	import Markdown from 'svelte-exmarkdown';
	import { gfmPlugin } from 'svelte-exmarkdown/gfm';
	import rehypeSlug from 'rehype-slug';
	import rehypeAutolinkHeadings from 'rehype-autolink-headings';
	import type { Element, ElementContent, Root, RootContent } from 'hast';
	import MarkdownLink from './MarkdownLink.svelte';
	import MarkdownCodeBlock from './MarkdownCodeBlock.svelte';

	let { md }: { md: string } = $props();

	function textOf(node: ElementContent): string {
		if (node.type === 'text') return node.value;
		if ('children' in node) return node.children.map(textOf).join('');
		return '';
	}

	// Stamps each fenced code block's raw text and language onto its <pre> so
	// the MarkdownCodeBlock renderer can hand them to Code.Root. Inline code
	// (no <pre> parent) is untouched.
	function rehypeCodeMeta() {
		return (tree: Root) => {
			const walk = (node: Root | RootContent) => {
				if (node.type !== 'root' && node.type !== 'element') return;
				if (node.type === 'element' && node.tagName === 'pre') {
					const elementChildren = node.children.filter((c) => c.type === 'element');
					const code = elementChildren[0];
					if (elementChildren.length === 1 && code.tagName === 'code') {
						const classes = code.properties.className;
						const langClass = Array.isArray(classes)
							? classes.find((c) => typeof c === 'string' && c.startsWith('language-'))
							: undefined;
						node.properties['data-code'] = textOf(code).replace(/\n$/, '');
						node.properties['data-lang'] =
							typeof langClass === 'string' ? langClass.slice('language-'.length) : '';
					}
					return;
				}
				node.children.forEach(walk);
			};
			walk(tree);
		};
	}

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
		{ rehypePlugin: rehypeCodeMeta },
		{ renderer: { a: MarkdownLink, pre: MarkdownCodeBlock } }
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
