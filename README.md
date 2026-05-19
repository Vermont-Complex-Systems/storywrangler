# Storywrangler

A research data registry and text analysis platform for computational social science,
built for a federated ecosystem of academic groups.

Research groups register their datasets here — where they live, who owns them, what
they contain, what they were derived from. The platform validates canonical identifiers
at registration, tracks lineage across groups, and serves instruments (allotaxonometer,
wordshift) to consumers like [Complex Stories](https://complexstories.uvm.edu).

The platform does not host data, run pipelines, or guarantee dataset availability.
Data stays on institutional storage. The registry is a discovery layer only — if the
API is down, groups query their data directly via DuckDB.

Funding agencies require FAIR-compliant data management plans. This platform satisfies
FAIR, and goes further: identifiers are validated at registration (not just recommended),
`derived_from` and `produced_by` make the methods section machine-readable, and
ownership fields let a dataset outlive the student who built it.

**What registering gives you and the ecosystem:**

- **Lineage** — `derived_from` links outputs to inputs across groups; the registry can
  tell you what breaks if a Silver dataset changes schema
- **Discoverability** — other groups can find and build on your data without coordinating
  directly with you
- **Ownership and succession** — when a student leaves, the institute can take custody
  and hand off to the next person; datasets don't disappear with their author
- **Availability guarantees** — data lives on institutional storage and stays queryable
  via DuckDB even if the API is down; registration doesn't create a new point of failure
- **Controlled sharing** — sensitivity and access fields let you register a dataset
  without making it fully public; partners can be listed explicitly in `consumers`
- **Attribution** — every `derived_from` reference is a machine-readable citation;
  groups building on your data appear in your impact record without you asking them to

**To register a dataset:** `pip install storywrangler-sdk`, write a `submit.py`
(see `babynames/` or `wikipedia-parsing/` for examples), run it. That's it.

## Repository Structure

This is a monorepo containing:

- **`packages/sdk/`** - Entity validation and standards implementation
- **`packages/api/`** - FastAPI application

## Standards Compliance

This implementation follows the [Storywrangler Specification v0.0.1](https://github.com/vermont-complex-systems/Storywrangler-Specification/blob/main/versions/0.0.1.md).

**Specification Repository:** https://github.com/vermont-complex-systems/Storywrangler-Specification

## Documentation

Full documentation lives in [`sites/docs/`](sites/docs/) — run `npm run dev` inside that
directory to browse locally. See the [registering a dataset](sites/docs/src/routes/docs/register/+page.svelte)
and [field reference](sites/docs/src/routes/docs/reference/+page.svelte) pages for the
most up-to-date examples.

## Registering a dataset (quick reference)

Registration is an upsert — safe to re-run as data or metadata changes. The SDK
validates all `entity_id` values against the Storywrangler-Specification before making
any network call. Malformed identifiers are rejected locally before anything reaches
the server.


## Development

### Install dependencies
```bash
uv sync
```

### Run API
```bash
uv run --directory packages/api uvicorn app.main:app --reload
```

### Run tests
```bash
uv run pytest
```

## Architecture

- **[Storywrangler-Specification](https://github.com/vermont-complex-systems/Storywrangler-Specification)** - Entity identifier and taxonomy specifications (separate repo)
- **storywrangler-sdk** - Implements specification validators
- **API** - FastAPI application serving the ecosystem
