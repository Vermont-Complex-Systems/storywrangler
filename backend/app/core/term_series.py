"""Shared helpers for the generic sparkline-backed endpoints (/storywrangler
term-series and top-ngrams).

These consume hive-partitioned ngram datasets with precomputed,
hash-bucket-sharded sparkline files. Everything that is not genuinely
endpoint-specific lives here:

  ngrams_context()        — (filter_vals, entity base path) for partition scans
  log_fast_path_miss()    — classify a sparkline failure before scan fallback
  bucket_files()          — glob the hash-bucket dirs that can hold a set of terms
  fetch_sparkline_rows()  — bucket-routed sparkline lookup for a set of terms
  fetch_provenance()      — bucket-routed source-document lookup (?include=)
  run_top_ngrams()        — the full top-ngrams endpoint body (off the event loop)
  prepare_term_series()   — shared term-series setup (dataset, cols, entity, path)
  term_series_rows()      — fast sparkline lookup / dist-tree scan for terms
  fetch_includes()        — resolve and fetch ?include= provenance companions
  series_row()            — shape one term-series row for the response
"""

import logging
from types import SimpleNamespace
from typing import List, Optional

from fastapi import HTTPException

from .duckdb_client import get_duckdb_client, run_blocking
from .duckdb_query import (
    assign_bucket, bucket_override_key, build_hive_path, derive_time_partitions,
    entity_base_path, get_bucket_config, handle_query_error, is_data_missing,
    load_system, resolve_bucket_count,
)
from .mongo_client import QUERY_TIMEOUT_S, handle_mongo_error, run_blocking_mongo
from .mongo_query import (
    date_range_filter, latest_available, resolve_collection, resolve_measures,
    series_projection,
)
from .query_utils import (
    dates_mode, extract_filter_vals, get_queryable_dims, latest_available_for,
    parse_dates, require_dates_supported, require_types_counts, resolve_companions,
    resolve_count_column, resolve_entity, resolve_series_columns,
)
from .registry_utils import get_latest_entry
from .timing import timed

log = logging.getLogger(__name__)


def ngrams_context(ngrams_obj, local_id, dim_values: dict) -> tuple:
    """Build (filter_vals, entity_base_path) for term-series partition scans."""
    dims = get_queryable_dims(ngrams_obj)
    filter_vals = {d: dim_values[d] for d in dims if d in dim_values}
    return filter_vals, entity_base_path(ngrams_obj, local_id, filter_vals)


def log_fast_path_miss(label: str, exc: Exception) -> None:
    """Classify a sparkline fast-path failure before falling back to the scan."""
    if is_data_missing(exc):
        log.info("%s: sparkline files missing; falling back to partition scan", label)
    else:
        log.warning(
            "%s: sparkline fast path failed (%s); falling back to partition scan",
            label, exc,
        )


def bucket_files(dataset_obj, terms, *, entity_value=None, filter_vals=None) -> List[str]:
    """Glob paths of the hash-bucket directories that can contain *terms*.

    Generic over the dataset's level layout: *filter_vals* holds the
    partition-level values ({"ngram_size": 1} for wikimedia, {"n": 1,
    "lang": "en"} for reddit), *entity_value* the entity level when one
    exists. Each bucket is globbed with ``/*.parquet`` — never a pinned
    filename: DuckLake-backed buckets hold several uniquely-named
    ``ducklake-<uuid>.parquet`` files whose set changes on every compaction.
    """
    hb = get_bucket_config(dataset_obj)
    key = bucket_override_key(dataset_obj, entity_value=entity_value, filter_vals=filter_vals)
    n_buckets = resolve_bucket_count(hb, key)
    buckets = {assign_bucket(t, n_buckets) for t in terms}
    return [
        build_hive_path(
            dataset_obj,
            filter_vals=filter_vals,
            entity_value=entity_value,
            bucket_value=b,
            glob_suffix="/*.parquet",
        )
        for b in sorted(buckets)
    ]


