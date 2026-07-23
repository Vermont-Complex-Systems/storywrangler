"""
Storywrangler instruments — platform-level analytics tools.

Currently includes:
  - allotax: rank-turbulence divergence between two types-counts distributions.
             Generic — works for any registered dataset with endpoint_schema.type='types-counts'.
  - rtd: lightweight rank-turbulence divergence (wordshift only, no diamond/balance).
         Designed for on-the-fly date-vs-date comparisons within a single entity.
"""

import logging
import math
from types import SimpleNamespace
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from ..core.allotax_utils import (
    sanitize_floats as _sanitize_floats,
    allotax_version as _allotax_version,
    wordshift_version as _wordshift_version,
)
from ..core.database import get_session
from ..core.duckdb_client import get_duckdb_client, run_blocking
from ..core.mongo_client import run_blocking_mongo
from ..core.mongo_query import load_instrument_system, require_single_dates
from ..core.duckdb_query import (
    build_hive_path, derive_time_partitions, handle_query_error, is_data_missing,
    load_system,
)
from ..core.query_utils import (
    dates_mode, extract_filter_vals, latest_available_for, latest_from_manifest,
    parse_dates, require_dates_supported, require_types_counts,
    resolve_count_column, resolve_entity, resolve_series_columns,
)
from ..core.registry_utils import get_latest_entry
from ..core.term_series import (
    fetch_provenance, fetch_sparkline_rows, ngrams_context, run_top_ngrams,
)
from . import openapi_docs as docs
from ..core.timing import timed

log = logging.getLogger(__name__)

router = APIRouter()


async def _resolve_types_counts(db, domain: str, dataset: str, dates=None, dates2=None):
    """Shared instrument/endpoint preamble: resolve a dataset and gate it.

    Every generic endpoint here (top-ngrams, allotax, rtd, wordshift,
    term-series) begins the same way: fetch the latest registry entry, 404 if
    absent, require the types-counts endpoint family, and reject dates on a
    dateless dataset.
    """
    dataset_obj = await get_latest_entry(db, domain, dataset)
    if not dataset_obj:
        raise HTTPException(status_code=404, detail=f"Dataset '{domain}/{dataset}' not found")
    require_types_counts(dataset_obj)
    require_dates_supported(dataset_obj, f"{domain}/{dataset}", dates, dates2)
    return dataset_obj


def _parse_reference_value(rv: Optional[str]):
    """Coerce the ``reference_value`` query param into what wordshift accepts.

    Query params arrive as strings, but the wordshift binding wants ``None``,
    the literal string ``"average"``, or a real Python float (a numeric *string*
    is rejected). Maps: absent/blank → ``None`` (system-1 weighted mean),
    ``"average"`` → ``"average"``, a numeric string → ``float``.
    """
    if rv is None or rv.strip() == "":
        return None
    if rv.strip().lower() == "average":
        return "average"
    try:
        return float(rv)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid reference_value: {rv!r}. Use 'average' or a number "
                   "(e.g. 5.0 for labMT's neutral midpoint).",
        )


# ── top-ngrams (generic) ──────────────────────────────────────────────────────

@router.get(
    "/top-ngrams",
    openapi_extra=docs.STORYWRANGLER_TOP_NGRAMS,
)
async def top_ngrams(
    request: Request,
    domain: str = Query("wikimedia", description="Domain owning the dataset"),
    dataset: str = Query("ngrams", description="Dataset ID within the domain"),
    dates: Optional[str] = Query(None, description="Date/year range for system 1. Single value '2024-10-01' or range '2024-10-01,2024-10-31'. Omit to load all time (datasets without a time dimension take no dates; mongodb datasets require a single date)."),
    dates2: Optional[str] = Query(None, description="Optional second range for a temporal comparison."),
    entity: Optional[str] = Query(None, description="Global entity ID (e.g. 'wikidata:Q30') or local ID. Omit for datasets without entity_mapping."),
    weight: Optional[str] = Query(None, description="Count measure — one of the dataset's endpoint_schema.count_column entries. Defaults to the first registered measure."),
    limit: int = Query(100, description="Max types per system (0 = no limit). manifest.availability's `types` gives the vocabulary ceiling."),
    db: AsyncSession = Depends(get_session),
):
    """Top types by count for any registered types-counts dataset.

    The generic form of the per-domain `/{domain}/top-ngrams` endpoints: the
    dataset is selected by query params and filter dimensions are passed by
    their registered column names — `?ngram_size=1&granularity=daily` for
    wikimedia, `?n=1&lang=en` for reddit, `?sex=M` for babynames. Discover
    them via `GET /registry/{domain}/{dataset_id}`; missing partition dims
    get the dataset's registered defaults.

    With `dates2`, returns two systems keyed by date range for a temporal
    comparison (same shape as the per-domain endpoints). mongodb pass-through
    datasets accept single dates only.
    """
    if dates2 and not dates:
        raise HTTPException(status_code=400, detail="dates is required when dates2 is provided.")

    dataset_obj = await _resolve_types_counts(db, domain, dataset, dates, dates2)

    filter_vals = extract_filter_vals(dataset_obj, request.query_params)
    count_col = resolve_count_column(dataset_obj, weight)

    has_entity_mapping = bool((dataset_obj.entity_mapping or {}).get("local_id_column"))
    if has_entity_mapping and entity:
        local_id = (await resolve_entity(db, domain, dataset, entity)).local_id
    else:
        local_id = None

    metadata = {
        "domain": domain,
        "dataset": dataset,
        "dataset_version": dataset_obj.version,
        "entity": entity,
        "filters": filter_vals,
        "weight": count_col,
    }

    if dataset_obj.data_format == "mongodb":
        require_single_dates([("dates", dates)])
        require_single_dates([("dates2", dates2)], required=False)
        if dates2 == dates:
            raise HTTPException(
                status_code=400,
                detail="dates and dates2 resolve to the same range; "
                       "use different dates to compare two systems.",
            )

        def _query():
            def _load(date_str):
                sys = load_instrument_system(
                    dataset_obj, domain, filter_vals, date_str, limit, count_col)
                return [{"types": t, "counts": c} for t, c in zip(sys["types"], sys["counts"])]

            formatted1 = _load(dates)
            if dates2:
                return {dates: formatted1, dates2: _load(dates2), "metadata": metadata}
            return {"data": formatted1, "metadata": metadata}

        with timed("query", "MongoDB find"):
            return await run_blocking_mongo(_query)

    return await run_top_ngrams(
        dataset_obj, f"{domain}/{dataset}", local_id, dates, dates2,
        filter_vals, limit, metadata=metadata, count_col=count_col,
    )


