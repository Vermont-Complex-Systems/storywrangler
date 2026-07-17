# Registering a dataset

Registering a dataset stores a pointer in Storywrangler's catalog: where the parquet lives, how it is laid out, who owns it, and where it came from. The data itself never moves — the platform queries it in place with DuckDB. There are two typical reasons to register:

1. **Share it more widely through the platform.** Your data has its own shape and no existing endpoint type fits, so the platform hosts it behind an endpoint written *for* it — which takes a PR to the [Storywrangler repo](https://github.com/Vermont-Complex-Systems/storywrangler/). Registration is then mostly a data-catalog entry, and that is already useful: discovery, health checks, ownership, lineage.
2. **Serve it through an existing endpoint type.** Your data matches a recurring shape — e.g. `types-counts`, a column of token values and a column of counts — and generic endpoints serve it immediately. This is how a dataset gets access to VCSI instruments such as the [allotaxonometer](/tools/allotaxonometer), which can then be served anywhere on the web.

This page walks through both, assuming a relatively small dataset: a single parquet file or a flat directory of parquet files, up to roughly a gigabyte. Past a few gigabytes — or once queries slice into a much larger whole — hive partitioning keeps them fast: see [registering big data](/register-big-data).

In both cases the dataset registers under an accepted domain (`GET /registry/domains` lists them). Domains cluster related datasets and improve discovery. Registration starts minimal and progressively adds capabilities along three axes (the performance axis is covered in [registering big data](/register-big-data)):

<!-- RegistrationFlowchart -->


## Sharing data through the platform

The platform can also help share data behind a bespoke endpoint. Adding it means opening a PR against the [Storywrangler repo](https://github.com/Vermont-Complex-Systems/storywrangler): a router function that looks the dataset up by its identity and hardcodes the query to the data's shape (see for instance the [`semantic-timeseries` endpoint](https://github.com/Vermont-Complex-Systems/storywrangler/blob/main/backend/app/routers/wikimedia.py), shown below). The registration is somewhat hardcoded too — `domain` and `dataset_id` become part of the contract, since the endpoint resolves the dataset by name. The PR can come after registration; the catalog entry is valid on its own.

What registration buys here is the data catalog and its governance. 

```json
{
    "catalog":    "compstorylab",
    "domain":     "wikimedia",
    "dataset_id": "semantic-timeseries",
    "data_location": "/netfiles/compstorylab/semantic_timeseries.parquet",
    "data_format":   "parquet",
    "description":   "Daily labMT and ousiometric scores for each country's pageview-weighted corpus.",
    "ownership": {"owner_group": "Computational Story Lab", "contact": "compstorylab@uvm.edu"},
    "lineage": {
        "repo": "https://github.com/Vermont-Complex-Systems/wikipedia-parsing",
        "derived_from": ["wikimedia/ngrams"]
    }
}
```

Even a catalog-only entry gets the platform's guarantees:

- The dataset appears in discovery (`GET /registry/domains`, the MCP `list-datasets` tool) and on [dataset health](/status).
- `ownership` and `lineage` record who maintains it and what it was derived from — `derived_from` is what builds the dependency graph between datasets.


### Opting into the platform's axes

Bespoke does not mean bare: the declarations from the first use case work here too, and bespoke endpoints use them.

- **Entity system** — declaring `entity_mapping` (plus `entities` rows) standardizes the endpoint's parameter: callers pass `?entity=wikidata:Q30` or the raw local value, and the router resolves either one to the stored `country` value before querying.
- **Time dimension** — declaring `transform.time_dimension` auto-derives `manifest.availability` at registration (min/max coverage per entity), so the UI and health checks know valid date ranges without touching the data.

```diff
+ "entity_mapping": {"local_id_column": "country", "entity_namespace": "wikidata"},
+ "entities": [
+     {"local_id": "United States", "entity_id": "wikidata:Q30", "entity_name": "United States"},
+     // … one row per country
+ ],
+ "transform": {"time_dimension": "date"},
```

In the router, entity resolution is one added line — swap the raw `country` parameter for `entity`, and resolve it to the stored value before querying (`resolve_entity` accepts canonical IDs and raw local values alike):

```python
local_id = (await resolve_entity(db, "wikimedia", "semantic-timeseries", entity)).local_id
```

And the endpoint now answers to a standardized identifier:

```bash
curl "https://storywrangler.uvm.edu/wikimedia/semantic-timeseries?entity=wikidata:Q30"
```

## Serving through an existing endpoint type

An instrument accepts any dataset that fulfils its requirements — the allotaxonometer requires a `types-counts` endpoint schema (see the instrument page). `types-counts` is the endpoint type for any rank-frequency distribution: a column of token values and a column of counts. At least one comparison axis is required — without one the API rejects the registration, since the allotaxonometer has no way to distinguish system 1 from system 2. `filter_dimensions` are categorical axes that serve as that comparison axis: the allotaxonometer compares `?town=Arlington vs ?town2=Addison`. At query time, omitting the parameter aggregates over all its values.

Payloads on this page are plain JSON: pass one as-is to `client.registry.register(...)` in Python, to the `validate-submission` MCP tool for a local dry-run, or as the body of `POST /registry/register`.

```json
{
    "catalog":    "verso",
    "domain":     "vt-zoning-atlas",
    "dataset_id": "ngrams",
    "data_location": "/data/vt-zoning/ngrams.parquet",
    "data_format":   "parquet",
    "description":   "Word frequencies from Vermont zoning bylaws by town.",
    "endpoint_schema": {"type": "types-counts"},
    "transform":       {"filter_dimensions": ["town"]},
    "ownership": {"owner_group": "verso", "contact": "verso@uvm.edu"},
    "lineage":   {
        "repo": "https://github.com/Vermont-Complex-Systems/vt-zoning-atlas"
    }
}
```

Once registered, each `filter_dimensions` entry becomes a bare query parameter on the allotaxonometer. Comparing Arlington vs Addison:

```bash
curl "https://storywrangler.uvm.edu/storywrangler/allotax\
  ?domain=vt-zoning-atlas&dataset=ngrams\
  &town=Arlington&town2=Addison"
```

Without any entity mapping, we adopt the convention of simply incrementing provided filter dimensions when querying the API, e.g. `town` and `town2`.

### Providing entity mapping

Drop `filter_dimensions` and add `entity_mapping` instead. The SDK validates all `entity_id` values locally before anything reaches the server. This also standardizes the API parameter: regardless of what the local column is called (`town`, `geo`, `country`…), callers always use `?entity=` and `?entity2=` — accepting either a canonical ID (`wikidata:Q675558`) or the raw local value (`Arlington`):

```diff
- "transform": {"filter_dimensions": ["town"]},

+ "entity_mapping": {"local_id_column": "town", "entity_namespace": "wikidata"},
+ "entities": [
+     {"local_id": "Arlington", "entity_id": "wikidata:Q675558", "entity_name": "Arlington, Vermont"},
+     {"local_id": "Addison",   "entity_id": "wikidata:Q353095", "entity_name": "Addison, Vermont"},
+     // ... one row per town
+ ],
```

The corresponding curl command:

```bash
curl "https://storywrangler.uvm.edu/storywrangler/allotax\
  ?domain=vt-zoning-atlas&dataset=ngrams\
  &entity=wikidata:Q675558&entity2=wikidata:Q353095"
```

By analogy to `filter_dimension`, the API now expects `entity` and `entity2` keys but values can either be the standardized or local identifiers.

### Adding a time axis

`transform.time_dimension` opens a date-range axis for `BETWEEN` queries. The meaningful comparisons are same location across two time ranges (e.g. US 1990 vs US 2020), or same time range across two locations (e.g. US 2020 vs Quebec 2020). When `time_dimension` is set, the platform auto-populates `manifest.availability` at registration time — computing min/max date coverage per entity, so the UI knows valid ranges without querying the data.

Start without entity mapping: `geo` stays in `filter_dimensions` and callers pass raw local IDs directly — `?geo=united_states` — with no namespace resolution. The manifest is keyed by the same local IDs.

```json
{
    "catalog":    "vcsi",
    "domain":     "babynames",
    "dataset_id": "ngrams",
    "data_location": "/data/babynames/ngrams.parquet",
    "data_format":   "parquet",
    "description":   "Baby names by popularity, year, and location.",
    "endpoint_schema": {"type": "types-counts"},
    "transform": {
        "filter_dimensions": ["year", "sex", "geo"]
    },
    "ownership": {"owner_group": "vcsi", "contact": "compstorylab@uvm.edu"},
    "lineage":   {"repo": "https://github.com/Vermont-Complex-Systems/babynames"}
}
```

And the corresponding curl command:

```bash
curl "https://storywrangler.uvm.edu/storywrangler/allotax\
  ?domain=babynames&dataset=ngrams\
  &year=1990&year2=2020\
  &geo=united_states&sex=F"
```

Moving `year` to `time_dimension` unlocks range queries and standardizes the API parameter: regardless of the underlying column name (`year`, `date`…), callers always use `?dates=` and `?dates2=`. Availability is auto-derived at registration — it tells the UI what date ranges are valid per entity without touching the data:

```diff
  "transform": {
-     "filter_dimensions": ["year", "sex", "geo"],
+     "filter_dimensions": ["sex", "geo"],
+     "time_dimension":    "year",
  },
+ // availability is auto-populated at registration:
+ // {"united_states": {"min": 1880, "max": 2022}, "quebec": {"min": 1980, "max": 2022}}
```

Adding `entity_mapping` promotes `geo` out of `filter_dimensions`. Availability keys auto-upgrade to canonical entity IDs:

```diff
- "filter_dimensions": ["sex", "geo"],
+ "filter_dimensions": ["sex"],

+ "entity_mapping": {"local_id_column": "geo", "entity_namespace": "wikidata"},
+ "entities": [
+     {"local_id": "united_states", "entity_id": "wikidata:Q30",  "entity_name": "United States"},
+     {"local_id": "quebec",        "entity_id": "wikidata:Q176", "entity_name": "Quebec"},
+ ],
```

The corresponding curl command:

```bash
curl "https://storywrangler.uvm.edu/storywrangler/allotax\
  ?domain=babynames&dataset=ngrams\
  &entity=wikidata:Q30\
  &dates=1990&dates2=2020\
  &sex=F"
```

## Case studies

The [scisciDB pipeline](/case-studies/scisciDB) walks the existing-endpoint-type path end to end (`time-series`, pre-aggregation, GROUP BY queries). The [Wikimedia pipeline](/case-studies/wikimedia) is a big data submission (`parquet_hive`) — see [registering big data](/register-big data) for those fields.
