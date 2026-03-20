<script lang="ts">
	import SunIcon from '@lucide/svelte/icons/sun';
	import MoonIcon from '@lucide/svelte/icons/moon';
	import { toggleMode } from 'mode-watcher';
	import { Button } from '$lib/components/ui/button/index.js';
</script>

<header class="border-border/40 bg-background/95 supports-[backdrop-filter]:bg-background/60 sticky top-0 z-50 w-full border-b backdrop-blur">
	<div class="flex h-14 max-w-screen-2xl items-center px-4 sm:px-6">
		<a href="/" class="flex items-center gap-2 font-semibold">
			<span class="text-foreground">Storywrangler</span>
		</a>

		<nav class="ml-6 flex items-center gap-4 text-sm">
			<a
				href="/docs"
				class="text-foreground/60 hover:text-foreground transition-colors"
			>
				Guides
			</a>
			<a
				href="/docs/api-reference"
				class="text-foreground/60 hover:text-foreground transition-colors"
			>
				API Reference
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
		</div>
	</div>
</header>