# ── term-series (generic) ──────────────────────────────────────────────────────

def _series_select(dataset_obj, weight, type_col, time_col) -> tuple:
    """(select_cols, cols) for a term-series row under the chosen weight.

    cols is {count, rank, freq} with None for companions the dataset did not
    declare (resolve_series_columns) — the response omits those. select_cols
    keeps a fixed 5-column shape (type, time, count, rank, freq), NULL-filling
    undeclared companions so row unpacking stays positional. type_col/time_col
    are the registered type/time columns.
    """
    cols = resolve_series_columns(dataset_obj, weight)
    if cols is None:
        cols = {"count": resolve_count_column(dataset_obj, weight), "rank": None, "freq": None}
    select_cols = (
        f"{type_col}, {time_col}, {cols['count']}, "
        f"{cols['rank'] or 'NULL'}, {cols['freq'] or 'NULL'}"
    )
    return select_cols, cols


def _series_row(row, cols, includes=None) -> dict:
    """Shape one term-series row, omitting companions the dataset didn't declare.

    *includes* is ``{dataset_id: {(type, date): [[doc, score], ...]}}`` — each
    requested ?include= provenance dataset's documents, attached under its id.
    """
    date_str = str(row[1])
    entry = {"date": date_str, "counts": int(row[2]) if row[2] else 0}
    if cols["rank"] is not None:
        entry["rank"] = int(row[3]) if row[3] else 0
    if cols["freq"] is not None:
        entry["freq"] = float(row[4]) if row[4] else 0.0
    for prov_id, prov in (includes or {}).items():
        entry[prov_id] = prov.get((row[0], date_str), [])
    return entry


async def _fetch_includes(db, domain, include, ctx, terms) -> dict:
    """Resolve and fetch each ?include= provenance dataset for *terms*.

    Returns ``{dataset_id: {(type, date): [[doc, score], ...]}}``. *include* is a
    comma-separated list of provenance dataset ids in this domain; an unknown or
    non-type-documents id is a 400 (rather than a silently empty field).
    """
    ids = [p.strip() for p in (include or "").split(",") if p.strip()]
    if not ids or not terms:
        return {}
    out: dict = {}
    for prov_id in ids:
        prov_obj = await get_latest_entry(db, domain, prov_id)
        if not prov_obj:
            raise HTTPException(
                status_code=400, detail=f"include dataset '{domain}/{prov_id}' not found")
        if (prov_obj.endpoint_schema or {}).get("type") != "type-documents":
            raise HTTPException(
                status_code=400,
                detail=f"include dataset '{domain}/{prov_id}' is not a type-documents "
                       "dataset (register it with endpoint_schema.type='type-documents').",
            )

        def _fetch(prov_obj=prov_obj, prov_id=prov_id):
            with get_duckdb_client().timed_connect() as conn:
                return fetch_provenance(
                    conn, prov_obj, sorted(terms),
                    entity_value=ctx.local_id, filter_vals=ctx.filter_vals,
                    date_condition=ctx.date_filter, date_params=ctx.date_params,
                    label=f"{domain}/{prov_id}", time_col=ctx.time_col,
                )
        with timed("include", f"provenance {prov_id}"):
            out[prov_id] = await run_blocking(_fetch)
    return out


