<script lang="ts">
	import SpecsDiagram from '$lib/components/SpecsDiagram.svelte';
	import InstrumentDesignDiagram from '$lib/components/InstrumentDesignDiagram.svelte';
</script>

<h1>Design & architecture</h1>

<p>
	The Storywrangler API is a <strong>data catalog with decentralized storage</strong>, loosely inspired by projects like <a href="https://www.unitycatalog.io/">Unity Catalog</a> and <a href="https://polaris.apache.org/">Apache Polaris</a>. The registry stores metadata; the data stays on the submitter's own infrastructure. The API's dual goals are to improve the governance and discoverability of datasets that would otherwise remain siloed, and to wire them up with VCSI instruments so that their analysis is reproducible. It also scales to terabytes of data, bringing standardization to large pipelines that have historically been opaque and hard to compare.
</p>

<p>
	Registration only require a few fields (see <a href="/register">registering a dataset</a> page), while unlocking concrete benefits: access to analytical instruments developed at the institute, versioned data+instrument pairings for reproducibility, lineage tracking that exposes who maintains each dataset, and (opt-in) dependency graphs showing downstream consumers. Registered datasets can also power performant dashboards and visual data essays, thanks for our query engine based on duckdb and parquet files.
</p>

<p>
	Every dataset is addressed as a three-level namespace: <code>catalog/domain/dataset_id</code> — e.g. <code>vcsi/wikimedia/ngrams</code> or <code>compstorylab/babynames/ngrams</code>. The institute can also take on long-term stewardship of datasets when needed, guaranteeing continued usability beyond any single research group.
</p>

<h2>Dataset model: registry as pointer store</h2>

<p>
	The registry stores metadata only — a pointer to wherever the data lives on institutional storage. The API resolves that pointer at query time and reads via DuckDB's <code>read_parquet()</code>. This has the benefit of preserving data sovereignty and avoids duplicating TB-scale datasets on platform storage. In that sense, we meet researchers where they are; they keep credit for the work they put into wrangling datasets. The health of datasets will be monitored daily to keep track of the status of the data ecosystems. 
</p>

<p>
	All current datasets are <strong>external</strong>: the submitting group owns the storage, the platform owns the query layer.
</p>

<p>
	Another benefit of this approach is to make sensitive data more shareable; for instance, users can submit encrypted <a href="https://duckdb.org/docs/current/data/parquet/encryption">parquet</a> files, which the API could expose to other groups that possess the proper keys to read them. The Storywrangler API itself would be blind to the data, but nonetheless facilitate sharing of the sensitive data.
</p>

<p>But Storywrangler is not any kind of data catalog, the Dataset schema has been designed to be compatible with a set of tools out of the box.</p>

<h2>Open specifications and derived schemas</h2>

<p>
	The contract between submitters and the platform is defined in a standalone <a href="/specification">Storywrangler-Specification</a> — a plain markdown document that anyone can read, discuss, and propose changes to. The spec is intentionally decoupled from any particular implementation, much like the <a href="https://parquet.apache.org/documentation/latest/">Parquet format spec</a> or <a href="https://spec.openapis.org/oas/latest.html">OpenAPI</a>.
</p>

<p>
	The monorepo then derives concrete code from this spec. The <a href="https://pypi.org/project/storywrangler-schemas/">storywrangler-schemas</a> package is a thin Python wrapper that turns the spec's prose into Pydantic models — it is the single source of truth shared by both the backend (validation at registration) and the <a href="https://pypi.org/project/storywrangler/">storywrangler-sdk</a> (client-side construction). Keeping the spec open means that adding a new field or endpoint type starts as a conversation in the spec repo, not a pull request buried in implementation code.
</p>

<SpecsDiagram />


<h2>Instrument architecture</h2>

<p>
	Instruments are standalone computational libraries that get wired into the platform at three tiers. The library itself has no dependency on Storywrangler — it is published independently (e.g. <a href="https://pypi.org/project/allotax/">allotax</a> on PyPI) and can be used directly in scripts or notebooks. A backend router then wraps the library behind dataset-aware API endpoints, handling data resolution and query routing. Finally, consumers — the SDK, frontends, or direct API calls — each surface the instrument in the way that fits their use case.
</p>

<p>
	This three-tier separation means adding a new instrument does not require changing the SDK or the specification. A new router that imports the library and exposes an endpoint is sufficient; the SDK's generic HTTP client can call it immediately.
</p>

<InstrumentDesignDiagram />

<h2>Data sovereignty by design</h2>

<p>Each layer of the platform is independently useful. Groups retain their pipeline outputs as parquet files regardless of the API's availability, and instruments remain runnable as standalone libraries. The API adds live querying and real-time evolution tracking on top of data that groups already own. The platform layer is additive, not extractive.</p>