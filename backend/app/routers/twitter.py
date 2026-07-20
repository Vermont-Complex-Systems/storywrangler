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
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_session
from ..core.mongo_client import (
    QUERY_TIMEOUT_S, get_mongo_collection_by_name, handle_mongo_error, run_blocking_mongo,
)
from ..core.mongo_query import (
    dataset_columns as _cols,
    day_filter as _day_filter,
    latest_available as _latest_available,
    range_filter as _range_filter,
    register_mongo_routing,
    resolve_measures,
    series_projection as _projection,
)
from ..core.query_utils import resolve_count_column
from ..core.registry_utils import get_latest_entry
from ..core.term_series import series_entry
from ..core.timing import timed

log = logging.getLogger(__name__)

router = APIRouter()

_DOMAIN = "twitter"
_DATASET_ID = "ngrams"
_LABEL = f"{_DOMAIN}/{_DATASET_ID}"
_TIMEOUT_MS = QUERY_TIMEOUT_S * 1000
_NGRAM_SIZES = (1, 2, 3)  # the {n}grams databases that exist on the server


# ── dataset + routing resolution ──────────────────────────────────────────────

async def _get_dataset(db: AsyncSession):
    dataset_obj = await get_latest_entry(db, _DOMAIN, _DATASET_ID)
    if not dataset_obj:
        raise HTTPException(status_code=404, detail=f"'{_LABEL}' dataset not found")
    if dataset_obj.data_format != "mongodb":
        raise HTTPException(
            status_code=400,
            detail=(
                f"'{_LABEL}' is registered as '{dataset_obj.data_format}', but this "
                "router serves mongodb pass-through datasets only."
            ),
        )
    return dataset_obj


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


def _coll(ngram_size: int, lang: str):
    db_name, coll_name = _route(ngram_size, lang)
    return get_mongo_collection_by_name(db_name, coll_name, _LABEL)


def _measures(dataset_obj, weight):
    """(count_col, rank_field, freq_field) for the requested ?weight=."""
    return resolve_measures(dataset_obj, resolve_count_column(dataset_obj, weight))


# ── term-series ───────────────────────────────────────────────────────────────

@router.get("/term-series", openapi_extra={"x-dataset": "ngrams"})
async def term_series(
    type: str = Query(..., description="The n-gram term to look up. Case-sensitive."),
    lang: str = Query("en", description="Language code — selects the MongoDB collection (e.g. 'en', 'es', '_all')."),
    ngram_size: int = Query(1, description="N-gram size (1|2|3) — selects the MongoDB database."),
    date: Optional[str] = Query(None, description="End date (YYYY-MM-DD). Defaults to latest available."),
    window: int = Query(365, description="Days to look back from date. 0 = full history."),
    weight: Optional[str] = Query(None, description="Measure — 'counts' (with retweets) or 'count_noRT'. Defaults to the first registered measure."),
    db: AsyncSession = Depends(get_session),
):
    """Per-date time series for a single term, routed to `{ngram_size}grams`/`lang`."""
    dataset_obj = await _get_dataset(db)
    type_col, time_col = _cols(dataset_obj)
    count_col, rank_field, freq_field = _measures(dataset_obj, weight)

    def _query():
        with handle_mongo_error(_LABEL):
            coll = _coll(ngram_size, lang)
            latest = _latest_available(coll, time_col)
            end = date or latest
            if not end:
                return latest, None
            q = {type_col: type, time_col: _range_filter(dataset_obj, time_col, end, window)}
            cursor = coll.find(
                q,
                projection=_projection(type_col, time_col, count_col, rank_field, freq_field),
                max_time_ms=_TIMEOUT_MS,
            ).sort(time_col, 1)
            return latest, list(cursor)

    with timed("query", "MongoDB find"):
        latest, docs = await run_blocking_mongo(_query)

    if docs is None:
        return JSONResponse(
            status_code=404,
            content={"detail": f"No data for lang={lang!r}, ngram_size={ngram_size}", "latest_available_date": None},
        )

    # The source collection contains exact-duplicate (word, day) rows (heavy in
    # some periods, e.g. early 2023), which would draw the same point repeatedly
    # and read as a flat rank. Keep one row per day — dups are identical, so this
    # is lossless. docs are time-sorted, so first-seen is canonical.
    series, seen = [], set()
    for d in docs:
        day = str(d[time_col])[:10]
        if day in seen:
            continue
        seen.add(day)
        series.append(series_entry(day, d.get(count_col), d.get(rank_field), d.get(freq_field)))

    return {"type": type, "latest_available_date": latest, "series": series}


# ── term-series/batch ─────────────────────────────────────────────────────────