async def _prepare_term_series(request, db, domain, dataset, entity, weight, dates):
    """Shared term-series setup — dataset, columns, entity, date range, path.

    *dates* is a single date or a 'start,end' range (parse_dates, same as the
    other generic endpoints); omit for full history. Returns (ctx, early) where
    early is a 404 JSONResponse when an undated request hits a slice with no
    data at all, else None.
    """
    dataset_obj = await _resolve_types_counts(db, domain, dataset, dates)
    if dates_mode(dataset_obj) == "none":
        raise HTTPException(
            status_code=400,
            detail=f"'{domain}/{dataset}' has no time dimension — a term time series needs one.",
        )

    # Type and time columns come from the registration (like load_system), not
    # hardcoded — so term-series works for any types-counts dataset, not only
    # the ngram/date ones. The response normalises to date/counts/rank/freq
    # regardless of the source column names.
    ep = dataset_obj.endpoint_schema or {}
    type_col = ep.get("type_column") or "types"
    time_col = (dataset_obj.transform or {}).get("time_dimension") or "date"

    select_cols, cols = _series_select(dataset_obj, weight, type_col, time_col)
    filter_vals = extract_filter_vals(dataset_obj, request.query_params)

    has_entity = bool((dataset_obj.entity_mapping or {}).get("local_id_column"))
    local_id = (
        (await resolve_entity(db, domain, dataset, entity)).local_id
        if has_entity and entity else None
    )

    latest_date = latest_available_for(dataset_obj, local_id, filter_vals)
    date_range = parse_dates(dates)
    if date_range is None and not latest_date:
        return None, JSONResponse(
            status_code=404,
            content={"detail": "No data found for this dataset", "latest_available_date": None},
        )

    # Explicit range → BETWEEN; omitted → full history (no time bound).
    if date_range:
        date_filter, date_params = f"{time_col} BETWEEN ? AND ?", [date_range[0], date_range[1]]
    else:
        date_filter, date_params = "1=1", []

    # base_path is the hive entity path (fallback for the dist-tree scan); flat
    # parquet has no level_order and scans read_parquet(data_location) directly.
    base_path = None
    if getattr(dataset_obj, "level_order", None):
        _, base_path = ngrams_context(dataset_obj, local_id, filter_vals)

    ctx = SimpleNamespace(
        dataset_obj=dataset_obj, select_cols=select_cols, cols=cols,
        filter_vals=filter_vals, local_id=local_id, latest_date=latest_date,
        date_filter=date_filter, date_params=date_params, base_path=base_path,
        type_col=type_col, time_col=time_col,
    )
    return ctx, None


def _term_series_scan_target(ctx) -> tuple:
    """(from_clause, extra_where, extra_params) for the direct date-first scan.

    parquet_hive pins entity / filter / single-valued time_partition components
    in the hive path (derive_time_partitions), adding WHERE IN conditions for
    multi-valued ones, so DuckDB prunes directories. Flat parquet has no hive
    levels: it reads read_parquet(data_location) and expresses entity and filter
    dimensions as in-file WHERE conditions.
    """
    obj = ctx.dataset_obj
    if getattr(obj, "level_order", None):
        tp_path_vals, tp_conditions, tp_params = derive_time_partitions(
            ctx.date_params, obj.level_order)
        path = build_hive_path(
            obj, entity_value=ctx.local_id, filter_vals=ctx.filter_vals,
            time_partition_vals=tp_path_vals, glob_suffix="/*.parquet",
        ) or f"{ctx.base_path}/*.parquet"
        return f"read_parquet('{path}', hive_partitioning=true)", tp_conditions, tp_params

    # Flat parquet: entity + filter dims are in-file columns → WHERE conditions.
    where, params = [], []
    entity_col = (obj.entity_mapping or {}).get("local_id_column")
    if entity_col and ctx.local_id is not None:
        where.append(f"{entity_col} = ?")
        params.append(ctx.local_id)
    for col, val in ctx.filter_vals.items():
        where.append(f"{col} = ?")
        params.append(val)
    loc = obj.data_location
    from_clause = (
        f"read_parquet('{loc}')" if isinstance(loc, str)
        else "read_parquet([" + ", ".join(f"'{p}'" for p in loc) + "])"
    )
    return from_clause, where, params


