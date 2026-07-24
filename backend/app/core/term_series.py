"""The generic term-series query engine (/storywrangler/term-series [+ /batch]).

How a request flows — the endpoints in routers/storywrangler.py call exactly
these four, in order:

  1. prepare_term_series()  — resolve the dataset and everything the query
                              needs (columns, entity, date range, companions),
                              validated; returns a SeriesCtx.
  2. term_series_rows()     — load (type, date, count, rank, freq) rows:
                              type-first bucket lookup first, then a
                              date-first scan for the terms it missed
                              (mongodb datasets take their own path).
  3. fetch_includes()       — optional ?include= provenance documents.
  4. series_row()           — shape each row for the response.

Contracts worth knowing (the why behind the branches):

  Declared companions — the fast path is the types-counts dataset with
  ``orientation: type-first`` whose ``lineage.derived_from`` names the
  primary, or the primary itself when it declares that orientation
  (term-bucketed corpora with no date-first tree). ?include= sources are the
  ``type-documents`` companions, addressed by their declared ``role``.
  Nothing is sniffed from names or structure.

  Coverage gate — a companion answers by pinning the request's filter dims
  into its hive path, so a dim it has no level for means its files would be
  read as-is and mislabelled (a daily-only sparkline answering
  granularity=weekly). Such companions are skipped; the scan is correct.

  Bounded scan — the fallback scans only the terms the fast path missed, over
  the request's date range. An undated request is clamped to the slice's
  availability range in prepare_term_series, so the scan is always bounded
  and directory-pruned — never an open walk of the whole date-first tree. A
  self-served type-first dataset (bluesky) has no date-first tree behind it,
  so its bucket read is final: a miss is an honest empty, no scan.

  Honest results — a term with no data yields an empty series; a real
  failure (timeout, query error) raises through handle_query_error as
  504/500, never an empty result. A self-served type-first dataset runs its
  bucket read strict (no fallback to absorb a real error).
"""

import logging
from dataclasses import dataclass, field
from typing import Any, List, Optional

from fastapi import HTTPException

from .duckdb_client import get_duckdb_client, run_blocking
from .duckdb_query import (
    build_hive_path, derive_time_partitions, handle_query_error, is_data_missing,
)
from .mongo_client import QUERY_TIMEOUT_S, handle_mongo_error, run_blocking_mongo
from .mongo_query import (
    date_range_filter, latest_available, resolve_collection, resolve_measures,
    series_projection,
)
from .query_utils import (
    availability_range_for, dates_mode, extract_filter_vals, parse_dates,
    require_dates_supported, require_types_counts, resolve_companions,
    resolve_count_column, resolve_entity, resolve_series_columns,
)
from .registry_utils import get_latest_entry
from .timing import timed
from .type_first import fetch_provenance, fetch_sparkline_rows

log = logging.getLogger(__name__)


@dataclass
class SeriesCtx:
    """One term-series request, resolved and validated.

    Built once by prepare_term_series(); read by term_series_rows() and
    fetch_includes(). Two variants share it: parquet requests fill the
    "parquet path" fields, mongodb pass-through requests the "mongo path"
    ones (and set latest_date later, from a live probe).
    """

    dataset_obj: Any                       # RegistryEntry of the queried primary
    is_mongo: bool = False
    filter_vals: dict = field(default_factory=dict)   # validated dims, defaults injected
    local_id: Optional[str] = None         # resolved entity value (None: no entity_mapping)
    type_col: str = "types"                # registered type column
    time_col: str = "date"                 # registered time column
    cols: dict = field(default_factory=dict)  # {"count","rank","freq"}; rank/freq None when undeclared
    latest_date: Optional[str] = None      # max availability across primary + type-first form

    # parquet path
    select_cols: Optional[str] = None      # fixed 5-column SELECT list (see _series_select)
    date_filter: str = "1=1"               # SQL time condition (always a real range post-prepare)
    date_params: list = field(default_factory=list)
    companions: Optional[dict] = None      # resolve_companions() result (type_first + documents)
    type_first_obj: Any = None             # the fast path's dataset, None when there is none
    serves_itself: bool = False            # the queried dataset IS its type-first form

    # mongo path
    date_range: Optional[list] = None      # [start, end] or None for full history


