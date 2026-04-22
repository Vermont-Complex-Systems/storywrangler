<script lang="ts">
	import { page } from '$app/state';
	import { UseToc, type Heading } from '$lib/hooks/use-toc.svelte';

	let { children } = $props();

	const toc = new UseToc();

	function slugify(text: string) {
		return text
			.toLowerCase()
			.replace(/[^a-z0-9]+/g, '-')
			.replace(/(^-|-$)/g, '');
	}

	// The hook builds a tree rooted at h1 (the page title). For the sidebar we
	// want h2s at the top level, so we skip h1 entries and show their children.
	function tocItems(headings: Heading[]): Heading[] {
		return headings.flatMap((h) => (h.level === 1 ? h.children : [h]));
	}

	const nav = [
		{
			title: 'Getting Started',
			items: [
				{ label: 'Introduction', href: '/' },
				{ label: 'Why Storywrangler?', href: '/manifesto' },
				{ label: 'Authentication', href: '/authentication' }
			]
		},
		{
			title: 'Guides',
			items: [
				{ label: 'Registering a dataset', href: '/register' },
				{ label: 'Design & architecture', href: '/design' },
				{ label: 'Versioning', href: '/versioning' },
				{ label: 'Storywrangler-Specs', href: '/specification' }
			]
		},
		{
			title: 'Instruments',
			items: [
				{ label: 'Allotaxonometry', href: '/tools/allotaxonometer' }
			]
		},
		{
			title: 'Case Studies',
			items: [
				{ label: 'Wikimedia pipeline', href: '/case-studies/wikimedia' },
				{ label: 'scisciDB pipeline', href: '/case-studies/scisciDB' }
			]
		}
	];

	function isActive(href: string) {
		return page.url.pathname === href;
	}

	function attachToc(el: HTMLElement) {
		function stampIds() {
			el.querySelectorAll('h2, h3').forEach((h) => {
				if (!h.id && h.textContent) h.id = slugify(h.textContent.trim());
			});
		}
		// Register our observer before handing the ref to the toc hook so our
		// ID-stamping fires before the toc's MutationObserver on each navigation.
		const observer = new MutationObserver(stampIds);
		observer.observe(el, { childList: true });
		stampIds();
		toc.ref = el;
		return () => observer.disconnect();
	}
</script>

<div class="flex min-h-[calc(100vh-3.5rem)]">
	<!-- Left nav -->
	<aside class="border-border/40 sticky top-14 h-[calc(100vh-3.5rem)] w-60 shrink-0 overflow-y-auto border-r pl-6 pr-4 py-8 max-lg:hidden">
		<nav class="flex flex-col gap-6">
			{#each nav as section (section.title)}
				<div>
					<p class="text-foreground mb-2 text-xs font-semibold tracking-wider uppercase">
						{section.title}
					</p>
					<ul class="flex flex-col gap-0.5">
						{#each section.items as item (item.href)}
							<li>
								<a
									href={item.href}
									class={[
										'text-muted-foreground hover:text-foreground block rounded-md px-2 py-1.5 text-sm transition-colors',
										isActive(item.href) && 'bg-accent text-accent-foreground font-medium'
									]}
								>
									{item.label}
								</a>
							</li>
						{/each}
					</ul>
				</div>
			{/each}
		</nav>
	</aside>

	<!-- Content + right TOC -->
	<div class="flex min-w-0 flex-1">
		<div class="min-w-0 flex-1 px-8 py-10 lg:px-14">
			<div class="max-w-3xl mx-auto">
				<span class="mb-4 inline-flex items-center gap-1.5 rounded-full bg-orange-600 px-2.5 py-0.5 text-xs font-medium text-white">
					<svg class="h-3 w-3" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
						<path d="M8 1.5a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13ZM0 8a8 8 0 1 1 16 0A8 8 0 0 1 0 8Zm9-1a1 1 0 1 1-2 0 1 1 0 0 1 2 0ZM6.75 10.25a.75.75 0 0 1 .75-.75h.75v-1.5h-.75a.75.75 0 0 1 0-1.5H8.5a.75.75 0 0 1 .75.75v2.25h.25a.75.75 0 0 1 0 1.5h-2a.75.75 0 0 1-.75-.75Z"/>
					</svg>
					Claude generated — content in progress
				</span>
			</div>
			<article
				class="prose dark:prose-invert prose-zinc max-w-3xl mx-auto"
				{@attach attachToc}
			>
				{@render children()}
			</article>
		</div>

		<!-- Right TOC -->
		{#if tocItems(toc.current).length > 0}
			<aside class="sticky top-14 h-[calc(100vh-3.5rem)] w-52 shrink-0 overflow-y-auto py-10 pr-4 max-xl:hidden">
				<p class="text-foreground mb-3 text-xs font-semibold tracking-wider uppercase">
					On this page
				</p>
				<nav class="flex flex-col gap-0.5">
					{#each tocItems(toc.current) as heading (heading.index)}
						<a
							href="#{slugify(heading.label)}"
							class={[
								'block py-1 text-sm transition-colors',
								heading.level === 3 && 'pl-3',
								heading.active
									? 'text-foreground font-medium'
									: 'text-muted-foreground hover:text-foreground'
							]}
						>
							{heading.label}
						</a>
					{/each}
				</nav>
			</aside>
		{/if}
	</div>
</div>
