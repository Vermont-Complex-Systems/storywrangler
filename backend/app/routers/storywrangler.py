"""
Storywrangler instruments — platform-level analytics tools.

Currently includes:
  - allotax: rank-turbulence divergence between two types-counts distributions.
             Generic — works for any registered dataset with endpoint_schema.type='types-counts'.
  - rtd: lightweight rank-turbulence divergence (wordshift only, no diamond/balance).
         Designed for on-the-fly date-vs-date comparisons within a single entity.
"""

import math
from importlib.metadata import PackageNotFoundError, version as pkg_version
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from storywrangler_schemas.coercion import coerce_scalar
from ..core.database import get_session
from ..core.duckdb_client import get_duckdb_client, run_blocking
from ..core.query_utils import (
    get_partition_defaults, get_queryable_dims, handle_query_error,
    latest_from_manifest, load_system, parse_dates, resolve_count_column,
    resolve_entity,
)
from ..core.registry_utils import get_latest_entry
from . import openapi_docs as docs
from ..core.timing import timed

router = APIRouter()


def _apply_defaults(filter_vals: dict, defaults: dict) -> None:
    """Inject defaults for missing partition dimensions (mutates filter_vals).

    *defaults* comes from ``get_partition_defaults()`` — values are already
    resolved scalars (no list handling needed).
    """
    for dim, default_val in defaults.items():
        filter_vals.setdefault(dim, default_val)


def _validate_and_coerce_filters(filter_dicts: list, filter_values: dict) -> None:
    """Validate filter values against introspected filter_values, with type coercion.

    Query params arrive as strings but filter_values stores typed values
    (ints, floats). Coerces string → int → float before checking membership.
    Raises 400 if a value is not in the valid set.
    """
    for vals_dict in filter_dicts:
        for dim, val in list(vals_dict.items()):
            valid = filter_values.get(dim, [])
            if not valid:
                continue
            if val not in valid:
                coerced = coerce_scalar(val)
                if coerced not in valid:
                    raise HTTPException(
                        status_code=400,
                        detail=f"{dim} must be one of {sorted(map(str, valid))}",
                    )
                vals_dict[dim] = coerced


def _sanitize_floats(obj):
    """Replace NaN → null, ±Infinity → string, so json.dumps won't choke."""
    if isinstance(obj, float):
        if math.isnan(obj):
            return None
        if math.isinf(obj):
            return "Infinity" if obj > 0 else "-Infinity"
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize_floats(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_floats(v) for v in obj]
    return obj


def _allotax_version() -> str:
    try:
        return pkg_version("allotax")
    except PackageNotFoundError:
        try:
            import allotax
            return getattr(allotax, "__version__", "unknown")
        except ImportError:
            return "not installed"


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

    dataset_obj = await get_latest_entry(db, domain, dataset)
    if not dataset_obj:
        raise HTTPException(status_code=404, detail=f"Dataset '{domain}/{dataset}' not found")

    ep = dataset_obj.endpoint_schema
    if not ep or ep.get("type") != "types-counts":
        raise HTTPException(
            status_code=400,
            detail="Dataset does not support the types-counts endpoint. Register with endpoint_schema.type='types-counts'.",
        )

    fv = dataset_obj.filter_values or {}
    all_dims = get_queryable_dims(dataset_obj)
    defaults = get_partition_defaults(dataset_obj)

    # Extract declared filter dimensions from query params.
    # Any column in level_order (partition/filter type) can be passed as
    # ?dim=val (system 1) or ?dim2=val (system 2). Use actual column names
    # from the dataset — e.g. ?ngram_size=1 for wikimedia, ?n=1 for reddit.
    qp = request.query_params
    filter_vals1 = {dim: qp[dim]       for dim in all_dims if dim in qp}
    filter_vals2 = {dim: qp[f"{dim}2"] for dim in all_dims if f"{dim}2" in qp}

    # Inject defaults from level_order for any partition dim still missing.
    _apply_defaults(filter_vals1, defaults)
    _apply_defaults(filter_vals2, defaults)

    # Validate and coerce filter values against introspected distinct values.
    _validate_and_coerce_filters([filter_vals1, filter_vals2], fv)

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

    return await run_blocking(_sync)


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
        dataset_obj = await get_latest_entry(db, domain, dataset)
        if not dataset_obj:
            raise HTTPException(status_code=404, detail=f"Dataset '{domain}/{dataset}' not found")

    ep = dataset_obj.endpoint_schema
    if not ep or ep.get("type") != "types-counts":
        raise HTTPException(
            status_code=400,
            detail="Dataset does not support the types-counts endpoint.",
        )

    if dates and not dates2:
        raise HTTPException(
            status_code=400,
            detail="dates2 is required when dates is provided.",
        )

    # Build filter vals from query params (same pattern as /allotax)
    all_dims = get_queryable_dims(dataset_obj)
    defaults = get_partition_defaults(dataset_obj)

    fv = dataset_obj.filter_values or {}
    qp = request.query_params
    filter_vals = {dim: qp[dim] for dim in all_dims if dim in qp}
    filter_vals2 = {dim: qp[f"{dim}2"] for dim in all_dims if f"{dim}2" in qp}

    _apply_defaults(filter_vals, defaults)
    _apply_defaults(filter_vals2, defaults)

    _validate_and_coerce_filters([filter_vals, filter_vals2], fv)

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
        with timed("query", "DuckDB data load"):
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

    return await run_blocking(_sync)