# ── 1. Request setup ──────────────────────────────────────────────────────────

async def prepare_term_series(request, db, domain, dataset, entity, weight, dates,
                              sparkline_dataset=None) -> SeriesCtx:
    """Resolve and validate everything a term-series request needs.

    *dates* is a single date or a 'start,end' range; omit for full history.
    *sparkline_dataset* is the deprecated fast-path override (None → resolve
    from lineage/orientation; '' → disable). Raises 404/400 on an unknown
    dataset, a non-types-counts dataset, a dateless dataset, a missing
    entity, or an undated request against a slice with no data at all.
    """
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

    # Columns come from the registration, never hardcoded; the response
    # normalises to date/counts/rank/freq whatever the source names are.
    ep = dataset_obj.endpoint_schema or {}
    type_col = ep.get("type_column") or "types"
    time_col = (dataset_obj.transform or {}).get("time_dimension") or "date"

    filter_vals = extract_filter_vals(dataset_obj, request.query_params)

    # A term series is one slice and cannot aggregate (rank/freq don't sum),
    # so an entity-partitioned dataset needs the entity pinned.
    has_entity = bool((dataset_obj.entity_mapping or {}).get("local_id_column"))
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

    # mongodb pass-through: a different backend (find, not read_parquet); its
    # latest date comes from a live probe in _mongo_rows, and no
    # sparkline/include/hive machinery applies.
    if dataset_obj.data_format == "mongodb":
        count_col, rank_f, freq_f = resolve_measures(
            dataset_obj, resolve_count_column(dataset_obj, weight))
        return SeriesCtx(
            dataset_obj=dataset_obj, is_mongo=True,
            filter_vals=filter_vals, local_id=local_id,
            type_col=type_col, time_col=time_col,
            cols={"count": count_col, "rank": rank_f, "freq": freq_f},
            date_range=date_range,
        )

    select_cols, cols = _series_select(dataset_obj, weight, type_col, time_col)

    # Companions come from declared lineage — resolved once, for both the
    # fast path here and the ?include= documents in fetch_includes.
    companions = await resolve_companions(db, domain, dataset)
    type_first_obj = await _resolve_type_first(
        db, domain, dataset_obj, companions, sparkline_dataset)
    if type_first_obj is not None and not _companion_covers(type_first_obj, filter_vals):
        log.info(
            "%s/%s: sparkline %r has no hive level for dims %s; using the "
            "date-first scan (re-register the companion with those levels "
            "to restore the fast path)",
            domain, dataset, type_first_obj.dataset_id,
            _uncovered_dims(type_first_obj, filter_vals),
        )
        type_first_obj = None

    # Availability across primary + sparkline (the two pipelines advance
    # independently). latest_date defaults the UI's date picker; the [min, max]
    # range clamps an undated request so its fallback scan stays bounded.
    lo, hi = _widest_availability(dataset_obj, type_first_obj, local_id, filter_vals)
    latest_date = hi
    if date_range is None:
        if not hi:
            raise HTTPException(status_code=404, detail="No data found for this dataset")
        # Undated → the full available range: same series for an in-vocabulary
        # term (its whole history is within [lo, hi]), but a fallback scan for
        # an out-of-vocabulary term now prunes to those dates instead of
        # walking the entire date-first tree.
        date_range = [lo or hi, hi]

    date_filter = f"{time_col} BETWEEN ? AND ?"
    date_params = [date_range[0], date_range[1]]

    return SeriesCtx(
        dataset_obj=dataset_obj,
        filter_vals=filter_vals, local_id=local_id,
        type_col=type_col, time_col=time_col,
        cols=cols, latest_date=latest_date,
        select_cols=select_cols,
        date_filter=date_filter, date_params=date_params,
        companions=companions,
        type_first_obj=type_first_obj,
        serves_itself=(
            type_first_obj is not None
            and type_first_obj.dataset_id == dataset_obj.dataset_id
        ),
    )


