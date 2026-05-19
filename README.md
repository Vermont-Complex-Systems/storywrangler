# Storywrangler

A research data registry and query platform for computational social science.
Groups register datasets (parquet on institutional storage), the platform validates
identifiers, tracks lineage, and serves instruments to
[Complex Stories](https://complexstories.uvm.edu).

## Monorepo Structure

```
storywrangler/
  backend/              FastAPI — registry, query layer, routers
  frontend/             SvelteKit documentation site
  packages/
    schemas/            Shared Pydantic schemas + assign_bucket()
    sdk/                Python SDK — CLI, client, entity validation
    templates/          Pipeline templates (simple-make)
```

See [`packages/sdk/README.md`](packages/sdk/README.md) for SDK usage.

## Registering a Dataset

```bash
uvx storywrangler new my-dataset --format parquet_hive
cd my-dataset
cp .env.example .env   # DATASET_ID, DOMAIN, DATA_PATH, API_KEY
uv sync
make submit
```

Registration is an upsert — safe to re-run. The server auto-derives `data_schema`,
`level_order`, `manifest.availability`, `filter_values`, and `hash_bucket` config
from the data at registration time.

## Standards

Implements [Storywrangler Specification v0.0.3](https://github.com/vermont-complex-systems/Storywrangler-Specification/blob/main/versions/0.0.3.md).

## Development

```bash
uv sync                                        # install dependencies
uv run uvicorn backend.app.main:app --reload   # API server
uv run pytest backend/tests/                   # tests
cd frontend && npm run dev                     # docs site
```
