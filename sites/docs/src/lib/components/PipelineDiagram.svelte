<div class="not-prose my-8 space-y-2 text-xs">

	<!-- ① Group pipeline -->
	<div
		class="rounded-xl border border-dashed border-zinc-300 bg-zinc-50/50 p-4 dark:border-zinc-700 dark:bg-zinc-900/20"
	>
		<div class="mb-3 flex items-center justify-between">
			<span class="text-[10px] font-semibold uppercase tracking-widest text-zinc-400"
				>Group pipeline</span
			>
			<span
				class="rounded-full border border-zinc-200 px-2 py-0.5 text-[10px] text-zinc-400 dark:border-zinc-700"
				>external</span
			>
		</div>

		<div class="flex flex-wrap items-center gap-2">
			<!-- Step 1: Source -->
			<a
				href="/docs/design#medallion-tiers"
				class="rounded-lg border border-zinc-200 bg-white px-3 py-2 transition-colors hover:border-zinc-300 dark:border-zinc-700 dark:bg-zinc-900 dark:hover:border-zinc-500"
			>
				<div class="text-[10px] font-semibold uppercase tracking-widest text-amber-700 dark:text-amber-500">Bronze</div>
				<div class="font-semibold text-zinc-700 dark:text-zinc-300">
					Wiki Enterprise dumps
				</div>
				<div class="mt-0.5 text-zinc-400">&gt;100 GB / day</div>
			</a>

			<!-- Rust connector -->
			<div class="flex items-center gap-1.5">
				<svg width="16" height="10" viewBox="0 0 16 10" aria-hidden="true">
					<line
						x1="1"
						y1="5"
						x2="14"
						y2="5"
						stroke="currentColor"
						stroke-width="1.5"
						stroke-dasharray="4 2"
						class="flow-h text-zinc-300 dark:text-zinc-600"
					/>
				</svg>
				<span
					class="inline-flex items-center gap-1 rounded-md border border-orange-200 bg-orange-50 px-2 py-1 font-medium text-orange-700 dark:border-orange-900 dark:bg-orange-950/30 dark:text-orange-400"
				>
					<img src="/logos/rust.png" class="h-3 w-3 dark:invert" alt="Rust" />
					tokenizer
				</span>
				<svg width="22" height="10" viewBox="0 0 22 10" aria-hidden="true">
					<line
						x1="1"
						y1="5"
						x2="16"
						y2="5"
						stroke="currentColor"
						stroke-width="1.5"
						stroke-dasharray="4 2"
						class="flow-h text-zinc-300 dark:text-zinc-600"
						style="animation-delay:-0.4s"
					/>
					<polyline
						points="12,1 20,5 12,9"
						fill="none"
						stroke="currentColor"
						stroke-width="1.5"
						class="text-zinc-400 dark:text-zinc-500"
					/>
				</svg>
			</div>

			<!-- Step 2: Article JSON -->
			<div
				class="rounded-lg border border-zinc-200 bg-white px-3 py-2 dark:border-zinc-700 dark:bg-zinc-900"
			>
				<div class="font-semibold text-zinc-700 dark:text-zinc-300">
					Ngrams by section
				</div>
				<div class="mt-0.5 text-zinc-400">80 GB JSON / day</div>
			</div>

			<!-- DuckDB connector (collapsed: daily count + aggregate) -->
			<div class="flex items-center gap-1.5">
				<svg width="16" height="10" viewBox="0 0 16 10" aria-hidden="true">
					<line
						x1="1"
						y1="5"
						x2="14"
						y2="5"
						stroke="currentColor"
						stroke-width="1.5"
						stroke-dasharray="4 2"
						class="flow-h text-zinc-300 dark:text-zinc-600"
						style="animation-delay:-0.35s"
					/>
				</svg>
				<span
					class="inline-flex items-center gap-1 rounded-md border border-sky-200 bg-sky-50 px-2 py-1 font-medium text-sky-700 dark:border-sky-900 dark:bg-sky-950/30 dark:text-sky-400"
				>
					<img src="/logos/duckdb.png" class="h-3" alt="DuckDB" />
					count
				</span>
				<svg width="22" height="10" viewBox="0 0 22 10" aria-hidden="true">
					<line
						x1="1"
						y1="5"
						x2="16"
						y2="5"
						stroke="currentColor"
						stroke-width="1.5"
						stroke-dasharray="4 2"
						class="flow-h text-zinc-300 dark:text-zinc-600"
						style="animation-delay:-0.7s"
					/>
					<polyline
						points="12,1 20,5 12,9"
						fill="none"
						stroke="currentColor"
						stroke-width="1.5"
						class="text-zinc-400 dark:text-zinc-500"
					/>
				</svg>
			</div>

			<!-- Step 3: Silver dataset (collapsed) -->
			<a
				href="/docs/design#medallion-tiers"
				class="rounded-lg border border-zinc-200 bg-white px-3 py-2 transition-colors hover:border-zinc-300 dark:border-zinc-700 dark:bg-zinc-900 dark:hover:border-zinc-500"
			>
				<div class="text-[10px] font-semibold uppercase tracking-widest text-zinc-400 dark:text-zinc-500">Silver</div>
				<div class="mt-1 text-zinc-500 dark:text-zinc-400">
					<code class="text-zinc-600 dark:text-zinc-300">wikimedia/ngrams</code>
				</div>
				<div class="mt-0.5 text-zinc-400">day / week / month</div>
			</a>
		</div>

		<!-- Adapter strip: runs locally before the group submits -->
		<div
			class="mt-3 flex items-center gap-2 rounded-md border border-green-100 bg-green-50 px-3 py-2 dark:border-green-900/40 dark:bg-green-950/20"
		>
			<svg
				class="h-3 w-3 shrink-0 text-green-500"
				viewBox="0 0 16 16"
				fill="currentColor"
				aria-hidden="true"
			>
				<path
					d="M13.854 3.646a.5.5 0 0 1 0 .708l-7 7a.5.5 0 0 1-.708 0l-3.5-3.5a.5.5 0 1 1 .708-.708L6.5 10.293l6.646-6.647a.5.5 0 0 1 .708 0z"
				/>
			</svg>
			<a
				href="/docs/specification"
				class="text-zinc-500 transition-colors hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200"
				>Storywrangler adapter — validates <code class="text-zinc-600 dark:text-zinc-300"
					>types-counts</code
				> contract before submit</a
			>
		</div>
	</div>

	<!-- Two connectors: left=writes parquet, right=adapter checkpoint→registers metadata -->
	<!-- flex-1 left | w-10 spacer (matches horizontal arrow) | flex-1 right -->
	<div class="flex gap-2 px-0">
		<!-- Left: plain write -->
		<div class="flex flex-1 flex-col items-center gap-0.5 py-1">
			<svg width="12" height="40" viewBox="0 0 12 40" aria-hidden="true">
				<line
					x1="6"
					y1="1"
					x2="6"
					y2="32"
					stroke="currentColor"
					stroke-width="1.5"
					stroke-dasharray="4 3"
					class="flow-v text-zinc-300 dark:text-zinc-600"
				/>
				<polyline
					points="2,28 6,38 10,28"
					fill="none"
					stroke="currentColor"
					stroke-width="1.5"
					class="text-zinc-400 dark:text-zinc-500"
				/>
			</svg>
			<span class="text-[10px] text-zinc-400">writes parquet</span>
		</div>
		<div class="w-10 shrink-0"></div>
		<!-- Right: registers metadata -->
		<div class="flex flex-1 flex-col items-center py-1">
			<svg width="12" height="24" viewBox="0 0 12 24" aria-hidden="true">
				<line
					x1="6"
					y1="1"
					x2="6"
					y2="24"
					stroke="currentColor"
					stroke-width="1.5"
					stroke-dasharray="4 3"
					class="flow-v text-zinc-300 dark:text-zinc-600"
					style="animation-delay:-0.5s"
				/>
			</svg>
			<a href="/docs/reference" class="whitespace-nowrap rounded-full border border-zinc-200 px-2 py-0.5 text-[10px] text-zinc-400 transition-colors hover:border-zinc-400 hover:text-zinc-600 dark:border-zinc-700 dark:hover:border-zinc-500 dark:hover:text-zinc-300">registers metadata</a>
			<svg width="12" height="20" viewBox="0 0 12 20" aria-hidden="true">
				<line
					x1="6"
					y1="0"
					x2="6"
					y2="12"
					stroke="currentColor"
					stroke-width="1.5"
					stroke-dasharray="4 3"
					class="flow-v text-zinc-300 dark:text-zinc-600"
					style="animation-delay:-0.5s"
				/>
				<polyline
					points="2,8 6,18 10,8"
					fill="none"
					stroke="currentColor"
					stroke-width="1.5"
					class="text-zinc-400 dark:text-zinc-500"
				/>
			</svg>
		</div>
	</div>

	<!-- ② Middle row: netfiles ──reads──► Storywrangler -->
	<div class="flex items-stretch gap-2">
		<!-- netfiles -->
		<a
			href="docs/register#choosing-a-storage-format"
			class="flex min-w-0 flex-1 flex-col gap-2 rounded-xl border border-zinc-200 bg-white p-3 transition-colors hover:border-zinc-300 dark:border-zinc-700 dark:bg-zinc-900 dark:hover:border-zinc-500"
		>
			<div class="flex items-center justify-between">
				<span class="text-[10px] font-semibold uppercase tracking-widest text-zinc-400">Storage</span>
				<span class="rounded-full border border-zinc-200 px-2 py-0.5 font-mono text-[10px] text-zinc-400 dark:border-zinc-700">parquet_hive</span>
			</div>
			<div class="font-semibold text-zinc-700 dark:text-zinc-300">netfiles</div>
			<div class="mt-auto space-y-0.5 text-zinc-400">
				<div class="truncate font-mono text-[10px]">/wikimedia/ngrams/</div>
				<div>day / week / month partitions</div>
				<div class="inline-flex items-center gap-1">
					<img src="/logos/duckdb.png" class="h-3" alt="DuckDB" />
					zone map index
				</div>
			</div>
		</a>

		<!-- Horizontal arrow: Storywrangler ←reads← netfiles -->
		<div class="flex w-10 shrink-0 flex-col items-center justify-center gap-1">
			<svg width="36" height="12" viewBox="0 0 36 12" aria-hidden="true">
				<line
					x1="35"
					y1="6"
					x2="8"
					y2="6"
					stroke="currentColor"
					stroke-width="1.5"
					stroke-dasharray="4 2"
					class="flow-h-rev text-zinc-300 dark:text-zinc-600"
					style="animation-delay:-0.8s"
				/>
				<polyline
					points="12,2 2,6 12,10"
					fill="none"
					stroke="currentColor"
					stroke-width="1.5"
					class="text-zinc-400 dark:text-zinc-500"
				/>
			</svg>
			<span class="text-[9px] leading-none text-zinc-400">reads</span>
		</div>

		<!-- Storywrangler + allotax -->
		<a
			href="/docs/object-model"
			class="flex flex-1 flex-col gap-2 rounded-xl border-2 border-amber-200 bg-amber-50 p-3 transition-colors hover:border-amber-300 dark:border-amber-900 dark:bg-amber-950/20 dark:hover:border-amber-700"
		>
			<div
				class="text-[10px] font-semibold uppercase tracking-widest text-amber-600 dark:text-amber-500"
			>
				Storywrangler
			</div>
			<div class="font-semibold text-zinc-700 dark:text-zinc-300">registry</div>
			<div class="text-zinc-500 dark:text-zinc-400">
				<code class="text-zinc-600 dark:text-zinc-300">wikimedia/ngrams</code> ✓
			</div>
			<div class="text-[10px] text-zinc-400">domain + schema enforced on receive</div>
			<div
				class="mt-auto flex items-center gap-1.5 rounded-md border border-dashed border-zinc-300 bg-zinc-50 px-2 py-1.5 dark:border-zinc-600 dark:bg-zinc-800/50"
			>
				<img src="/logos/rust.png" class="h-3 w-3 shrink-0 dark:invert" alt="Rust" />
				<div>
					<div class="text-zinc-600 dark:text-zinc-400">calls allotaxonometer-core</div>
					<div class="text-[10px] text-zinc-400">independent crate · server-side</div>
				</div>
			</div>
		</a>
	</div>

	<!-- Connector from Storywrangler down — aligned with right column -->
	<div class="flex gap-2">
		<div class="flex-1"></div>
		<div class="w-10 shrink-0"></div>
		<div class="flex flex-1 flex-col items-center gap-0.5 py-1">
			<svg width="12" height="40" viewBox="0 0 12 40" aria-hidden="true">
				<line
					x1="6"
					y1="1"
					x2="6"
					y2="32"
					stroke="currentColor"
					stroke-width="1.5"
					stroke-dasharray="4 3"
					class="flow-v text-zinc-300 dark:text-zinc-600"
					style="animation-delay:-1.1s"
				/>
				<polyline
					points="2,28 6,38 10,28"
					fill="none"
					stroke="currentColor"
					stroke-width="1.5"
					class="text-zinc-400 dark:text-zinc-500"
				/>
			</svg>
			<span class="text-[10px] text-zinc-400">JSON results</span>
		</div>
	</div>

	<!-- ③ Frontend — aligned with right column (Storywrangler) -->
	<div class="flex gap-2">
		<div class="flex-1"></div>
		<div class="w-10 shrink-0"></div>
		<div
			class="flex flex-1 flex-col rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-700 dark:bg-zinc-900"
		>
			<div class="mb-1.5 flex items-center justify-between">
				<span class="text-[10px] font-semibold uppercase tracking-widest text-zinc-400"
					>Frontend</span
				>
				<img src="/logos/svelte.svg" class="h-3.5 w-3.5" alt="Svelte" />
			</div>
			<div class="font-semibold text-zinc-700 dark:text-zinc-300">wikimedia.uvm.edu</div>
			<div class="mt-1 text-zinc-400">on-the-fly aggregation · any time range · no download</div>
			<div class="mt-3 border-t border-zinc-100 pt-2 dark:border-zinc-800">
				<div class="mb-1.5 text-[10px] text-zinc-400">
					interoperable — same instrument on any <code>types-counts</code> dataset:
				</div>
				<div class="flex flex-wrap gap-1">
					<span
						class="rounded-full border border-zinc-300 px-2 py-0.5 font-medium text-zinc-600 dark:border-zinc-600 dark:text-zinc-300"
						>Wikimedia</span
					>
					<span
						class="rounded-full border border-zinc-200 px-2 py-0.5 text-zinc-400 dark:border-zinc-700"
						>Bluesky</span
					>
					<span
						class="rounded-full border border-zinc-200 px-2 py-0.5 text-zinc-400 dark:border-zinc-700"
						>Reddit</span
					>
					<span
						class="rounded-full border border-dashed border-zinc-200 px-2 py-0.5 text-zinc-300 dark:border-zinc-700"
						>…</span
					>
				</div>
			</div>
		</div>
	</div>
</div>

<style>
	@keyframes flow-h {
		to {
			stroke-dashoffset: -12;
		}
	}
	@keyframes flow-v {
		to {
			stroke-dashoffset: -14;
		}
	}
	.flow-h {
		animation: flow-h 1s linear infinite;
	}
	@keyframes flow-h-rev {
		to {
			stroke-dashoffset: 12;
		}
	}
	.flow-h-rev {
		animation: flow-h-rev 1s linear infinite;
	}
	.flow-v {
		animation: flow-v 1.4s linear infinite;
	}
</style>