@router.get("/term-series/batch", openapi_extra={"x-dataset": "ngrams"})
async def term_series_batch(
    types: str = Query(..., description="Comma-separated terms, e.g. 'trump,covid,the'. Case-sensitive."),
    lang: str = Query("en", description="Language code — selects the MongoDB collection."),
    ngram_size: int = Query(1, description="N-gram size (1|2|3) — selects the MongoDB database."),
    date: Optional[str] = Query(None, description="End date (YYYY-MM-DD). Defaults to latest available."),
    window: int = Query(365, description="Days to look back from date. 0 = full history."),
    weight: Optional[str] = Query(None, description="Measure — 'counts' or 'count_noRT'."),
    db: AsyncSession = Depends(get_session),
):
    """Batch time series lookup — a map of term → series in one request."""
    dataset_obj = await _get_dataset(db)
    type_col, time_col = _cols(dataset_obj)
    count_col, rank_field, freq_field = _measures(dataset_obj, weight)

    type_list = [t.strip() for t in types.split(",") if t.strip()]
    if not type_list:
        raise HTTPException(status_code=400, detail="types parameter must contain at least one term")

    def _query():
        with handle_mongo_error(_LABEL):
            coll = _coll(ngram_size, lang)
            latest = _latest_available(coll, time_col)
            end = date or latest
            if not end:
                return latest, None
            q = {type_col: {"$in": type_list},
                 time_col: _range_filter(dataset_obj, time_col, end, window)}
            cursor = coll.find(
                q,
                projection=_projection(type_col, time_col, count_col, rank_field, freq_field),
                max_time_ms=_TIMEOUT_MS,
            ).sort([(type_col, 1), (time_col, 1)])
            return latest, list(cursor)

    with timed("query", "MongoDB find"):
        latest, docs = await run_blocking_mongo(_query)

    if docs is None:
        return JSONResponse(
            status_code=404,
            content={"detail": f"No data for lang={lang!r}, ngram_size={ngram_size}", "latest_available_date": None},
        )

    # Dedupe the source's exact-duplicate (word, day) rows — one point per
    # (term, day). See term-series for why.
    results: dict = {t: [] for t in type_list}
    seen = set()
    for d in docs:
        term = d[type_col]
        day = str(d[time_col])[:10]
        if (term, day) in seen:
            continue
        seen.add((term, day))
        results[term].append(
            series_entry(day, d.get(count_col), d.get(rank_field), d.get(freq_field))
        )

    return {"results": results, "latest_available_date": latest}


# ── top-ngrams ────────────────────────────────────────────────────────────────

@router.get("/top-ngrams", openapi_extra={"x-dataset": "ngrams"})
async def top_ngrams(
    dates: str = Query(..., description="A single date (YYYY-MM-DD) for system 1."),
    dates2: Optional[str] = Query(None, description="Optional single date for a second system to compare."),
    lang: str = Query("en", description="Language code — selects the MongoDB collection."),
    ngram_size: int = Query(1, description="N-gram size (1|2|3) — selects the MongoDB database."),
    weight: Optional[str] = Query(None, description="Measure — 'counts' or 'count_noRT'."),
    limit: int = Query(100, le=10000),
    db: AsyncSession = Depends(get_session),
):
    """Top terms for a single date (optionally two dates to compare).

    Uses the pipeline-precomputed `rank`, so a plain sort/limit suffices —
    no server-side aggregation. Single dates only: summing counts over a
    range would need an aggregation pipeline (parquet territory).
    """
    for label, val in (("dates", dates), ("dates2", dates2)):
        if val and "," in val:
            raise HTTPException(
                status_code=400,
                detail=f"{label} must be a single YYYY-MM-DD date for mongodb datasets — "
                       "range aggregation is not supported on the pass-through path.",
            )

    dataset_obj = await _get_dataset(db)
    type_col, time_col = _cols(dataset_obj)
    count_col, _, _ = _measures(dataset_obj, weight)

    def _top(coll, date_str: str) -> list:
        q = {time_col: _day_filter(dataset_obj, time_col, date_str)}
        # Over-fetch so dedupe still yields ~limit unique terms on heavily-
        # duplicated days: some days are uniformly ~5x duplicated at the source
        # (whole-day re-ingestion), so top-N by count is 1/5 unique. 8x covers
        # that with margin; pathological days may still fall short (the real fix
        # is upstream deduplication of the collection).
        cursor = (
            coll.find(q, projection={type_col: True, count_col: True, "_id": False},
                      max_time_ms=_TIMEOUT_MS)
            .sort(count_col, -1)
            .limit(limit * 8)
        )
        out, seen = [], set()
        for d in cursor:
            term = d.get(type_col)
            if term in seen:
                continue
            seen.add(term)
            out.append({"types": term, "counts": d.get(count_col)})
            if len(out) >= limit:
                break
        return out

    def _query():
        with handle_mongo_error(_LABEL):
            coll = _coll(ngram_size, lang)
            first = _top(coll, dates)
            second = _top(coll, dates2) if dates2 else None
            return first, second

    with timed("query", "MongoDB find"):
        first, second = await run_blocking_mongo(_query)

    metadata = {"lang": lang, "ngram_size": ngram_size, "weight": count_col}
    if second is not None:
        return {dates: first, dates2: second, "metadata": metadata}
    return {"data": first, "metadata": metadata}


# ── instrument routing ────────────────────────────────────────────────────────
# Allotax/RTD go through the platform instruments (/storywrangler/allotax,
# /storywrangler/rtd). Host-form data_location means this router owns the
# db/collection layout — registered as the domain's routing hook so
# mongo_query can resolve collections for instrument requests.


def _instrument_routing(filter_vals: dict) -> tuple:
    return _route(int(filter_vals.get("ngram_size", 1)), str(filter_vals.get("lang", "en")))


register_mongo_routing(_DOMAIN, _instrument_routing)
