<script lang="ts">
	import * as TreeView from '$lib/components/ui/tree-view';
	import { Upload, Server, Monitor, Check } from '@lucide/svelte';
</script>

<div class="not-prose mt-6 flex flex-col md:hidden">

	<!-- Row 1: Submitter's Pipeline (full width) -->
	<div class="rounded-xl border border-zinc-200 bg-zinc-50 p-3 dark:border-zinc-800 dark:bg-zinc-900">
		<div class="flex items-center gap-2 mb-3">
			<div class="bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 flex h-7 w-7 items-center justify-center rounded-lg shrink-0">
				<Upload class="h-4 w-4" />
			</div>
			<p class="text-foreground text-xs font-semibold">Submitter's Pipeline</p>
		</div>
		<div class="text-xs">
			<TreeView.Root>
				<TreeView.Folder name="my-pipeline">
					<TreeView.Folder name="extract">
						<TreeView.File name="fetch.py" />
					</TreeView.Folder>
					<TreeView.Folder name="transform">
						<TreeView.File name="process.py" />
					</TreeView.Folder>
					<TreeView.Folder name="load">
						<TreeView.File name="submit.py" class="font-bold text-foreground" />
					</TreeView.Folder>
				</TreeView.Folder>
			</TreeView.Root>
		</div>
	</div>

	<!-- Connectors: register → Card 2, write → Card 3 -->
	<div class="relative h-10 text-muted-foreground">
		<div class="absolute left-1/4 -translate-x-1/2 flex flex-col items-center gap-0.5">
			<span class="text-[9px] font-mono">register</span>
			<svg width="12" height="14" viewBox="0 0 12 14" fill="none">
				<line x1="6" y1="0" x2="6" y2="10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
				<path d="M 3 7.5 L 6 11.5 L 9 7.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
			</svg>
		</div>
		<div class="absolute left-3/4 -translate-x-1/2 flex flex-col items-center gap-0.5">
			<span class="text-[9px] font-mono">write</span>
			<svg width="12" height="14" viewBox="0 0 12 14" fill="none">
				<line x1="6" y1="0" x2="6" y2="10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
				<path d="M 3 7.5 L 6 11.5 L 9 7.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
			</svg>
		</div>
	</div>

	<!-- Row 2: Platform (left) + Storage (right) -->
	<div class="grid grid-cols-2 gap-3">
		<!-- Card 2: Storywrangler Catalog -->
		<div class="border-border rounded-xl border p-3">
			<div class="flex items-center gap-2 mb-3">
				<div class="bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 flex h-7 w-7 items-center justify-center rounded-lg shrink-0">
					<Server class="h-4 w-4" />
				</div>
				<p class="text-foreground text-xs font-semibold">Storywrangler Catalog</p>
			</div>
			<ul class="text-muted-foreground text-[10px] space-y-1">
				<li class="flex items-start gap-1.5"><Check class="h-3 w-3 mt-0.5 shrink-0 text-foreground" />Schema validation on register</li>
				<li class="flex items-start gap-1.5"><Check class="h-3 w-3 mt-0.5 shrink-0 text-foreground" />Instrument wiring</li>
				<li class="flex items-start gap-1.5"><Check class="h-3 w-3 mt-0.5 shrink-0 text-foreground" />Ownership &amp; lineage tracking</li>
			</ul>
		</div>
		<!-- Card 3: Storage: Parquet -->
		<div class="border-border rounded-xl border p-3">
			<p class="text-foreground text-xs mb-3"><span class="font-semibold">Storage:</span> Parquet</p>
			<div class="flex items-start gap-3">
				<p class="text-muted-foreground text-[10px] min-w-0">Columnar Parquet files owned and managed by submitters. Supports flat files and hive-partitioned trees.</p>
				<img src="/parquet_folder.svg" alt="Parquet folder" class="h-10 shrink-0" />
			</div>
		</div>
	</div>

	<!-- Connector: serve (from Platform side) -->
	<div class="relative h-8 text-muted-foreground">
		<div class="absolute left-1/4 -translate-x-1/2 flex flex-col items-center">
			<svg width="12" height="14" viewBox="0 0 12 14" fill="none">
				<line x1="6" y1="0" x2="6" y2="10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
				<path d="M 3 7.5 L 6 11.5 L 9 7.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
			</svg>
		</div>
	</div>

	<!-- Row 3: Web Applications (full width) -->
	<div class="border-border rounded-xl border p-3">
		<div class="flex items-center gap-2 mb-3">
			<div class="bg-grey-100 dark:bg-grey-950 text-grey-600 dark:text-grey-400 flex h-7 w-7 items-center justify-center rounded-lg shrink-0">
				<Monitor class="h-4 w-4" />
			</div>
			<p class="text-foreground text-xs font-semibold">Web Applications</p>
		</div>
		<p class="text-muted-foreground text-[10px]">Feeds downstream applications like <a href="https://complexstories.uvm.edu">complex-stories</a> and <a href="https://wikimedia.uvm.edu">wikimedia.uvm.edu</a>, and surfaces queryable endpoints for any registered dataset.</p>
	</div>
</div>

