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
from ..core.database import get_session
from ..core.duckdb_client import get_duckdb_client
from ..core.query_utils import (
    _is_data_missing, build_hive_path, get_partition_defaults, get_queryable_dims,
    handle_query_error, load_system, parse_dates, resolve_entity,
)
from ..core.registry_utils import get_latest_entry
from ..core.timing import timed

router = APIRouter()


def _apply_defaults(filter_vals: dict, defaults: dict) -> None:
    """Inject defaults for missing partition dimensions (mutates filter_vals).

    *defaults* comes from ``get_partition_defaults()`` — values are already
    resolved scalars (no list handling needed).
    """
    for dim, default_val in defaults.items():
        filter_vals.setdefault(dim, default_val)


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
    openapi_extra={
        "x-powered-by": "rust",
        "responses": {
            "200": {
                "description": "Successful response",
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {
                                "normalization": {"type": "number", "description": "Normalization constant for the rank-turbulence divergence"},
                                "delta_sum": {"type": "number", "description": "Sum of normalized divergence elements — the actual D_alpha^R value"},
                                "diamond_counts": {"type": "array", "description": "2D rank-space histogram used to render the diamond plot"},
                                "max_delta_loss": {"type": "number", "description": "Maximum delta-loss value (used for color-scale normalization)"},
                                "ncells": {"type": "integer", "description": "Number of cells along one side of the diamond grid; use to size the band scale"},
                                "maxlog10": {"type": "number", "description": "Largest log10(rank) across both systems, rounded up to at least 1; use to label diamond axes"},
                                "alpha": {"type": "number", "description": "Alpha parameter used in the computation"},
                                "balance": {"type": "number", "description": "Balance measure between the two systems (0.5 = equal, >0.5 = system 2 dominates)"},
                                "wordshift": {
                                    "type": "array",
                                    "description": "Top contributing types, sorted by absolute divergence contribution.",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "type": {"type": "string", "description": "The n-gram / token"},
                                            "rank1": {"type": "integer", "description": "Rank in system 1 (0 = absent)"},
                                            "rank2": {"type": "integer", "description": "Rank in system 2 (0 = absent)"},
                                            "score": {"type": "number", "description": "Signed divergence contribution (positive = system 2 favours this type)"},
                                        },
                                    },
                                },
                                "meta": {
                                    "type": "object",
                                    "description": "Request metadata echoed back",
                                    "properties": {
                                        "system1": {"type": "object", "description": "System 1 parameters: entity, dates, filters, type count"},
                                        "system2": {"type": "object", "description": "System 2 parameters: entity, dates, filters, type count"},
                                        "domain": {"type": "string", "description": "Dataset domain"},
                                        "dataset": {"type": "string", "description": "Dataset ID"},
                                        "granularity": {"type": "string", "description": "Granularity used"},
                                    },
                                },
                            },
                        },
                        "example": {
                            "normalization": 0.9871,
                            "diamond_counts": [[0, 1, 0], [2, 5, 3], [1, 4, 2]],
                            "max_delta_loss": 0.0421,
                            "alpha": 1.0,
                            "balance": 0.523,
                            "wordshift": [
                                {"type": "COVID", "rank1": 850, "rank2": 45, "score": 0.0189},
                                {"type": "election", "rank1": 1200, "rank2": 78, "score": 0.0142},
                                {"type": "the", "rank1": 1, "rank2": 2, "score": -0.0021},
                            ],
                            "meta": {
                                "system1": {
                                    "entity": "wikidata:Q30",
                                    "dates": "2024-10-01,2024-10-31",
                                    "filters": {},
                                    "types": 50000,
                                },
                                "system2": {
                                    "entity": "wikidata:Q145",
                                    "dates": "2024-11-01,2024-11-30",
                                    "filters": {},
                                    "types": 48000,
                                },
                                "domain": "wikimedia",
                                "dataset": "ngrams",
                                "granularity": "daily",
                            },
                        },
                    }
                },
            }
        }
    },
)
async def allotaxonometer(
    request: Request,
    domain: str = Query("wikimedia", description="Domain owning the dataset"),
    dataset: str = Query("ngrams", description="Dataset ID within the domain"),
    entity: Optional[str] = Query(None, description="Global entity ID for system 1, e.g. 'wikidata:Q30' (United States). Optional — omit for datasets using filter_dimensions as the comparison axis."),
    entity2: Optional[str] = Query(None, description="Global entity ID for system 2, e.g. 'wikidata:Q145' (United Kingdom). Optional — omit for datasets using filter_dimensions as the comparison axis."),
    dates: Optional[str] = Query(None, description="Date/year range for system 1. Single value '2024-10-01' or range '2024-10-01,2024-10-31'. Omit to load all time."),
    dates2: Optional[str] = Query(None, description="Date/year range for system 2. Omit to load all time."),
    granularity: str = Query("daily", description="Hive granularity (parquet_hive only): daily | weekly | monthly"),
    alpha: str = Query("1.0", description="RTD alpha parameter (number or 'inf')"),
    alphas: Optional[str] = Query(None, description="Comma-separated alphas for multi-alpha mode, e.g. '0.5,1.0,inf'"),
    ngram_limit: int = Query(10000, description="Max types to load per system before computing"),
    wordshift_limit: int = Query(200, description="Truncate wordshift output to top N entries"),
    n: int = Query(1, description="N-gram size (1 = unigrams, 2 = bigrams). Only used when 'ngram_size' is in transform.filter_dimensions."),
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

    # Step 1 — generic: any declared dim passed as ?dim=val / ?dim2=val
    qp = request.query_params
    filter_vals1 = {dim: qp[dim]       for dim in all_dims if dim in qp}
    filter_vals2 = {dim: qp[f"{dim}2"] for dim in all_dims if f"{dim}2" in qp}

    # Step 2 — alias injection: n → ngram_size (n is not a dim name).
    # Use the raw query param to detect explicit caller intent before defaults run.
    if "ngram_size" in all_dims:
        if "n" in qp and "ngram_size" not in filter_vals1:
            filter_vals1["ngram_size"] = n
        if "n2" in qp and "ngram_size" not in filter_vals2:
            filter_vals2["ngram_size"] = int(qp["n2"])

    # Step 3 — inject defaults from level_order for any partition dim still missing.
    _apply_defaults(filter_vals1, defaults)
    _apply_defaults(filter_vals2, defaults)

    # Validate assembled filter values against pre-introspected distinct values
    for vals_dict in (filter_vals1, filter_vals2):
        for dim, val in vals_dict.items():
            valid = fv.get(dim, [])
            if valid and val not in valid:
                raise HTTPException(
                    status_code=400,
                    detail=f"{dim} must be one of {sorted(map(str, valid))}",
                )

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

    with handle_query_error(f"{domain}/{dataset}"):
        conn = get_duckdb_client().connect()
        use_hive = dataset_obj.data_format == "parquet_hive"
        if use_hive and dr1 and dr1[0] == dr1[1]:
            sys1 = _load_hive_direct(conn, dataset_obj, local_id1, dr1[0], filter_vals1, ngram_limit)
        else:
            sys1 = load_system(conn, dataset_obj, local_id1, dr1, filter_vals1, ngram_limit)
        if use_hive and dr2 and dr2[0] == dr2[1]:
            sys2 = _load_hive_direct(conn, dataset_obj, local_id2, dr2[0], filter_vals2, ngram_limit)
        else:
            sys2 = load_system(conn, dataset_obj, local_id2, dr2, filter_vals2, ngram_limit)

    try:
        if alphas:
            alpha_list = [float(a) for a in alphas.split(",")]
            result_data = allotax.compute_allotax_multi_alpha(sys1, sys2, alpha_list, wordshift_limit)
            # serde_json serializes f64::INFINITY as null → Python None.
            # Restore from the original input; use string since JSON has no Infinity.
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
                "domain": domain,
                "dataset": dataset,
                "dataset_version": dataset_obj.version,
                "granularity": granularity,
                "allotax_version": _allotax_version(),
            },
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Allotax computation failed: {str(e)}")