async def _term_series_rows(db, domain, ctx, terms, sparkline_dataset):
    """Fast sparkline bucket lookup, falling back to a dist-tree scan.

    Fast path: hash-bucket point lookup on the type-first sparkline dataset.
    Slow path: a scan of the date-first tree (year/month pruned where the tree
    has those levels) for terms outside the precomputed vocabulary.

    A term with no data on disk yields no rows — an empty series, the same
    whether one term or many was asked for. A *real* failure (a timeout, a
    genuine query error) raises through handle_query_error (504 / 500); it is
    never swallowed into an empty result, so a slow scan that times out reads
    as a timeout, not as "no data".
    """
    label = f"{domain}/term-series"
    rows = []
    sparkline_obj = (
        await get_latest_entry(db, domain, sparkline_dataset) if sparkline_dataset else None
    )
    if sparkline_obj:
        def _fast():
            with get_duckdb_client().timed_connect() as conn:
                return fetch_sparkline_rows(
                    conn, sparkline_obj, terms,
                    entity_value=ctx.local_id, filter_vals=ctx.filter_vals,
                    select_cols=ctx.select_cols, date_condition=ctx.date_filter,
                    date_params=ctx.date_params, label=label,
                    type_col=ctx.type_col, time_col=ctx.time_col,
                )
        with timed("fast_query", "sparkline bucket read"):
            rows = await run_blocking(_fast)
    if rows:
        return rows

    from_clause, extra_where, extra_params = _term_series_scan_target(ctx)
    placeholders = ", ".join(["?"] * len(terms))
    where = [f"{ctx.type_col} IN ({placeholders})"]
    if ctx.date_filter != "1=1":
        where.append(ctx.date_filter)
    where.extend(extra_where)
    sql = (
        f"SELECT {ctx.select_cols} FROM {from_clause} "
        f"WHERE {' AND '.join(where)} ORDER BY {ctx.type_col}, {ctx.time_col}"
    )
    params = [*terms, *ctx.date_params, *extra_params]

    def _slow():
        with handle_query_error(f"{domain}/{ctx.dataset_obj.dataset_id}"):
            with get_duckdb_client().timed_connect() as conn:
                try:
                    return conn.execute(sql, params).fetchall()
                except Exception as exc:
                    # A missing partition/file is a legitimate empty result (the
                    # slice-level 404 is handled earlier in _prepare_term_series);
                    # anything else re-raises for handle_query_error to classify.
                    if is_data_missing(exc):
                        log.info("%s: no partition data for %s", label, terms)
                        return []
                    raise

    with timed("slow_query", "DuckDB partition scan"):
        return await run_blocking(_slow)


@router.get("/term-series", openapi_extra=docs.STORYWRANGLER_TERM_SERIES)
async def term_series(
    request: Request,
    domain: str = Query("wikimedia", description="Domain owning the dataset"),
    dataset: str = Query("ngrams", description="Dataset ID within the domain"),
    type: str = Query(..., description="The type/term to look up. Case-sensitive."),
    entity: Optional[str] = Query(None, description="Global entity ID (e.g. 'wikidata:Q30') or local ID. Omit for datasets without entity_mapping."),
    dates: Optional[str] = Query(None, description="Date range: a single date '2024-06-01' or 'start,end' like '2024-01-01,2024-12-31'. Omit for full history."),
    weight: Optional[str] = Query(None, description="Count measure — one of the dataset's endpoint_schema.count_column entries. Defaults to the first."),
    sparkline_dataset: str = Query("sparklines", description="Registry dataset_id for the type-first sparkline precompute (default: 'sparklines'). Empty falls back to the dist-tree scan."),
    include: Optional[str] = Query(None, description="Comma-separated type-documents dataset id(s) whose ranked source documents to attach per date (e.g. 'top_articles_ngrams'). Each is added to every entry under its dataset id."),
    db: AsyncSession = Depends(get_session),
):
    """Per-date time series for a single type in any registered types-counts dataset.

    Returns counts, and rank/freq when the dataset declares `rank_column`/
    `freq_column`. Fast path: hash-bucket lookup on the type-first sparkline
    dataset; slow fallback: a scan of the date-first tree for types outside the
    precomputed vocabulary. mongodb datasets are served by their bespoke
    `/{domain}/term-series`.

    `include=<type-documents dataset id>` attaches that dataset's ranked source
    documents per date (the provenance behind each entry).
    """
    ctx, early = await _prepare_term_series(request, db, domain, dataset, entity, weight, dates)
    if early is not None:
        return early
    rows = await _term_series_rows(db, domain, ctx, [type], sparkline_dataset)
    includes = await _fetch_includes(db, domain, include, ctx, {r[0] for r in rows})
    return {
        "type": type,
        "latest_available_date": ctx.latest_date,
        "series": [_series_row(r, ctx.cols, includes) for r in rows],
    }


@router.get("/term-series/batch", openapi_extra={"x-dataset": "ngrams"})
async def term_series_batch(
    request: Request,
    domain: str = Query("wikimedia", description="Domain owning the dataset"),
    dataset: str = Query("ngrams", description="Dataset ID within the domain"),
    types: str = Query(..., description="Comma-separated types, e.g. 'trump,covid,the'. Case-sensitive."),
    entity: Optional[str] = Query(None, description="Global entity ID or local ID. Omit for datasets without entity_mapping."),
    dates: Optional[str] = Query(None, description="Date range: a single date or 'start,end'. Omit for full history."),
    weight: Optional[str] = Query(None, description="Count measure — defaults to the first registered."),
    sparkline_dataset: str = Query("sparklines", description="Type-first sparkline dataset_id (default: 'sparklines')."),
    include: Optional[str] = Query(None, description="Comma-separated type-documents dataset id(s) whose ranked source documents to attach per date."),
    db: AsyncSession = Depends(get_session),
):
    """Batch term-series — a map of type → series in one request."""
    type_list = [t.strip() for t in types.split(",") if t.strip()]
    if not type_list:
        raise HTTPException(status_code=400, detail="types parameter must contain at least one term")
    ctx, early = await _prepare_term_series(request, db, domain, dataset, entity, weight, dates)
    if early is not None:
        return early
    rows = await _term_series_rows(db, domain, ctx, type_list, sparkline_dataset)
    includes = await _fetch_includes(db, domain, include, ctx, {r[0] for r in rows})
    results = {t: [] for t in type_list}
    for r in rows:
        results[r[0]].append(_series_row(r, ctx.cols, includes))
    return {"results": results, "latest_available_date": ctx.latest_date}


