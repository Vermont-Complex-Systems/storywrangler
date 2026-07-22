"""
Register the Twitter n-grams dataset (MongoDB pass-through).

Prereqs:
  - API_KEY (and optionally API_URL) in the environment / .env — the admin key
    the SDK authenticates with.
  - Server-side MONGODB_URI must point at wranglerdb01a for the endpoints to
    *serve*. Registration itself does NOT need Mongo reachable: the host-form
    data_location carries an explicit data_schema, so nothing is sampled.

Run:  uv run python backend/scripts/register_twitter.py
"""

from storywrangler import Storywrangler

PAYLOAD = {
    "catalog": "vcsi",
    "domain": "twitter",
    "dataset_id": "ngrams",
    "data_format": "mongodb",
    # Host only — signals where the data lives. The router hardcodes the layout
    # (n-gram size -> database {n}grams, language -> collection). Credentials
    # come from the server's MONGODB_URI, never here.
    "data_location": "wranglerdb01a.uvm.edu:27017",
    "description": (
        "Storywrangler Twitter n-grams (1/2/3-grams across 169 languages), "
        "served from MongoDB. One document per (word, day) with with-RT and "
        "no-RT counts, ranks, and frequencies."
    ),
    # Required for host-form mongodb (no collection to sample). These are the
    # fields on every {n}grams/<lang> collection.
    "data_schema": {
        "word": "VARCHAR",
        "counts": "BIGINT",
        "count_noRT": "BIGINT",
        "rank": "DOUBLE",
        "rank_noRT": "DOUBLE",
        "freq": "DOUBLE",
        "freq_noRT": "DOUBLE",
        "time": "TIMESTAMP",
    },
    "endpoint_schema": {
        "type": "types-counts",
        "type_column": "word",
        "count_column": ["counts", "count_noRT"],  # first = default; ?weight= picks
    },
    "transform": {
        "time_dimension": "time",
        # Routing flags exposed as filter dims so the platform instruments
        # (?lang=/&ngram_size=, plus *2 variants) pick them up generically.
        "filter_dimensions": ["lang", "ngram_size"],
    },
    "ownership": {"owner_group": "vcsi", "contact": "compstorylab@uvm.edu"},
    "lineage": {"repo": "https://gitlab.com/compstorylab/storywrangler"},
}


def main() -> None:
    client = Storywrangler()  # reads API_KEY / API_URL from env or .env
    ok = client.registry.register(PAYLOAD)
    if ok:
        got = client.registry.get("twitter", "ngrams", full=True)
        print("\nRegistered. Server stored:")
        print("  data_location:", got.get("data_location"))
        print("  data_schema  :", got.get("data_schema"))
        print("  endpoint     :", got.get("endpoint_schema"))
    else:
        print("\nRegistration failed — see the error above.")


if __name__ == "__main__":
    main()
