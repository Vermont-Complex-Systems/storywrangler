<script>
const snippet = `from storywrangler import Storywrangler

client = Storywrangler()
client.registry.register({
  "catalog": "vcsi",
  "domain": "babynames",
  "dataset_id": "ngrams",
  "data_location": "/data/my-ngrams.parquet",
  "data_format": "parquet",
  "description": "Zoning bylaw word frequencies by town.",
  "format_config": {},
  "ownership": {"owner_group": "vcsi"},
  "lineage": {
    "repo": "https://github.com/vcsi/babynames"
  },
  "endpoint_schema": {
    "type": "types-counts",
    "filter_dimensions": ["sex", "country"],
  },
})`;
</script>

<div class="not-prose my-6 -mx-8 lg:-mx-10 text-xs">

<!-- ═══ MOBILE: top-down stack (hidden on md+) ═══ -->
<div class="flex flex-col gap-0 md:hidden px-3">

	<!-- Pipeline -->
	<div class="flex flex-col gap-2 rounded-xl border border-dashed border-zinc-300 bg-zinc-50/50 p-3 dark:border-zinc-700 dark:bg-zinc-900/20">
		<div class="flex items-center justify-between">
			<span class="text-[10px] font-semibold uppercase tracking-widest text-zinc-400">Your pipeline</span>
			<span class="rounded-full border border-zinc-200 px-1.5 py-0.5 text-[10px] text-zinc-400 dark:border-zinc-700">external</span>
		</div>
		<div class="space-y-1">
			<div class="flex items-center gap-1 text-[10px]">
				<span class="font-medium text-amber-600 dark:text-amber-500">Bronze</span>
				<span class="text-zinc-300 dark:text-zinc-600">→</span>
				<span class="text-zinc-400">transform</span>
				<span class="text-zinc-300 dark:text-zinc-600">→</span>
				<span class="text-zinc-500 dark:text-zinc-400">Silver</span>
			</div>
			<div class="flex flex-wrap gap-1">
				<span class="rounded border border-sky-100 bg-sky-50 px-1.5 py-0.5 font-mono text-[10px] text-sky-700 dark:border-sky-900 dark:bg-sky-950/30 dark:text-sky-400">parquet</span>
				<span class="rounded border border-sky-100 bg-sky-50 px-1.5 py-0.5 font-mono text-[10px] text-sky-700 dark:border-sky-900 dark:bg-sky-950/30 dark:text-sky-400">ducklake</span>
				<span class="rounded border border-sky-100 bg-sky-50 px-1.5 py-0.5 font-mono text-[10px] text-sky-700 dark:border-sky-900 dark:bg-sky-950/30 dark:text-sky-400">duckdb</span>
			</div>
		</div>
		<div class="mt-1 overflow-hidden rounded-lg bg-zinc-900 dark:bg-zinc-950">
			<div class="flex items-center gap-1.5 border-b border-zinc-700 px-2 py-1">
				<span class="h-2 w-2 rounded-full bg-zinc-600"></span>
				<span class="font-mono text-[9px] text-zinc-400">submit.py</span>
			</div>
			<pre class="overflow-auto p-2 font-mono text-[9.5px] leading-relaxed text-zinc-200">{snippet}</pre>
		</div>
	</div>

	<!-- ↓ writes -->
	<div class="flex flex-col items-center gap-0.5 py-1">
		<svg width="12" height="28" viewBox="0 0 12 28" aria-hidden="true">
			<line x1="6" y1="1" x2="6" y2="20" stroke="currentColor" stroke-width="1.5" stroke-dasharray="4 3" class="flow-v text-zinc-300 dark:text-zinc-600" />
			<polyline points="2,16 6,26 10,16" fill="none" stroke="currentColor" stroke-width="1.5" class="text-zinc-400 dark:text-zinc-500" />
		</svg>
		<span class="text-[9px] text-zinc-400">writes</span>
	</div>

	<!-- Storage -->
	<div class="rounded-xl border border-zinc-200 bg-white p-3 dark:border-zinc-700 dark:bg-zinc-900">
		<div class="flex items-center justify-between">
			<span class="text-[10px] font-semibold uppercase tracking-widest text-zinc-400">Storage</span>
			<span class="rounded-full border border-zinc-200 px-1.5 py-0.5 font-mono text-[10px] text-zinc-400 dark:border-zinc-700">parquet</span>
		</div>
		<div class="mt-1 truncate font-mono text-[10px] text-zinc-500 dark:text-zinc-400">/data/my-ngrams.parquet</div>
		<div class="mt-1.5 flex items-center gap-1 text-[10px] text-green-600 dark:text-green-500">
			<span>✓</span><span>types-counts format</span>
		</div>
	</div>

	<!-- ↑ reads (Storywrangler reads from storage) -->
	<div class="flex flex-col items-center gap-0.5 py-1">
		<svg width="12" height="28" viewBox="0 0 12 28" aria-hidden="true">
			<polyline points="2,12 6,2 10,12" fill="none" stroke="currentColor" stroke-width="1.5" class="text-zinc-400 dark:text-zinc-500" />
			<line x1="6" y1="8" x2="6" y2="27" stroke="currentColor" stroke-width="1.5" stroke-dasharray="4 3" class="flow-v-rev text-zinc-300 dark:text-zinc-600" />
		</svg>
		<span class="text-[9px] text-zinc-400">reads</span>
	</div>

	<!-- Platform -->
	<div class="overflow-hidden rounded-xl border-2 border-amber-200 bg-amber-50 dark:border-amber-900 dark:bg-amber-950/20">
		<div class="p-3 pb-2">
			<div class="text-[10px] font-semibold uppercase tracking-widest text-amber-600 dark:text-amber-500">Storywrangler platform</div>
			<div class="text-[11px] font-semibold text-zinc-700 dark:text-zinc-300">registry</div>
			<div class="mt-1.5 space-y-0.5 text-[10px] text-zinc-500 dark:text-zinc-400">
				<div class="flex items-center gap-1"><span class="text-green-500">✓</span> domain</div>
				<div class="flex items-center gap-1"><span class="text-green-500">✓</span> schema</div>
			</div>
			<div class="mt-1.5 font-mono text-[10px] text-zinc-400">catalog / domain / id</div>
		</div>
		<div class="border-t border-amber-200 bg-violet-50 p-3 pt-2 dark:border-amber-900 dark:bg-violet-950/20">
			<div class="flex items-center gap-1.5">
				<img src="/logos/rust.png" class="h-3 w-3 shrink-0 dark:invert" alt="Rust" />
				<div>
					<div class="text-[10px] font-semibold text-zinc-600 dark:text-zinc-400">allotaxonometer-core</div>
					<div class="text-[9px] text-zinc-400">independent crate · server-side</div>
				</div>
			</div>
		</div>
	</div>

	<!-- ↓ serves -->
	<div class="flex flex-col items-center gap-0.5 py-1">
		<svg width="12" height="28" viewBox="0 0 12 28" aria-hidden="true">
			<line x1="6" y1="1" x2="6" y2="20" stroke="currentColor" stroke-width="1.5" stroke-dasharray="4 3" class="flow-v text-zinc-300 dark:text-zinc-600" style="animation-delay:-0.5s" />
			<polyline points="2,16 6,26 10,16" fill="none" stroke="currentColor" stroke-width="1.5" class="text-zinc-400 dark:text-zinc-500" />
		</svg>
	</div>

	<!-- Destinations: 2-col grid for the two real apps, partner below -->
	<div class="grid grid-cols-2 gap-2">
		<a href="https://wikimedia.uvm.edu/allotax?mode=dates&granularity=daily&country=United+States&dateRange1Start=2025-06-22&dateRange1End=2025-06-23&dateRange2Start=2026-01-22&dateRange2End=2026-01-23&topN=100000&alphaIndex=4" target="_blank" rel="noopener noreferrer" class="overflow-hidden rounded-lg border border-zinc-200 bg-white transition-colors hover:border-zinc-400 dark:border-zinc-700 dark:bg-zinc-900 dark:hover:border-zinc-500">
			<img src="/wiki-allotax.png" alt="wikimedia allotaxonometer" class="h-28 w-full object-cover object-top" />
			<div class="px-2 py-1.5 text-[10px] font-medium text-zinc-600 dark:text-zinc-300">wikimedia.uvm.edu</div>
		</a>
		<a href="https://complexstories.uvm.edu/allotaxonometry" target="_blank" rel="noopener noreferrer" class="overflow-hidden rounded-lg border border-zinc-200 bg-white transition-colors hover:border-zinc-400 dark:border-zinc-700 dark:bg-zinc-900 dark:hover:border-zinc-500">
			<img src="/comp-allotax.png" alt="complex stories allotaxonometer" class="h-28 w-full object-cover object-top" />
			<div class="px-2 py-1.5 text-[10px] font-medium text-zinc-600 dark:text-zinc-300">complex-stories.uvm.edu</div>
		</a>
		<div class="col-span-2 rounded-lg border border-dashed border-zinc-200 bg-zinc-50 px-2.5 py-1.5 dark:border-zinc-700 dark:bg-zinc-800/50">
			<div class="text-[10px] text-zinc-400">Other partner groups...</div>
		</div>
	</div>