# ── instruments ───────────────────────────────────────────────────────────────

@router.get(
    "/allotax",
    openapi_extra=docs.STORYWRANGLER_ALLOTAXONOMETER,
)
async def allotaxonometer(
    request: Request,
    domain: str = Query("wikimedia", description="Domain owning the dataset"),
    dataset: str = Query("ngrams", description="Dataset ID within the domain"),
    entity: Optional[str] = Query(None, description="Global entity ID for system 1, e.g. 'wikidata:Q30' (United States). Optional — omit for datasets using filter_dimensions as the comparison axis."),
    entity2: Optional[str] = Query(None, description="Global entity ID for system 2, e.g. 'wikidata:Q145' (United Kingdom). Optional — omit for datasets using filter_dimensions as the comparison axis."),
    dates: Optional[str] = Query(None, description="Date/year range for system 1. Single value '2024-10-01' or range '2024-10-01,2024-10-31'. Omit to load all time."),
    dates2: Optional[str] = Query(None, description="Date/year range for system 2. Omit to load all time."),
    alpha: str = Query("1.0", description="RTD alpha parameter (number or 'inf')"),
    alphas: Optional[str] = Query(None, description="Comma-separated alphas for multi-alpha mode, e.g. '0.5,1.0,inf'"),
    weight: Optional[str] = Query(None, description="Count measure for both systems — one of the dataset's endpoint_schema.count_column entries. Defaults to the first registered measure."),
    ngram_limit: int = Query(10000, description="Max types to load per system before computing"),
    wordshift_limit: int = Query(200, description="Truncate wordshift output to top N entries"),
    db: AsyncSession = Depends(get_session),
):
    """Compares two type-frequency systems using the allotaxonometer (rank-turbulence divergence).

    Each system is defined by a dataset, an optional entity, a date range, and optional filter values.
    The two systems may differ on any combination of axes:

    - **entity vs entity** — e.g. US Wikipedia vs UK Wikipedia
    - **dates vs dates** — e.g. October vs November
    - **filter-only** — e.g. `sex=M` vs `sex2=F` (skipping entity registry)

    > **Filter dimensions** — look up a dataset's available filter dimensions via
    > `GET /registry/{domain}/{dataset_id}` (`transform.filter_dimensions`).
    > Pass them as extra query params using the `dim` / `dim2` suffix convention:
    > `?sex=M&sex2=F` compares boy vs girl babynames, `?geo=US&geo2=CA` compares countries.
    > Entity registration is optional when a filter dimension serves as the comparison axis.
    """
    try:
        alpha_f = float(alpha)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid alpha: {alpha!r}. Must be a number or 'inf'.")

    dataset_obj = await _resolve_types_counts(db, domain, dataset, dates, dates2)

    # Any level_order column (partition/filter type) can be passed as
    # ?dim=val (system 1) or ?dim2=val (system 2), using actual column names
    # from the dataset — e.g. ?ngram_size=1 for wikimedia, ?n=1 for reddit.
    filter_vals1 = extract_filter_vals(dataset_obj, request.query_params)
    filter_vals2 = extract_filter_vals(dataset_obj, request.query_params, suffix="2")

    # mongodb pass-through datasets load systems via the router-registered
    # hook (host-form data_location keeps db/collection routing in the bespoke
    # router). Single dates only: range aggregation is parquet territory.
    is_mongo = dataset_obj.data_format == "mongodb"
    if is_mongo:
        require_single_dates([("dates", dates), ("dates2", dates2)])
        # System 2 inherits system 1's routing/filters unless overridden (?lang2=...)
        filter_vals2 = {**filter_vals1, **filter_vals2}

    count_col = resolve_count_column(dataset_obj, weight)

    dr1 = parse_dates(dates)
    dr2 = parse_dates(dates2)

    has_entity_mapping = bool((dataset_obj.entity_mapping or {}).get("local_id_column"))
    if has_entity_mapping and entity:
        local_id1 = (await resolve_entity(db, domain, dataset, entity)).local_id
    else:
        local_id1 = None
    if has_entity_mapping and entity2:
        local_id2 = (await resolve_entity(db, domain, dataset, entity2)).local_id
    else:
        # date-vs-date mode: reuse entity1's local_id so the hive path
        # includes the correct entity partition for both systems.
        local_id2 = local_id1

    try:
        import allotax
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="allotax module not available. Install via: pip install allotax",
        )

    def _sync():
        if is_mongo:
            sys1 = load_instrument_system(dataset_obj, domain, filter_vals1, dates, ngram_limit, count_col)
            sys2 = load_instrument_system(dataset_obj, domain, filter_vals2, dates2, ngram_limit, count_col)
            if not sys1["types"]:
                raise HTTPException(status_code=404, detail=f"No data for system 1 ({filter_vals1}, date={dates})")
            if not sys2["types"]:
                raise HTTPException(status_code=404, detail=f"No data for system 2 ({filter_vals2}, date={dates2})")
        else:
            with handle_query_error(f"{domain}/{dataset}"):
                with get_duckdb_client().timed_connect() as conn:
                    sys1 = load_system(conn, dataset_obj, local_id1, dr1, filter_vals1, ngram_limit, count_col=count_col)
                    sys2 = load_system(conn, dataset_obj, local_id2, dr2, filter_vals2, ngram_limit, count_col=count_col)

        try:
            if alphas:
                alpha_list = [float(a) for a in alphas.split(",")]
                result_data = allotax.compute_allotax_multi_alpha(sys1, sys2, alpha_list, wordshift_limit)
                for ar, a in zip(result_data.get("alpha_results", []), alpha_list):
                    if ar.get("alpha") is None and math.isinf(a):
                        ar["alpha"] = "Infinity"
            else:
                result_data = allotax.compute_allotax(sys1, sys2, alpha_f, wordshift_limit)
                if result_data.get("alpha") is None and math.isinf(alpha_f):
                    result_data["alpha"] = "Infinity"

            return _sanitize_floats({
                **result_data,
                "meta": {
                    "system1": {"entity": entity, "dates": dates, "filters": filter_vals1, "types": len(sys1["types"])},
                    "system2": {"entity": entity2, "dates": dates2, "filters": filter_vals2, "types": len(sys2["types"])},
                    "weight": count_col,
                    "domain": domain,
                    "dataset": dataset,
                    "dataset_version": dataset_obj.version,
                    "allotax_version": _allotax_version(),
                },
            })
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Allotax computation failed: {str(e)}")

    return await (run_blocking_mongo(_sync) if is_mongo else run_blocking(_sync))


