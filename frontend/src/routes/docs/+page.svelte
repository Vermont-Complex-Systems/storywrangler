<script lang="ts">
	import * as Code from '$lib/components/ui/code';
	import { Upload, Server, Folder, Monitor } from '@lucide/svelte';

	const installCode = `uv add storywrangler-sdk`;

	const usageCode = `# Import the SDK and the client module
from storywrangler import Storywrangler, DatasetCreate

# Connect to the Storywrangler API 
client = Storywrangler(api_key='YOUR_API_KEY')

# A basic request to verify connection is working
me = client.users.whoami()

# Create a dataset
dataset = DatasetCreate(
	  catalog="vcsi",
    domain="babynames",
    dataset_id="ngrams",
    data_location="/mydata/babynames.parquet",
    data_format="parquet",
    description="Babynames frequencies by year and sex in the US.",
	  endpoint_schema={"type": "types-counts"},
	  transform={"filter_dimensions": ["year", "sex"]},
	  ownership={"owner_group": "vcsi", "contact": "vcsi@uvm.edu"},
    lineage={"repo": "https://github.com/Vermont-Complex-Systems/wikigrams"}
)

# Register
client.registry.register(dataset)`;

	const usageAllotax = `client.instrument.allotaxonomter(
	domain="babynames",
	dataset_id="ngrams",
	year="1925"
	year2="2025"
	sex="M"
	alpha=0.333,
	ngram_limit=1,
	wordshift_limit=1
)`

	const dataframeCode = `types,counts,year,sex
John,4394,1925,M
Robert,2559,1925,M
Axell,1956,1925,M
Donald,1565,1925,M
Peter,1464,1925,M
...`;
</script>


<div class="not-prose mt-10 mb-12 md:mt-20 md:mb-40 text-center">
	<h1 class="font-baskerville font-regular text-3xl md:text-5xl leading-snug tracking-tight mb-4 md:mb-5">
		Storywrangler is a decentralized data catalog for <span style="background: linear-gradient(transparent 75%, rgba(192, 132, 252, 0.35) 45%)">complex system instruments</span> and <span style="background: linear-gradient(transparent 75%, rgba(251, 146, 60, 0.35) 45%)">data governance</span>
	</h1>
	<p class="text-muted-foreground text-sm md:text-lg max-w-2xl mx-auto">
		Register your datasets once and unlock analytical tools out of the box. Built at the <a href="https://vermontcomplexsystems.org/" class="text-foreground underline underline-offset-4">Vermont Complex Systems Institute</a> to study collective attention as ecological timeseries, while improving data discoverability, ownership, and lineage tracking.
	</p>
</div>

