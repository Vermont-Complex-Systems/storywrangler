# Getting started

Storywrangler is a text-analysis data platform from the Vermont Complex Systems Institute. It serves n-gram frequencies, time series, and rank-turbulence divergence (allotaxonometry) over small and large parquet datasets through a single FastAPI service backed by DuckDB.

Register a parquet dataset once, and its analytical instruments — the allotaxonometer, top n-grams, per-term time series — work on it immediately. This guide takes you from install to a first registered dataset you can query.

## Core concepts

- **Domain** — a top-level data family with its own router and endpoints. `GET /registry/domains` lists the valid ones.
- **Dataset** — a registered parquet source inside a domain, identified as `{domain}/{dataset_id}` (e.g. `wikimedia/ngrams`). The registry stores its location, layout, slice axes, and introspected metadata.
- **Registry** — the catalog. `GET /registry/` lists every dataset with its `level_order` (hive nesting), `filter_values` (valid values per dimension), and `endpoint_schema` (output shape). This is the ground truth for what is queryable — always check it before constructing queries.
- **Instruments** — the analysis endpoints layered on datasets: top n-grams, per-term time series, and the [allotaxonometer](/tools/allotaxonometer) (rank-turbulence divergence between two systems).
- **Entities** — datasets are partitioned by an entity (a country, a subreddit, a town). Entities use namespaced identifiers such as `wikidata:Q30` (United States). `GET /registry/{domain}/{dataset_id}/adapter` maps local IDs to canonical entity IDs and human-readable names.

## Install the SDK

Read endpoints (registry lookups, domain queries) are public, but registration requires a Bearer API key — see [authentication](/authentication). We recommend installing the SDK with [uv](https://docs.astral.sh/uv/) (or pip):

```bash
uv init --python 3.12 # create environment
uv sync               # creates the ~/.venv
uv add storywrangler
```

The API base URL comes from the `STORYWRANGLER_URL` environment variable (or pass `base_url=`); your key from `API_KEY`. Interactive OpenAPI docs live at the API's `/docs`, and a machine-readable spec at `/openapi.json`.

This documentation site is also machine-readable: `/llms.txt` returns everything as plain markdown, and `/sections.json` lists every section with a per-section `/{slug}/llms.txt` export — designed for LLM agents working with the platform.

## Scaffold a dataset project

The SDK ships a scaffolder that lays out a complete submission project — `extract/` → `transform/` → `adapter/` — with a `submit.py` wired to the current schema and the agent assets (MCP config + Claude skills) already in place:

```bash
uvx storywrangler new babynames --format parquet
# or, for hive-partitioned data:
uvx storywrangler new ngrams --format parquet_hive
```

Fill in `.env` (`DATASET_ID`, `DOMAIN`, `DATA_PATH`, `API_KEY`), map your entities in `config/entities.yaml`, edit `adapter/submit.py`, then `make submit` to register. See [registering a dataset](/register) for the field-by-field walkthrough.

## Register your first dataset

Registration is a single POST. Suppose your parquet has one row per name, year, and sex:

```
types,counts,year,sex
John,4394,1925,M
Robert,2559,1925,M
Axell,1956,1925,M
Donald,1565,1925,M
Peter,1464,1925,M
...
```

You tell the API where the data lives, its output shape (`endpoint_schema`), and which axes it can be sliced on (`transform`):

```python
from storywrangler import Storywrangler, DatasetCreate

client = Storywrangler(api_key="<your-key>")   # or set API_KEY / STORYWRANGLER_URL

# Verify the connection
client.users.whoami()

dataset = DatasetCreate(
    catalog="vcsi",
    domain="babynames",
    dataset_id="ngrams",
    data_location="/mydata/babynames.parquet",
    data_format="parquet",
    description="Babynames frequencies by year and sex in the US.",
    endpoint_schema={"type": "types-counts"},
    transform={"time_dimension": "year", "filter_dimensions": ["sex"]},
    ownership={"owner_group": "vcsi", "contact": "vcsi@uvm.edu"},
    lineage={"repo": "https://github.com/Vermont-Complex-Systems/babynames"},
)

client.registry.register(dataset)
```

`endpoint_schema={"type": "types-counts"}` is the shape the allotaxonometer expects; `transform` declares the sliceable axes (here `year` as the time dimension and `sex` as a filter). The server introspects the parquet at registration time to derive valid filter values and availability — you don't compute them client-side.

## Query it

Once a dataset is registered, use the dataset-scoped client. It discovers filters and validates them against the registry before sending a request, so mistakes surface as clear errors instead of empty results:

```python
wiki = client.dataset("wikimedia", "ngrams")
wiki.filters        # {'ngram_size': {'default': 1, 'valid': [1, 2]}, 'granularity': {...}}
wiki.availability   # date ranges per entity, from manifest.availability

result = wiki.allotax(
    entity="wikidata:Q30", entity2="wikidata:Q145",
    dates="2026-05-01", dates2="2026-05-01",
    ngram_size=1, granularity="daily",
)
```

For a fast, lightweight comparison between two dates on a single entity, use `rtd` — it returns the wordshift only (no diamond plot or balance):

```python
result = client.instrument.rtd(
    domain="babynames", dataset="ngrams",
    entity="wikidata:Q30", dates="1925", dates2="2025", sex="M",
)
print(result["wordshift"][:5])
```

```python
[{'type': 'Jackson',
  'rank1': 676.0,
  'rank2': 74.0,
  'divergence': 0.00013999022173321902},
 {'type': 'Duvall',
  'rank1': 10309.5,
  'rank2': 428.0,
  'divergence': 0.0001209265034150297},
 {'type': 'Bunny',
  'rank1': 564.0,
  'rank2': 5765.0,
  'divergence': -9.604679669786964e-05},
 {'type': 'Weaver',
  'rank1': 8522.5,
  'rank2': 736.0,
  'divergence': 9.389480911305102e-05},
 {'type': 'Bowl',
  'rank1': 254.0,
  'rank2': 1169.0,
  'divergence': -8.660948752039387e-05}]
```

`GET /version` reports the API, schemas, DuckDB, and allotax versions in effect. Storywrangler [versions](/versioning) the interaction between an instrument and a pipeline, so any result stays reproducible for papers and pipelines.

## Where to go next

- [Querying datasets](/querying) — the discovery-first query workflow, instrument endpoints, and performance guidance.
- [Registering a dataset](/register) — how to publish a new parquet dataset to the platform, including the hive-partitioning convention.
- [Why Storywrangler?](/manifesto) — the motivation behind the platform.
