---
name: storywrangler-submission
description: Craft for submitting datasets to the Storywrangler platform — the DatasetCreate contract and field responsibilities, pre-submission registry checks, what the server auto-derives, validation before POST, and versioning discipline. Load this when registering or re-registering a dataset, writing or reviewing a submit.py, checking whether existing data is submittable, or deciding what shape a pipeline's output must take (endpoint type, partition layout). NOT for building the extract/transform pipeline itself — that is generic ETL work; this skill owns the contract the pipeline's output must meet, and starts once the data (or its design) exists.
---

# Submitting datasets to Storywrangler

Registration is one API call, but the payload encodes a contract. The craft is
knowing which field answers which question, declaring the minimum, and letting
the server derive the rest.

**Scope:** this skill covers the *act of submission* — not the pipeline that
produces the data. Two entry points, same contract:

- **From scratch** — read the contract *forward*: design the pipeline's output
  to satisfy it (see "Designing for submission" below, and the `pipelines`
  guide for the full pipeline craft).
- **Migration** — read the contract *backward*: an existing dataset either
  gets reshaped (pipeline work, out of scope here) or *declared around*
  (column-name overrides, `filter_dimensions`) to meet it.

## Check the registry before you register

The registry is shared state — inspect it before writing to it (the
`storywrangler-analyst` skill covers this discovery craft in depth):

- **Does the target domain exist?** `GET /registry/domains` (datasets can
  fall back to the `guest` domain).
- **Is the `dataset_id` taken?** `list-datasets` / `get-dataset` — an existing
  entry means you are updating, not creating: check its live `version` and
  whether your change is a re-register or a version bump.
- **What do sibling datasets do?** Match their entity namespace and column
  conventions so datasets compose (`wikidata:` entities join across datasets).

## The output contract — what the data must satisfy

- `parquet` — single file or flat directory.
- `parquet_hive` — hive-partitioned tree where **every** level uses `col=val/`
  naming. Non-hive directory names (`1grams/`, `daily/`) are not registrable —
  the tree must be renamed (`ngram_size=1/`, `granularity=daily/`).
- `data_location` for `parquet_hive` is the **root** of the tree: the
  directory directly above the first `col=val/` level.
- The path must be reachable *from the API server* (institutional storage),
  not from the submitter's laptop.

## Each field answers one question — do not conflate them

| Field | Question it answers |
| --- | --- |
| `data_location` | Where is the data on disk? |
| `data_format` | How is it laid out? (`parquet` / `parquet_hive`) |
| `endpoint_schema` | What does the API **return**? Output shape only: `type` (e.g. `types-counts`, `time-series`) plus `type_column`/`count_column` when non-default. No time dimension, no granularities, no filter lists here. |
| `transform` | What axes can callers **slice** on? |
| `entity_mapping` | Which column identifies the entity, in which namespace? |
| `manifest` | What coverage exists? (auto-populated; never read at query time) |
| `ownership` / `lineage` | Who owns it, where did it come from? (governance) |

The classic mistake is stuffing query axes into `endpoint_schema` or output
columns into `transform`. If it changes *what comes back*, it's
`endpoint_schema`; if it changes *which rows are read*, it's `transform`.

## Declare the minimum — the server derives the rest

At registration the server introspects the data and derives: `level_order`
(the full hive nesting with types and defaults), `filter_values` (distinct
values per dimension), `manifest.availability` (min/max time per entity), and
hash-bucket counts. Therefore:

- **Do not** enumerate hive partition levels in `transform` — they are
  auto-discovered. Declare only `time_dimension`.
- **Do not** compute availability client-side in `submit.py`.
- `filter_dimensions` is only for *non-hive columns inside the parquet files*
  where omitting the parameter means "aggregate over all values" (e.g. `sex`).
- `hash_bucket` is just the column name as a string (e.g. `"ngram_bucket"`);
  the server derives per-entity bucket counts. The pipeline must assign rows
  with `storywrangler.hashing.assign_bucket()` — the same murmur3 the query
  layer uses. Never hand-roll the hash.

