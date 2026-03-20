"""
Storywrangler instruments — platform-level analytics tools.

Currently includes:
  - allotax: rank-turbulence divergence between two types-counts distributions.
             Generic — works for any registered dataset with endpoint_schema.type='types-counts'.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..core.database import get_session
from ..core.duckdb_client import get_duckdb_client
from ..core.query_utils import load_system, resolve_entity
from ..models.registry import RegistryEntry

router = APIRouter()


@router.get("/allotax")
async def allotax_endpoint(
    request: Request,
    domain: str = Query("wikimedia", description="Domain owning the dataset"),
    dataset: str = Query("ngrams", description="Dataset ID within the domain"),
    entity: Optional[str] = Query(None, description="Global entity ID for system 1, e.g. 'wikidata:Q30' (United States). Optional — omit for datasets using filter_dimensions as the comparison axis."),
    entity2: Optional[str] = Query(None, description="Global entity ID for system 2, e.g. 'wikidata:Q145' (United Kingdom). Optional — omit for datasets using filter_dimensions as the comparison axis."),
    dates: str = Query("2024-10-01,2024-10-31", description="Date/year range for system 1. Single value '2024-10-01' or range '2024-10-01,2024-10-31'"),
    dates2: str = Query("2024-11-01,2024-11-30", description="Date/year range for system 2"),
    granularity: str = Query("daily", description="Hive granularity (parquet_hive only): daily | weekly | monthly"),
    alpha: float = Query(1.0, description="RTD alpha parameter"),
    alphas: Optional[str] = Query(None, description="Comma-separated alphas for multi-alpha mode, e.g. '0.5,1.0,2.0'"),
    ngram_limit: int = Query(10000, description="Max types to load per system before computing"),
    wordshift_limit: int = Query(200, description="Truncate wordshift output to top N entries"),
    n: int = Query(1, description="N-gram size (1 = unigrams, 2 = bigrams). Only used when endpoint_schema.ngram_sizes is set."),
    db: AsyncSession = Depends(get_session),
):
    """Allotaxonometer (rank-turbulence divergence) between two types-counts distributions.

    Generic — driven entirely by the dataset's registered endpoint_schema and entity_mapping.
    Works for any dataset with endpoint_schema.type='types-counts'.

    Comparison axes — any two systems differing on at least one dimension:
      entity vs entity     ?domain=wikimedia&dataset=ngrams&entity=wikidata:Q30&entity2=wikidata:Q16
      time vs time         ?entity=wikidata:Q30&dates=2020&dates2=2010
      entity x time        ?entity=wikidata:Q30&dates=2024-01&entity2=wikidata:Q16&dates2=2023-01
      filter-only          ?geo=US&geo2=CA  (no entity param needed when dataset has no entity_mapping)

    For parquet_hive datasets (e.g. ngrams), granularity is required:
      &granularity=daily

    Filter dimensions (e.g. sex in babynames, geo for datasets without entity_mapping) are declared
    in endpoint_schema.filter_dimensions and passed as extra query params: ?sex=M&sex2=F

    Entity registration is optional. Datasets that register geo (or any comparison axis) as a
    filter_dimension can skip entity_mapping entirely — pass the raw column value directly.

    Alpha slider pattern — precompute a discrete set of alphas in one call:
      &alphas=0.33,0.5,1.0,2.0,3.0
    """
    result = await db.execute(
        select(RegistryEntry).where(
            RegistryEntry.domain == domain,
            RegistryEntry.dataset_id == dataset,
        )
    )
    dataset_obj = result.scalar_one_or_none()
    if not dataset_obj:
        raise HTTPException(status_code=404, detail=f"Dataset '{domain}/{dataset}' not found")

    ep = dataset_obj.endpoint_schema
    if not ep or ep.get("type") != "types-counts":
        raise HTTPException(
            status_code=400,
            detail="Dataset does not support the types-counts endpoint. Register with endpoint_schema.type='types-counts'.",
        )

    if dataset_obj.data_format == "parquet_hive":
        granularities = ep.get("granularities", {})
        if not granularity:
            raise HTTPException(
                status_code=400,
                detail=f"granularity is required for parquet_hive datasets. Options: {sorted(granularities)}",
            )
        if granularity not in granularities:
            raise HTTPException(
                status_code=400,
                detail=f"granularity must be one of {sorted(granularities)}",
            )

    ngram_sizes = ep.get("ngram_sizes")
    if ngram_sizes is not None and n not in ngram_sizes:
        raise HTTPException(
            status_code=400,
            detail=f"n must be one of {ngram_sizes}",
        )

    filter_dims = ep.get("filter_dimensions") or []
    qp = request.query_params
    filter_vals1 = {dim: qp[dim]       for dim in filter_dims if dim in qp}
    filter_vals2 = {dim: qp[f"{dim}2"] for dim in filter_dims if f"{dim}2" in qp}

    def parse_dates(s: str) -> List[str]:
        parts = s.split(",")
        return [parts[0], parts[0]] if len(parts) == 1 else [parts[0], parts[1]]

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
        local_id2 = None

    try:
        import allotax
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="allotax module not available. Install via: cd allotaxonometer-core/crates/allotax-py && maturin develop --release",
        )

    try:
        conn = get_duckdb_client().connect()
        sys1 = load_system(conn, dataset_obj, local_id1, dr1, filter_vals1, granularity, ngram_limit, n=n)
        sys2 = load_system(conn, dataset_obj, local_id2, dr2, filter_vals2, granularity, ngram_limit, n=n)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Data loading failed: {str(e)}")

    try:
        if alphas:
            alpha_list = [float(a) for a in alphas.split(",")]
            result_data = allotax.compute_allotax_multi_alpha(sys1, sys2, alpha_list, wordshift_limit)
        else:
            result_data = allotax.compute_allotax(sys1, sys2, alpha, wordshift_limit)

        return {
            **result_data,
            "meta": {
                "system1": {"entity": entity, "dates": dates, "filters": filter_vals1, "types": len(sys1["types"])},
                "system2": {"entity": entity2, "dates": dates2, "filters": filter_vals2, "types": len(sys2["types"])},
                "domain": domain,
                "dataset": dataset,
                "granularity": granularity,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Allotax computation failed: {str(e)}")