def _load_hive_direct(conn, dataset_obj, local_id, date_str, filter_vals, limit):
    """Load types+counts via direct Hive partition path (no glob scan).

    Constructs the exact partition directory path from filter values, entity,
    and date — avoids the expensive /**/*.parquet glob that load_system uses.
    """
    ep = dataset_obj.endpoint_schema or {}
    type_col = ep.get("type_column") or "types"
    count_col = ep.get("count_column") or "counts"

    path = build_hive_path(
        dataset_obj,
        entity_value=local_id,
        filter_vals=filter_vals,
        time_value=date_str,
    )
    if path is None:
        raise ValueError(
            f"parquet_hive dataset '{dataset_obj.dataset_id}' has no level_order. "
            "Re-register the dataset to populate level_order."
        )

    try:
        if limit:
            order_and_limit = f" ORDER BY {count_col} DESC LIMIT {int(limit)}"
        else:
            order_and_limit = ""
        rows = conn.execute(
            f"SELECT {type_col}, {count_col} FROM read_parquet('{path}')"
            f"{order_and_limit}",
        ).fetchall()
    except Exception as exc:
        if _is_data_missing(exc):
            return {"types": [], "counts": []}
        raise

    return {"types": [r[0] for r in rows], "counts": [float(r[1]) for r in rows]}


def _latest_from_manifest(dataset_obj, local_id, granularity=None):
    """Read the latest available date from manifest.availability.

    Availability is keyed by local_id (entity column value) with nested
    partition dims and min/max bounds.  Searches recursively for the
    granularity key, falling back to the first path at each level.
    """
    availability = (dataset_obj.manifest or {}).get("availability", {})
    if not availability:
        return None
    if local_id is not None and local_id in availability:
        entry = availability[local_id]
    elif local_id is None:
        entry = availability
    else:
        return None

    def _find_max(d, target):
        if not isinstance(d, dict):
            return None
        if "min" in d and "max" in d:
            return d["max"]
        if target and target in d:
            return _find_max(d[target], None)
        for v in d.values():
            if isinstance(v, dict):
                result = _find_max(v, target)
                if result is not None:
                    return result
        return None

    return _find_max(entry, granularity)


