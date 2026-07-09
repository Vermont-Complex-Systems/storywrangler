<script lang="ts">
	import * as Code from '$lib/components/ui/code';
	import ArchitectureDiagram from '$lib/components/ArchitectureDiagram.svelte';
	import KeyFeatures from '$lib/components/KeyFeatures.svelte';
	import { Callout } from '$lib/components/ui/callout';
	import HomeFaq from '$lib/components/HomeFaq.svelte';

	const installCode = `uv init --python 3.12 # create environment
uv sync # creates the ~/.venv
uv add storywrangler`;

	const usageAllotax = `result = client.instrument.rtd(
    domain="babynames",
    dataset="ngrams",
    entity="wikidata:Q30",
    dates="1925",
    dates2="2025",
    sex="M",
)
print(result['wordshift'][:5])`;
</script>


<!-- Gradient lives on the page container (layout .home-gradient); hero just centers. -->
<div class="not-prose flex min-h-[60vh] flex-col items-center justify-center pb-8 text-center">
	<h1 class="font-baskerville font-regular text-3xl md:text-5xl leading-snug tracking-tight mb-4 md:mb-5">
		Storywrangler is a decentralized data catalog for <span style="background: linear-gradient(transparent 75%, rgba(192, 132, 252, 0.35) 45%)">complex system instruments</span> and <span style="background: linear-gradient(transparent 75%, rgba(251, 146, 60, 0.35) 45%)">data governance</span>
	</h1>
	<p class="text-muted-foreground text-sm md:text-lg max-w-2xl mx-auto">
		By register your datasets to the Storywrangler platform, you first gain access to cool instruments out of the box. Built at the <a href="https://vermontcomplexsystems.org/" class="text-foreground underline underline-offset-4">Vermont Complex Systems Institute</a> to study collective attention as ecological timeseries, while improving data discoverability, ownership, and lineage tracking.
	</p>
	<a href="/getting-started" class="mt-8 inline-flex items-center gap-1 rounded-md bg-foreground px-5 py-2.5 text-sm font-medium text-background no-underline transition hover:opacity-90">
		Get started →
	</a>
</div>

	<h2 class="font-baskerville font-regular text-xl md:text-4xl leading-snug tracking-tight mb-2 md:mb-5">Text as ecological signal</h2>

<p>
	Storywrangler is hosting a set of tools to facilitate the study of large-scale text corpora. Text produced on social media (Bluesky, Reddit, Twitter), news outlets, Wikipedia, and higher education are treated as ecological time series — living records of how collective attention shifts across populations and over time.
</p>

<div class="not-prose mt-6 mb-2">
	<img src="/storywrangler.png" alt="Text sources flow into the Storywrangler platform and produce analytical instruments like time series and allotaxonometer visualizations" class="w-full rounded-lg dark:[filter:invert(.88)]" />
</div>

<p>
	The registered datasets are exposed out of the box via the <a href="/api-reference">storywrangler API</a> as well as the <a href="https://pypi.org/project/storywrangler/">python SDK</a> through the available instruments. For exposing the datasets through custom endpoints, submitters must open pull requests.
</p>

<div class="not-prose my-6">
	<a href="/querying" class="inline-flex items-center gap-1 rounded-md bg-foreground px-5 py-2.5 text-sm font-medium text-background no-underline transition hover:opacity-90">
		Query the registry →
	</a>
</div>

<h2 class="font-baskerville font-regular text-xl md:text-4xl leading-snug tracking-tight mb-2 md:mb-5">Key features</h2>

<p>
	Storywrangler is a digital commons where participants nurture a collective data garden, learn about each others' work, and share complex system tools.
</p>

<KeyFeatures />

<a href="/manifesto" class="mt-8 inline-flex items-center gap-1 rounded-md bg-foreground px-5 py-2.5 text-sm font-medium text-background no-underline transition hover:opacity-90">
		See Manifesto →
	</a>

<h2 class="font-baskerville font-regular text-xl md:text-4xl leading-snug tracking-tight mb-2 md:mb-5">Storywrangler's architecture</h2>

<p>
	Submitters write datasets as parquet files to shared storage and register their metadata via a simple POST request. The API validates schema compatibility and availability, wires datasets to instruments automatically where applicable, and records ownership, lineage, and discoverability.
</p>

<ArchitectureDiagram />

<div class="not-prose my-6">
	<a href="/design" class="inline-flex items-center gap-1 rounded-md bg-foreground px-5 py-2.5 text-sm font-medium text-background no-underline transition hover:opacity-90">
		More on design & architecture →
	</a>
</div>

<h2 class="font-baskerville font-regular text-xl md:text-4xl leading-snug tracking-tight mb-2 md:mb-5">Register a dataset</h2>

<Callout title="Beta release — manual account provisioning" class="mb-6">
	Account creation is not yet self-serve. To get access, contact the VCSI team to have an account created and your API key issued. The key should then be stored in your <code class="rounded bg-zinc-200 px-1 dark:bg-zinc-800">API_KEY</code> environment variable.
</Callout>

<p>
	Register a parquet dataset with a single POST and its instruments — the <a href="/tools/allotaxonometer" class="text-foreground underline underline-offset-4">allotaxonometer</a> and others — light up automatically. Install the SDK with <a href="https://docs.astral.sh/uv/" class="text-foreground underline underline-offset-4">uv</a> (or pip):
</p>

<Code.Root code={installCode} lang="bash" hideLines={true}>
	<Code.CopyButton />
</Code.Root>

<p>Once your data is registered, share its analysis with anyone on earth:</p>

<Code.Root code={usageAllotax} lang="python">
	<Code.CopyButton />
</Code.Root>

<div class="not-prose mt-8 flex flex-wrap items-center gap-4">
	<a href="/register" class="inline-flex items-center gap-1 rounded-md bg-foreground px-5 py-2.5 text-sm font-medium text-background no-underline transition hover:opacity-90">
		Registering walkthrough →
	</a>
</div>

<h2 class="font-baskerville font-regular text-xl md:text-4xl leading-snug tracking-tight mb-2 md:mb-5">Frequently asked questions</h2>

<HomeFaq />

<style>
	h2 {
		margin-top: 8rem !important;
	}
</style>
