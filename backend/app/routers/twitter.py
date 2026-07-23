"""
Twitter endpoints — classic Storywrangler n-grams, served straight from MongoDB.

The twitter n-gram corpus predates the platform's parquet convention and still
lives in MongoDB (host wranglerdb01a). It is registered as a single `mongodb`
pass-through dataset (`twitter/top-ngrams`); this bespoke router owns the classic
Storywrangler layout:

    n-gram size  →  DATABASE     (1grams / 2grams / 3grams)
    language     →  COLLECTION   (en, es, …, _all)
    (word, day)  →  DOCUMENT     {word, time, counts, count_noRT,
                                  rank, rank_noRT, freq, freq_noRT}

So `ngram_size` and `lang` are ROUTING flags (they select db + collection),
while `word` / `date` / `window` become the MongoDB filter document. The
with-retweets vs. no-retweets choice is a measure column inside each document,
exposed as `?weight=` (counts | count_noRT), with matching rank/freq companions.

The registry does NOT record the database/collection names — only the host
(`data_location = "wranglerdb01a.uvm.edu:27017"`). The db/collection mapping
above lives here, in ``_route()`` / ``_NGRAM_SIZES``: a deliberate consequence
of the host-form data_location — the router owns routing. Since there is no
single collection to sample, the schema is declared in the registration
(`data_schema`); latest-date availability is probed per-collection at query time.

Scope guardrail: equality filters + time range + sort/limit only — never Mongo
aggregation pipelines. Top-ngrams uses the pipeline-precomputed rank, so no
server-side aggregation is needed. The moment an endpoint needs an aggregation,
that slice of the data wants to be parquet.
"""

import logging

from fastapi import APIRouter, HTTPException

from ..core.mongo_query import register_mongo_routing

log = logging.getLogger(__name__)

router = APIRouter()

_DOMAIN = "twitter"
_DATASET_ID = "ngrams"
_LABEL = f"{_DOMAIN}/{_DATASET_ID}"
_NGRAM_SIZES = (1, 2, 3)  # the {n}grams databases that exist on the server


# ── routing resolution ────────────────────────────────────────────────────────

def _route(ngram_size: int, lang: str) -> tuple:
    """(database, collection) for the classic Storywrangler layout.

    Routing is hardcoded here on purpose: twitter is a special, single dataset
    with a fixed layout (n-gram size → database, language → collection). The
    registry's ``data_location`` records the Mongo host for humans; the
    connection itself comes from the server's MONGODB_URI.

    An unknown lang is not rejected here — the collection simply yields no data
    and the endpoint returns a 404, which avoids listing 169 collection names on
    every request.
    """
    if ngram_size not in _NGRAM_SIZES:
        raise HTTPException(
            status_code=400,
            detail=f"ngram_size must be one of {list(_NGRAM_SIZES)}",
        )
    return f"{ngram_size}grams", lang


# ── instrument routing ────────────────────────────────────────────────────────
# Allotax/RTD go through the platform instruments (/storywrangler/allotax,
# /storywrangler/rtd). Host-form data_location means this router owns the
# db/collection layout — registered as the domain's routing hook so
# mongo_query can resolve collections for instrument requests.


def _instrument_routing(filter_vals: dict) -> tuple:
    return _route(int(filter_vals.get("ngram_size", 1)), str(filter_vals.get("lang", "en")))


register_mongo_routing(_DOMAIN, _instrument_routing)
