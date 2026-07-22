---
name: storywrangler-submitter
description: Interactive guide for getting data onto the Storywrangler platform — writing or improving a DatasetCreate payload, deciding between serving through an existing endpoint type or disseminating behind a bespoke endpoint, validating before registration, and verifying what the server derived. Use whenever a user wants to submit, register, share, or publish a dataset on Storywrangler, needs help writing the registration payload, asks whether their data is submittable, or wants to fix or optimize an existing submission — even if they never say the word "submission". Not for building the extract/transform pipeline that produces the data.
---

# Submitting datasets to Storywrangler

The payload is built in conversation with its author: propose, confirm, then
build. Start from the smallest valid payload and add only what earns its place.

## The shared core (every submission)

Whatever else happens, every payload needs:

- **identity**: `catalog`, `domain`, `dataset_id` — check the registry first
  (`GET /registry/domains`, `list-datasets`): an existing entry means update,
  not create.
- **location**: `data_location` + `data_format` (`parquet` unless the data is
  a hive-partitioned tree).
- **governance**: `description`, `ownership.owner_group`, `ownership.contact`,
  `lineage.repo`.

An author with a single `data.parquet` should get from "here's my file" to a
valid payload in two or three questions. Governance is the only part they must
be asked; identity can usually be proposed from context.

## The fork: existing endpoint type, or dissemination?

One question then decides how much more of the contract matters:

**Existing endpoint type** — the data's shape matches a recurring endpoint
type (`types-counts`: rank distributions; `time-series`: tabular measures),
so generic endpoints can serve it directly. Declare `endpoint_schema` plus
what the type requires:

- `types-counts` — columns default to `types`/`counts`; declare
  `type_column`/`count_column` only when the data's names differ (declare
  around the data, never rename it). Requires one comparison axis:
  `entity_mapping` or `transform.filter_dimensions`.
- `time-series` — requires `transform.time_dimension` and at least one
  `filter_dimension`.

**Dissemination** — the platform hosts the data behind an endpoint written
*for* it (e.g. `/wikimedia/semantic-timeseries`, essentially
`SELECT * WHERE country = ?`). The endpoint hardcodes the data's shape, so no
`endpoint_schema` is needed and the author doesn't have to learn those fields
— the core payload is enough to register. Serving needs the bespoke endpoint
to exist: a PR to the Storywrangler repo, which can come after registration.

When the data plainly reduces to (type, count) rows or GROUP-BY-able
measures, recommend the endpoint-type path; wide bespoke shapes (score
columns, JSON maps) point to dissemination. Recommend, don't decide.

## Performance declarations (both paths, all opt-in)

Everything beyond the core exists for one reason: Storywrangler's query layer
is a thin DuckDB layer over parquet, and each declaration lets it read less.
Offer each as one question with its payoff attached:

- `transform.time_dimension` → time-range pruning, `?dates=` queries, and
  coverage auto-derived at registration.
- `transform.filter_dimensions` → categorical slicing on in-file columns
  (omitting the parameter = aggregate over all values).
- `entity_mapping` (+ `entities` rows when IDs are opaque) → `?entity=`
  resolution and cross-dataset joins — bespoke endpoints use it too.
- `data_format="parquet_hive"` → partition pruning at scale. Only now does
  layout matter: every level `col=val/`, `data_location` = the tree root. If
  the layout doesn't conform, propose a fix (e.g. a rename script) and wait —
  never restructure the author's data unasked.
- `transform.hash_bucket` → term-first lookup routing. Just the column name;
  the pipeline must assign rows with `storywrangler.hashing.assign_bucket()`.

Declare the minimum — the server derives the rest at registration
(`level_order`, `filter_values`, availability, bucket counts). Never
enumerate hive levels, never compute availability client-side. And guard the
boundary: `endpoint_schema` = what comes back; `transform` = which rows are
read.

## Running the conversation

- **Look at only what the current decision needs.** A single file →
  `DESCRIBE` it and move on. A directory tree's structure matters only once
  hive partitioning is on the table. Don't survey a deep tree to answer a
  question nobody asked.
- **One decision per question**, with a recommendation and its consequence.
  Use AskUserQuestion when available.
- **Stop when it's enough** — an optional field the author doesn't need is
  noise, not thoroughness.
- Field-level reference lives in the docs/MCP (`get-documentation`) — fetch
  it rather than guessing.

## Close the loop

- `validate-submission` (MCP) on every draft: real schema contract, mirrored
  server guards, on-disk layout checks. Show payload and result together;
  errors become the next question, not silent fixes.
- Register only on the author's explicit go. `version="latest"` is the
  mutable slot — routine re-runs are not version bumps; semver strings are
  immutable snapshots (409 on re-register), bumped only on interface changes.
  Never set `schema_version`.
- Verify: `GET /registry/{domain}/{dataset_id}` and check the derived fields.
  Empty `level_order`/`availability` means introspection failed (unreachable
  path, naming violation) — not success, even on a 200.

## Scope

- **No data yet** → settle the fork and (if applicable) the endpoint type
  before the pipeline is built — the shape is cheap to design in and
  expensive to retrofit. Pipeline craft itself is the `pipelines` guide
  (`get-documentation pipelines`), not this skill.
- **Existing submission to review or fix** → start at validate; walk back
  only where the errors point.
- **Generic ETL with no submission in it** → out of scope.
