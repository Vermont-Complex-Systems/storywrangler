# Building a dataset pipeline

The registration call is deliberately small; the pipeline that produces the
data is where the real work lives. This guide describes the storywrangler way
of building that pipeline — standard data-engineering patterns (medallion
tiers, columnar storage, declarative orchestration) adapted to academic
reality, where the "data engineering team" is one grad student, compute is a
laptop plus a SLURM allocation, storage is institutional NFS, and the pipeline
must outlive its author.

`storywrangler new` scaffolds this structure. The
[Wikimedia](/case-studies/wikimedia) and [scisciDB](/case-studies/scisciDB)
case studies are worked examples of everything below.

## The shape: extract → transform → load

```
my-dataset/
  extract/     acquire raw data (scrape, download, API pulls)
  transform/   raw → submission-shaped parquet
  load/        submit.py — the registration payload, nothing else
  config/      entities.yaml — entity mappings
  tests/       entity coverage + contract checks
  Makefile     extract / transform / validate / submit / test
```

The triad is literally ETL — with one platform-specific twist: the **L loads
the catalog, not a warehouse**. Registration is a metadata upsert (a pointer
plus the contract); the parquet files stay where the transform wrote them.
That is data sovereignty made visible in the folder layout.

Each stage owns one thing. `extract` fetches and never reshapes; `transform`
owns all reshaping; `load` owns only the contract (`build_payload()` +
`register()`). If `submit.py` needs to mangle data, that logic belongs in
`transform` — the load step should stay boring enough that re-registering is
a non-event.

## Medallion tiers, academically

Industry lakehouses organise data as bronze → silver → gold. The same
discipline works on institutional storage without any lakehouse machinery:

- **Bronze** — raw inputs exactly as fetched, immutable. Wikipedia enterprise
  dumps, SSA zip files, API responses. Keep them: re-running `transform` must
  never require re-scraping.
- **Silver** — cleaned, submission-shaped parquet. **This is what you
  register.** One table-like layout, stable column names, hive-partitioned
  when large.
- **Gold** — derived artifacts (aggregations, embeddings, model outputs).
  These register later as their own datasets with `lineage.derived_from`
  pointing at the silver dataset — not as mutations of it.

The payoff of the discipline is the same as in industry: every tier is
reproducible from the one below it, and consumers (the query layer, your
colleagues, your successor) only ever touch silver and gold.

## Parquet-first, out-of-core

All transforms target parquet, and DuckDB is the workhorse. Columnar
compression plus predicate pushdown means terabyte-scale n-gram counts are
tractable on a laptop — the Wikimedia pipeline turns >100 GB/day of dumps
into partitioned parquet without a cluster. There is no Spark, no warehouse:
the same files your pipeline writes are the files the platform queries with
`read_parquet()`. Data sovereignty comes free — you keep the files, the
platform keeps a pointer.

## Partitioning: hive when large, flat when not

- **Flat parquet** (single file or directory) is right up to a few GB. Don't
  partition small data.
- **Partition** (`parquet_hive`) when the data is large *and* queried by
  slices. Partition keys should be exactly the axes callers filter on —
  entity, granularity, time — nothing else. Every level is named `col=val/`,
  and the tree root is what you register as `data_location`.
- **Size files in the hundreds of MB.** Wikimedia lands at 300–400 MB per
  daily file: big enough that DuckDB isn't drowning in file opens, small
  enough to stream. Within each file, sort by your type column — rank
  lookups become range scans.
- **Hash buckets** (`transform.hash_bucket` + `assign_bucket()` from the SDK)
  only when you need term-first lookups (one term across all dates). They are
  routing, not query axes — most datasets never need them.

## Design for submission from day one

These choices cost nothing at the start and are expensive to retrofit after
terabytes are written:

1. **Pick the endpoint type first** — `types-counts` (rank distributions,
   feeds the allotaxonometer) or `time-series` (tabular GROUP BY). It
   dictates your column shape.
2. **Name the columns** — `types`/`counts` by default, or plan to declare
   `type_column`/`count_column` overrides.
3. **One time column** (`time_dimension`), consistent across granularities;
   **one entity column** whose values you can map in `config/entities.yaml`.
4. **Validate early**: `uvx storywrangler-mcp validate-submission` on a
   sample payload/layout, before the full run — not after.

The field-by-field contract is [registering a dataset](/register).

## Orchestration: make first, snakemake for clusters

`make` is the default — five targets (`extract`, `transform`, `validate`,
`submit`, `test`) anyone can read. Reach for `snakemake` when runs move to
SLURM and you want sentinels, logs, and resumability. Either way the last
two steps are the same, because registration is an upsert:

```
make validate   # dry-run the payload through the validator (exits non-zero on errors)
make submit     # re-register; the `latest` slot updates freely on every run
```

`validate` gating `submit` in CI is the cheap insurance that a pipeline
change didn't silently break the contract.

## Tests that earn their keep

Two checks catch most real-world drift:

- **Entity coverage** — every distinct value in the entity column has a
  mapping in `entities.yaml`. Upstream sources add countries, states, and
  venues without telling you.
- **No null entities** — a null entity row is unqueryable and invisible.

These are scaffolded in `tests/`; keep them wired to the real transform
output, not fixtures.

## Built to outlive you

The academic failure mode is not bad code — it's the pipeline that leaves
with its author. The conventions that prevent it:

- Machine-specifics live in `.env` (`DATA_PATH`, keys), never hardcoded.
- Data lives on institutional storage (declare `ownership.storage_risk`),
  not a laptop.
- `lineage.repo` points at the pipeline repository; `lineage.archival_doi`
  records the archived copy when a version is citable.
- The registry records `schema_version` and derived availability at every
  registration — your successor can see exactly what contract was in effect.

## Where to go next

- [Registering a dataset](/register) — the submission contract, field by field.
- [Versioning](/versioning) — when a re-run is just a re-run and when it's a release.
- [Wikimedia](/case-studies/wikimedia) and [scisciDB](/case-studies/scisciDB) —
  the patterns above applied to 100 GB/day of dumps and 200M paper records.
