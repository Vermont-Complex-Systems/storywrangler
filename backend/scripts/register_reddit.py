"""Register the reddit domain: ngrams (date-first) + ngrams-sparklines (type-first).

The two-dataset layout every sparkline-backed corpus follows:

  reddit/ngrams             the date-first dist tree (n / lang / year / month,
                            one ISO week per file) — feeds top-ngrams, the
                            instruments, and the term-series slow fallback.
  reddit/ngrams-sparklines  the type-first hash-bucketed tree (n / lang /
                            ngram_bucket, one bucket file per shard holding
                            every date for its terms, ngram-sorted; written by
                            scripts/reshard_reddit_sparklines.py) — the
                            term-series fast path (~400x faster warm than
                            scanning the raw weekly corpus).

The pairing is declared, never sniffed: the sparklines carry
``orientation: "type-first"`` and ``lineage.derived_from: ["reddit/ngrams"]``,
which is how /storywrangler/term-series resolves the fast path (there is no
sparkline_dataset param to pass). Both must ALSO declare the same
count/rank/freq menus — the generic endpoint reads its SELECT columns from the
primary and runs them against the sparkline files, so the two registrations
mirror each other. Reddit's ``rank`` is a scalar: the pipeline's single
canonical (score-weighted) ranking, which does NOT track the chosen ?weight= —
while ``freq_column`` is a parallel list that does. That scalar-vs-list split
is the whole point of the declared contract (a naming heuristic cannot know
which semantics a dataset has).

The coverage gate is satisfied by construction here: the request filter dims
(n, lang) are hive levels of the sparkline tree, so every slice is pinnable —
no wikimedia-style granularity nesting needed.

Prereqs:
  - API_KEY (admin) in the environment / .env.
  - Both trees present at their data_location (run reshard first for the
    sparklines, then rsync to the serving host if not on netfiles).

Registration derives the rest from each tree: level_order, per-(n, lang)
hash_bucket counts (default_count + overrides like {"1/en": 64}),
filter_values, data_schema, and availability.

Run:  uv run python backend/scripts/register_reddit.py
"""

from storywrangler import Storywrangler

_OWNERSHIP = {"owner_group": "vcsi", "contact": "compstorylab@uvm.edu"}

# Content type (all/comments/submissions) × weighting (score/controversy/
# unweighted). First entry = the ?weight= default.
_COUNT_MENU = [
    "all_score_weighted", "all_controversy_weighted",
    "comments_score_weighted", "comments_controversy_weighted",
    "comments_unweighted",
    "submissions_score_weighted", "submissions_controversy_weighted",
    "submissions_unweighted",
]
_FREQ_MENU = [
    "all_score_freq", "all_controversy_freq",
    "comments_score_freq", "comments_controversy_freq",
    "comments_unweighted_freq",
    "submissions_score_freq", "submissions_controversy_freq",
    "submissions_unweighted_freq",
]

NGRAMS = {
    "catalog": "vcsi",
    "domain": "reddit",
    "dataset_id": "ngrams",
    "data_format": "parquet_hive",
    "data_location": "/netfiles/wikimedia_snapshots/reddit_agg/dist",
    "description": "Reddit ngrams",
    "endpoint_schema": {
        "type": "types-counts",
        "type_column": "ngram",
        "count_column": _COUNT_MENU,
        # Canonical scalar rank (weight-independent) + per-measure freq list.
        "rank_column": "rank",
        "freq_column": _FREQ_MENU,
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
    "lineage": {"repo": "https://gitlab.com/compstorylab/reddit-ngrams"},
}

SPARKLINES = {
    "catalog": "vcsi",
    "domain": "reddit",
    "dataset_id": "ngrams-sparklines",
    "data_format": "parquet_hive",
    "data_location": "/netfiles/wikimedia_snapshots/reddit_agg/sparklines",
    "description": (
        "Precomputed per-term time series for reddit/ngrams — all count "
        "measures per (ngram, date), hash-bucketed by term for point lookups. "
        "The type-first companion of reddit/ngrams (term-series fast path)."
    ),
    # orientation + derived_from below are the whole fast-path contract:
    # term-series resolves this dataset from the primary's lineage. Columns
    # mirror ngrams so the fast and slow paths select identically.
    "endpoint_schema": {
        "type": "types-counts",
        "type_column": "ngram",
        "count_column": _COUNT_MENU,
        "rank_column": "rank",
        "freq_column": _FREQ_MENU,
        "orientation": "type-first",
    },
    "transform": {"time_dimension": "date", "hash_bucket": "ngram_bucket",
                  "defaults": {"lang": "en", "n": 1}},
    "ownership": _OWNERSHIP,
    "lineage": {
        "derived_from": ["reddit/ngrams"],
        "repo": "https://github.com/Vermont-Complex-Systems/storywrangler",
    },
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
