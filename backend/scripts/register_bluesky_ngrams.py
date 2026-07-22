"""Register bluesky/ngrams — served from a term-bucketed sparkline tree.

Unlike reddit, bluesky has no date-sharded dist tree yet: the mmh3
hash-bucketed tree (n / lang / ngram_bucket, every date for a term's bucket
in one ngram-sorted file) is the domain's primary — and only — dataset. It
serves the /bluesky/term-series endpoints as point lookups; top-ngrams needs
a dist tree and is not exposed. When the pipeline produces one, re-register
ngrams at the dist location and register this tree as bluesky/sparklines,
mirroring reddit's layout.

Unlike reddit/sparklines (unlisted acceleration plumbing), this registration
carries an endpoint_schema: the count-column menu backs the ?weight= param
(count = the default measure, count_all = the companion with its own
freq_all/rank_all columns) and marks the dataset as the domain's public
product, so client.dataset("bluesky") resolves to it.

Prereqs:
  - API_KEY (admin) in the environment / .env.
  - The bucketed tree present at data_location.
  - The API restarted with 'bluesky' in main.py DOMAIN_ROUTERS (VALID_DOMAINS).

Registration derives everything from the tree: level_order (n / lang /
ngram_bucket), per-(n,lang) hash_bucket counts (default_count + overrides),
filter_values, data_schema, and availability.

Run:  uv run python backend/scripts/register_bluesky_ngrams.py
"""

from storywrangler import Storywrangler

PAYLOAD = {
    "catalog": "vcsi",
    "domain": "bluesky",
    "dataset_id": "ngrams",
    "data_format": "parquet_hive",
    "data_location": "/netfiles/wikimedia_snapshots/bluesky_agg/sparklines",
    "description": (
        "Bluesky n-gram time series — per-(ngram, date) counts, frequencies, "
        "and ranks by language and n-gram size, hash-bucketed by term for "
        "point lookups."
    ),
    "endpoint_schema": {
        "type": "types-counts",
        "type_column": "ngram",
        "count_column": ["count", "count_all"],
    },
    "transform": {"time_dimension": "date", "hash_bucket": "ngram_bucket"},
    "ownership": {"owner_group": "vcsi", "contact": "compstorylab@uvm.edu"},
    "lineage": {
        "repo": "https://github.com/Vermont-Complex-Systems/storywrangler",
    },
}


def main() -> None:
    client = Storywrangler()  # reads API_KEY / STORYWRANGLER_URL from env or .env
    if not client.registry.register(PAYLOAD):
        print("\nRegistration failed — see the error above.")
        return
    got = client.registry.get("bluesky", "ngrams", full=True)
    hb = (got.get("transform") or {}).get("hash_bucket") or {}
    print("\nRegistered. Server derived:")
    print("  level_order   :", [(l["column"], l["type"]) for l in got.get("level_order") or []])
    print("  default_count :", hb.get("default_count"))
    print("  overrides     :", dict(list((hb.get("overrides") or {}).items())[:6]), "...")


if __name__ == "__main__":
    main()
