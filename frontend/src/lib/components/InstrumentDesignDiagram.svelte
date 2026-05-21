<script lang="ts">
	import { Package, Server, Terminal, Code, Monitor, ArrowDown, ArrowRight } from '@lucide/svelte';
</script>

<!-- Mobile layout -->
<div class="not-prose mt-6 flex flex-col gap-3 md:hidden">
	<!-- Tier 1: Standalone Library -->
	<div class="rounded-xl border border-zinc-200 bg-zinc-50 p-3 dark:border-zinc-800 dark:bg-zinc-900">
		<div class="mb-2 flex items-center gap-2">
			<div
				class="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-purple-100 text-purple-600 dark:bg-purple-950 dark:text-purple-400"
			>
				<Package class="h-4 w-4" />
			</div>
			<div>
				<p class="text-foreground text-xs font-semibold">Standalone library</p>
				<p class="text-muted-foreground text-[10px]">
					Independently useful — no Storywrangler dependency
				</p>
			</div>
		</div>
		<div class="rounded-lg border border-purple-200 bg-purple-50 p-2.5 dark:border-purple-900 dark:bg-purple-950/30">
			<p class="text-foreground text-[11px] font-semibold">allotaxonometer-core</p>
			<div class="mt-1.5 flex flex-wrap gap-1.5">
				<span
					class="rounded bg-purple-100 px-1.5 py-0.5 font-mono text-[10px] text-purple-700 dark:bg-purple-900/50 dark:text-purple-300"
					>allotax-core <span class="text-[9px] opacity-70">Rust</span></span
				>
				<span
					class="rounded bg-purple-100 px-1.5 py-0.5 font-mono text-[10px] text-purple-700 dark:bg-purple-900/50 dark:text-purple-300"
					>allotax-py <span class="text-[9px] opacity-70">PyO3</span></span
				>
				<span
					class="rounded bg-purple-100 px-1.5 py-0.5 font-mono text-[10px] text-purple-700 dark:bg-purple-900/50 dark:text-purple-300"
					>allotax-wasm <span class="text-[9px] opacity-70">WASM</span></span
				>
			</div>
			<p class="text-muted-foreground mt-1.5 text-[10px]">
				Published to PyPI as <code class="text-foreground text-[10px]">allotax</code> — usable
				directly: <code class="text-foreground text-[10px]">import allotax</code>
			</p>
		</div>
	</div>

	<!-- Arrow: wraps as API -->
	<div class="flex flex-col items-center gap-0.5 text-muted-foreground">
		<span class="text-[9px] font-mono">wraps as API</span>
		<ArrowDown class="h-5 w-5" />
	</div>

	<!-- Tier 2: Backend Router -->
	<div class="rounded-xl border border-zinc-200 bg-zinc-50 p-3 dark:border-zinc-800 dark:bg-zinc-900">
		<div class="mb-2 flex items-center gap-2">
			<div
				class="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-purple-100 text-purple-600 dark:bg-purple-950 dark:text-purple-400"
			>
				<Server class="h-4 w-4" />
			</div>
			<div>
				<p class="text-foreground text-xs font-semibold">Backend router</p>
				<p class="text-muted-foreground text-[10px]">
					Wraps the library behind dataset-aware endpoints
				</p>
			</div>
		</div>
		<div class="rounded-lg border border-zinc-200 bg-white p-2 dark:border-zinc-700 dark:bg-zinc-800">
			<p class="text-muted-foreground text-[10px]">
				<code class="text-foreground text-[10px]">backend/app/routers/storywrangler.py</code>
			</p>
			<p class="text-muted-foreground mt-1 text-[10px]">
				Exposes <code class="text-foreground text-[10px]">@router.get("/rtd")</code> — resolves
				dataset, loads data, calls allotax, returns results
			</p>
		</div>
	</div>

	<!-- Arrow: fans out -->
	<div class="flex flex-col items-center gap-0.5 text-muted-foreground">
		<ArrowDown class="h-5 w-5" />
	</div>

	<!-- Tier 3: Consumer Interfaces -->
	<div class="flex flex-col gap-2">
		<!-- Programmatic -->
		<div class="rounded-xl border border-zinc-200 bg-zinc-50 p-3 dark:border-zinc-800 dark:bg-zinc-900">
			<div class="mb-1.5 flex items-center gap-2">
				<div
					class="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-purple-100 text-purple-600 dark:bg-purple-950 dark:text-purple-400"
				>
					<Terminal class="h-3.5 w-3.5" />
				</div>
				<p class="text-foreground text-[11px] font-semibold">Programmatic</p>
			</div>
			<p class="text-muted-foreground text-[10px]">
				<code class="text-foreground text-[10px]">import allotax</code> directly in scripts/notebooks
			</p>
		</div>

		<!-- SDK -->
		<div class="rounded-xl border border-zinc-200 bg-zinc-50 p-3 dark:border-zinc-800 dark:bg-zinc-900">
			<div class="mb-1.5 flex items-center gap-2">
				<div
					class="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-purple-100 text-purple-600 dark:bg-purple-950 dark:text-purple-400"
				>
					<Code class="h-3.5 w-3.5" />
				</div>
				<p class="text-foreground text-[11px] font-semibold">SDK</p>
			</div>
			<p class="text-muted-foreground text-[10px]">
				<code class="text-foreground text-[10px]"
					>client.instrument.rtd(domain=..., dataset=..., entity=..., dates=...)</code
				>
			</p>
		</div>

		<!-- Frontend -->
		<div class="rounded-xl border border-zinc-200 bg-zinc-50 p-3 dark:border-zinc-800 dark:bg-zinc-900">
			<div class="mb-1.5 flex items-center gap-2">
				<div
					class="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-purple-100 text-purple-600 dark:bg-purple-950 dark:text-purple-400"
				>
					<Monitor class="h-3.5 w-3.5" />
				</div>
				<p class="text-foreground text-[11px] font-semibold">Frontend</p>
			</div>
			<p class="text-muted-foreground text-[10px]">
				Svelte/JS app fetches from the API endpoint
			</p>
		</div>
	</div>
