# Storywrangler — Architecture Notes for Claude

Decisions made during development. Read this before suggesting schema or query changes.

---

## Data formats: parquet first-class, mongodb pass-through

Storywrangler accepts three storage formats from submitters:

- `parquet` — single file or flat directory
- `parquet_hive` — hive-partitioned directory tree (all partition levels use `col=val` naming)
- `mongodb` — pass-through: served from a live MongoDB collection (guest format, see below)

**Why not ducklake or duckdb:** Both were dropped because at query time they resolved
to `read_parquet()` anyway. DuckLake catalogs were bypassed; duckdb with `table_files`
was just parquet under a path convention. No legacy formats are tolerated.

**Why mongodb is different:** it does *not* resolve to `read_parquet()` — it is a
genuinely different backend, admitted for corpora where migration is not worth it
(twitter ngrams). It is a pass-through format, not a first-class one:

- `data_location` is a non-secret locator — a literal `<database>/<collection>`
  (sampled at registration), a Mongo host (e.g. `wranglerdb01a.uvm.edu:27017`,
  signalling where the data lives while a bespoke router owns db/collection
  routing), or a `{placeholder}` routing template. Host/template forms need an
  explicit `data_schema`. Credentials never appear here — the connection URI is
  server config (`MONGODB_URI`). twitter uses the host form; its layout
  (n-gram size → database, language → collection) is hardcoded in the router.
- No level_order, no hash buckets, no `load_system()` — served by a bespoke router
  (`routers/twitter.py`) via `core/mongo_client.py`.
- Registration skips DuckDB introspection; `mongo_introspect()` does best-effort
  pymongo probes instead (sampled `data_schema`, `distinct()` → `filter_values`,
  min/max → `manifest.availability` as flat `{"min", "max"}`).
- Schema-level guards (in `DatasetCreate.validate_mongodb_constraints`): location
  must be `db/collection`, `hash_bucket` rejected.
- **Scope guardrail:** mongo queries are equality filters + time range + sort/limit
  only — never aggregation pipelines. The moment an endpoint needs an aggregation,
  that slice of the data wants to be parquet. This is what keeps the pass-through
  from re-growing into the old half-Mongo half-parquet bifurcation.
- Timeouts use Mongo's native `maxTimeMS` (`ExecutionTimeout` → 504); blocking
  pymongo work runs on a dedicated executor (`run_blocking_mongo`), not DuckDB's.

---

## parquet_hive convention: full `col=val` at every level

For `parquet_hive`, **every partition level must follow hive naming** (`col=val/`).
Non-hive directory names like `1grams/` or `daily/` are not supported.

`data_location` must be the **root** of the hive tree — the directory directly above the
first `col=val/` level. Example layout:
```
/data/ngrams/                        ← data_location points here
  ngram_size=1/
    granularity=daily/
      location=en/
        date=2024-01-01/data.parquet
```

**Why:** DuckDB's `hive_partitioning=true` then handles partition pruning automatically
for any combination of WHERE conditions. No manual path construction in the codebase.
All filtering is uniform WHERE clauses for both `parquet` and `parquet_hive`.

**Performance:** DuckDB reads partition values from directory names (not file contents)
for filter_dimensions introspection and for pruning. This is equivalent to manual glob
construction but generalises to any partition structure and any filter combination.

---

## DatasetCreate field responsibilities

Each top-level field answers a distinct question. Do not conflate them.

| Field | Question | Used at query time? |
|---|---|---|
| `data_location` | Where is the data on disk? | Yes — embedded in `read_parquet()` |
| `data_format` | How is the data laid out? | Yes — selects query strategy |
| `endpoint_schema` | What does the API return? | Yes — column names only |
| `transform` | What axes can callers slice on? | Yes — WHERE clause columns |
| `entity_mapping` | How to resolve entity identifiers? | Yes — entity column + namespace |
| `level_order` | What is the on-disk hive nesting order? | Yes — exact path construction |
| `manifest` | What data exists (coverage/partition index)? | No — UI/discovery only |
| `ownership` | Who owns this? | No — governance only |
| `lineage` | Where did it come from? | No — provenance only |