def _bucket_read(
    conn, dataset_obj, terms: List[str], *, entity_value, filter_vals: dict,
    select_cols: str, date_condition: str, date_params: list, label: str,
    type_col: str, time_col: str, order_extra: Optional[str] = None,
    strict: bool = False,
) -> list:
    """Bucket-routed read shared by the sparkline and provenance lookups.

    Globs the hash buckets that can hold *terms*, selects *select_cols* where
    the type is in *terms* and *date_condition* holds, ordered by (type, time)
    plus *order_extra* when given. Returns rows — or [] with a classified log
    line on failure (a missing shard is expected; anything else is warned).

    *strict* is for reads with no fallback behind them (a type-first primary
    serving itself): a missing shard still yields [], but any other failure
    re-raises so the caller's handle_query_error classifies it as 504/500
    instead of it reading as "no data".
    """
    files = bucket_files(dataset_obj, terms, entity_value=entity_value, filter_vals=filter_vals)
    file_list = ", ".join(f"'{f}'" for f in files)
    placeholders = ", ".join(["?"] * len(terms))
    order_by = f"{type_col}, {time_col}" + (f", {order_extra}" if order_extra else "")
    try:
        return conn.execute(
            f"""
            SELECT {select_cols}
            FROM read_parquet([{file_list}])
            WHERE {type_col} IN ({placeholders})
              AND {date_condition}
            ORDER BY {order_by}
            """,
            [*terms, *date_params],
        ).fetchall()
    except Exception as exc:
        if strict and not is_data_missing(exc):
            raise
        log_fast_path_miss(label, exc)
        return []


def fetch_sparkline_rows(
    conn, sparkline_obj, terms: List[str],
    *, entity_value, filter_vals: dict, select_cols: str,
    date_condition: str, date_params: list, label: str,
    type_col: str = "ngram", time_col: str = "date",
    strict: bool = False,
) -> list:
    """Bucket-routed sparkline lookup for *terms*.

    Generic over the dataset's layout: *filter_vals* holds the partition
    values ({"ngram_size": n} for wikimedia, {"n": n, "lang": lang} for
    reddit/bluesky), *entity_value* the entity level when one exists, and
    *select_cols* the SELECT list (columns vary per domain: pv_* for
    wikimedia, count/rank/freq for reddit/bluesky). *type_col*/*time_col* are
    the registered type/time columns (default ngram/date). Rows come back
    ordered by type, time — or [] with a classified log line on failure.
    """
    return _bucket_read(
        conn, sparkline_obj, terms, entity_value=entity_value, filter_vals=filter_vals,
        select_cols=select_cols, date_condition=date_condition, date_params=date_params,
        label=label, type_col=type_col, time_col=time_col, strict=strict,
    )


def fetch_provenance(
    conn, prov_obj, terms: List[str],
    *, entity_value, filter_vals: dict,
    date_condition: str, date_params: list, label: str,
    time_col: str = "date",
) -> dict:
    """Ranked source documents per (type, date) for *terms* — the include=.

    Reads a type-documents provenance dataset (doc/score/order columns from its
    endpoint_schema) via the same hash-bucket routing as the sparklines, and
    returns ``{(type, date): [[document, score], ...]}`` ordered by the declared
    order_column (or score descending). *time_col* is the registered time column
    (default 'date'). Missing files or an undeclared doc/score column yield
    ``{}`` (a classified log line, same as the sparkline path).
    """
    ep = prov_obj.endpoint_schema or {}
    type_col = ep.get("type_column") or "ngram"
    doc_col = ep.get("doc_column")
    score_col = ep.get("score_column")
    if not doc_col or not score_col:
        return {}
    order_by = ep.get("order_column") or f"{score_col} DESC"

    rows = _bucket_read(
        conn, prov_obj, sorted(terms), entity_value=entity_value, filter_vals=filter_vals,
        select_cols=f"{type_col}, {time_col}, {doc_col}, {score_col}",
        date_condition=date_condition, date_params=date_params, label=label,
        type_col=type_col, time_col=time_col, order_extra=order_by,
    )
    out: dict = {}
    for term, dt, doc, score in rows:
        out.setdefault((term, str(dt)), []).append([doc, float(score) if score else 0.0])
    return out