@router.get("/rtd")
async def rank_turbulence_divergence(
    request: Request,
    domain: str = Query("wikimedia", description="Domain owning the dataset"),
    dataset: str = Query("ngrams", description="Dataset ID within the domain"),
    entity: Optional[str] = Query(None, description="Global entity ID, e.g. 'wikidata:Q30' (United States)"),
    dates: Optional[str] = Query(None, description="Target date, e.g. '2026-02-17'"),
    dates2: Optional[str] = Query(None, description="Reference date, e.g. '2026-02-10'"),
    alpha: str = Query("0.25", description="RTD alpha parameter (number or 'inf')"),
    alphas: Optional[str] = Query(None, description="Comma-separated alphas for multi-alpha mode, e.g. '0.25,1.0,inf'"),
    weight: Optional[str] = Query(None, description="Count measure for both systems — one of the dataset's endpoint_schema.count_column entries. Defaults to the first registered measure."),
    ngram_limit: int = Query(10000, description="Max types to load per system (0 = no limit)"),
    wordshift_limit: int = Query(10000, description="Max wordshift entries to return (0 = no limit)"),
    db: AsyncSession = Depends(get_session),
):
    """Lightweight rank-turbulence divergence between two dates for a single entity.

    Returns per-term signed divergence contributions (wordshift) without the full
    allotaxonometer overhead (no diamond plot, no balance). Designed for fast
    on-the-fly comparisons (~80ms).

    Positive divergence = term is more prominent on the target date.

    Both `dates` and `dates2` must be provided. The frontend should compute
    valid dates from manifest.availability metadata.

    **Filter dimensions** are passed as extra query params (not listed above).
    Look up available filters via `GET /registry/{domain}/{dataset_id}`
    (`transform.filter_dimensions`). Use the `dim` / `dim2` suffix convention:
    `?sex=M` filters both systems, `?sex=M&sex2=F` compares across filter values.
    """
    try:
        alpha_f = float(alpha)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid alpha: {alpha!r}. Must be a number or 'inf'.")

    with timed("registry", "Registry lookup"):
        dataset_obj = await _resolve_types_counts(db, domain, dataset, dates, dates2)

    if dates and not dates2:
        raise HTTPException(
            status_code=400,
            detail="dates2 is required when dates is provided.",
        )

    # Build filter vals from query params (same pattern as /allotax)
    filter_vals = extract_filter_vals(dataset_obj, request.query_params)
    filter_vals2 = extract_filter_vals(dataset_obj, request.query_params, suffix="2")

    is_mongo = dataset_obj.data_format == "mongodb"
    if is_mongo:
        require_single_dates([("dates", dates), ("dates2", dates2)])
        filter_vals2 = {**filter_vals, **filter_vals2}

    # Same entity for both systems (date-vs-date comparison)
    if not filter_vals2:
        filter_vals2 = dict(filter_vals)

    count_col = resolve_count_column(dataset_obj, weight)

    dr1 = parse_dates(dates)
    dr2 = parse_dates(dates2)

    with timed("resolve", "Entity resolution"):
        has_entity_mapping = bool((dataset_obj.entity_mapping or {}).get("local_id_column"))
        if has_entity_mapping and entity:
            local_id = (await resolve_entity(db, domain, dataset, entity)).local_id
        else:
            local_id = None

    try:
        import allotax
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="allotax module not available. Install via: pip install allotax",
        )

    with timed("discover", "Latest date from manifest"):
        latest_date = latest_from_manifest(dataset_obj, local_id, filter_vals.get("granularity"))

    def _sync():
        with timed("query", "data load"):
            if is_mongo:
                target = load_instrument_system(dataset_obj, domain, filter_vals, dates, ngram_limit, count_col)
                ref = load_instrument_system(dataset_obj, domain, filter_vals2, dates2, ngram_limit, count_col)
            else:
                with handle_query_error(f"{domain}/{dataset}"):
                    with get_duckdb_client().timed_connect() as conn:
                        target = load_system(conn, dataset_obj, local_id, dr1, filter_vals, ngram_limit, count_col=count_col)
                        ref = load_system(conn, dataset_obj, local_id, dr2, filter_vals2, ngram_limit, count_col=count_col)

        if not target["types"]:
            raise HTTPException(status_code=404, detail=f"No data for target date {dates}")
        if not ref["types"]:
            raise HTTPException(status_code=404, detail=f"No data for reference date {dates2}")

        try:
            with timed("allotax", "RTD computation"):
                # ref first → positive divergence = "more prominent on target date"
                if alphas:
                    alpha_list = [float(a) for a in alphas.split(",")]
                    result = allotax.rank_turbulence_divergence_multi_alpha(
                        ref, target, alpha_list, limit=wordshift_limit)
                    for ar, a in zip(result.get("alpha_results", []), alpha_list):
                        if ar.get("alpha") is None and math.isinf(a):
                            ar["alpha"] = "Infinity"
                    result_data = result
                else:
                    result = allotax.rank_turbulence_divergence(
                        ref, target, alpha_f, limit=wordshift_limit)
                    if result.get("alpha") is not None:
                        pass  # no fixup needed
                    result_data = {
                        "wordshift": result["wordshift"],
                        "normalization": result["normalization"],
                        "delta_sum": result["delta_sum"],
                    }

            with timed("serialize", "Response serialization"):
                return _sanitize_floats({
                    **result_data,
                    "latest_available_date": latest_date,
                    "meta": {
                        "entity": entity,
                        "dates": dates,
                        "dates2": dates2,
                        "alpha": alpha_f if not alphas else alpha_list,
                        "domain": domain,
                        "dataset": dataset,
                        "dataset_version": dataset_obj.version,
                        "filters": filter_vals,
                        "ngram_limit": ngram_limit,
                        "wordshift_limit": wordshift_limit,
                        "types_target": len(target["types"]),
                        "types_ref": len(ref["types"]),
                        "allotax_version": _allotax_version(),
                    },
                })
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"RTD computation failed: {str(e)}")

    return await (run_blocking_mongo(_sync) if is_mongo else run_blocking(_sync))


