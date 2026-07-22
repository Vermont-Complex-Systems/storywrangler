"""Register reddit/sparklines — the term-bucketed timeseries precompute.

The reshard job (scripts/reshard_reddit_sparklines.py) writes an mmh3
hash-bucketed tree from reddit_agg/ts: n/lang/ngram_bucket, one bucket file
per shard holding every date for its terms (ngram-sorted). This registers it
so the reddit term-series fast path can point-look-up a term's bucket instead
of scanning the raw weekly corpus (~400x faster warm).

Prereqs:
  - API_KEY (admin) in the environment / .env.
  - The resharded tree present at data_location (run reshard first, then rsync
    to the serving host if not on netfiles).

Registration derives everything from the tree: level_order (n / lang /
ngram_bucket), the per-(n,lang) hash_bucket counts (default_count + overrides
like {"1/en": 64}), filter_values, and data_schema. No endpoint_schema — this
is acceleration plumbing, not a public types-counts product (same as
wikimedia/sparklines), so client.dataset("reddit") still resolves to ngrams.

Run:  uv run python backend/scripts/register_reddit_sparklines.py
"""

from storywrangler import Storywrangler

PAYLOAD = {
    "catalog": "vcsi",
    "domain": "reddit",
    "dataset_id": "sparklines",
    "data_format": "parquet_hive",
    "data_location": "/netfiles/wikimedia_snapshots/reddit_agg/sparklines",
    "description": (
        "Precomputed per-term time series for reddit/ngrams — all count "
        "measures per (ngram, date), hash-bucketed by term for point lookups."
    ),
    "transform": {"time_dimension": "date", "hash_bucket": "ngram_bucket"},
    "ownership": {"owner_group": "vcsi", "contact": "compstorylab@uvm.edu"},
    "lineage": {
        "derived_from": ["reddit/ngrams"],
        "repo": "https://github.com/Vermont-Complex-Systems/storywrangler",
    },
}


def main() -> None:
    client = Storywrangler()  # reads API_KEY / STORYWRANGLER_URL from env or .env
    if not client.registry.register(PAYLOAD):
        print("\nRegistration failed — see the error above.")
        return
    got = client.registry.get("reddit", "sparklines", full=True)
    hb = (got.get("transform") or {}).get("hash_bucket") or {}
    print("\nRegistered. Server derived:")
    print("  level_order   :", [(l["column"], l["type"]) for l in got.get("level_order") or []])
    print("  default_count :", hb.get("default_count"))
    print("  overrides     :", dict(list((hb.get("overrides") or {}).items())[:6]), "...")


if __name__ == "__main__":
    main()