async def run_top_ngrams(
    dataset_obj,
    label: str,
    local_id: Optional[str],
    dates: Optional[str],
    dates2: Optional[str],
    filter_vals: dict,
    limit: int,
    metadata: dict,
    count_col: Optional[str] = None,
) -> dict:
    """The generic top-ngrams endpoint body, executed off the event loop.

    Loads one types-counts system (or two for a temporal comparison keyed
    by date range, start/end joined with "_") and formats the response.
    *dates* may be None for all-time / dateless datasets. *count_col*
    selects a measure from the registered count-column menu (resolve via
    resolve_count_column); None uses the dataset default.
    """
    if dates2 and parse_dates(dates) == parse_dates(dates2):
        # Identical ranges collide into one JSON key and silently drop system 1
        # — reject rather than return half the comparison with HTTP 200.
        raise HTTPException(
            status_code=400,
            detail="dates and dates2 resolve to the same range; "
                   "use different dates to compare two systems.",
        )

    def _query():
        with handle_query_error(label):
            with get_duckdb_client().timed_connect() as conn:
                dr1 = parse_dates(dates)
                sys1 = load_system(conn, dataset_obj, local_id, dr1, filter_vals, limit, count_col=count_col)
                formatted1 = [{"types": t, "counts": c} for t, c in zip(sys1["types"], sys1["counts"])]

                if dates2:
                    dr2 = parse_dates(dates2)
                    sys2 = load_system(conn, dataset_obj, local_id, dr2, filter_vals, limit, count_col=count_col)
                    formatted2 = [{"types": t, "counts": c} for t, c in zip(sys2["types"], sys2["counts"])]
                    key1 = dr1[0] if dr1[0] == dr1[1] else f"{dr1[0]}_{dr1[1]}"
                    key2 = dr2[0] if dr2[0] == dr2[1] else f"{dr2[0]}_{dr2[1]}"
                    return {key1: formatted1, key2: formatted2, "metadata": metadata}

                return {"data": formatted1, "metadata": metadata}

    return await run_blocking(_query)


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


def series_row(row, cols, includes=None) -> dict:
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


async def _resolve_include(db, domain, token, doc_companions) -> tuple:
    """Resolve one ?include= token → (key, prov_obj).

    A token is a declared provenance *role* (the clean surface — resolved from
    the primary's lineage companions), falling back to a raw type-documents
    dataset id (deprecated alias). Unknown or non-type-documents tokens are a
    400, not a silently empty field. The returned *key* is the token as asked,
    so the response nests under the role (or id) the caller used.
    """
    if token in doc_companions:
        return token, doc_companions[token]
    prov_obj = await get_latest_entry(db, domain, token)
    if not prov_obj:
        raise HTTPException(
            status_code=400,
            detail=f"include '{token}' is not a known provenance role or dataset "
                   f"in '{domain}'. Available roles: {sorted(doc_companions)}",
        )
    if (prov_obj.endpoint_schema or {}).get("type") != "type-documents":
        raise HTTPException(
            status_code=400,
            detail=f"include '{domain}/{token}' is not a type-documents dataset "
                   "(register it with endpoint_schema.type='type-documents').",
        )
    return token, prov_obj


async def fetch_includes(db, domain, include, ctx, terms) -> dict:
    """Resolve and fetch each ?include= provenance companion for *terms*.

    Returns ``{key: {(type, date): [[doc, score], ...]}}`` keyed by role (or
    dataset id for the deprecated raw-id form). *include* is a comma-separated
    list of provenance roles declared on the primary's lineage companions, or
    the literal ``all`` for every companion.
    """
    tokens = [p.strip() for p in (include or "").split(",") if p.strip()]
    # Provenance is a bucket-routed parquet read; mongodb pass-through datasets
    # have no type-documents companions, so include is a no-op there.
    if not tokens or not terms or getattr(ctx, "is_mongo", False):
        return {}

    doc_companions = (getattr(ctx, "companions", None) or {}).get("documents", {})
    selected: dict = {}
    for token in tokens:
        if token == "all":
            selected.update(doc_companions)
            continue
        key, prov_obj = await _resolve_include(db, domain, token, doc_companions)
        selected[key] = prov_obj

    out: dict = {}
    for key, prov_obj in selected.items():
        def _fetch(prov_obj=prov_obj):
            with get_duckdb_client().timed_connect() as conn:
                return fetch_provenance(
                    conn, prov_obj, sorted(terms),
                    entity_value=ctx.local_id, filter_vals=ctx.filter_vals,
                    date_condition=ctx.date_filter, date_params=ctx.date_params,
                    label=f"{domain}/{prov_obj.dataset_id}", time_col=ctx.time_col,
                )
        with timed("include", f"provenance {key}"):
            out[key] = await run_blocking(_fetch)
    return out


async def _resolve_sparkline_obj(db, domain, dataset_obj, companions, sparkline_dataset):
    """The dataset term-series bucket-routes for its fast path reads.

    Default (``sparkline_dataset is None``): the queried dataset itself when it
    declares ``orientation: type-first`` (it *is* the term-bucketed form — e.g.
    bluesky/ngrams — so the bucket read is the read, not a fast path over
    something slower), else the declared type-first companion (lineage +
    ``orientation: type-first``). None → no fast path, so the query uses the
    correct-but-slower date-first scan until a sparkline is registered with
    that orientation. An explicit ``sparkline_dataset`` overrides by id
    (deprecated); ``""`` also disables the fast path.
    """
    if sparkline_dataset is not None:
        return await get_latest_entry(db, domain, sparkline_dataset) if sparkline_dataset else None
    if (dataset_obj.endpoint_schema or {}).get("orientation") == "type-first":
        return dataset_obj
    return companions["type_first"]


