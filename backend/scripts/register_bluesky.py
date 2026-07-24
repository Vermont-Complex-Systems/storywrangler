"""Register the bluesky domain: ngrams (date-first) + ngrams-sparklines (type-first).

The two-dataset layout every sparkline-backed corpus follows:

  bluesky/ngrams             the date-first dist tree (n / lang / year / month,
                             one ISO week per file) — feeds top-ngrams, the
                             instruments, and the term-series slow fallback.
  bluesky/ngrams-sparklines  the type-first hash-bucketed tree (n / lang /
                             ngram_bucket, every date for a term's bucket in
                             one ngram-sorted file) — the term-series fast path.

The pairing is declared, never sniffed: the sparklines carry
``orientation: "type-first"`` and ``lineage.derived_from: ["bluesky/ngrams"]``,
which is how /storywrangler/term-series resolves the fast path (there is no
sparkline_dataset param to pass). Both must ALSO declare the same
count/rank/freq menus — the generic endpoint reads its SELECT columns from the
primary and runs them against the sparkline files, so the two registrations
mirror each other. Bluesky's rank/freq are per-measure (count → rank/freq,
count_all → rank_all/freq_all), hence parallel lists.

The coverage gate is satisfied by construction here: the request filter dims
(n, lang) are hive levels of the sparkline tree, so every slice is pinnable —
no wikimedia-style granularity nesting needed.

Prereqs:
  - API_KEY (admin) in the environment / .env.
  - Both trees present at their data_location.

Registration derives the rest from each tree: level_order, per-(n, lang)
hash_bucket counts (default_count + overrides), filter_values, data_schema,
and availability.

Run:  uv run python backend/scripts/register_bluesky.py
"""

from storywrangler import Storywrangler

_OWNERSHIP = {"owner_group": "vcsi", "contact": "compstorylab@uvm.edu"}
_REPO = "https://gitlab.com/compstorylab/bluesky-parsing"

NGRAMS = {
    "catalog": "vcsi",
    "domain": "bluesky",
    "dataset_id": "ngrams",
    "data_format": "parquet_hive",
    "data_location": "/netfiles/wikimedia_snapshots/bluesky_agg/dist",
    "description": (
        "Date-first ngram distributions for Bluesky — all count measures per "
        "(ngram, date), by language and ngram size, bundled one ISO week per "
        "file under year/month for single-date distribution and "
        "rank-divergence queries. Includes repost/quote attention-weighted "
        "measures (count_all). Companion to the hash-bucketed "
        "bluesky/sparklines per-term time series."
    ),
    "endpoint_schema": {
        "type": "types-counts",
        "type_column": "ngram",
        # Per-measure companions: the rank/freq lists are parallel to
        # count_column, indexed by the chosen ?weight= (unlike reddit's
        # single canonical rank).
        "count_column": ["count", "count_all"],
        "rank_column": ["rank", "rank_all"],
        "freq_column": ["freq", "freq_all"],
    },
    "transform": {
        "time_dimension": "date",
        "filter_dimensions": ["lang", "n"],
        # year/month hive levels are path-pruning derivatives of `date`,
        # not independent query axes.
        "time_partitions": ["year", "month"],
        # Without this, auto-discovery defaults lang to the first directory
        # alphabetically — 'af' — so bare queries served Afrikaans.
        "defaults": {"lang": "en", "n": 1},
    },
    "ownership": _OWNERSHIP,
    "lineage": {"repo": _REPO},
}

SPARKLINES = {
    "catalog": "vcsi",
    "domain": "bluesky",
    "dataset_id": "ngrams-sparklines",
    "data_format": "parquet_hive",
    "data_location": "/netfiles/wikimedia_snapshots/bluesky_agg/sparklines",
    "description": (
        "Precomputed per-term time series for bluesky/ngrams — all count "
        "measures per (ngram, date), by language and ngram size, hash-bucketed "
        "by term for point lookups. Includes repost/quote attention-weighted "
        "measures (count_all). The type-first companion of bluesky/ngrams."
    ),
    # orientation + derived_from below are the whole fast-path contract:
    # term-series resolves this dataset from the primary's lineage. Columns
    # mirror ngrams so the fast and slow paths select identically.
    "endpoint_schema": {
        "type": "types-counts",
        "type_column": "ngram",
        "count_column": ["count", "count_all"],
        "rank_column": ["rank", "rank_all"],
        "freq_column": ["freq", "freq_all"],
        "orientation": "type-first",
    },
    "transform": {"time_dimension": "date", "hash_bucket": "ngram_bucket",
                  "defaults": {"lang": "en", "n": 1}},
    "ownership": _OWNERSHIP,
    "lineage": {"derived_from": ["bluesky/ngrams"], "repo": _REPO},
}


def _show(client, domain, dataset_id):
    got = client.registry.get(domain, dataset_id, full=True)
    hb = (got.get("transform") or {}).get("hash_bucket") or {}
    print(f"  {domain}/{dataset_id} — server derived:")
    print("    level_order   :", [(lv["column"], lv["type"]) for lv in got.get("level_order") or []])
    if hb:
        print("    default_count :", hb.get("default_count"))
        print("    overrides     :", dict(list((hb.get("overrides") or {}).items())[:6]), "...")


def main() -> None:
    client = Storywrangler()  # reads API_KEY / STORYWRANGLER_URL from env or .env
    for payload in (NGRAMS, SPARKLINES):
        print(f"Registering {payload['domain']}/{payload['dataset_id']} ...")
        if not client.registry.register(payload):
            print("  FAILED — see the error above.")
            continue
        _show(client, payload["domain"], payload["dataset_id"])


if __name__ == "__main__":
    main()