</div>

<!-- ═══ DESKTOP: horizontal diagram (hidden on mobile) ═══ -->
<div class="hidden md:block overflow-x-auto">
<div class="flex min-w-max items-stretch gap-3">

	<!-- ① Pipeline (left, full height) -->
	<div class="flex min-w-[22rem] flex-col gap-2 rounded-xl border border-dashed border-zinc-300 bg-zinc-50/50 p-3 dark:border-zinc-700 dark:bg-zinc-900/20">
		<div class="flex items-center justify-between">
			<span class="text-[10px] font-semibold uppercase tracking-widest text-zinc-400">Your pipeline</span>
			<span class="rounded-full border border-zinc-200 px-1.5 py-0.5 text-[10px] text-zinc-400 dark:border-zinc-700">external</span>
		</div>
		<div class="space-y-1">
			<div class="flex items-center gap-1 text-[10px]">
				<span class="font-medium text-amber-600 dark:text-amber-500">Bronze</span>
				<span class="text-zinc-300 dark:text-zinc-600">→</span>
				<span class="text-zinc-400">transform</span>
				<span class="text-zinc-300 dark:text-zinc-600">→</span>
				<span class="text-zinc-500 dark:text-zinc-400">Silver</span>
			</div>
			<div class="flex flex-wrap gap-1">
				<span class="rounded border border-sky-100 bg-sky-50 px-1.5 py-0.5 font-mono text-[10px] text-sky-700 dark:border-sky-900 dark:bg-sky-950/30 dark:text-sky-400">parquet</span>
				<span class="rounded border border-sky-100 bg-sky-50 px-1.5 py-0.5 font-mono text-[10px] text-sky-700 dark:border-sky-900 dark:bg-sky-950/30 dark:text-sky-400">ducklake</span>
				<span class="rounded border border-sky-100 bg-sky-50 px-1.5 py-0.5 font-mono text-[10px] text-sky-700 dark:border-sky-900 dark:bg-sky-950/30 dark:text-sky-400">duckdb</span>
			</div>
		</div>
		<div class="mt-auto overflow-hidden rounded-lg bg-zinc-900 dark:bg-zinc-950">
			<div class="flex items-center gap-1.5 border-b border-zinc-700 px-2 py-1">
				<span class="h-2 w-2 rounded-full bg-zinc-600"></span>
				<span class="font-mono text-[9px] text-zinc-400">submit.py</span>
			</div>
			<pre class="overflow-auto p-2 font-mono text-[9.5px] leading-relaxed text-zinc-200">{snippet}</pre>
		</div>
	</div>

	<!-- ② Right section -->
	<div class="flex flex-col">

		<!-- Storage row: writes → Storage -->
		<div class="flex items-center gap-2">
			<div class="flex w-14 shrink-0 flex-col items-center gap-0.5">
				<span class="text-[9px] text-zinc-400">writes</span>
				<svg width="28" height="10" viewBox="0 0 28 10" aria-hidden="true">
					<line x1="1" y1="5" x2="21" y2="5" stroke="currentColor" stroke-width="1.5" stroke-dasharray="3 2" class="flow-h text-zinc-300 dark:text-zinc-600" />
					<polyline points="17,1 25,5 17,9" fill="none" stroke="currentColor" stroke-width="1.5" class="text-zinc-400 dark:text-zinc-500" />
				</svg>
			</div>
			<div class="w-44 rounded-xl border border-zinc-200 bg-white p-3 dark:border-zinc-700 dark:bg-zinc-900">
				<div class="flex items-center justify-between">
					<span class="text-[10px] font-semibold uppercase tracking-widest text-zinc-400">Storage</span>
					<span class="rounded-full border border-zinc-200 px-1.5 py-0.5 font-mono text-[10px] text-zinc-400 dark:border-zinc-700">parquet</span>
				</div>
				<div class="mt-1 truncate font-mono text-[10px] text-zinc-500 dark:text-zinc-400">/data/my-ngrams.parquet</div>
				<div class="mt-1.5 flex items-center gap-1 text-[10px] text-green-600 dark:text-green-500">
					<span>✓</span><span>types-counts format</span>
				</div>
			</div>
		</div>

		<!-- Reads connector: ↑ centered under storage (Storywrangler reads) -->
		<div class="flex items-start gap-2">
			<div class="w-14 shrink-0"></div>
			<div class="flex w-44 flex-col items-center gap-0.5 py-1">
				<svg width="12" height="28" viewBox="0 0 12 28" aria-hidden="true">
					<polyline points="2,12 6,2 10,12" fill="none" stroke="currentColor" stroke-width="1.5" class="text-zinc-400 dark:text-zinc-500" />
					<line x1="6" y1="8" x2="6" y2="27" stroke="currentColor" stroke-width="1.5" stroke-dasharray="4 3" class="flow-v-rev text-zinc-300 dark:text-zinc-600" />
				</svg>
				<span class="text-[9px] text-zinc-400">reads</span>
			</div>
		</div>

		<!-- Platform row: registers → Platform → fan-out → destinations -->
		<div class="flex flex-1 items-stretch gap-2">

			<div class="flex w-14 shrink-0 flex-col items-center justify-center gap-0.5">
				<svg width="28" height="10" viewBox="0 0 28 10" aria-hidden="true">
					<line x1="1" y1="5" x2="21" y2="5" stroke="currentColor" stroke-width="1.5" stroke-dasharray="3 2" class="flow-h text-zinc-300 dark:text-zinc-600" style="animation-delay:-0.5s" />
					<polyline points="17,1 25,5 17,9" fill="none" stroke="currentColor" stroke-width="1.5" class="text-zinc-400 dark:text-zinc-500" />
				</svg>
				<span class="text-[9px] text-zinc-400">registers</span>
			</div>

			<!-- Platform -->
			<div class="w-44 overflow-hidden rounded-xl border-2 border-amber-200 bg-amber-50 dark:border-amber-900 dark:bg-amber-950/20">
				<div class="p-3 pb-2">
					<div class="text-[10px] font-semibold uppercase tracking-widest text-amber-600 dark:text-amber-500">Storywrangler platform</div>
					<div class="text-[11px] font-semibold text-zinc-700 dark:text-zinc-300">registry</div>
					<div class="mt-1.5 space-y-0.5 text-[10px] text-zinc-500 dark:text-zinc-400">
						<div class="flex items-center gap-1"><span class="text-green-500">✓</span> domain</div>
						<div class="flex items-center gap-1"><span class="text-green-500">✓</span> schema</div>
					</div>
					<div class="mt-1.5 font-mono text-[10px] text-zinc-400">catalog / domain / id</div>
				</div>
				<div class="border-t border-amber-200 bg-violet-50 p-3 pt-2 dark:border-amber-900 dark:bg-violet-950/20">
					<div class="flex items-center gap-1.5">
						<img src="/logos/rust.png" class="h-3 w-3 shrink-0 dark:invert" alt="Rust" />
						<div>
							<div class="text-[10px] font-semibold text-zinc-600 dark:text-zinc-400">allotaxonometer-core</div>
							<div class="text-[9px] text-zinc-400">independent crate · server-side</div>
						</div>
					</div>
				</div>
			</div>

			<!-- Fan-out arrows -->
			<div class="flex shrink-0 flex-col justify-around">
				<svg width="22" height="10" viewBox="0 0 22 10" aria-hidden="true">
					<line x1="1" y1="5" x2="15" y2="5" stroke="currentColor" stroke-width="1.5" stroke-dasharray="3 2" class="flow-h text-zinc-300 dark:text-zinc-600" style="animation-delay:-0.1s" />
					<polyline points="11,1 19,5 11,9" fill="none" stroke="currentColor" stroke-width="1.5" class="text-zinc-400 dark:text-zinc-500" />
				</svg>
				<svg width="22" height="10" viewBox="0 0 22 10" aria-hidden="true">
					<line x1="1" y1="5" x2="15" y2="5" stroke="currentColor" stroke-width="1.5" stroke-dasharray="3 2" class="flow-h text-zinc-300 dark:text-zinc-600" style="animation-delay:-0.5s" />
					<polyline points="11,1 19,5 11,9" fill="none" stroke="currentColor" stroke-width="1.5" class="text-zinc-400 dark:text-zinc-500" />
				</svg>
				<svg width="22" height="10" viewBox="0 0 22 10" aria-hidden="true">
					<line x1="1" y1="5" x2="15" y2="5" stroke="currentColor" stroke-width="1.5" stroke-dasharray="3 2" class="flow-h text-zinc-300 dark:text-zinc-600" style="animation-delay:-0.9s" />
					<polyline points="11,1 19,5 11,9" fill="none" stroke="currentColor" stroke-width="1.5" class="text-zinc-400 dark:text-zinc-500" />
				</svg>
			</div>

			<!-- Destinations -->
			<div class="flex flex-col justify-around gap-2">
				<a href="https://wikimedia.uvm.edu/allotax?mode=dates&granularity=daily&country=United+States&dateRange1Start=2025-06-22&dateRange1End=2025-06-23&dateRange2Start=2026-01-22&dateRange2End=2026-01-23&topN=100000&alphaIndex=4" target="_blank" rel="noopener noreferrer" class="overflow-hidden rounded-lg border border-zinc-200 bg-white transition-colors hover:border-zinc-400 dark:border-zinc-700 dark:bg-zinc-900 dark:hover:border-zinc-500">
					<img src="/wiki-allotax.png" alt="wikimedia allotaxonometer" class="h-20 w-full object-cover object-top" />
					<div class="px-2.5 py-1.5 text-[10px] font-medium text-zinc-600 dark:text-zinc-300">wikimedia.uvm.edu</div>
				</a>
				<div class="rounded-lg border border-dashed border-zinc-200 bg-zinc-50 px-2.5 py-1.5 dark:border-zinc-700 dark:bg-zinc-800/50">
					<div class="text-[10px] text-zinc-400">Other partner groups...</div>
				</div>
				<a href="https://complexstories.uvm.edu/allotaxonometry" target="_blank" rel="noopener noreferrer" class="overflow-hidden rounded-lg border border-zinc-200 bg-white transition-colors hover:border-zinc-400 dark:border-zinc-700 dark:bg-zinc-900 dark:hover:border-zinc-500">
					<img src="/comp-allotax.png" alt="complex stories allotaxonometer" class="h-20 w-full object-cover object-top" />
					<div class="px-2.5 py-1.5 text-[10px] font-medium text-zinc-600 dark:text-zinc-300">complex-stories.uvm.edu</div>
				</a>
			</div>

		</div>
	</div>

</div>
</div>

</div>

<style>
	@keyframes flow-h {
		to { stroke-dashoffset: -12; }
	}
	@keyframes flow-v {
		to { stroke-dashoffset: -14; }
	}
	@keyframes flow-v-rev {
		to { stroke-dashoffset: 14; }
	}
	.flow-h { animation: flow-h 1s linear infinite; }
	.flow-v { animation: flow-v 1.4s linear infinite; }
	.flow-v-rev { animation: flow-v-rev 1.4s linear infinite; }
</style>
