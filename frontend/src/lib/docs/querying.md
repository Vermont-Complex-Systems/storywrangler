# Querying Datasets

The Storywrangler platform is a set of API endpoints that expose the metadata of datatasets contributed by the community. This means reading the registry is cheap, as it is only metadata. The required metadata is specified according to the Storywrangler [Specifications](/specification), which provide a formal standards by which we declare what metadata is necessary the whereabouts of the data.

## Step 1 - Discover datasets

```
GET /registry/                     → all datasets (latest version each)
```

The per-dataset response contains everything needed to build a valid query. The registry can be glanced over from the [API references](https://storywrangler.uvm.edu/api-reference) page. For each domain, we list available datasets with query parameters and their description.

## Step 2 - Dive into a dataset

```
GET /registry/{domain}/{dataset}   → one dataset's metadata
```