@router.get("/wordshift")
async def weighted_avg_wordshift(
    request: Request,
    domain: str = Query("wikimedia", description="Domain owning the dataset"),
    dataset: str = Query("ngrams", description="Dataset ID within the domain"),
    entity: Optional[str] = Query(None, description="Global entity ID for system 1, e.g. 'wikidata:Q30' (United States). Optional — omit for datasets using filter_dimensions as the comparison axis."),
    entity2: Optional[str] = Query(None, description="Global entity ID for system 2, e.g. 'wikidata:Q145' (United Kingdom). Omit to reuse system 1's entity (e.g. date-vs-date)."),
    dates: Optional[str] = Query(None, description="Date/year range for system 1. Single value '2024-10-01' or range '2024-10-01,2024-10-31'. Omit to load all time."),
    dates2: Optional[str] = Query(None, description="Date/year range for system 2. Omit to load all time."),
    lexicon: str = Query("labMT_English", description="labMT language lexicon: labMT_English, labMT_French, labMT_German, labMT_Spanish, labMT_Portuguese, labMT_Russian, labMT_Chinese, labMT_Hindi, labMT_Indonesian, labMT_Korean (short names like 'English' also accepted)."),
    reference_value: Optional[str] = Query(None, description="Score partition point: omit for system 1's frequency-weighted mean (the baseline), 'average' (equivalent), or a number like 5.0 (labMT's neutral midpoint)."),
    weight: Optional[str] = Query(None, description="Count measure for both systems — one of the dataset's endpoint_schema.count_column entries. Defaults to the first registered measure."),
    ngram_limit: int = Query(10000, description="Max types to load per system before computing (0 = no limit)"),
    wordshift_limit: int = Query(200, description="Truncate per-word output to the top N by |shift| (0 = all). Component sums are always computed over the full vocabulary."),
    db: AsyncSession = Depends(get_session),
):
    """Weighted-average sentiment word shift between two type-frequency systems.

    Scores each system's vocabulary with a bundled labMT happiness lexicon and
    returns each word's signed contribution to the change in average sentiment,
    plus the six component sums needed to render a shift graph. This is the
    sentiment analogue of `/rtd`: same data-loading path, a different instrument.

    **System 1 is the baseline; system 2 is read as a shift away from it.** The
    two systems may differ on any axis (like `/allotax`):

    - **entity vs entity** — e.g. US Wikipedia vs UK Wikipedia
    - **dates vs dates** — e.g. October vs November (omit `entity2` to reuse the entity)
    - **filter-only** — e.g. `?sex=M&sex2=F`

    Positive `shift_score` = the word pushed system 2's average sentiment up
    relative to system 1. `s_avg_1`/`s_avg_2` are the two weighted-mean scores.

    > **Lexicon** — wikipedia ngrams are English (enwiki), so `labMT_English`
    > is correct for every entity. Override `lexicon` only for corpora in
    > another language. labMT scores single words, so keep `ngram_size=1`
    > (the default); higher n-gram sizes match nothing and return an empty shift.

    > **Filter dimensions** — look up available filters via
    > `GET /registry/{domain}/{dataset_id}` (`transform.filter_dimensions`) and
    > pass them with the `dim` / `dim2` suffix convention.
    """
    dataset_obj = await _resolve_types_counts(db, domain, dataset, dates, dates2)

    ref_val = _parse_reference_value(reference_value)

    # ?dim=val → system 1, ?dim2=val → system 2 (same convention as /allotax).
    filter_vals1 = extract_filter_vals(dataset_obj, request.query_params)
    filter_vals2 = extract_filter_vals(dataset_obj, request.query_params, suffix="2")

    is_mongo = dataset_obj.data_format == "mongodb"
    if is_mongo:
        require_single_dates([("dates", dates), ("dates2", dates2)])
        # System 2 inherits system 1's routing/filters unless overridden (?lang2=...)
        filter_vals2 = {**filter_vals1, **filter_vals2}

    count_col = resolve_count_column(dataset_obj, weight)

    dr1 = parse_dates(dates)
    dr2 = parse_dates(dates2)

    has_entity_mapping = bool((dataset_obj.entity_mapping or {}).get("local_id_column"))
    if has_entity_mapping and entity:
        local_id1 = (await resolve_entity(db, domain, dataset, entity)).local_id
    else:
        local_id1 = None
    if has_entity_mapping and entity2:
        local_id2 = (await resolve_entity(db, domain, dataset, entity2)).local_id
    else:
        # reuse system 1's entity so the hive path pins the correct partition
        # for both systems (date-vs-date / filter-only mode).
        local_id2 = local_id1

    try:
        import wordshift
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="wordshift module not available. Install via: pip install wordshift",
        )

    # Validate the lexicon up front (cheap) so a bad name fails before the load.
    try:
        wordshift.weighted_avg_shift({}, {}, lexicon=lexicon)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Unknown lexicon {lexicon!r}: {e}")

    def _sync():
        if is_mongo:
            sys1 = load_instrument_system(dataset_obj, domain, filter_vals1, dates, ngram_limit, count_col)
            sys2 = load_instrument_system(dataset_obj, domain, filter_vals2, dates2, ngram_limit, count_col)
        else:
            with handle_query_error(f"{domain}/{dataset}"):
                with get_duckdb_client().timed_connect() as conn:
                    sys1 = load_system(conn, dataset_obj, local_id1, dr1, filter_vals1, ngram_limit, count_col=count_col)
                    sys2 = load_system(conn, dataset_obj, local_id2, dr2, filter_vals2, ngram_limit, count_col=count_col)

        if not sys1["types"]:
            raise HTTPException(status_code=404, detail=f"No data for system 1 ({filter_vals1}, dates={dates})")
        if not sys2["types"]:
            raise HTTPException(status_code=404, detail=f"No data for system 2 ({filter_vals2}, dates={dates2})")

        # load_system returns parallel {types, counts}; wordshift wants {word: freq}.
        t2f1 = dict(zip(sys1["types"], sys1["counts"]))
        t2f2 = dict(zip(sys2["types"], sys2["counts"]))

        try:
            result = wordshift.weighted_avg_shift(
                t2f1, t2f2, lexicon=lexicon, reference_value=ref_val, top_n=wordshift_limit,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"wordshift rejected input: {e}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"wordshift computation failed: {str(e)}")

        return _sanitize_floats({
            **result,
            "meta": {
                "system1": {"entity": entity, "dates": dates, "filters": filter_vals1, "types": len(sys1["types"])},
                "system2": {"entity": entity2, "dates": dates2, "filters": filter_vals2, "types": len(sys2["types"])},
                "lexicon": lexicon,
                "weight": count_col,
                "domain": domain,
                "dataset": dataset,
                "dataset_version": dataset_obj.version,
                "wordshift_version": _wordshift_version(),
            },
        })

    return await (run_blocking_mongo(_sync) if is_mongo else run_blocking(_sync))