@router.get("/rtd")
async def rank_turbulence_divergence(
    request: Request,
    domain: str = Query("wikimedia", description="Domain owning the dataset"),
    dataset: str = Query("ngrams", description="Dataset ID within the domain"),
    entity: Optional[str] = Query(None, description="Global entity ID, e.g. 'wikidata:Q30' (United States)"),
    dates: Optional[str] = Query(None, description="Target date, e.g. '2026-02-17'"),
    dates2: Optional[str] = Query(None, description="Reference date, e.g. '2026-02-10'"),
    granularity: str = Query("daily", description="Hive granularity: daily | weekly | monthly"),
    alpha: str = Query("0.25", description="RTD alpha parameter (number or 'inf')"),
    alphas: Optional[str] = Query(None, description="Comma-separated alphas for multi-alpha mode, e.g. '0.25,1.0,inf'"),
    ngram_limit: int = Query(10000, description="Max types to load per system (0 = no limit)"),
    limit: int = Query(10000, description="Max wordshift entries to return (0 = no limit)"),
    n: int = Query(1, description="N-gram size (1 = unigrams, 2 = bigrams)"),
    db: AsyncSession = Depends(get_session),
):
    """Lightweight rank-turbulence divergence between two dates for a single entity.

    Returns per-term signed divergence contributions (wordshift) without the full
    allotaxonometer overhead (no diamond plot, no balance). Designed for fast
    on-the-fly comparisons (~80ms).

    Positive divergence = term is more prominent on the target date.

    Both `dates` and `dates2` must be provided. The frontend should compute
    valid dates from manifest.availability metadata.
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

    qp = request.query_params
    filter_vals1 = {dim: qp[dim] for dim in all_dims if dim in qp}
    filter_vals2 = {dim: qp[f"{dim}2"] for dim in all_dims if f"{dim}2" in qp}

    if "ngram_size" in all_dims:
        if "n" in qp and "ngram_size" not in filter_vals1:
            filter_vals1["ngram_size"] = n
        if "n2" in qp and "ngram_size" not in filter_vals2:
            filter_vals2["ngram_size"] = int(qp["n2"])

    _apply_defaults(filter_vals1, defaults)
    _apply_defaults(filter_vals2, defaults)

    # Same entity for both systems (date-vs-date comparison)
    if not filter_vals2:
        filter_vals2 = dict(filter_vals1)

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
        latest_date = _latest_from_manifest(dataset_obj, local_id, granularity)

    with timed("query", "DuckDB data load"):
        with handle_query_error(f"{domain}/{dataset}"):
            conn = get_duckdb_client().connect()
            if dataset_obj.data_format == "parquet_hive":
                sys_target = _load_hive_direct(
                    conn, dataset_obj, local_id, dates.split(",")[0],
                    filter_vals1, ngram_limit)
                sys_ref = _load_hive_direct(
                    conn, dataset_obj, local_id, dates2.split(",")[0],
                    filter_vals2, ngram_limit)
            else:
                sys_target = load_system(conn, dataset_obj, local_id, dr1, filter_vals1, ngram_limit)
                sys_ref = load_system(conn, dataset_obj, local_id, dr2, filter_vals2, ngram_limit)

    if not sys_target["types"]:
        raise HTTPException(status_code=404, detail=f"No data for target date {dates}")
    if not sys_ref["types"]:
        raise HTTPException(status_code=404, detail=f"No data for reference date {dates2}")

    try:
        with timed("allotax", "RTD computation"):
            # ref first → positive divergence = "more prominent on target date"
            if alphas:
                alpha_list = [float(a) for a in alphas.split(",")]
                result = allotax.rank_turbulence_divergence_multi_alpha(
                    sys_ref, sys_target, alpha_list, limit=limit)
                # serde_json serializes f64::INFINITY as null → Python None.
                # Restore from the original input; use string since JSON has no Infinity.
                for ar, a in zip(result.get("alpha_results", []), alpha_list):
                    if ar.get("alpha") is None and math.isinf(a):
                        ar["alpha"] = "Infinity"
                result_data = result
            else:
                result = allotax.rank_turbulence_divergence(
                    sys_ref, sys_target, alpha_f, limit=limit)
                if result.get("alpha") is not None:
                    pass  # no fixup needed
                result_data = {
                    "wordshift": result["wordshift"],
                    "normalization": result["normalization"],
                    "delta_sum": result["delta_sum"],
                }

        with timed("serialize", "Response serialization"):
            response = _sanitize_floats({
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
                    "granularity": granularity,
                    "ngram_limit": ngram_limit,
                    "limit": limit,
                    "types_target": len(sys_target["types"]),
                    "types_ref": len(sys_ref["types"]),
                    "allotax_version": _allotax_version(),
                },
            })

        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"RTD computation failed: {str(e)}")
