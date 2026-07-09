<script lang="ts">
	import SunIcon from '@lucide/svelte/icons/sun';
	import MoonIcon from '@lucide/svelte/icons/moon';
	import MenuIcon from '@lucide/svelte/icons/menu';
	import XIcon from '@lucide/svelte/icons/x';
	import { toggleMode } from 'mode-watcher';
	import { untrack, onMount } from 'svelte';
	import { Button } from '$lib/components/ui/button/index.js';
	import { page } from '$app/state';
	import { nav } from '$lib/nav';

	let menuOpen = $state(false);
	let previousPathname = $state('');

	// On the home page the header floats transparently over the gradient hero
	// (so the gradient runs to the top), then turns solid once you scroll past it.
	const isHome = $derived(page.url.pathname === '/');
	let scrolled = $state(false);
	onMount(() => {
		const onScroll = () => (scrolled = window.scrollY > 300);
		onScroll();
		window.addEventListener('scroll', onScroll, { passive: true });
		return () => window.removeEventListener('scroll', onScroll);
	});
	const solid = $derived(!isHome || scrolled);

	function openMenu() {
		menuOpen = true;
	}

	function closeMenu() {
		menuOpen = false;
	}

	function isActive(href: string) {
		return page.url.pathname === href;
	}

	// Auto-close the menu on navigation
	$effect(() => {
		const current = page.url.pathname;
		if (previousPathname && current !== previousPathname) {
			untrack(() => {
				menuOpen = false;
			});
		}
		previousPathname = current;
	});
</script>

<header
	class={[
		'sticky top-0 z-50 w-full border-b transition-colors duration-300',
		solid
			? 'border-border/40 bg-background/95 supports-[backdrop-filter]:bg-background/60 backdrop-blur'
			: 'border-transparent'
	]}
>
	<div class="flex h-14 max-w-screen-2xl items-center px-4 sm:px-6">
		<a href="/" class="flex items-center gap-2 font-semibold">
			<span class="text-foreground">Storywrangler</span>
		</a>

		<nav class="ml-4 sm:ml-6 flex items-center gap-3 sm:gap-4 text-sm">
			<a href="/getting-started" class="text-foreground/60 hover:text-foreground transition-colors">
				Guides
			</a>
			<a href="/api-reference" class="text-foreground/60 hover:text-foreground transition-colors">
				<span class="sm:hidden">API</span>
				<span class="hidden sm:inline">API Reference</span>
			</a>
		</nav>

		<div class="ml-auto flex items-center gap-2">
			<Button onclick={toggleMode} variant="outline" size="icon">
				<SunIcon
					class="h-[1.2rem] w-[1.2rem] scale-100 rotate-0 !transition-all dark:scale-0 dark:-rotate-90"
				/>
				<MoonIcon
					class="absolute h-[1.2rem] w-[1.2rem] scale-0 rotate-90 !transition-all dark:scale-100 dark:rotate-0"
				/>
				<span class="sr-only">Toggle theme</span>
			</Button>

			<Button onclick={openMenu} variant="outline" size="icon" class="lg:hidden">
				<MenuIcon class="h-[1.2rem] w-[1.2rem]" />
				<span class="sr-only">Open menu</span>
			</Button>
		</div>
	</div>
</header>

<!-- Mobile slide-out panel -->
{#if menuOpen}
	<!-- Backdrop -->
	<button
		class="fixed inset-0 z-50 bg-black/50 transition-opacity duration-300 lg:hidden"
		class:opacity-100={menuOpen}
		onclick={closeMenu}
		aria-label="Close menu"
		tabindex="-1"
	></button>
{/if}

<div
	class={[
		'bg-background border-border/40 fixed top-0 right-0 z-50 h-full w-72 border-l shadow-lg transition-transform duration-300 ease-in-out lg:hidden',
		menuOpen ? 'translate-x-0' : 'translate-x-full'
	]}
>
	<div class="flex h-14 items-center justify-between px-4 border-b border-border/40">
		<span class="text-foreground font-semibold">Navigation</span>
		<Button onclick={closeMenu} variant="outline" size="icon">
			<XIcon class="h-[1.2rem] w-[1.2rem]" />
			<span class="sr-only">Close menu</span>
		</Button>
	</div>

	<nav class="overflow-y-auto h-[calc(100%-3.5rem)] px-4 py-6">
		<div class="flex flex-col gap-6">
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
									onclick={closeMenu}
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

			<!-- API Reference section -->
			<div>
				<p class="text-foreground mb-2 text-xs font-semibold tracking-wider uppercase">
					Reference
				</p>
				<ul class="flex flex-col gap-0.5">
					<li>
						<a
							href="/api-reference"
							onclick={closeMenu}
							class={[
								'text-muted-foreground hover:text-foreground block rounded-md px-2 py-1.5 text-sm transition-colors',
								isActive('/api-reference') && 'bg-accent text-accent-foreground font-medium'
							]}
						>
							API Reference
						</a>
					</li>
				</ul>
			</div>
		</div>
	</nav>
</div>
