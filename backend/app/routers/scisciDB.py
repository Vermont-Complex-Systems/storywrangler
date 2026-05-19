"""
scisciDB metrics endpoint — flexible time-series queries over precomputed OpenAlex metrics.

Uses query_utils.load_time_series(), which is available to any dataset registered with
endpoint_schema.type='time-series'. The router is intentionally thin: registry lookup,
validation, then delegate to the shared utility.

Example queries:
  GET /scisciDB/metrics?group_by=field,year&metric_type=total&start_year=2000&end_year=2024
  GET /scisciDB/metrics?group_by=venue,year&field=Computer+Science&metric_type=total
  GET /scisciDB/metrics?group_by=field,year,metric_type&start_year=2020
  GET /scisciDB/metrics?group_by=venue,metric_type&venue=Nature,Science,PLOS+ONE&field=Computer+Science
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from ..core.database import get_session
from ..core.duckdb_client import get_duckdb_client
from ..core.query_utils import get_partition_defaults, get_queryable_dims, handle_query_error, load_time_series
from ..core.registry_utils import get_latest_entry

router = APIRouter()

_DOMAIN = "scisciDB"

@router.get("/metrics")
async def get_metrics(
    request: Request,
    group_by: str = Query(..., description="Comma-separated columns to GROUP BY, e.g. 'field,year'"),
    dataset: str = Query(default="field-venue-metrics", description="Registered dataset ID within scisciDB"),
    start_year: Optional[int] = Query(default=None, ge=1900, le=2030),
    end_year: Optional[int] = Query(default=None, ge=1900, le=2030),
    exclude_nulls: bool = Query(default=True, description="Exclude rows where any group_by column is NULL"),
    top_n: Optional[int] = Query(default=None, ge=1, le=500, description="Return only the top N groups by total count (non-time dimensions)"),
    limit: int = Query(default=1000, le=10000),
    db: AsyncSession = Depends(get_session),
) -> List[Dict[str, Any]]:
    """Flexible time-series query over a registered scisciDB metrics dataset.

    Specify which dimensions to aggregate with `group_by`, and pass any declared
    filter or partition dimensions as extra query params to narrow the result.
    Comma-separated values are supported for multi-value filtering (IN clause).

    Partition dimensions (e.g. metric_type) have safe defaults injected when
    omitted from both group_by and filters — prevents accidental cross-partition
    aggregation (e.g. summing total + has_abstract would double-count).

    Examples:
      ?group_by=field,year&metric_type=total
      ?group_by=venue,year&field=Computer+Science&metric_type=total
      ?group_by=venue,metric_type&venue=Nature,Science&field=Computer+Science
    """
    dataset_obj = await get_latest_entry(db, _DOMAIN, dataset)
    if not dataset_obj:
        raise HTTPException(
            status_code=404,
            detail=f"Dataset '{_DOMAIN}/{dataset}' not found. Register it first via POST /registry/register.",
        )

    ep = dataset_obj.endpoint_schema or {}
    if ep.get("type") != "time-series":
        raise HTTPException(
            status_code=400,
            detail="Dataset does not support the time-series endpoint. Register with endpoint_schema.type='time-series'.",
        )

    tr = dataset_obj.transform or {}
    all_dims = get_queryable_dims(dataset_obj)
    defaults = get_partition_defaults(dataset_obj)
    time_dim = tr.get("time_dimension") or "year"

    # Parse and validate group_by columns
    group_cols = [c.strip() for c in group_by.split(",") if c.strip()]
    if not group_cols:
        raise HTTPException(status_code=422, detail="group_by must specify at least one column")

    known_cols = set(all_dims) | {time_dim}
    unknown = [c for c in group_cols if c not in known_cols]
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown group_by column(s) {unknown}. Available: {sorted(known_cols)}",
        )

    # Collect filter values from extra query params (supports comma-separated → list)
    qp = request.query_params
    filter_vals: Dict[str, Any] = {}
    for dim in all_dims:
        if dim in qp:
            raw = qp[dim]
            filter_vals[dim] = raw.split(",") if "," in raw else raw

    # Inject defaults when dim is NOT in group_by AND NOT in filter_vals.
    # If dim IS in group_by, the user wants to break down by it (no default needed).
    for dim, default_val in defaults.items():
        if dim not in group_cols and dim not in filter_vals:
            filter_vals[dim] = default_val

    # Validate against pre-introspected distinct values (if available)
    fv = dataset_obj.filter_values or {}
    for dim, val in filter_vals.items():
        valid = fv.get(dim, [])
        if not valid:
            continue
        vals_to_check = val if isinstance(val, list) else [val]
        for v in vals_to_check:
            if v not in valid:
                raise HTTPException(
                    status_code=400,
                    detail=f"'{v}' is not a valid value for '{dim}'. Valid: {sorted(map(str, valid))}",
                )

    with handle_query_error(f"{_DOMAIN}/{dataset}"):
        conn = get_duckdb_client().connect()
        return load_time_series(conn, dataset_obj, group_cols, filter_vals, start_year, end_year, limit, exclude_nulls, top_n)