async def _resolve_type_first(db, domain, dataset_obj, companions, sparkline_dataset):
    """The dataset whose buckets term-series point-looks-up — or None.

    Default (``sparkline_dataset is None``): the queried dataset itself when
    it declares ``orientation: type-first`` (it *is* the term-bucketed form),
    else the declared type-first companion from lineage. None means no fast
    path — the date-first scan serves everything, correct but slower. An
    explicit ``sparkline_dataset`` overrides by id (deprecated); ``""``
    disables the fast path.
    """
    if sparkline_dataset is not None:
        return await get_latest_entry(db, domain, sparkline_dataset) if sparkline_dataset else None
    if (dataset_obj.endpoint_schema or {}).get("orientation") == "type-first":
        return dataset_obj
    return companions["type_first"]


def _series_select(dataset_obj, weight, type_col, time_col) -> tuple:
    """(select_cols, cols) for a term-series row under the chosen weight.

    cols is {count, rank, freq} with None for companions the dataset did not
    declare — the response omits those. select_cols keeps a fixed 5-column
    shape (type, time, count, rank, freq), NULL-filling undeclared companions
    so row unpacking stays positional.
    """
    cols = resolve_series_columns(dataset_obj, weight)
    if cols is None:
        cols = {"count": resolve_count_column(dataset_obj, weight), "rank": None, "freq": None}
    select_cols = (
        f"{type_col}, {time_col}, {cols['count']}, "
        f"{cols['rank'] or 'NULL'}, {cols['freq'] or 'NULL'}"
    )
    return select_cols, cols


def _widest_availability(dataset_obj, type_first_obj, local_id, filter_vals) -> tuple:
    """(min, max) available dates across the primary and its type-first form.

    The two are built by separate pipelines that advance independently, so the
    widest span is the honest coverage — a fresh sparkline must not truncate a
    request, nor a lagging primary manifest hide dates the sparkline has.
    """
    los, his = [], []
    for obj in (dataset_obj, type_first_obj):
        if obj is None:
            continue
        lo, hi = availability_range_for(obj, local_id, filter_vals)
        if lo:
            los.append(lo)
        if hi:
            his.append(hi)
    return (min(los) if los else None, max(his) if his else None)


def _companion_covers(companion_obj, filter_vals: dict) -> bool:
    """Can the companion express every request filter dim as a hive level?

    (The coverage gate — see the module docstring.) A dim the companion
    levels on but holds no data for needs no check here: the pinned path
    misses, the read returns [], and the scan takes over.
    """
    levels = {lv["column"] for lv in (getattr(companion_obj, "level_order", None) or [])}
    return all(dim in levels for dim in filter_vals)


def _uncovered_dims(companion_obj, filter_vals: dict) -> list:
    """The request dims the companion has no hive level for (for log lines)."""
    levels = {lv["column"] for lv in (getattr(companion_obj, "level_order", None) or [])}
    return sorted(set(filter_vals) - levels)


# ── 2. Row loading ────────────────────────────────────────────────────────────

async def term_series_rows(domain: str, ctx: SeriesCtx, terms: List[str]) -> list:
    """(type, date, count, rank, freq) rows for *terms*, fast path first.

    Bucket point lookup on the type-first form, then a bounded date-first scan
    for the terms it did not find — per missing term, so a batch mixing
    vocabulary and out-of-vocabulary terms never returns a silent empty
    because a sibling hit. A self-served type-first dataset has no date-first
    tree, so its bucket read is final. Details: module docstring.
    """
    if ctx.is_mongo:
        return await _mongo_rows(domain, ctx, terms)

    rows = await _fast_rows(domain, ctx, terms) if ctx.type_first_obj else []
    if ctx.serves_itself:
        return rows  # the bucket read IS the read; a miss is an honest empty

    missing = [t for t in terms if t not in {r[0] for r in rows}]
    if not missing:
        return rows

    if rows:
        log.info("%s/term-series: %d/%d terms missing from sparkline; scanning %s",
                 domain, len(missing), len(terms), missing)
    scan_rows = await _scan_rows(domain, ctx, missing)
    # Each term's rows come whole from one source (time-sorted within it), so
    # concatenation preserves per-term chronology for the response builders.
    return [*rows, *scan_rows]