async def prepare_term_series(request, db, domain, dataset, entity, weight, dates,
                              sparkline_dataset=None):
    """Shared term-series setup — dataset, columns, entity, date range, path.

    *dates* is a single date or a 'start,end' range (parse_dates, same as the
    other generic endpoints); omit for full history. *sparkline_dataset* is the
    deprecated fast-path override (default None → resolve via lineage). Returns
    the request ctx; raises 404 when an undated request hits a slice with no
    data at all.
    """
    # Same preamble as the router's other generic endpoints: resolve the latest
    # registry entry, 404 if absent, require types-counts, reject dates on a
    # dateless dataset.
    dataset_obj = await get_latest_entry(db, domain, dataset)
    if not dataset_obj:
        raise HTTPException(status_code=404, detail=f"Dataset '{domain}/{dataset}' not found")
    require_types_counts(dataset_obj)
    require_dates_supported(dataset_obj, f"{domain}/{dataset}", dates)
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

    filter_vals = extract_filter_vals(dataset_obj, request.query_params)
    has_entity = bool((dataset_obj.entity_mapping or {}).get("local_id_column"))
    # A term series is a single slice, and it cannot aggregate (rank/freq don't
    # sum). So an entity-partitioned dataset needs the entity pinned — otherwise
    # the scan spans every entity and returns duplicate-date rows.
    if has_entity and not entity:
        raise HTTPException(
            status_code=400,
            detail=f"'{domain}/{dataset}' is partitioned by entity — pass ?entity= "
                   "(a term series is a single entity's trajectory).",
        )
    local_id = (
        (await resolve_entity(db, domain, dataset, entity)).local_id if has_entity else None
    )
    date_range = parse_dates(dates)

    # mongodb pass-through: a different backend (find, not read_parquet). Its
    # cols come from resolve_measures and its latest date from a live probe in
    # _mongo_term_series_rows; no sparkline/include/hive machinery applies.
    if dataset_obj.data_format == "mongodb":
        count_col = resolve_count_column(dataset_obj, weight)
        count_col, rank_f, freq_f = resolve_measures(dataset_obj, count_col)
        ctx = SimpleNamespace(
            dataset_obj=dataset_obj, is_mongo=True,
            cols={"count": count_col, "rank": rank_f, "freq": freq_f},
            filter_vals=filter_vals, local_id=local_id, date_range=date_range,
            type_col=type_col, time_col=time_col, latest_date=None,
        )
        return ctx

    select_cols, cols = _series_select(dataset_obj, weight, type_col, time_col)

    # Companions are deduced from declared lineage: the type-first sparkline
    # (fast path) and the type-documents provenance sets (?include=). Resolved
    # here so the row scan and fetch_includes reuse them — and so latest date /
    # the no-data 404 can consider the sparkline, which refreshes nightly and
    # can run ahead of the primary's lagging manifest.
    companions = await resolve_companions(db, domain, dataset)
    sparkline_obj = await _resolve_sparkline_obj(
        db, domain, dataset_obj, companions, sparkline_dataset)

    # latest_available_date is the max of primary and sparkline availability
    # (the two pipelines advance independently); the undated no-data 404 uses it
    # too, so a fresh sparkline over a stale primary manifest does not false-404.
    latest_date = latest_available_for(dataset_obj, local_id, filter_vals)
    if sparkline_obj is not None:
        spark_latest = latest_available_for(sparkline_obj, local_id, filter_vals)
        latest_date = max((d for d in (latest_date, spark_latest) if d), default=None)
    if date_range is None and not latest_date:
        raise HTTPException(status_code=404, detail="No data found for this dataset")

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
        dataset_obj=dataset_obj, is_mongo=False, select_cols=select_cols, cols=cols,
        filter_vals=filter_vals, local_id=local_id, latest_date=latest_date,
        date_filter=date_filter, date_params=date_params, base_path=base_path,
        type_col=type_col, time_col=time_col,
        companions=companions, sparkline_obj=sparkline_obj,
    )
    return ctx


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
        # Columns that are not hive levels live inside the files — the pinned
        # path can't encode them, so entity / filter dims absent from level_order
        # still need WHERE clauses (mirrors load_system; latent while every dim
        # is a hive level, but keeps the "any types-counts dataset" claim true).
        conditions, params = list(tp_conditions), list(tp_params)
        level_cols = {lv["column"] for lv in obj.level_order}
        entity_col = (obj.entity_mapping or {}).get("local_id_column")
        if entity_col and ctx.local_id is not None and entity_col not in level_cols:
            conditions.append(f"{entity_col} = ?")
            params.append(ctx.local_id)
        for col, val in ctx.filter_vals.items():
            if col not in level_cols:
                conditions.append(f"{col} = ?")
                params.append(val)
        return f"read_parquet('{path}', hive_partitioning=true)", conditions, params

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


