<script lang="ts">
	import * as Code from '$lib/components/ui/code';
</script>

<div class="not-prose mt-10 mb-12 md:mt-20 md:mb-30 text-center">
	<h1 class="font-baskerville font-regular text-3xl md:text-5xl leading-snug tracking-tight mb-4 md:mb-5">
		The challenge of building digital commons for academia
	</h1>
	<p class="text-muted-foreground text-sm md:text-lg max-w-2xl mx-auto">
		Academia is struggling to build the digital infrastructure that would benefit everyone collectively, yet is too costly for any individual group to undertake alone. This is another instance of the tragedy of the commons.
	</p>
</div>

<h2>Background</h2>

<p>
	At the Vermont Complex Systems Institute, we study collective attention — how populations allocate their awareness across ideas, events, and narratives over time. The raw material for this work is language: n-grams, phrases, and topics extracted from the platforms through which modern societies distribute their attention. Twitter, Reddit, Bluesky, Wikipedia, news archives, Google Books — in a reductive but powerful sense, all of these can be modeled as <em>ecological time series</em>: words propagating through amplification mechanisms, competing for collective focus.
</p>

<p>
	To study these systems at scale requires both large datasets and sophisticated analytical instruments. The <a href="/docs/tools/allotaxonometer">allotaxonometer</a>, for instance, can compare two word-frequency distributions and identify which terms drove a divergence — but it needs a consistent data contract to do so across sources. Building that contract once per dataset, manually, does not scale.
</p>

<h2>The tragedy of the commons in academic data</h2>

<p>
	The bulk of computational work in academia is done by graduate students who come and go. A student builds a pipeline to collect and process social media data, writes a paper, and leaves. The pipeline lives on a personal laptop or a research VM no one else can access. The dataset is never formally archived. The next student starts from scratch.
</p>

<p>
	This is not negligence — it is a structural problem. No individual student has the incentive to invest in infrastructure that outlasts them. No individual lab can sustain the engineering effort needed to build proper data governance. The community as a whole would benefit enormously from shared, maintained datasets and tools, but the cost of building that commons falls disproportionately on whoever acts first.
</p>

<p>
	Existing platforms help at the margins. <a href="https://zenodo.org">Zenodo</a> provides DOIs for datasets and code. <a href="https://github.com">GitHub</a> hosts pipelines. <a href="https://dataverse.harvard.edu">Harvard Dataverse</a> archives large files. But none of these create the feedback loop that makes sharing feel worthwhile: knowing that your data is being <em>used</em>, seeing who built on it, having a clear path from archived data to live analysis.
</p>

<h2>The current landscape</h2>

<p>
	Industry has solved parts of this problem. Projects like <a href="https://www.unitycatalog.io/">Unity Catalog</a> and <a href="https://polaris.apache.org/">Apache Polaris</a> provide data catalogs that register datasets centrally, enforce schemas, and make data discoverable across teams. But these tools are designed for organizations with dedicated data engineering teams, not for research groups where the "data engineer" is a second-year PhD student with three other papers to write.
</p>

<p>
	What academia needs is something narrower and more opinionated: a catalog designed around a specific research community, with instruments already built in, and governance rules that match academic reality — where ownership is personal, turnover is high, and the motivation to share is social rather than commercial.
</p>

<h2>The Storywrangler platform</h2>

<p>
	Storywrangler is our attempt at that infrastructure. It is a decentralized data catalog that stores pointers to datasets — not the data itself — and enforces a schema contract at registration time. The key design decision is that <strong>registering a dataset and making it analysis-ready are the same act</strong>: if your dataset conforms to a known endpoint schema, the allotaxonometer (and future instruments) will work on it immediately, without any additional integration work.
</p>

<p>
	This is the opposite of the typical academic workflow, where a researcher adapts a tool to their data format after the fact. Here, the instrument defines the contract; the submitter meets it once; everyone benefits automatically.
</p>

<h3>Why would you register your dataset?</h3>

<p>The answer depends on where you are in your research lifecycle:</p>

<ul>
	<li>
		<strong>You want your analysis to be reproducible.</strong> The registry records the data contract, the instrument version, and the query parameters of every result. A colleague can reproduce your allotaxonometer figure by pointing at the same registry entry.
	</li>
	<li>
		<strong>You want your data to outlast you.</strong> When you leave, ownership transfers to your group or the institute. The dataset doesn't disappear with your GitHub account.
	</li>
	<li>
		<strong>You want to know who is using your data.</strong> Downstream groups register their dependency in the registry. Their work appears in your impact record — research credit propagates without anyone coordinating directly.
	</li>
	<li>
		<strong>You want to share a dataset that isn't fully open.</strong> Fine-grained access control means you can expose aggregate query results to the public, a filtered subset to collaborators, and full access to your own group — without having to choose between all-or-nothing.
	</li>
</ul>

<h2>Simplicity as a design principle</h2>

<p>
	The platform is deliberately narrow. It does not try to be a compute environment, a notebook host, or a publication system. It does one thing: connect datasets to instruments through a shared schema contract, and record the governance metadata that makes that connection trustworthy over time.
</p>

<p>
	Registration is a single API call. The SDK reduces it to a few lines of Python. The platform validates schema compatibility immediately — if your data doesn't have the columns the instrument expects, you find out at registration time, not when a collaborator tries to reproduce your results six months later.
</p>

<Code.Root lang="python" code={`from storywrangler import Storywrangler, DatasetCreate

client = Storywrangler(api_key="...")
client.registry.register(DatasetCreate(
    domain="my-domain",
    dataset_id="my-dataset",
    data_location="/data/my-dataset.parquet",
    data_format="parquet",
    endpoint_schema={"type": "types-counts"},
    transform={"time_dimension": "date", "filter_dimensions": ["language"]},
))`}>
	<Code.CopyButton />
</Code.Root>

<h2>Summary</h2>

<p>
	Storywrangler is a bet that the right response to the academic data commons problem is not a better archive, but a better interface between data and instruments. If the cost of sharing is low enough — one registration call, a schema you were going to write anyway — and the benefit is immediate (your data works with existing tools, your impact is tracked, your datasets survive your departure), then the commons sustains itself.
</p>

<p>
	We are building this at VCSI because we need it ourselves. The wikigrams pipeline, the babynames data, the Open Academic Analytics project — all of these live in the registry because the alternative is re-implementing the same integration code every time a new student joins the lab. We are opening it to the broader community because the problem is not specific to us, and the value of the catalog grows with every dataset registered.
</p>

<p>
	If you study collective attention, language, or sociotechnical systems — and you have data that can be modeled as an ecological time series — <a href="/docs/register">register it</a>. The instruments are already waiting.
</p>