</div>

<!-- Desktop layout -->
<div class="not-prose mt-6 hidden md:flex md:flex-row md:items-center md:gap-0">
	<!-- Tier 1: Standalone Library -->
	<div
		class="flex-1 rounded-xl border border-zinc-200 bg-zinc-50 p-4 dark:border-zinc-800 dark:bg-zinc-900"
	>
		<div class="mb-2.5 flex items-center gap-2">
			<div
				class="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-purple-100 text-purple-600 dark:bg-purple-950 dark:text-purple-400"
			>
				<Package class="h-4 w-4" />
			</div>
			<div>
				<p class="text-foreground text-xs font-semibold">Standalone library</p>
				<p class="text-muted-foreground text-[10px]">
					Independently useful — no Storywrangler dependency
				</p>
			</div>
		</div>
		<div class="rounded-lg border border-purple-200 bg-purple-50 p-2.5 dark:border-purple-900 dark:bg-purple-950/30">
			<p class="text-foreground text-[11px] font-semibold">allotaxonometer-core</p>
			<div class="mt-1.5 flex flex-wrap gap-1.5">
				<span
					class="rounded bg-purple-100 px-1.5 py-0.5 font-mono text-[10px] text-purple-700 dark:bg-purple-900/50 dark:text-purple-300"
					>allotax-core <span class="text-[9px] opacity-70">Rust</span></span
				>
				<span
					class="rounded bg-purple-100 px-1.5 py-0.5 font-mono text-[10px] text-purple-700 dark:bg-purple-900/50 dark:text-purple-300"
					>allotax-py <span class="text-[9px] opacity-70">PyO3</span></span
				>
				<span
					class="rounded bg-purple-100 px-1.5 py-0.5 font-mono text-[10px] text-purple-700 dark:bg-purple-900/50 dark:text-purple-300"
					>allotax-wasm <span class="text-[9px] opacity-70">WASM</span></span
				>
			</div>
			<p class="text-muted-foreground mt-1.5 text-[10px]">
				PyPI: <code class="text-foreground text-[10px]">allotax</code> — usable directly:
				<code class="text-foreground text-[10px]">import allotax</code>
			</p>
		</div>
	</div>

	<!-- Arrow: wraps as API -->
	<div class="flex flex-col items-center px-3 text-muted-foreground">
		<span class="text-[9px] font-mono">wraps as API</span>
		<ArrowRight class="h-5 w-5" />
	</div>

	<!-- Tier 2: Backend Router -->
	<div
		class="flex-1 rounded-xl border border-zinc-200 bg-zinc-50 p-4 dark:border-zinc-800 dark:bg-zinc-900"
	>
		<div class="mb-2.5 flex items-center gap-2">
			<div
				class="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-purple-100 text-purple-600 dark:bg-purple-950 dark:text-purple-400"
			>
				<Server class="h-4 w-4" />
			</div>
			<div>
				<p class="text-foreground text-xs font-semibold">Backend router</p>
				<p class="text-muted-foreground text-[10px]">
					Wraps the library behind dataset-aware endpoints
				</p>
			</div>
		</div>
		<div class="rounded-lg border border-zinc-200 bg-white p-2.5 dark:border-zinc-700 dark:bg-zinc-800">
			<p class="text-muted-foreground text-[10px]">
				<code class="text-foreground text-[10px]">backend/app/routers/storywrangler.py</code>
				exposes
				<code class="text-foreground text-[10px]">@router.get("/rtd")</code> — resolves dataset,
				loads data, calls allotax, returns results
			</p>
		</div>
	</div>

	<!-- Arrow: fans out to consumers -->
	<div class="flex flex-col items-center px-3 text-muted-foreground">
		<ArrowRight class="h-5 w-5" />
	</div>

	<!-- Tier 3: Consumer Interfaces (vertical stack) -->
	<div class="flex flex-1 flex-col gap-2.5">
		<!-- Programmatic -->
		<div class="rounded-xl border border-zinc-200 bg-zinc-50 p-3 dark:border-zinc-800 dark:bg-zinc-900">
			<div class="mb-1.5 flex items-center gap-1.5">
				<div
					class="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-purple-100 text-purple-600 dark:bg-purple-950 dark:text-purple-400"
				>
					<Terminal class="h-3.5 w-3.5" />
				</div>
				<p class="text-foreground text-[11px] font-semibold">Programmatic</p>
			</div>
			<p class="text-muted-foreground text-[10px]">
				<code class="text-foreground text-[10px]">import allotax</code> directly in scripts/notebooks
			</p>
		</div>

		<!-- SDK -->
		<div class="rounded-xl border border-zinc-200 bg-zinc-50 p-3 dark:border-zinc-800 dark:bg-zinc-900">
			<div class="mb-1.5 flex items-center gap-1.5">
				<div
					class="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-purple-100 text-purple-600 dark:bg-purple-950 dark:text-purple-400"
				>
					<Code class="h-3.5 w-3.5" />
				</div>
				<p class="text-foreground text-[11px] font-semibold">SDK</p>
			</div>
			<p class="text-muted-foreground text-[10px]">
				<code class="text-foreground text-[10px]">client.instrument.rtd(...)</code>
			</p>
		</div>

		<!-- Frontend -->
		<div class="rounded-xl border border-zinc-200 bg-zinc-50 p-3 dark:border-zinc-800 dark:bg-zinc-900">
			<div class="mb-1.5 flex items-center gap-1.5">
				<div
					class="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-purple-100 text-purple-600 dark:bg-purple-950 dark:text-purple-400"
				>
					<Monitor class="h-3.5 w-3.5" />
				</div>
				<p class="text-foreground text-[11px] font-semibold">Frontend</p>
			</div>
			<p class="text-muted-foreground text-[10px]">
				Svelte/JS app fetches from the API endpoint
			</p>
		</div>
	</div>
</div>
