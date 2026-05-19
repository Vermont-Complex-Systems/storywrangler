<h1>Design & architecture</h1>

<p>
	The registry is a <strong>data catalog</strong>, loosely inspired by projects like the <a href="https://www.unitycatalog.io/">Unity Catalogs</a> or <a href="https://polaris.apache.org/">Apache Polaris</a>. When registered, it simply stores pointers to data, not the data itself. If our API is unreachable, groups can still query their data directly as normal. The health of datasets will be monitored daily to keep track of the status of the data ecosystems.
</p>

<p>
	Every dataset is addressed as a three-level namespace; <code>catalog/domain/dataset_id</code> — e.g.
	<code>vcsi/wikimedia/ngrams</code> or <code>compstorylab/babynames/ngrams</code>. We can also plan to manage datasets, where we run and ensure data maintainability over long term, if necessary. The goal is to provide garantees about the long term usability of datasets that stem from the VCSI and beyond.
</p>

<h2>Dataset model: registry as pointer store</h2>

<p>
	Data stays with the submitter. The registry stores metadata only — a pointer to wherever the
	data lives on institutional storage. The API resolves that pointer at query time and reads via
	DuckDB's <code>read_parquet()</code>. This has the benefit of preserving data sovereignty and avoids duplicating
	TB-scale datasets on platform storage. In that sense, we meet researchers where they are; they keep credit for the work they put into wrangling datasets.
</p>

<p>
	All current datasets are <strong>external</strong>: the submitting group owns the storage, the platform owns the query layer.
</p>

<p>
	Another benefot of this approach is to makez sensitive data more shreable; for instance, users can submit encripted <a href="https://duckdb.org/docs/current/data/parquet/encryption">parquet</a> files, which the API could expose to other groups that possess the proper keys to read them. It means that the Storywrangler API itself could be blind to the data; but nonetheless facilitate sharing of the sensitive data. 
</p>

<h3>Pitfalls and solution</h3>

<p>
	By not owning the datasets, the platform run the risk of serving obsolete datasets.  There are different ways by which we migrate this. 
	
	The <code>storage_risk</code> field in <code>ownership</code>
	documents how stable that storage is (<code>institutional</code> · <code>cloud</code> ·
	<code>personal</code>).
</p>