{#snippet iconCorpora()}
	<path stroke-linecap="round" stroke-linejoin="round" d="M3.75 3v11.25A2.25 2.25 0 0 0 6 16.5h2.25M3.75 3h-1.5m1.5 0h16.5m0 0h1.5m-1.5 0v11.25A2.25 2.25 0 0 1 18 16.5h-2.25m-7.5 0h7.5m-7.5 0-1 3m8.5-3 1 3m0 0 .5 1.5m-.5-1.5h-9.5m0 0-.5 1.5m.75-9 3-3 2.148 2.148A12.061 12.061 0 0 1 16.5 7.605" />
{/snippet}

{#snippet iconLineage()}
	<path stroke-linecap="round" stroke-linejoin="round" d="M7.217 10.907a2.25 2.25 0 1 0 0 2.186m0-2.186c.18.324.283.696.283 1.093s-.103.77-.283 1.093m0-2.186 9.566-5.314m-9.566 7.5 9.566 5.314m0 0a2.25 2.25 0 1 0 3.935 2.186 2.25 2.25 0 0 0-3.935-2.186Zm0-12.814a2.25 2.25 0 1 0 3.933-2.185 2.25 2.25 0 0 0-3.933 2.185Z" />
{/snippet}

{#snippet iconInstruments()}
	<path stroke-linecap="round" stroke-linejoin="round" d="M11.42 15.17 17.25 21A2.652 2.652 0 0 0 21 17.25l-5.877-5.877M11.42 15.17l2.496-3.03c.317-.384.74-.626 1.208-.766M11.42 15.17l-4.655 5.653a2.548 2.548 0 1 1-3.586-3.586l5.654-4.654m5.65-4.65 3.029-2.497a.532.532 0 0 1 .765.766L12.873 9.63M11.42 15.17l1.453-1.453" />
{/snippet}

{#snippet iconInterop()}
	<path stroke-linecap="round" stroke-linejoin="round" d="M13.19 8.688a4.5 4.5 0 0 1 1.242 7.244l-4.5 4.5a4.5 4.5 0 0 1-6.364-6.364l1.757-1.757m13.35-.622 1.757-1.757a4.5 4.5 0 0 0-6.364-6.364l-4.5 4.5a4.5 4.5 0 0 0 1.242 7.244" />
{/snippet}

{#snippet iconGovernance()}
	<path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75 11.25 15 15 9.75m-3-7.036A11.959 11.959 0 0 1 3.598 6 11.99 11.99 0 0 0 3 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285Z" />
{/snippet}

{#snippet iconDiscover()}
	<path stroke-linecap="round" stroke-linejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
{/snippet}

<h2 class="font-baskerville font-regular text-xl md:text-4xl leading-snug tracking-tight mb-2 md:mb-5">Storywrangler's architecture</h2>

<p>
	Submitters write datasets as parquet files to shared storage and register their metadata via a simple POST request. The API validates schema compatibility and availability, wires datasets to instruments automatically where applicable, and records ownership, lineage, and discoverability. 
</p>

<div class="not-prose mt-6 flex flex-col md:hidden">

	<!-- Row 1: Submitter's Pipeline (full width) -->
	<div class="border-border rounded-xl border p-3 h-36 relative overflow-hidden group cursor-default">
		<div class="transition-opacity duration-200 group-hover:opacity-0 flex flex-col items-center justify-center h-full gap-2">
			<div class="bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 flex h-10 w-10 items-center justify-center rounded-xl">
				<Upload class="h-5 w-5" />
			</div>
			<p class="text-foreground text-xs font-semibold text-center">Submitter's Pipeline</p>
		</div>
		<div class="absolute inset-0 p-4 transition-opacity duration-200 opacity-0 group-hover:opacity-100 flex flex-col justify-center">
			<p class="text-foreground text-xs font-semibold mb-2">Submitter's Pipeline</p>
			<pre class="text-[10px] font-mono text-muted-foreground leading-relaxed m-0 bg-transparent border-0 p-0">my-pipeline/
├── extract/   fetch.py
├── transform/ process.py
└── load/      <span class="font-bold text-foreground">submit.py</span>  ← adapter script</pre>
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
		<!-- Card 2: Storywrangler Platform -->
		<div class="border-border rounded-xl border p-3 h-28 relative overflow-hidden group cursor-default">
			<div class="transition-opacity duration-200 group-hover:opacity-0 flex flex-col items-center justify-center h-full gap-2">
				<div class="bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 flex h-10 w-10 items-center justify-center rounded-xl">
					<Server class="h-5 w-5" />
				</div>
				<p class="text-foreground text-xs font-semibold text-center">Storywrangler Platform</p>
			</div>
			<div class="absolute inset-0 p-3 transition-opacity duration-200 opacity-0 group-hover:opacity-100 flex flex-col justify-center gap-1">
				<p class="text-foreground text-xs font-semibold mb-1">Storywrangler Platform</p>
				<p class="text-muted-foreground text-[10px]">Validates schemas and exposes instrument-ready API endpoints, querying Parquet directly at request time.</p>
			</div>
		</div>
		<!-- Card 3: Storage: Parquet -->
		<div class="border-border rounded-xl border p-3 h-28 relative overflow-hidden group cursor-default">
			<div class="transition-opacity duration-200 group-hover:opacity-0 flex flex-col items-center justify-center h-full gap-2">
				<div class="relative inline-flex items-end justify-center">
					<Folder class="h-10 w-10 text-zinc-300 dark:text-zinc-600" strokeWidth={1} />
					<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1000" class="absolute bottom-0.5 right-0.5 h-5 w-5">
						<path fill="rgb(85,168,237)" d="M 375.007812 498.863281 L 252.613281 586.578125 L 311.058594 646.273438 L 434.609375 549.871094 L 375.007812 498.863281 M 697.5625 267.691406 L 397.355469 482.84375 L 457.074219 532.34375 L 755.898438 299.246094 L 697.5625 267.691406 M 533.703125 288.480469 L 182.832031 515.363281 L 234.335938 567.949219 L 587.402344 321.589844 L 533.703125 288.480469 M 625.835938 228.910156 L 549.972656 277.96875 L 603.609375 310.28125 L 679.007812 257.667969 L 625.835938 228.910156 M 580.953125 467.296875 L 331.851562 667.496094 L 398.777344 735.796875 L 648.023438 515.363281 L 580.953125 467.296875 M 776.296875 310.28125 L 599.765625 452.175781 L 666.679688 498.863281 L 840.589844 345.050781 L 776.296875 310.28125 M 361.859375 310.28125 L 120.9375 452.175781 L 166.691406 498.886719 L 410.378906 345.050781 L 361.859375 310.28125 M 863.109375 357.246094 L 422.683594 760.230469 L 500 839.164062 L 934.320312 395.761719 L 863.109375 357.246094 M 560.242188 193.421875 L 380.597656 299.246094 L 429.210938 333.164062 L 608.90625 219.742188 L 560.242188 193.421875 M 500 160.835938 L 544.703125 185.03125 L 106.554688 437.488281 L 65.679688 395.761719 Z M 500 160.835938" />
					</svg>
				</div>
				<p class="text-foreground text-xs font-semibold">Storage: Parquet</p>
			</div>
			<div class="absolute inset-0 p-3 transition-opacity duration-200 opacity-0 group-hover:opacity-100 flex flex-col justify-center gap-1">
				<p class="text-foreground text-xs font-semibold mb-1">Storage: Parquet</p>
				<p class="text-muted-foreground text-[10px]">Columnar Parquet files owned and managed by submitters. Supports flat files and hive-partitioned trees.</p>
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
	<div class="border-border rounded-xl border p-3 h-36 relative overflow-hidden group cursor-default">
		<div class="transition-opacity duration-200 group-hover:opacity-0 flex flex-col items-center justify-center h-full gap-2">
			<div class="bg-orange-100 dark:bg-orange-950 text-orange-600 dark:text-orange-400 flex h-10 w-10 items-center justify-center rounded-xl">
				<Monitor class="h-5 w-5" />
			</div>
			<p class="text-foreground text-xs font-semibold text-center">Web Applications</p>
		</div>
		<div class="absolute inset-0 p-3 transition-opacity duration-200 opacity-0 group-hover:opacity-100 flex flex-col justify-center gap-1">
			<p class="text-foreground text-xs font-semibold mb-1">Web Applications</p>
			<p class="text-muted-foreground text-[10px]">Feeds downstream applications like <a href="https://complexstories.uvm.edu">complex-stories</a> and <a href="https://wikimedia.uvm.edu">wikimedia.uvm.edu</a>, and surfaces queryable endpoints for any registered dataset.</p>
		</div>
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

		<rect x="10" y="10" width="185" height="280" rx="12" fill="var(--color-card)" stroke="var(--color-border)" stroke-width="1" />
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
			<div xmlns="http://www.w3.org/1999/xhtml" class="p-3 h-full relative overflow-hidden group cursor-default">
				<div class="transition-opacity duration-200 group-hover:opacity-0 flex flex-col items-center justify-center h-full gap-2">
					<div class="bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 flex h-10 w-10 items-center justify-center rounded-xl">
						<Upload class="h-5 w-5" />
					</div>
					<p class="text-foreground text-[10px] font-semibold text-center">Submitter's Pipeline</p>
				</div>
				<div class="absolute inset-0 p-4 transition-opacity duration-200 opacity-0 group-hover:opacity-100 flex flex-col justify-center">
					<p class="text-foreground text-[10px] font-semibold mb-2">Submitter's Pipeline</p>
					<pre class="text-[10px] font-mono text-muted-foreground leading-relaxed m-0 bg-transparent border-0 p-0">my-pipeline/
├── extract/
│   └── fetch.py
├── transform/
│   └── process.py
└── load/
    └── <span class="font-bold text-foreground">submit.py</span>
       ← adapter script</pre>
				</div>
			</div>
		</foreignObject>

		<!-- Card 2: Storywrangler Platform -->
		<foreignObject x="255" y="10" width="185" height="130">
			<div xmlns="http://www.w3.org/1999/xhtml" class="p-3 h-full relative overflow-hidden group cursor-default">
				<div class="transition-opacity duration-200 group-hover:opacity-0 flex flex-col items-center justify-center h-full gap-2">
					<div class="bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 flex h-10 w-10 items-center justify-center rounded-xl">
						<Server class="h-5 w-5" />
					</div>
					<p class="text-foreground text-[10px] font-semibold text-center">Storywrangler Platform</p>
				</div>
				<div class="absolute inset-0 p-3 transition-opacity duration-200 opacity-0 group-hover:opacity-100 flex flex-col justify-center gap-1">
					<p class="text-foreground text-[10px] font-semibold mb-1">Storywrangler Platform</p>
					<p class="text-muted-foreground text-[9px]">Validates schemas and exposes instrument-ready API endpoints, querying Parquet directly at request time.</p>
				</div>
			</div>
		</foreignObject>

		<!-- Card 3: Storage: Parquet -->
		<foreignObject x="255" y="160" width="185" height="130">
			<div xmlns="http://www.w3.org/1999/xhtml" class="p-3 h-full relative overflow-hidden group cursor-default">
				<div class="transition-opacity duration-200 group-hover:opacity-0 flex flex-col items-center justify-center h-full gap-2">
					<div class="relative inline-flex items-end justify-center">
						<Folder class="h-16 w-16 text-zinc-300 dark:text-zinc-600" strokeWidth={1}/>
						<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1000" class="absolute bottom-3.5 right-4.5 h-7 w-7">
							<path fill="rgb(85,168,237)" d="M 375.007812 498.863281 L 252.613281 586.578125 L 311.058594 646.273438 L 434.609375 549.871094 L 375.007812 498.863281 M 697.5625 267.691406 L 397.355469 482.84375 L 457.074219 532.34375 L 755.898438 299.246094 L 697.5625 267.691406 M 533.703125 288.480469 L 182.832031 515.363281 L 234.335938 567.949219 L 587.402344 321.589844 L 533.703125 288.480469 M 625.835938 228.910156 L 549.972656 277.96875 L 603.609375 310.28125 L 679.007812 257.667969 L 625.835938 228.910156 M 580.953125 467.296875 L 331.851562 667.496094 L 398.777344 735.796875 L 648.023438 515.363281 L 580.953125 467.296875 M 776.296875 310.28125 L 599.765625 452.175781 L 666.679688 498.863281 L 840.589844 345.050781 L 776.296875 310.28125 M 361.859375 310.28125 L 120.9375 452.175781 L 166.691406 498.886719 L 410.378906 345.050781 L 361.859375 310.28125 M 863.109375 357.246094 L 422.683594 760.230469 L 500 839.164062 L 934.320312 395.761719 L 863.109375 357.246094 M 560.242188 193.421875 L 380.597656 299.246094 L 429.210938 333.164062 L 608.90625 219.742188 L 560.242188 193.421875 M 500 160.835938 L 544.703125 185.03125 L 106.554688 437.488281 L 65.679688 395.761719 Z M 500 160.835938" />
						</svg>
					</div>
					<p class="text-foreground text-[10px] font-semibold">Storage: Parquet</p>
				</div>
				<div class="absolute inset-0 p-3 transition-opacity duration-200 opacity-0 group-hover:opacity-100 flex flex-col justify-center gap-1">
					<p class="text-foreground text-[10px] font-semibold mb-1">Storage: Parquet</p>
					<p class="text-muted-foreground text-[9px]">Columnar Parquet files owned and managed by submitters. Supports flat files and hive-partitioned trees.</p>
				</div>
			</div>
		</foreignObject>

		<!-- Card 4: Web Applications -->
		<foreignObject x="500" y="10" width="190" height="280">
			<div xmlns="http://www.w3.org/1999/xhtml" class="p-3 h-full relative overflow-hidden group cursor-default">
				<div class="transition-opacity duration-200 group-hover:opacity-0 flex flex-col items-center justify-center h-full gap-2">
					<div class="bg-orange-100 dark:bg-orange-950 text-orange-600 dark:text-orange-400 flex h-10 w-10 items-center justify-center rounded-xl">
						<Monitor class="h-5 w-5" />
					</div>
					<p class="text-foreground text-[10px] font-semibold text-center">Web Applications</p>
				</div>
				<div class="absolute inset-0 p-3 transition-opacity duration-200 opacity-0 group-hover:opacity-100 flex flex-col justify-center gap-1">
					<p class="text-foreground text-[10px] font-semibold mb-1">Web Applications</p>
					<p class="text-muted-foreground text-[9px]">Feeds downstream applications like complex-stories and wikimedia.uvm.edu, and surfaces queryable endpoints for any registered dataset.</p>
				</div>
			</div>
		</foreignObject>
	</svg>
</div>

<h2 class="font-baskerville font-regular text-xl md:text-4xl leading-snug tracking-tight mb-2 md:mb-5">Storywrangler's key features</h2>

<p>
	The platform is a digital commons, where participants can nurture our collective data garden, learn about each others' work, tied together by the common theme of using complex system tools. 
</p>

<div class="not-prose mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
	{#each [
		{
			icon: iconCorpora,
			color: 'purple',
			title: 'Text as Ecological Signal',
			body: 'Social media (Bluesky, Reddit, Twitter), news outlets, Wikipedia, and higher education are treated as ecological time series — living records of how collective attention shifts across populations and over time.',
		},
		{
			icon: iconInstruments,
			color: 'purple',
			title: 'Analysis-Ready Instruments',
			body: 'The allotaxonometer and other VCSI tools become available the moment a dataset is registered. The schema contract is the wiring — no per-dataset integration work required.',
		},
		{
			icon: iconInterop,
			color: 'purple',
			title: 'Interoperability by Design',
			body: 'Datasets declare their query axes and output shape once. The platform bridges heterogeneous identifier namespaces — Wikidata, OpenAlex, local IDs — through a unified entity graph.',
		},
		{
			icon: iconGovernance,
			color: 'orange',
			title: 'Selective Sharing & Succession',
			body: 'Fine-grained access control means datasets that cannot be fully open can still be shared: expose aggregate results only, a filtered row subset, or full access per collaborator. Ownership succession ensures datasets survive student turnover.',
		},
		{
			icon: iconDiscover,
			color: 'orange',
			title: 'Discoverable Analysis',
			body: "Search the registry to find datasets that are already instrument-ready. The schema contract tells you not just where the data lives, but what analyses are immediately available — discovery and reproducibility are the same guarantee.",
		},
		{
			icon: iconLineage,
			color: 'orange',
			title: 'Lineage & Impact',
			body: 'Downstream groups that build on your data register their dependency in the registry. Their work appears in your impact record automatically — research credit propagates without either group coordinating directly.',
		},
	] as card (card.title)}
		<div class="border-border rounded-lg border p-5 flex flex-col gap-3">
			<div class={[
				'flex h-9 w-9 items-center justify-center rounded-md',
				card.color === 'purple'
					? 'bg-purple-100 dark:bg-purple-950 text-purple-600 dark:text-purple-400'
					: 'bg-orange-100 dark:bg-orange-950 text-orange-600 dark:text-orange-400'
			]}>
				<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="h-5 w-5" aria-hidden="true">
					{@render card.icon()}
				</svg>
			</div>
			<p class="text-foreground text-sm font-semibold">{card.title}</p>
			<p class="text-muted-foreground text-sm leading-relaxed">{card.body}</p>
		</div>
	{/each}
</div>

<h2 class="font-baskerville font-regular text-xl md:text-4xl leading-snug tracking-tight mb-2 md:mb-5">Getting started</h2>

<div class="not-prose mb-6 flex gap-3 rounded-lg border border-amber-200 bg-amber-50 p-4 dark:border-amber-800 dark:bg-amber-950/40">
	<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="mt-0.5 h-5 w-5 shrink-0 text-amber-600 dark:text-amber-400" aria-hidden="true">
		<path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
	</svg>
	<div class="text-sm text-amber-800 dark:text-amber-200">
		<p class="font-semibold">Beta release — manual account provisioning</p>
		<p class="mt-1 leading-relaxed">
			Account creation is not yet self-serve. To get access, contact the VCSI team to have an account created and your API key issued. The key should then be stored in your <code class="rounded bg-amber-100 px-1 dark:bg-amber-900">API_KEY</code> environment variable.
		</p>
	</div>
</div>

<p>The registration process is a simple POST request documented <a href="/docs/api-reference/registry/post-registry-register">here</a>.</p>

<p>We also provide an SDK to ease the use of the platform, which we recommend to install with <a href="https://docs.astral.sh/uv/">uv</a> (or pip):</p>

<Code.Root code={installCode} lang="bash" hideLines={true}>
	<Code.CopyButton />
</Code.Root>

<p>
	Once you have your username and password, call <code>Storywrangler.login()</code> (or <code>POST /auth/login</code>)
	to get your <code>api_key</code>. Save that key — on subsequent runs you can pass it
	directly or store it in the <code>API_KEY</code> environment variable to avoid logging in again. Using the python SDK:
</p>

<Code.Root code={usageCode} lang="python">
	<Code.CopyButton />
</Code.Root>

<p>You can find a walkthrough of the <code>types-counts</code> API schema that the allotaxonometer expects in <a href="/docs/register">Registering a dataset</a>. In this case, we are telling the API that the dataset has the following shape and is available at the <code>data/</code> location:</p>

<Code.Root code={dataframeCode} hideLines={true} />

<p>Provided the registration is successful, you can now share your analysis of babynames with anyone on earth using:</p>

<Code.Root code={usageAllotax} lang="python">
	<Code.CopyButton />
</Code.Root>

<p>Under the hood, we are versioning the interaction of the allotaxonometer tool and the submitted babynames pipeline for reproducibility.</p>

<div class="not-prose mb-12 flex gap-3 rounded-lg border border-amber-200 bg-amber-50 p-4 dark:border-amber-800 dark:bg-amber-950/40">
	<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="mt-0.5 h-5 w-5 shrink-0 text-amber-600 dark:text-amber-400" aria-hidden="true">
		<path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
	</svg>
	<div class="text-sm text-amber-800 dark:text-amber-200">
		<p class="font-semibold">Making your data accessible</p>
		<p class="mt-1 leading-relaxed">
			We are still working to find the best way for the API to easily access external datasets. At the moment, the API can serve groups at the University of Vermont by accessing the netfiles shared storage system. It is not an automatic process yet. The research VM where the platform is hosted needs the permission to mount the relevant netfiles before accessing it. Alternatively, one could use low-cost <a href="https://aws.amazon.com/s3/pricing/?loc=ft#AWS_Free_Tier">S3 buckets</a> to make their parquet files accessible to the platform. 
		</p>
	</div>
</div>
 

<p>We are also offering utilities for increased discoverability and interoperability. For instance, submitters might have babynames data from all over the world. While registering "country" as <code>filter_dimensions</code> is directly usable, it decreases overall discoverability because the platform remains agnostic of what is going in the <code>filter_dimensions</code>. Instead, the users can submit their <code>entity_mapping</code> where they provide the link between their local ids and identifiers part of our global namespace (see <a href="/docs/specification">Storywrangler Specifications</a>). See our more detailed <a href="/docs/register">Registering a dataset</a> section to see how the registration of entity mapping is done.</p>

<h2 class="font-baskerville font-regular text-xl md:text-4xl leading-snug tracking-tight mb-2 md:mb-5">Next steps</h2>

<ul>
	<li><a href="/docs/case-studies/wikimedia">Wikimedia case study</a> — How we are using Storywrangler internally to make our Wikimedia pipeline available to all.</li>
</ul>

<style>
	h2 {
		margin-top: 8rem !important;
	}
</style>