async def _fast_rows(domain: str, ctx: SeriesCtx, terms: List[str]) -> list:
    """Hash-bucket point lookup on the type-first form.

    Self-served datasets read strict under handle_query_error — with no scan
    behind the read, a real failure must classify as 504/500, not as "no
    data". Companion reads stay lax: a failure logs and the scan covers it.
    """
    def _read():
        with get_duckdb_client().timed_connect() as conn:
            return fetch_sparkline_rows(
                conn, ctx.type_first_obj, terms,
                entity_value=ctx.local_id, filter_vals=ctx.filter_vals,
                select_cols=ctx.select_cols, date_condition=ctx.date_filter,
                date_params=ctx.date_params, label=f"{domain}/term-series",
                type_col=ctx.type_col, time_col=ctx.time_col,
                strict=ctx.serves_itself,
            )

    if ctx.serves_itself:
        def _classified():
            with handle_query_error(f"{domain}/{ctx.dataset_obj.dataset_id}"):
                return _read()
        with timed("fast_query", "type-first bucket read"):
            return await run_blocking(_classified)

    with timed("fast_query", "sparkline bucket read"):
        return await run_blocking(_read)


async def _scan_rows(domain: str, ctx: SeriesCtx, terms: List[str]) -> list:
    """Date-first scan for *terms* (the terms the fast path did not find).

    Bounded by ctx.date_filter — always a real range, since prepare clamps an
    undated request to the slice's availability — so DuckDB prunes to those
    directories rather than walking the whole tree.
    """
    from_clause, extra_where, extra_params = _scan_target(ctx)
    placeholders = ", ".join(["?"] * len(terms))
    where = [f"{ctx.type_col} IN ({placeholders})", ctx.date_filter]
    where.extend(extra_where)
    sql = (
        f"SELECT {ctx.select_cols} FROM {from_clause} "
        f"WHERE {' AND '.join(where)} ORDER BY {ctx.type_col}, {ctx.time_col}"
    )
    params = [*terms, *ctx.date_params, *extra_params]

    def _run():
        with handle_query_error(f"{domain}/{ctx.dataset_obj.dataset_id}"):
            with get_duckdb_client().timed_connect() as conn:
                try:
                    return conn.execute(sql, params).fetchall()
                except Exception as exc:
                    # A missing partition/file is a legitimate empty result
                    # (the slice-level 404 fired in prepare_term_series if due);
                    # anything else classifies via handle_query_error.
                    if is_data_missing(exc):
                        log.info("%s/term-series: no partition data for %s", domain, terms)
                        return []
                    raise

    with timed("slow_query", "DuckDB partition scan"):
        return await run_blocking(_run)


def _scan_target(ctx: SeriesCtx) -> tuple:
    """(from_clause, extra_where, extra_params) for the date-first scan.

    parquet_hive pins entity / filter / single-valued time_partition levels
    into the hive path (derive_time_partitions) so DuckDB prunes directories,
    with WHERE IN for multi-valued ones. Columns that are not hive levels
    live inside the files and get plain WHERE clauses — on flat parquet that
    is all of them.
    """
    obj = ctx.dataset_obj
    entity_col = (obj.entity_mapping or {}).get("local_id_column")

    if getattr(obj, "level_order", None):
        tp_path_vals, conditions, params = derive_time_partitions(
            ctx.date_params, obj.level_order)
        path = build_hive_path(
            obj, entity_value=ctx.local_id, filter_vals=ctx.filter_vals,
            time_partition_vals=tp_path_vals, glob_suffix="/*.parquet",
        )
        level_cols = {lv["column"] for lv in obj.level_order}
        if entity_col and ctx.local_id is not None and entity_col not in level_cols:
            conditions.append(f"{entity_col} = ?")
            params.append(ctx.local_id)
        for col, val in ctx.filter_vals.items():
            if col not in level_cols:
                conditions.append(f"{col} = ?")
                params.append(val)
        return f"read_parquet('{path}', hive_partitioning=true)", conditions, params

    where, params = [], []
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