## Start minimal, add axes progressively

1. **Minimum viable**: `endpoint_schema={"type": "types-counts"}` plus one
   comparison axis — either `filter_dimensions` or `entity_mapping`. Without
   a comparison axis the server rejects the registration (the allotaxonometer
   cannot distinguish system 1 from system 2).
2. **Add `time_dimension`** → callers get standardized `?dates=`/`?dates2=`
   range queries and availability is derived automatically.
3. **Add `entity_mapping` + `entities`** → callers get standardized
   `?entity=`/`?entity2=`; the SDK validates entity IDs locally before upload.
4. **Move to `parquet_hive`** for scale; add `hash_bucket` only when
   term-first lookups (single term across all dates) matter.

**Verify after every registration**: `GET /registry/{domain}/{dataset_id}` and
check that `level_order` lists the expected levels with the right types and
that `manifest.availability` is populated. Empty derived fields mean
introspection failed — usually a `data_location` the server cannot reach or a
naming-convention violation.

## Designing for submission (from-scratch pipelines)

When the pipeline doesn't exist yet, the contract is cheap to satisfy by
design and expensive to retrofit after terabytes are written. Settle these
before the transform is built:

- **Endpoint type first**: `types-counts` (rank distributions → the
  allotaxonometer) or `time-series` (tabular GROUP BY). It determines the
  column shape everything else feeds.
- **Partition keys = query axes**: partition by what callers will filter on
  (entity, granularity, time), nothing else.
- **One time column, one entity column**, named consistently across the tree.
- Sanity-check the planned layout early: `validate-submission` on a sample.

The pipeline craft itself — medallion tiers, parquet-first transforms,
orchestration, file sizing — is the `pipelines` guide
(`get-documentation pipelines`), not this skill.

## Versioning discipline

- `version="latest"` (default) is the mutable slot — re-register freely on
  every pipeline run. Routine re-runs that add rows are **not** version bumps.
- Semver strings are immutable snapshots (re-registering one → `409`). Bump
  only when the *interface* changes: MAJOR for renamed columns or changed
  `endpoint_schema`/`transform` axes, MINOR for new coverage, PATCH for
  corrected values.
- `schema_version` is injected automatically — never set it.
- For citation, archive the snapshot externally (e.g. Dataverse) and record
  `lineage.archival_doi`.

## Workflow gates

- **Never rename, move, or rewrite the user's data files unasked** — not even
  to fix a naming-convention violation. Propose the change, or write a script
  the user can run themselves, and stop there. Data trees are pipeline outputs
  that may be expensive to regenerate, often live on shared institutional
  storage where other consumers read the same paths, and may already be a
  registered dataset's `data_location` — renaming directories silently breaks
  every query against that registration.
- **Validate before POSTing**: run the `validate-submission` MCP tool on the
  payload after writing or editing a submit.py. It applies the real
  registration schema, the server's guards, and lints for silently-ignored
  keys; when the data path is reachable it checks the hive layout too. Fix
  all errors and re-run until clean. No MCP connection? The same check runs
  from the shell — `uvx storywrangler-mcp validate-submission payload.json`
  (or `-` to read stdin); it exits non-zero on blocking errors, so it can
  also gate the pipeline's submit step in CI.
- Registration needs a Bearer API key (`POST /auth/login`); reads do not.
- Propose the `DatasetCreate` payload to the user before POSTing — a
  registration under the wrong identity (`catalog/domain/dataset_id`) pollutes
  the shared registry.

## Where the details live

The full walkthrough with five worked examples (filter-only → entity-mapped →
time axis → hive → hash buckets) is the `register` section on the
`storywrangler` MCP server (`get-documentation`), alongside `versioning`,
`pipelines` (pipeline structure and design-for-submission), and
`api-reference/registry`. Registry inspection craft is the
`storywrangler-analyst` skill. Without MCP: `{docs}/register/llms.txt`.
