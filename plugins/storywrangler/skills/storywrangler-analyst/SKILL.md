---
name: storywrangler-analyst
description: Craft for querying the Storywrangler data platform — discovery-first workflow via the registry, entity resolution, date availability, allotaxonometer comparisons, and performance patterns. Load this whenever querying Storywrangler datasets (n-grams, term series, rank-turbulence divergence) through the API, SDK, or MCP tools, even if the user doesn't name Storywrangler.
---

# Querying Storywrangler

Storywrangler serves n-gram frequencies, per-term time series, and
rank-turbulence divergence (allotaxonometry) over registered parquet datasets.
The craft of querying it well is one habit applied consistently: **read the
registry before constructing any query**. Everything below is a variation on
that habit.

## The registry is ground truth — discovery first

Never guess dimension values, entity IDs, granularities, or date ranges. The
registry records what actually exists, introspected from the data itself:

1. **List datasets** — `list-datasets` (MCP) or `GET /registry/`.
2. **Read one dataset's metadata** — `get-dataset` (MCP) or
   `GET /registry/{domain}/{dataset_id}`. Four fields drive everything:
   - `level_order` — the queryable dimensions, in order, with defaults.
     Levels typed `partition`/`filter` are the query parameters you may pass;
     omitted ones get their `default_value`.
   - `filter_values` — the valid values per dimension. A value outside this
     list returns an *empty result, not an error*.
   - `manifest.availability` — min/max time coverage per entity and
     granularity. Check it before requesting any date range.
   - `endpoint_schema` — the output shape (which columns hold types/counts).
3. **Construct the query** from what you found, nothing more.

With the SDK, `client.dataset(domain, id).filters` and `.availability` wrap
steps 1–2 and validate parameters before sending.

## Entities are namespaced identifiers

Datasets are partitioned by an entity (a country, a subreddit, a town) using
namespaced IDs like `wikidata:Q30` (United States). Endpoints accept either
the canonical ID or the raw local value. **Never fabricate a Q-id from
memory** — resolve it via `GET /registry/{domain}/{dataset_id}/adapter`
(maps local IDs ↔ canonical IDs ↔ human names), or pass the local value.

## Terms are case-sensitive

`COVID` and `covid` are different lookups. When a user gives you a term,
preserve their casing, and if a lookup comes back empty, try the obvious case
variants before concluding the term is absent.

## Diagnose empty results before reporting failure

An empty `data`/`series` array with HTTP 200 almost always means a filter
value that doesn't exist, a date range outside availability, or a case
mismatch — in that order of likelihood. Re-check `filter_values` and
`availability` before telling the user the data is missing. Structured errors
mean something different:

- `404 DATA_NOT_AVAILABLE` — registered but files absent on this server;
  report it, don't retry.
- `500 QUERY_FAILED` — re-check parameters against `filter_values`.
- `504 QUERY_TIMEOUT` — narrow the date range or use a coarser granularity.

## Allotaxonometer comparisons

The allotaxonometer compares two *systems*. System-2 parameters take a `2`
suffix (`entity2`, `dates2`, `sex2`, …). Meaningful comparisons vary one axis
at a time: same entity across two time ranges, or two entities over the same
range. Comparing different entities *and* different dates at once is rarely
interpretable — flag it if the user asks for one.

## Performance craft

- `include_articles=false` on wikimedia term-series is ~2× faster; only
  request articles when the user drills into contributing pages.
- Vocabulary terms (~65K) return in tens of milliseconds; arbitrary terms fall
  back to a 3–5 s partition scan. Prefer vocabulary terms for interactive use.
- `window=0` returns full history; use `window=30`/`window=90` for recent data.
- Batch endpoints fetch many term sparklines in one request; missing terms
  return empty arrays, never errors.
- The `Server-Timing` response header shows where query time went — read it
  before speculating about slowness.

## Reproducibility is part of the result

This is an academic platform: any figure or number destined for a paper should
record the dataset identity (`domain/dataset_id`), its `version`, and the
software stack from `GET /version` (API, schemas, duckdb, allotax versions).
Allotaxonometer responses echo `dataset_version` and `allotax_version` in
their `meta` block — keep them with the output.

## Where the details live

Exact endpoint paths, parameters, and response shapes: the `storywrangler`
MCP server (`list-sections` → `get-documentation`), especially the `querying`
guide and the `api-reference/{domain}` sections. No MCP connection? The same
tools run as a CLI — `uvx storywrangler-mcp list-sections`,
`get-documentation <section>`, `list-datasets`, `get-dataset <domain> <id>` —
and the raw content is at `{docs}/llms.txt`, `{docs}/sections.json`, and
`{docs}/{slug}/llms.txt`.
