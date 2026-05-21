<script lang="ts">
	import { ArrowRight, ArrowDown, ArrowUp } from '@lucide/svelte';
</script>

<div class="not-prose mt-6">
	<!-- Mobile layout: stacked vertically -->
	<div class="flex flex-col gap-3 md:hidden">
		<!-- Spec -->
		<div class="rounded-xl border border-zinc-200 bg-zinc-50 p-4 dark:border-zinc-800 dark:bg-zinc-900">
			<p class="text-foreground text-sm font-semibold mb-2">Storywrangler-Specification</p>
			<p class="text-muted-foreground text-xs">A markdown file -- open, discussed, collectively agreed upon. Similar to the parquet format or OpenAPI specs.</p>
			<ul class="mt-3 space-y-2">
				<li>
					<p class="text-foreground text-xs font-semibold">Dataset registry schema</p>
					<p class="text-muted-foreground text-[11px] mt-0.5">What is expected when registering. Does not define the shape of the data.</p>
				</li>
				<li>
					<p class="text-foreground text-xs font-semibold">API endpoints</p>
					<p class="text-muted-foreground text-[11px] mt-0.5">Stricter registry schema with expectations about the data shape.</p>
				</li>
				<li>
					<p class="text-foreground text-xs font-semibold">Entity Identifier Systems</p>
					<p class="text-muted-foreground text-[11px] mt-0.5">Accepted identifiers to make registered datasets joinable and discoverable.</p>
				</li>
			</ul>
		</div>

		<div class="flex justify-center text-muted-foreground">
			<ArrowDown class="h-6 w-6" />
		</div>

		<!-- Monorepo -->
		<div class="rounded-xl border border-zinc-200 bg-zinc-50 p-4 dark:border-zinc-800 dark:bg-zinc-900">
			<p class="text-foreground text-sm font-semibold mb-3">Vermont-Complex-Systems/storywrangler/</p>
			<div class="flex flex-col items-center gap-2">
				<div class="w-full rounded-lg border border-zinc-200 bg-white p-2.5 dark:border-zinc-700 dark:bg-zinc-800">
					<p class="text-foreground text-xs font-semibold">storywrangler-sdk</p>
					<p class="text-muted-foreground text-[11px] mt-0.5">User-friendly SDK to interact with the Storywrangler API.</p>
				</div>
				<ArrowUp class="h-4 w-4 text-muted-foreground" />
				<div class="w-full rounded-lg border border-zinc-200 bg-white p-2.5 dark:border-zinc-700 dark:bg-zinc-800">
					<p class="text-foreground text-xs font-semibold">storywrangler-schemas</p>
					<p class="text-muted-foreground text-[11px] mt-0.5">Python wrapper of the Storywrangler-Spec. Tiny package.</p>
				</div>
				<ArrowDown class="h-4 w-4 text-muted-foreground" />
				<div class="w-full rounded-lg border border-zinc-200 bg-white p-2.5 dark:border-zinc-700 dark:bg-zinc-800">
					<p class="text-foreground text-xs font-semibold">backend</p>
					<p class="text-muted-foreground text-[11px] mt-0.5">Uses schemas to validate upon registration.</p>
				</div>
			</div>
		</div>
	</div>

	<!-- Desktop layout: Spec → monorepo with schemas in the middle -->
	<div class="hidden md:grid md:grid-cols-[1fr_auto_1fr] md:gap-4 md:items-stretch">
		<!-- Left: Spec -->
		<div class="rounded-xl border border-zinc-200 bg-zinc-50 p-5 dark:border-zinc-800 dark:bg-zinc-900">
			<p class="text-foreground text-sm font-semibold mb-2">Storywrangler-Specification</p>
			<p class="text-muted-foreground text-xs mb-5">A markdown file -- open, discussed, collectively agreed upon. Similar to the parquet format or OpenAPI specs.</p>
			<ul class="space-y-7">
				<li>
					<p class="text-foreground text-xs font-semibold">Dataset registry schema</p>
					<p class="text-muted-foreground text-[11px] mt-0.5">What is expected when registering. Does not define the shape of the data.</p>
				</li>
				<li>
					<p class="text-foreground text-xs font-semibold">API endpoints</p>
					<p class="text-muted-foreground text-[11px] mt-0.5">Stricter registry schema with expectations about the data shape.</p>
				</li>
				<li>
					<p class="text-foreground text-xs font-semibold">Entity Identifier Systems</p>
					<p class="text-muted-foreground text-[11px] mt-0.5">Accepted identifiers to make registered datasets joinable and discoverable.</p>
				</li>
			</ul>
		</div>

		<!-- Center: Arrow -->
		<div class="flex items-center justify-center">
			<ArrowRight class="h-6 w-6 text-muted-foreground" />
		</div>

		<!-- Right: Monorepo with schemas in the middle -->
		<div class="rounded-xl border border-zinc-200 bg-zinc-50 p-5 dark:border-zinc-800 dark:bg-zinc-900">
			<p class="text-foreground text-sm font-semibold mb-3">Vermont-Complex-Systems/storywrangler/</p>
			<div class="flex flex-col items-center gap-2">
				<div class="w-full rounded-lg border border-zinc-200 bg-white p-3 dark:border-zinc-700 dark:bg-zinc-800">
					<p class="text-foreground text-xs font-semibold">storywrangler-sdk</p>
					<p class="text-muted-foreground text-[11px] mt-0.5">User-friendly SDK to interact with the Storywrangler API.</p>
				</div>
				<ArrowUp class="h-4 w-4 text-muted-foreground" />
				<div class="w-full rounded-lg border border-zinc-200 bg-white p-3 dark:border-zinc-700 dark:bg-zinc-800">
					<p class="text-foreground text-xs font-semibold">storywrangler-schemas</p>
					<p class="text-muted-foreground text-[11px] mt-0.5">Python wrapper of the Storywrangler-Spec. Tiny package.</p>
				</div>
				<ArrowDown class="h-4 w-4 text-muted-foreground" />
				<div class="w-full rounded-lg border border-zinc-200 bg-white p-3 dark:border-zinc-700 dark:bg-zinc-800">
					<p class="text-foreground text-xs font-semibold">backend</p>
					<p class="text-muted-foreground text-[11px] mt-0.5">Uses schemas to validate upon registration.</p>
				</div>
			</div>
		</div>
	</div>
</div>