async def _mongo_rows(domain: str, ctx: SeriesCtx, terms: List[str]) -> list:
    """Rows for *terms* from a mongodb pass-through dataset.

    The mongo analogue of the parquet path: resolve the collection (routing
    hook), find ``{type: {$in: terms}, time: range}`` — a plain range read,
    no aggregation (the pass-through guardrail) — and return the same
    ``(type, time, count, rank, freq)`` tuples the parquet path yields.
    Duplicate (type, day) source rows are collapsed; ctx.latest_date is set
    from a live max-time probe.
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


# ── 3. ?include= provenance ───────────────────────────────────────────────────

async def fetch_includes(db, domain, include, ctx: SeriesCtx, terms,
                         include_dates=None) -> dict:
    """Resolve and fetch each ?include= provenance companion for *terms*.

    Returns ``{key: {(type, date): [[doc, score], ...]}}`` keyed by role (or
    dataset id, deprecated). *include* is a comma-separated list of roles, or
    ``all`` for every declared companion. *include_dates* (comma-separated
    exact dates) narrows the provenance read independently of the series
    range — a UI renders documents for the hovered/comparison dates, not for
    every point of a full-history sparkline.

    A companion that fails the coverage gate is skipped with a log line —
    same sparse-result semantics as a companion with no data.
    """
    tokens = [p.strip() for p in (include or "").split(",") if p.strip()]
    # mongodb pass-through datasets have no type-documents companions.
    if not tokens or not terms or ctx.is_mongo:
        return {}

    date_condition, date_params = ctx.date_filter, ctx.date_params
    dates = [d.strip() for d in (include_dates or "").split(",") if d.strip()]
    if dates:
        placeholders = ", ".join(["?"] * len(dates))
        date_condition, date_params = f"{ctx.time_col} IN ({placeholders})", dates

    doc_companions = (ctx.companions or {}).get("documents", {})
    selected: dict = {}
    for token in tokens:
        if token == "all":
            selected.update(doc_companions)
            continue
        key, prov_obj = await _resolve_include(db, domain, token, doc_companions)
        selected[key] = prov_obj

    out: dict = {}
    for key, prov_obj in selected.items():
        if not _companion_covers(prov_obj, ctx.filter_vals):
            log.info(
                "include %r (%s/%s): companion has no hive level for dims %s; "
                "skipping (its documents would come from the wrong slice)",
                key, domain, prov_obj.dataset_id,
                _uncovered_dims(prov_obj, ctx.filter_vals),
            )
            continue

        def _fetch(prov_obj=prov_obj):
            with get_duckdb_client().timed_connect() as conn:
                return fetch_provenance(
                    conn, prov_obj, sorted(terms),
                    entity_value=ctx.local_id, filter_vals=ctx.filter_vals,
                    date_condition=date_condition, date_params=date_params,
                    label=f"{domain}/{prov_obj.dataset_id}", time_col=ctx.time_col,
                )
        with timed("include", f"provenance {key}"):
            out[key] = await run_blocking(_fetch)
    return out


async def _resolve_include(db, domain, token, doc_companions) -> tuple:
    """Resolve one ?include= token → (key, prov_obj).

    A token is a declared provenance *role*, falling back to a raw
    type-documents dataset id (deprecated alias). Unknown or wrong-typed
    tokens are a 400, not a silently empty field.
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


# ── 4. Response shaping ───────────────────────────────────────────────────────

def series_row(row, cols, includes=None) -> dict:
    """Shape one (type, time, count, rank, freq) row for the response.

    rank/freq are omitted (not zero-filled) when the dataset declared no such
    column — "no rank" must stay distinguishable from "rank 0". *includes*
    attaches each provenance set's documents under its role key.
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
