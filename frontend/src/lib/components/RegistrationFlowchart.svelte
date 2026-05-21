<script lang="ts">
	import { Settings, Filter, Database, Zap, BarChart3 } from '@lucide/svelte';
</script>

<!-- Mobile: stacked vertical layout -->
<div class="not-prose mt-6 flex flex-col gap-3 md:hidden">

	<!-- Top node: Minimal Registration -->
	<div class="rounded-xl border border-zinc-200 bg-zinc-50 p-3 dark:border-zinc-800 dark:bg-zinc-900">
		<div class="flex items-center gap-2 mb-2">
			<div class="bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 flex h-7 w-7 items-center justify-center rounded-lg shrink-0">
				<Settings class="h-4 w-4" />
			</div>
			<p class="text-foreground text-xs font-semibold">Minimal Registration</p>
		</div>
		<p class="text-[10px] text-muted-foreground">
			<code class="rounded bg-zinc-200 px-1 dark:bg-zinc-800 text-[9px]">data_format</code>,
			<code class="rounded bg-zinc-200 px-1 dark:bg-zinc-800 text-[9px]">data_location</code>,
			<code class="rounded bg-orange-200 px-1 dark:bg-orange-900 text-[9px]">ownership</code>,
			<code class="rounded bg-orange-200 px-1 dark:bg-orange-900 text-[9px]">lineage</code>
		</p>
	</div>

	<!-- filter_dimensions -->
	<div class="rounded-xl border border-zinc-200 bg-zinc-50 p-3 dark:border-zinc-800 dark:bg-zinc-900">
		<div class="flex items-center gap-2 mb-2">
			<div class="bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 flex h-7 w-7 items-center justify-center rounded-lg shrink-0">
				<Filter class="h-4 w-4" />
			</div>
			<p class="text-foreground text-xs font-semibold">filter_dimensions</p>
		</div>
		<p class="text-[10px] text-muted-foreground">Non-hive columns inside parquet files for WHERE filtering</p>
	</div>

	<!-- Branch 1: Specifying the API -->
	<div class="rounded-xl border border-zinc-200 bg-zinc-50 p-3 dark:border-zinc-800 dark:bg-zinc-900">
		<div class="flex items-center gap-2 mb-2">
			<div class="bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 flex h-7 w-7 items-center justify-center rounded-lg shrink-0">
				<Database class="h-4 w-4" />
			</div>
			<p class="text-foreground text-xs font-semibold">Specifying the API</p>
		</div>
		<div class="grid grid-cols-2 gap-2">
			<div class="border-border rounded-lg border p-2">
				<p class="text-foreground text-[10px] font-semibold mb-1">time_dimension</p>
				<p class="text-[9px] text-muted-foreground">Date-range queries, auto-derived availability</p>
			</div>
			<div class="border-border rounded-lg border border-dashed p-2">
				<p class="text-foreground text-[10px] font-semibold mb-1">entities</p>
				<p class="text-[9px] text-muted-foreground">Canonical IDs in shared identifier space</p>
			</div>
		</div>
	</div>

	<!-- Branch 2: Performance -->
	<div class="rounded-xl border border-zinc-200 bg-zinc-50 p-3 dark:border-zinc-800 dark:bg-zinc-900">
		<div class="flex items-center gap-2 mb-2">
			<div class="bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 flex h-7 w-7 items-center justify-center rounded-lg shrink-0">
				<Zap class="h-4 w-4" />
			</div>
			<p class="text-foreground text-xs font-semibold">Performance</p>
		</div>
		<div class="grid grid-cols-2 gap-2">
			<div class="border-border rounded-lg border p-2">
				<p class="text-foreground text-[10px] font-semibold mb-1">parquet_hive</p>
				<p class="text-[9px] text-muted-foreground">Hive partitioning prunes files per query</p>
			</div>
			<div class="border-border rounded-lg border p-2">
				<p class="text-foreground text-[10px] font-semibold mb-1">hash_bucket</p>
				<p class="text-[9px] text-muted-foreground">Content-sharded partitions for term-first lookups</p>
			</div>
		</div>
	</div>

	<!-- Branch 3: Instruments -->
	<div class="rounded-xl border border-zinc-200 bg-zinc-50 p-3 dark:border-zinc-800 dark:bg-zinc-900">
		<div class="flex items-center gap-2 mb-2">
			<div class="bg-purple-100 dark:bg-purple-950 text-purple-600 dark:text-purple-400 flex h-7 w-7 items-center justify-center rounded-lg shrink-0">
				<BarChart3 class="h-4 w-4" />
			</div>
			<p class="text-foreground text-xs font-semibold">Instruments</p>
		</div>
		<div class="grid grid-cols-2 gap-2">
			<div class="border-border rounded-lg border p-2">
				<p class="text-foreground text-[10px] font-semibold mb-1"><span class="rounded bg-purple-200 px-1 dark:bg-purple-900">types-counts</span></p>
				<p class="text-[9px] text-muted-foreground">Allotaxonometer, word shifts</p>
			</div>
			<div class="border-border rounded-lg border p-2">
				<p class="text-foreground text-[10px] font-semibold mb-1">time-series</p>
				<p class="text-[9px] text-muted-foreground">Temporal trends</p>
			</div>
		</div>
	</div>