### `endpoint_schema` — output shape only

```python
{"type": "types-counts", "type_column": "ngram", "count_column": "pv_count"}
```

Only three fields: endpoint type and the column names for types and counts.
No time dimension, no filter dimensions, no granularities, no ngram_sizes here.

`count_column` may be a **list** of selectable measure columns (first = default)
when the data carries several alternative measures of the same count — e.g.
reddit's content type × weighting columns. Endpoints expose the choice as a
`?weight=` query param; `resolve_count_column()` in `core/query_utils.py`
validates it against the registered list (which doubles as the SQL-injection
allowlist) and `load_system(count_col=...)` applies it. Stored rank columns
are canonical (pipeline-side) and do not switch with the weight.

### `transform` — query slice axes

For `parquet_hive`, most of the transform is auto-discovered from the hive directory
tree at registration time. The minimal submission only requires declaring which column
is the time dimension:

```python
{
  "time_dimension": "date",
}
```

All other hive levels are auto-discovered and classified:
- Levels matching `entity_mapping.local_id_column` → entity
- Levels matching `time_dimension` → time
- Levels matching `hash_bucket` (string column name) → hash_bucket
- Everything else → partition (gets auto-default from first on-disk value)

Optional fields:
- `filter_dimensions`: non-hive columns inside parquet files where omitting = aggregate
  over all values. E.g. `["sex"]` — omitting sex returns all names.
- `defaults`: declared default per queryable hive level, e.g. `{"lang": "en", "n": 1}`.
  Overrides the auto-discovered default (first on-disk value alphabetically — right
  for `ngram_size=1`, wrong for languages, where `af` wins). Validated at
  registration: keys must be partition/filter levels, values must exist in the
  introspected `filter_values` (422 otherwise). Stored in `level_order.default_value`
  — the query layer is unchanged.

Query-time defaults come from `level_order.default_value` (stored at registration).
Helper functions `get_partition_defaults()` and `get_queryable_dims()` in
`core/query_utils.py` provide the query layer's view — they read from `level_order`.

Neither field includes the entity column — that is handled by `entity_mapping.local_id_column`.

### `transform.hash_bucket` — content-sharded partition routing

**Submission format** — just the column name:

```python
"ngram_bucket"
```

**Stored format** — auto-derived at registration by `_derive_bucket_config()`:

```python
{"column": "ngram_bucket", "default_count": 1, "overrides": {"1/United States": 16, "2/United States": 32}}
```

The submitter declares only which hive partition column holds the bucket ID.
At registration, `_derive_bucket_config()` walks the directory tree, counts
bucket directories per entity × partition combination, and derives
`default_count` (mode of all counts) and `overrides` (entity/partition
combos that differ from the default). The full config dict replaces the
string in the stored `transform.hash_bucket` before persisting.

The hash algorithm and seed are explicit schema fields on `TransformConfig`:
- `hash_algorithm`: `Literal["murmur3_32"]`, default `"murmur3_32"`
- `hash_seed`: `int`, default `0`

The canonical hashing implementation lives in a single source of truth:
`storywrangler_schemas.hashing.assign_bucket()`. Both the backend and pipeline
code import from this module. The SDK re-exports it as
`storywrangler.hashing.assign_bucket()`.

The query layer computes the bucket at request time via `assign_bucket()`:

    bucket = (mmh3.hash(term, seed=hash_seed) & 0x7FFFFFFF) % count

