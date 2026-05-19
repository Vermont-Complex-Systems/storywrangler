<script lang="ts">
	import * as Code from '$lib/components/ui/code';
	import ArchitectureDiagram from '$lib/components/ArchitectureDiagram.svelte';
	import KeyFeatures from '$lib/components/KeyFeatures.svelte';
	import { Callout } from '$lib/components/ui/callout';
	import HomeFaq from '$lib/components/HomeFaq.svelte';

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

<h2 class="font-baskerville font-regular text-xl md:text-4xl leading-snug tracking-tight mb-2 md:mb-5">Text as ecological signal</h2>

<p>
	Storywrangler is hosting a set of tools to facilitate the study of large-scale text corpora. Text produced on social media (Bluesky, Reddit, Twitter), news outlets, Wikipedia, and higher education are treated as ecological time series — living records of how collective attention shifts across populations and over time.
</p>

<div class="not-prose mt-6 mb-2">
	<img src="/storywrangler.png" alt="Text sources flow into the Storywrangler platform and produce analytical instruments like time series and allotaxonometer visualizations" class="w-full rounded-lg" />
</div>

<h2 class="font-baskerville font-regular text-xl md:text-4xl leading-snug tracking-tight mb-2 md:mb-5">Storywrangler's architecture</h2>

<p>
	Submitters write datasets as parquet files to shared storage and register their metadata via a simple POST request. The API validates schema compatibility and availability, wires datasets to instruments automatically where applicable, and records ownership, lineage, and discoverability. 
</p>

<ArchitectureDiagram />

<h2 class="font-baskerville font-regular text-xl md:text-4xl leading-snug tracking-tight mb-2 md:mb-5">Key features</h2>

<p>
	Storywrangler is a digital commons where participants nurture a collective data garden, learn about each others' work, and share complex system tools.
</p>

<KeyFeatures />

<h2 class="font-baskerville font-regular text-xl md:text-4xl leading-snug tracking-tight mb-2 md:mb-5">Registering your first data pipeline</h2>

<Callout title="Beta release — manual account provisioning" class="mb-6">
	Account creation is not yet self-serve. To get access, contact the VCSI team to have an account created and your API key issued. The key should then be stored in your <code class="rounded bg-zinc-200 px-1 dark:bg-zinc-800">API_KEY</code> environment variable.
</Callout>

<p>The registration process is a simple POST request documented <a href="/api-reference/registry/post-registry-register">here</a>.</p>

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

<p>You can find a walkthrough of the <code>types-counts</code> API schema that the allotaxonometer expects in <a href="/register">Registering a dataset</a>. In this case, we are telling the API that the dataset has the following shape and is available at the <code>data/</code> location:</p>

<Code.Root code={dataframeCode} hideLines={true} />

<p>Provided the registration is successful, you can now share your analysis of babynames with anyone on earth using:</p>

<Code.Root code={usageAllotax} lang="python">
	<Code.CopyButton />
</Code.Root>

<p>Under the hood, we are <a href="/versioning">versioning</a> the interaction of the allotaxonometer tool and the submitted babynames pipeline for reproducibility.</p>

<p>For more details on entity mapping, discoverability, and storage options, see <a href="/register">Registering a dataset</a>.</p>

<h2 class="font-baskerville font-regular text-xl md:text-4xl leading-snug tracking-tight mb-2 md:mb-5">Frequently asked questions</h2>

<HomeFaq />

<style>
	h2 {
		margin-top: 8rem !important;
	}
</style>
