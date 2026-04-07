"""
scisciDB metrics endpoint — flexible time-series queries over precomputed OpenAlex metrics.

Uses query_utils.load_time_series(), which is available to any dataset registered with
endpoint_schema.type='time-series'. The router is intentionally thin: registry lookup,
validation, then delegate to the shared utility.

Example queries:
  GET /scisciDB/metrics?group_by=field,year&metric_type=total&start_year=2000&end_year=2024
  GET /scisciDB/metrics?group_by=venue,year&field=Computer+Science&metric_type=total
  GET /scisciDB/metrics?group_by=field,year,metric_type&start_year=2020
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..core.database import get_session
from ..core.duckdb_client import get_duckdb_client
from ..core.query_utils import load_time_series
from ..models.registry import RegistryEntry

router = APIRouter()

_DOMAIN = "scisciDB"

@router.get("/metrics")
async def get_metrics(
    request: Request,
    group_by: str = Query(..., description="Comma-separated columns to GROUP BY, e.g. 'field,year'"),
    dataset: str = Query(default="field-metrics", description="Registered dataset ID within scisciDB"),
    start_year: Optional[int] = Query(default=None, ge=1900, le=2030),
    end_year: Optional[int] = Query(default=None, ge=1900, le=2030),
    limit: int = Query(default=1000, le=10000),
    db: AsyncSession = Depends(get_session),
) -> List[Dict[str, Any]]:
    """Flexible time-series query over a registered scisciDB metrics dataset.

    Specify which dimensions to aggregate with `group_by`, and pass any declared
    `filter_dimensions` as extra query params to narrow the result.

    Available filter dimensions depend on the registered dataset — check
    `GET /registry/scisciDB/{dataset}` for `transform.filter_dimensions`.

    Examples:
      ?group_by=field,year&metric_type=total
      ?group_by=venue,year&field=Computer+Science&metric_type=total
    """
    result = await db.execute(
        select(RegistryEntry).where(
            RegistryEntry.domain == _DOMAIN,
            RegistryEntry.dataset_id == dataset,
        )
    )
    dataset_obj = result.scalar_one_or_none()
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
    filter_dims = tr.get("filter_dimensions") or []
    time_dim = tr.get("time_dimension") or "year"

    # Parse and validate group_by columns
    group_cols = [c.strip() for c in group_by.split(",") if c.strip()]
    if not group_cols:
        raise HTTPException(status_code=422, detail="group_by must specify at least one column")

    known_cols = set(filter_dims) | {time_dim}
    unknown = [c for c in group_cols if c not in known_cols]
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown group_by column(s) {unknown}. Available: {sorted(known_cols)}",
        )

    # Collect filter values from extra query params for declared filter_dimensions
    qp = request.query_params
    filter_vals = {dim: qp[dim] for dim in filter_dims if dim in qp}

    # Validate against pre-introspected distinct values (if available)
    fv = dataset_obj.filter_values or {}
    for dim, val in filter_vals.items():
        valid = fv.get(dim, [])
        if valid and val not in valid:
            raise HTTPException(
                status_code=400,
                detail=f"'{val}' is not a valid value for '{dim}'. Valid: {sorted(map(str, valid))}",
            )

    try:
        conn = get_duckdb_client().connect()
        return load_time_series(conn, dataset_obj, group_cols, filter_vals, start_year, end_year, limit)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query execution failed: {str(e)}")