- `& 0x7FFFFFFF` clears the sign bit (mmh3 returns signed int32; bucket IDs must be >= 0).
- Seed 0 (the default `hash_seed`) matches DuckDB/DuckLake's `murmur3_32()` default.
- Bucket count is per-dataset registration (e.g. US gets 32, smaller countries get 16).
- `default_count` is the fallback when no override matches.
- `overrides` is a flat dict keyed by the expanded level values above the
  bucket level (entity and partition dims), joined in level_order order —
  valid with or without an entity level (e.g. reddit's `"1/en"` for n/lang).
  Resolution: `bucket_override_key()` builds the request's key,
  `overrides[key]` → `default_count`.
- Hash buckets are routing-only, not query axes.
- Helpers in `core/duckdb_query.py`: `assign_bucket()` (imported from
  `storywrangler_schemas.hashing`), `get_bucket_config()`,
  `bucket_override_key()`, `resolve_bucket_count()` — generic, usable by any router.

### `entity_mapping.local_id_column` — dual role (documented, not a bug)

For `parquet_hive`, `local_id_column` is both:
1. The column used in `WHERE entity_col = ?` (entity resolution)
2. The hive partition key — the directory is `entity_col=value/`

These are the same concept: "the column that identifies the entity in stored data."
Hive partitioning promotes a column to the path level; the name is still the column name.

### `manifest` — coverage index, borrowed from Apache Iceberg (never query-time)

Contains `availability` (time/entity ranges) and `partition_index` (enumerable
partition list with per-partition stats). Neither is read at query time.

The name is borrowed from Apache Iceberg: a pre-computed record of partition bounds
and file-level statistics — exactly what `availability` and `partition_index` are.

`availability` is **auto-populated by `parquet_introspect.py`** at registration time
when `transform.time_dimension` is set. It computes `MIN/MAX` of the time column
grouped by entity and partition dimensions. Entity-first format:
```json
{"United States": {"daily": {"min": "2024-01-01", "max": "2026-04-20", "types": 2648755}, "weekly": {...}}}
```
For datasets without entity_mapping: `{"daily": {"min": ..., "max": ...}}`.

`types` appears only on **types-counts datasets**: the vocabulary size (distinct type count) at the latest available date, a topN ceiling hint for UI consumers. Hive-time datasets get it from a footer-only
`COUNT(*)` on the max-date leaf (one row per type per date; buckets summed via `**` glob); flat parquet gets one dataset-level `COUNT(DISTINCT type_col)`.
Best-effort — a leaf holds bounds only if its count could not be read. Datasets
where time lives inside the files (`_targeted_availability`, e.g. reddit) do
not get counts yet — that path needs a real data scan per combo.

`partition_index` is submitter-provided, stored in a separate DB column (excluded
from summary responses via SQLAlchemy `load_only`) and re-injected into `manifest`
on `GET ?full=true`.

---

## Query layer: `load_system()` is format-agnostic

`load_system()` in `core/duckdb_query.py` (the parquet/DuckDB query engine; format-agnostic helpers stay in `core/query_utils.py`) uses identical WHERE-based logic for both
formats. The only difference is the FROM expression:

```python
# parquet
read_parquet('{data_location}')

# parquet_hive (with level_order — exact-depth wildcard path)
read_parquet('{data_location}/*/*/*/*.parquet', hive_partitioning=true)

# parquet_hive (without level_order — recursive glob fallback)
read_parquet('{data_location}/**/*.parquet', hive_partitioning=true)
```

When `level_order` is populated, `_path_expr()` builds a fixed-depth wildcard
path (one `/*` per level) instead of the recursive `/**/*.parquet` glob. This
avoids NFS directory walking overhead.

For routers that need exact partition paths (sparklines, RTD), `build_hive_path()`
constructs paths from level_order with concrete values for each level. Falls back
to `None` when level_order is absent, signalling the caller to use legacy path logic.

Callers (wikimedia, allotax routers) pass `granularity` and `ngram_size` as plain
entries in `filter_vals` — they are just WHERE clause values, not special cases.

---

## Validation: from `filter_values`, not from schema declarations

Routers validate `granularity` and `n` against `dataset_obj.filter_values` (a JSON
column populated at registration by `parquet_introspect.py`). This is authoritative
because it reflects what is actually in the data, not what a submitter declared.

If `filter_values` is empty (dataset not yet introspected), validation is skipped
and DuckDB will return an empty result for invalid values.

---

## `parquet_introspect.py` — registration-time only

Runs once on `POST /register`. Uses `hive_partitioning=true` for `parquet_hive` so:
- `DESCRIBE SELECT *` includes partition columns in `data_schema`
- `SELECT DISTINCT dim` reads from directory metadata, not file contents

Never raises — failures are logged and registration proceeds without derived fields.

---

### `level_order` — hive nesting order (derived, query-time)

The single source of truth for a `parquet_hive` dataset's directory structure.
Derived at registration time, included in default GET responses.

```json
[
  {"column": "ngram_size",  "type": "partition", "default_value": 1},
  {"column": "granularity", "type": "partition", "default_value": "daily"},
  {"column": "country",     "type": "entity",    "default_value": "Afghanistan"},
  {"column": "date",        "type": "time",      "default_value": "2020-01-01"}
]
```

**Type tags:** `partition` (undeclared hive levels), `entity` (entity_mapping.local_id_column),
`hash_bucket` (transform.hash_bucket), `time` (time_dimension), `filter` (filter_dimensions item).

**`default_value`:** The first on-disk value (sorted alphabetically) for each level.
Type-coerced against `filter_values` at registration (string `"1"` → int `1` when
filter_values has ints).

**Computed by:** `validate_and_build_level_order()` in `parquet_introspect.py`.
`_discover_levels()` walks one branch of the hive tree, returning both column names
and first values. Undeclared levels default to type `"partition"`. Registration
fails with 422 if `hash_bucket` column is missing on disk.

**Used by:**
- `build_hive_path()` — exact partition paths at query time
- `get_partition_defaults()` — query-time default injection
- `get_queryable_dims()` — list of filterable columns
- Default GET response — human-readable summary of the full hive structure

**Required for parquet_hive:** `level_order` must be populated — `_path_expr()` raises
if absent. All datasets must be registered (or re-registered) to populate it.

---

## Transform boundary: server vs. frontend

`TransformConfig` declares **available axes** — what the dataset can be sliced on.
It does not declare rendering or aggregation preferences.

Rule of thumb:
- **Server-side**: anything requiring the full dataset (aggregation, WHERE pruning)
- **Query parameter**: things that vary per request (`?normalized=true` someday)
- **Frontend**: Observable Plot territory — sort, bin, window, stack, normalize on subset

Do not add more fields to `TransformConfig` unless they describe a new *axis* that
requires schema-level declaration (i.e., cannot be expressed as a query parameter).

---

## OAA (Open Academic Analytics)

Uses the same `read_parquet()` pattern as all other routers. Pipeline pre-materialises:
- `papers.parquet`, `coauthors.parquet`, `training.parquet`
- `authors.parquet` — pre-joined summary (one row per ego author)
- `embeddings.parquet` — papers filtered to those with UMAP coordinates

All registered under `domain="open-academic-analytics"`. Router resolves
`data_location` from the registry; no bespoke DuckDB connections.

`academic-research-groups` (faculty roster) is registered under `domain="datasets"`.

---

## SDK CLI (`storywrangler new`)

Scaffolds `parquet` or `parquet_hive` project templates only. `ducklake` and `duckdb`
format templates were removed. The generated `submit.py` uses the current `DatasetCreate`
structure: `endpoint_schema` for output shape, `transform` for slice axes.

Templates do **not** compute availability client-side — the server auto-derives it at
registration time from `parquet_introspect.py`. The `parquet_hive` template declares
only `time_dimension` (and optionally `filter_dimensions` / `hash_bucket`); all hive
partition levels are auto-discovered.

---

## Agent/LLM layer: docs-as-markdown + MCP (vcsi-starter pattern)

Documentation follows the volatility split used by sveltejs/ai-tools and
vcsi-starter: durable prose lives as markdown, volatile API reference is
generated live from the OpenAPI spec, and an MCP server fetches both at
runtime so nothing is duplicated or drifts.

- **Source of truth for prose:** `frontend/src/lib/docs/*.md`. Each file is one
  section; the first `# heading` is its title; `use_cases.json` holds discovery
  keywords per slug. The `(docs)/[...slug]` catch-all renders every doc at its
  slug URL via `MarkdownDoc.svelte` (svelte-exmarkdown) — no per-page route
  files. Docs can embed Svelte components (diagrams, flowchart, demo video)
  with `<!-- ComponentName -->` markers; the catch-all splits on names
  registered in `lib/docs-components.ts` and interleaves them. To add an
  embed: register the component there, drop the marker in the markdown.
  Markers are stripped from llms.txt exports.
- **Machine exports (frontend, adapter-node, all live):** `/sections.json`,
  `/llms.txt` (everything), `/{slug}/llms.txt` per guide, and
  `/api-reference/{tag}/llms.txt` rendered from the backend's `openapi.json`
  (`src/lib/server/llms.ts` + `openapi-md.ts`, 5-min cache, graceful when the
  backend is down).
- **Endpoint reference content** comes from `backend/app/routers/openapi_docs.py`
  (`openapi_extra` payloads: response schemas, examples, `x-performance`,
  `x-frontend-notes`). To document an endpoint for agents, enrich it there —
  never hand-write endpoint docs in markdown.
- **MCP server:** `packages/mcp-server` (`storywrangler-mcp`). Two transports,
  one tool implementation: uvx stdio, and remote streamable HTTP mounted by
  the backend at `/mcp` (stateless; session manager runs inside the app
  lifespan in `main.py`; configure `STORYWRANGLER_*_URL` to localhost on the
  server). Tools: `list-sections` / `get-documentation` (docs site),
  `list-datasets` / `get-dataset` (live registry), `validate-submission`
  (local dry-run of a DatasetCreate: real storywrangler-schemas contract +
  mirrored registration guards from `routers/registry.py` + conflation lints
  + on-disk hive layout checks — keep `validate.py` in sync when guards
  change). Env: `STORYWRANGLER_DOCS_URL`, `STORYWRANGLER_URL`; TLS
  verification is on by default (`STORYWRANGLER_INSECURE=1` to opt out while
  the uvm.edu cert mismatch persists).
- **Skills (durable workflow craft):** `.claude/skills/storywrangler-analyst`
  (discovery-first querying, entity resolution, empty-result diagnosis,
  reproducibility) and `.claude/skills/storywrangler-submission` (field
  responsibilities, declare-minimum/derive-rest, hive naming, versioning
  discipline). Skills hold the *when/why*; exact endpoint and field reference
  stays in docs/MCP — don't duplicate it into skills. Each skill has
  `evals/evals.json` guarding its classic failure modes; update the evals
  when a convention changes.
- **Distribution:** `.claude/skills/` is canonical; after editing a skill run
  `scripts/sync_agent_assets.py`, which copies SKILL.md (not evals) into the
  two generated locations: `packages/sdk/src/storywrangler/agent_assets/`
  (shipped in the SDK wheel — `storywrangler new` scaffolds `.mcp.json` +
  `.claude/skills/` into new dataset projects) and `plugins/storywrangler/`
  (Claude plugin, installable via the in-repo marketplace:
  `/plugin marketplace add Vermont-Complex-Systems/storywrangler`). Never
  edit the generated copies.

When adding a guide: create the `.md` in `lib/docs/`, add a `use_cases.json`
entry and a nav entry (`lib/nav.ts` — section order in the exports follows the
nav; unlisted docs are appended alphabetically). The page and the llms.txt
exports appear automatically.