<div class="not-prose mt-6 hidden md:block">
	<svg
		viewBox="0 0 700 300"
		xmlns="http://www.w3.org/2000/svg"
		class="w-full"
		role="img"
		aria-label="Architecture: Submitter pipeline registers with the platform and writes parquet to storage; the platform queries storage and serves web applications"
	>
		<defs>
			<marker id="arch-arrow" viewBox="0 0 10 10" refX="9" refY="5"
				markerWidth="4" markerHeight="4" orient="auto">
				<path d="M 0 1 L 9 5 L 0 9 Z" fill="var(--color-border)" />
			</marker>
		</defs>

		<rect x="10" y="10" width="185" height="280" rx="12" class="fill-zinc-50 stroke-zinc-200 dark:fill-zinc-900 dark:stroke-zinc-800" stroke-width="1" />
		<rect x="255" y="10" width="185" height="130" rx="12" fill="var(--color-card)" stroke="var(--color-border)" stroke-width="1" />
		<rect x="255" y="160" width="185" height="130" rx="12" fill="var(--color-card)" stroke="var(--color-border)" stroke-width="1" />
		<rect x="500" y="10" width="190" height="280" rx="12" fill="var(--color-card)" stroke="var(--color-border)" stroke-width="1" />

		<path d="M 196 75 H 250" stroke="var(--color-border)" stroke-width="1.5" stroke-linecap="round" fill="none" marker-end="url(#arch-arrow)" />
		<text x="223" y="68" text-anchor="middle" fill="var(--color-muted-foreground)" font-size="9" font-family="ui-monospace,monospace">register</text>
		<path d="M 196 225 H 250" stroke="var(--color-border)" stroke-width="1.5" stroke-linecap="round" fill="none" marker-end="url(#arch-arrow)" />
		<text x="223" y="218" text-anchor="middle" fill="var(--color-muted-foreground)" font-size="9" font-family="ui-monospace,monospace">write</text>
		<path d="M 347 141 V 154" stroke="var(--color-border)" stroke-width="1.5" stroke-linecap="round" fill="none" marker-end="url(#arch-arrow)" />
		<path d="M 441 75 C 476 75, 476 150, 494 150" stroke="var(--color-border)" stroke-width="1.5" stroke-linecap="round" fill="none" marker-end="url(#arch-arrow)" />

		<!-- Card 1: Submitter's Pipeline -->
		<foreignObject x="10" y="10" width="185" height="280">
			<div xmlns="http://www.w3.org/1999/xhtml" class="p-3 h-full">
				<div class="flex items-center gap-2 mb-3">
					<div class="bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 flex h-7 w-7 items-center justify-center rounded-lg shrink-0">
						<Upload class="h-4 w-4" />
					</div>
					<p class="text-foreground text-[10px] font-semibold">Submitter's Pipeline</p>
				</div>
				<div class="text-[10px]">
					<TreeView.Root>
						<TreeView.Folder name="my-pipeline">
							<TreeView.Folder name="extract">
								<TreeView.File name="fetch.py" />
							</TreeView.Folder>
							<TreeView.Folder name="transform">
								<TreeView.File name="process.py" />
							</TreeView.Folder>
							<TreeView.Folder name="load">
								<TreeView.File name="submit.py" class="font-bold text-foreground" />
							</TreeView.Folder>
						</TreeView.Folder>
					</TreeView.Root>
				</div>
			</div>
		</foreignObject>

		<!-- Card 2: Storywrangler Catalog -->
		<foreignObject x="255" y="10" width="185" height="130">
			<div xmlns="http://www.w3.org/1999/xhtml" class="p-3 h-full">
				<div class="flex items-center gap-2 mb-3">
					<div class="bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 flex h-7 w-7 items-center justify-center rounded-lg shrink-0">
						<Server class="h-4 w-4" />
					</div>
					<p class="text-foreground text-[10px] font-semibold">Storywrangler Catalog</p>
				</div>
				<ul class="text-muted-foreground text-[9px] space-y-1">
					<li class="flex items-start gap-1.5"><Check class="h-3 w-3 mt-0.5 shrink-0 text-foreground" />Instrument wiring</li>
					<li class="flex items-start gap-1.5"><Check class="h-3 w-3 mt-0.5 shrink-0 text-foreground" />Versioning</li>
					<li class="flex items-start gap-1.5"><Check class="h-3 w-3 mt-0.5 shrink-0 text-foreground" />Ownership &amp; lineage tracking</li>
					<li class="flex items-start gap-1.5"><Check class="h-3 w-3 mt-0.5 shrink-0 text-foreground" />Schema validation on register</li>
				</ul>
			</div>
		</foreignObject>

		<!-- Card 3: Storage: Parquet -->
		<foreignObject x="255" y="160" width="185" height="130">
			<div xmlns="http://www.w3.org/1999/xhtml" class="p-3 h-full">
				<p class="text-foreground text-[10px] mb-3"><span class="font-semibold">Storage:</span> Parquet</p>
				<div class="flex items-start gap-3">
					<p class="text-muted-foreground text-[9px] min-w-0">Parquet files can be stored on local disk or in object storage.</p>
					<img src="/parquet_folder.svg" alt="Parquet folder" class="h-10 shrink-0" />
				</div>
			</div>
		</foreignObject>

		<!-- Card 4: Web Applications -->
		<foreignObject x="500" y="10" width="190" height="280">
			<div xmlns="http://www.w3.org/1999/xhtml" class="p-3 h-full">
				<div class="flex items-center gap-2 mb-3">
					<div class="bg-grey-100 dark:bg-grey-950 text-grey-600 dark:text-grey-400 flex h-7 w-7 items-center justify-center rounded-lg shrink-0">
						<Monitor class="h-4 w-4" />
					</div>
					<p class="text-foreground text-[10px] font-semibold">Web Applications</p>
				</div>
				<p class="text-muted-foreground text-[9px]">Feeds downstream applications like complex-stories and wikimedia.uvm.edu, and surfaces queryable endpoints for any registered dataset.</p>
			</div>
		</foreignObject>
	</svg>
</div>