async def _mongo_term_series_rows(domain, ctx, terms) -> list:
    """Per-(type, date) rows for *terms* from a mongodb pass-through dataset.

    The mongo analogue of the parquet path: resolve the collection (routing
    hook), find ``{type: {$in: terms}, time: range}`` (a plain range read, no
    aggregation — the pass-through guardrail), and return rows in the same
    ``(type, time, count, rank, freq)`` tuple shape the parquet scan yields, so
    series_row handles both. Duplicate (type, day) rows in the source are
    collapsed (some corpora re-ingest whole days). Sets ctx.latest_date from a
    live max-time probe.
    """
    obj = ctx.dataset_obj
    count_col = ctx.cols["count"]
    rank_f, freq_f = ctx.cols["rank"], ctx.cols["freq"]

    def _query():
        with handle_mongo_error(f"{domain}/{obj.dataset_id}"):
            coll = resolve_collection(obj, domain, ctx.filter_vals)
            latest = latest_available(coll, ctx.time_col)
            q = {ctx.type_col: {"$in": list(terms)}}
            time_filter = date_range_filter(obj, ctx.time_col, ctx.date_range)
            if time_filter is not None:
                q[ctx.time_col] = time_filter
            cursor = coll.find(
                q,
                projection=series_projection(ctx.type_col, ctx.time_col, count_col, rank_f, freq_f),
                max_time_ms=QUERY_TIMEOUT_S * 1000,
            ).sort([(ctx.type_col, 1), (ctx.time_col, 1)])
            return latest, list(cursor)

    with timed("mongo_query", "MongoDB find"):
        latest, docs = await run_blocking_mongo(_query)
    ctx.latest_date = latest

    rows, seen = [], set()
    for d in docs:
        term = d.get(ctx.type_col)
        day = str(d.get(ctx.time_col))[:10]
        if (term, day) in seen:
            continue
        seen.add((term, day))
        rows.append((term, day, d.get(count_col), d.get(rank_f), d.get(freq_f)))
    return rows


async def term_series_rows(domain, ctx, terms):
    """Fast sparkline bucket lookup, falling back to a dist-tree scan.

    Fast path: hash-bucket point lookup on the type-first form — the sparkline
    companion resolved from lineage, or the queried dataset itself when it
    declares ``orientation: type-first`` (bluesky-style term-bucketed trees).
    Slow path: a scan of the date-first tree (year/month pruned where the tree
    has those levels) for terms outside the precomputed vocabulary. A
    self-served type-first dataset has no date-first tree, so there is no slow
    path: a bucket miss is an honest empty series, not a cue to re-read the
    same bucket tree through a wildcard glob.

    A term with no data on disk yields no rows — an empty series, the same
    whether one term or many was asked for. A *real* failure (a timeout, a
    genuine query error) raises through handle_query_error (504 / 500); it is
    never swallowed into an empty result, so a slow scan that times out reads
    as a timeout, not as "no data".
    """
    if getattr(ctx, "is_mongo", False):
        return await _mongo_term_series_rows(domain, ctx, terms)

    label = f"{domain}/term-series"
    rows = []
    sparkline_obj = ctx.sparkline_obj
    # Self-served: the queried dataset is its own type-first form (compare ids,
    # not identity — the deprecated ?sparkline_dataset= override re-fetches).
    self_served = (
        sparkline_obj is not None
        and sparkline_obj.dataset_id == ctx.dataset_obj.dataset_id
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
                    strict=self_served,
                )
        if self_served:
            # The bucket read is the only read: classify real errors (504/500)
            # rather than falling back, and return the honest result as-is.
            def _only():
                with handle_query_error(f"{domain}/{ctx.dataset_obj.dataset_id}"):
                    return _fast()
            with timed("fast_query", "type-first bucket read"):
                return await run_blocking(_only)
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
                    # slice-level 404 is handled earlier in prepare_term_series);
                    # anything else re-raises for handle_query_error to classify.
                    if is_data_missing(exc):
                        log.info("%s: no partition data for %s", label, terms)
                        return []
                    raise

    with timed("slow_query", "DuckDB partition scan"):
        return await run_blocking(_slow)