</div>

<!-- Desktop: SVG layout -->
<div class="not-prose mt-6 hidden md:block">
	<svg
		viewBox="0 0 700 395"
		xmlns="http://www.w3.org/2000/svg"
		class="w-full"
		role="img"
		aria-label="Registration flowchart: minimal registration progresses through filter dimensions, then branches into API specification, performance tuning, and instrument selection"
	>
		<defs>
			<marker id="flow-arrow" viewBox="0 0 10 10" refX="9" refY="5"
				markerWidth="4" markerHeight="4" orient="auto">
				<path d="M 0 1 L 9 5 L 0 9 Z" fill="var(--color-border)" />
			</marker>
		</defs>

		<!-- ═══ Row 1: Minimal Registration ═══ -->
		<rect x="200" y="5" width="300" height="78" rx="12"
			class="fill-zinc-50 stroke-zinc-200 dark:fill-zinc-900 dark:stroke-zinc-800" stroke-width="1" />
		<foreignObject x="200" y="5" width="300" height="78">
			<div xmlns="http://www.w3.org/1999/xhtml" class="p-3 h-full">
				<div class="flex items-center gap-2 mb-1.5">
					<div class="bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 flex h-7 w-7 items-center justify-center rounded-lg shrink-0">
						<Settings class="h-4 w-4" />
					</div>
					<p class="text-foreground text-[10px] font-semibold">Minimal Registration</p>
				</div>
				<p class="text-[9px] text-muted-foreground leading-relaxed">
					<code class="rounded bg-zinc-200 px-1 dark:bg-zinc-800 text-[9px]">data_format</code>,
					<code class="rounded bg-zinc-200 px-1 dark:bg-zinc-800 text-[9px]">data_location</code>,
					<code class="rounded bg-orange-200 px-1 dark:bg-orange-900 text-[9px]">ownership</code>,
					<code class="rounded bg-orange-200 px-1 dark:bg-orange-900 text-[9px]">lineage</code>
				</p>
			</div>
		</foreignObject>

		<!-- Arrow: Row 1 → Row 2 -->
		<path d="M 350 83 V 110"
			stroke="var(--color-border)" stroke-width="1.5" stroke-linecap="round" fill="none" marker-end="url(#flow-arrow)" />

		<!-- ═══ Row 2: filter_dimensions ═══ -->
		<rect x="200" y="115" width="300" height="48" rx="12"
			class="fill-zinc-50 stroke-zinc-200 dark:fill-zinc-900 dark:stroke-zinc-800" stroke-width="1" />
		<foreignObject x="200" y="115" width="300" height="48">
			<div xmlns="http://www.w3.org/1999/xhtml" class="p-3 h-full">
				<div class="flex items-center gap-2">
					<div class="bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 flex h-7 w-7 items-center justify-center rounded-lg shrink-0">
						<Filter class="h-4 w-4" />
					</div>
					<div>
						<p class="text-foreground text-[10px] font-semibold">filter_dimensions</p>
						<p class="text-[8px] text-muted-foreground">Non-hive columns for WHERE filtering</p>
					</div>
				</div>
			</div>
		</foreignObject>

		<!-- ═══ Three branch arrows from Row 2 ═══ -->
		<!-- Left branch arrow -->
		<path d="M 290 163 V 177 Q 290 187, 280 187 H 120 Q 110 187, 110 197 V 211"
			stroke="var(--color-border)" stroke-width="1.5" stroke-linecap="round" fill="none" marker-end="url(#flow-arrow)" />
		<text x="185" y="184" text-anchor="middle" fill="var(--color-muted-foreground)" font-size="9" font-family="ui-monospace,monospace">Specifying the API</text>

		<!-- Center branch arrow -->
		<path d="M 350 163 V 211"
			stroke="var(--color-border)" stroke-width="1.5" stroke-linecap="round" fill="none" marker-end="url(#flow-arrow)" />
		<text x="350" y="191" text-anchor="middle" fill="var(--color-muted-foreground)" font-size="9" font-family="ui-monospace,monospace">Performance</text>

		<!-- Right branch arrow -->
		<path d="M 410 163 V 177 Q 410 187, 420 187 H 580 Q 590 187, 590 197 V 211"
			stroke="var(--color-border)" stroke-width="1.5" stroke-linecap="round" fill="none" marker-end="url(#flow-arrow)" />
		<text x="510" y="184" text-anchor="middle" fill="var(--color-muted-foreground)" font-size="9" font-family="ui-monospace,monospace">Instruments</text>

		<!-- ═══ Left branch: Specifying the API — two sibling cards ═══ -->
		<!-- Fork: left arrow splits into two -->
		<path d="M 110 211 V 221 Q 110 231, 100 231 H 60 Q 50 231, 50 241 V 251"
			stroke="var(--color-border)" stroke-width="1.5" stroke-linecap="round" fill="none" marker-end="url(#flow-arrow)" />
		<path d="M 110 211 V 221 Q 110 231, 120 231 H 160 Q 170 231, 170 241 V 251"
			stroke="var(--color-border)" stroke-width="1.5" stroke-linecap="round" fill="none" marker-end="url(#flow-arrow)" />

		<!-- Left sub-card: time_dimension -->
		<rect x="5" y="255" width="100" height="72" rx="12"
			class="fill-zinc-50 stroke-zinc-200 dark:fill-zinc-900 dark:stroke-zinc-800" stroke-width="1" />
		<foreignObject x="5" y="255" width="100" height="72">
			<div xmlns="http://www.w3.org/1999/xhtml" class="p-2 h-full">
				<p class="text-foreground text-[9px] font-semibold mb-1">time_dimension</p>
				<p class="text-[8px] text-muted-foreground">Date-range queries, auto-derived availability</p>
			</div>
		</foreignObject>

		<!-- Left sub-card: entities (dashed) -->
		<rect x="115" y="255" width="100" height="72" rx="12"
			fill="var(--color-card)" stroke="var(--color-border)" stroke-width="1" stroke-dasharray="5,4" />
		<foreignObject x="115" y="255" width="100" height="72">
			<div xmlns="http://www.w3.org/1999/xhtml" class="p-2 h-full">
				<p class="text-foreground text-[9px] font-semibold mb-1">entities</p>
				<p class="text-[8px] text-muted-foreground">Canonical IDs in shared identifier space</p>
			</div>
		</foreignObject>

		<!-- ═══ Center branch: Performance ═══ -->
		<rect x="245" y="215" width="210" height="72" rx="12"
			class="fill-zinc-50 stroke-zinc-200 dark:fill-zinc-900 dark:stroke-zinc-800" stroke-width="1" />
		<foreignObject x="245" y="215" width="210" height="72">
			<div xmlns="http://www.w3.org/1999/xhtml" class="p-3 h-full">
				<div class="flex items-center gap-2 mb-1">
					<div class="bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 flex h-7 w-7 items-center justify-center rounded-lg shrink-0">
						<Zap class="h-4 w-4" />
					</div>
					<p class="text-foreground text-[10px] font-semibold">parquet_hive</p>
				</div>
				<p class="text-[9px] text-muted-foreground">Hive partitioning prunes files per query</p>
			</div>
		</foreignObject>

		<!-- Center branch arrow to hash_bucket -->
		<path d="M 350 287 V 309"
			stroke="var(--color-border)" stroke-width="1.5" stroke-linecap="round" fill="none" marker-end="url(#flow-arrow)" />

		<!-- Center sub-card: hash_bucket -->
		<rect x="245" y="313" width="210" height="68" rx="12"
			fill="var(--color-card)" stroke="var(--color-border)" stroke-width="1" />
		<foreignObject x="245" y="313" width="210" height="68">
			<div xmlns="http://www.w3.org/1999/xhtml" class="p-3 h-full">
				<p class="text-foreground text-[10px] font-semibold mb-1">transform.hash_bucket</p>
				<p class="text-[9px] text-muted-foreground">Content-sharded partitions for term-first lookups</p>
			</div>
		</foreignObject>

		<!-- ═══ Right branch: Instruments ═══ -->
		<rect x="485" y="215" width="210" height="72" rx="12"
			class="fill-zinc-50 stroke-zinc-200 dark:fill-zinc-900 dark:stroke-zinc-800" stroke-width="1" />
		<foreignObject x="485" y="215" width="210" height="72">
			<div xmlns="http://www.w3.org/1999/xhtml" class="p-3 h-full">
				<div class="flex items-center gap-2 mb-1">
					<div class="bg-purple-100 dark:bg-purple-950 text-purple-600 dark:text-purple-400 flex h-7 w-7 items-center justify-center rounded-lg shrink-0">
						<BarChart3 class="h-4 w-4" />
					</div>
					<p class="text-foreground text-[10px] font-semibold">endpoint_schema</p>
				</div>
				<p class="text-[9px] text-muted-foreground">Standardized API response shapes</p>
			</div>
		</foreignObject>

		<!-- Right branch: two arrows to sub-cards -->
		<path d="M 555 287 V 309"
			stroke="var(--color-border)" stroke-width="1.5" stroke-linecap="round" fill="none" marker-end="url(#flow-arrow)" />
		<path d="M 630 287 V 309"
			stroke="var(--color-border)" stroke-width="1.5" stroke-linecap="round" fill="none" marker-end="url(#flow-arrow)" />

		<!-- Right sub-card: types-counts -->
		<rect x="485" y="313" width="100" height="58" rx="12"
			fill="var(--color-card)" stroke="var(--color-border)" stroke-width="1" />
		<foreignObject x="485" y="313" width="100" height="58">
			<div xmlns="http://www.w3.org/1999/xhtml" class="p-2 h-full">
				<p class="text-foreground text-[10px] font-semibold mb-1"><span class="rounded bg-purple-200 px-1 dark:bg-purple-900">types-counts</span></p>
				<p class="text-[8px] text-muted-foreground">Allotaxonometer, word shifts</p>
			</div>
		</foreignObject>

		<!-- Right sub-card: time-series -->
		<rect x="595" y="313" width="100" height="58" rx="12"
			fill="var(--color-card)" stroke="var(--color-border)" stroke-width="1" />
		<foreignObject x="595" y="313" width="100" height="58">
			<div xmlns="http://www.w3.org/1999/xhtml" class="p-2 h-full">
				<p class="text-foreground text-[10px] font-semibold mb-1">time-series</p>
				<p class="text-[8px] text-muted-foreground">Temporal trends</p>
			</div>
		</foreignObject>
	</svg>
</div>
