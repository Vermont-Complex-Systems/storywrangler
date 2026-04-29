"""
Open Academic Analytics endpoints.

Datasets registered under domain="open-academic-analytics":

  dataset_id="papers"      — one row per paper per ego author
  dataset_id="coauthors"   — one row per coauthor per publication year per ego author
  dataset_id="training"    — one row per ego author per year (wide format + change point rates)
  dataset_id="authors"     — materialized summary: one row per ego author (pipeline pre-joins coauthors × training)
  /embeddings              — served from papers dataset, filtered to umap_1 IS NOT NULL at query time
  dataset_id="academic-research-groups" — UVM faculty roster

All endpoints resolve data_location from the registry and query via read_parquet()
using the shared DuckDB client — the same pattern as every other router.
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_session
from ..core.duckdb_client import get_duckdb_client
from ..core.query_utils import handle_query_error
from ..core.registry_utils import get_latest_entry

router = APIRouter()


async def _get_path(db: AsyncSession, dataset_id: str) -> str:
    """Resolve a registered OAA dataset to its parquet file path."""
    entry = await get_latest_entry(db, "open-academic-analytics", dataset_id)
    if not entry:
        raise HTTPException(
            status_code=404,
            detail=f"Dataset 'open-academic-analytics/{dataset_id}' not found. Register it first.",
        )
    return entry.data_location

# ── /academic-research-groups ──────────────────────────────────────────────────

@router.get("/academic-research-groups")
async def get_academic_research_groups(
    inst_ipeds_id: Optional[str] = Query(None, description="Filter by institution IPEDS ID, e.g. '231174' for UVM"),
    payroll_year: Optional[int] = Query(None, description="Filter by payroll year, e.g. 2023"),
    db: AsyncSession = Depends(get_session),
) -> List[Dict[str, Any]]:
    """Get the UVM faculty roster with OpenAlex IDs and research group metadata."""
    path = await _get_path(db, "academic-research-groups")

    conditions, params = [], []
    if inst_ipeds_id is not None:
        conditions.append("inst_ipeds_id = ?")
        params.append(inst_ipeds_id)
    if payroll_year is not None:
        conditions.append("payroll_year = ?")
        params.append(payroll_year)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    sql = f"""
        SELECT *
        FROM read_parquet('{path}')
        {where}
        ORDER BY payroll_name
    """

    with handle_query_error("open-academic-analytics/academic-research-groups"):
        conn = get_duckdb_client().connect()
        result = conn.execute(sql, params)
        cols = [d[0] for d in result.description]
        rows = result.fetchall()

    return [dict(zip(cols, row)) for row in rows]


# ── /authors ───────────────────────────────────────────────────────────────────

@router.get("/authors")
async def get_all_authors(
    db: AsyncSession = Depends(get_session),
) -> List[Dict[str, Any]]:
    """Get all authors with current age, last publication year, and research group status."""
    path = await _get_path(db, "authors")

    with handle_query_error("open-academic-analytics/authors"):
        conn = get_duckdb_client().connect()
        result = conn.execute(f"SELECT * FROM read_parquet('{path}') ORDER BY ego_display_name")
        cols = [d[0] for d in result.description]
        rows = result.fetchall()

    return [dict(zip(cols, row)) for row in rows]


# ── /coauthors/{author_name} ───────────────────────────────────────────────────

@router.get("/coauthors/{author_name}")
async def get_coauthors_for_author(
    author_name: str,
    filter_big_papers: bool = Query(False, description="Filter out papers with >25 coauthors"),
    limit: Optional[int] = Query(None, description="Limit number of results"),
    db: AsyncSession = Depends(get_session),
) -> List[Dict[str, Any]]:
    """Get coauthor data for a specific author."""
    path = await _get_path(db, "coauthors")

    where = "WHERE ego_display_name = ?"
    params: list = [author_name]
    if filter_big_papers:
        where += " AND nb_coauthors < 25"

    sql = f"""
        SELECT *
        FROM read_parquet('{path}')
        {where}
        ORDER BY publication_date DESC
        {"LIMIT ?" if limit else ""}
    """
    if limit:
        params.append(limit)

    with handle_query_error("open-academic-analytics/coauthors"):
        conn = get_duckdb_client().connect()
        result = conn.execute(sql, params)
        cols = [d[0] for d in result.description]
        rows = result.fetchall()

    return [dict(zip(cols, row)) for row in rows]


# ── /embeddings ────────────────────────────────────────────────────────────────

@router.get("/embeddings")
async def get_embeddings_data(
    limit: int = Query(6000, description="Number of papers to sample", ge=1, le=50000),
    db: AsyncSession = Depends(get_session),
) -> List[Dict[str, Any]]:
    """Papers with UMAP embeddings and department metadata for visualization."""
    path = await _get_path(db, "papers")

    with handle_query_error("open-academic-analytics/papers"):
        conn = get_duckdb_client().connect()
        result = conn.execute(
            f"SELECT * FROM read_parquet('{path}') WHERE umap_1 IS NOT NULL ORDER BY random() LIMIT {limit}"
        )
        cols = [d[0] for d in result.description]
        rows = result.fetchall()

    return [dict(zip(cols, row)) for row in rows]

# ── /papers/{author_name} ──────────────────────────────────────────────────────

@router.get("/papers/{author_name}")
async def get_papers_for_author(
    author_name: str,
    filter_big_papers: bool = Query(False, description="Filter out papers with >25 coauthors"),
    limit: Optional[int] = Query(None, description="Limit number of results"),
    db: AsyncSession = Depends(get_session),
) -> List[Dict[str, Any]]:
    """Get processed papers for a specific author."""
    path = await _get_path(db, "papers")

    where = "WHERE ego_display_name = ?"
    params: list = [author_name]
    if filter_big_papers:
        where += " AND nb_coauthors < 25"

    sql = f"""
        SELECT *
        FROM read_parquet('{path}')
        {where}
        ORDER BY publication_date DESC
        {"LIMIT ?" if limit else ""}
    """
    if limit:
        params.append(limit)

    with handle_query_error("open-academic-analytics/papers"):
        conn = get_duckdb_client().connect()
        result = conn.execute(sql, params)
        cols = [d[0] for d in result.description]
        rows = result.fetchall()

    return [dict(zip(cols, row)) for row in rows]

# ── /training/{author_name} ────────────────────────────────────────────────────

@router.get("/training/{author_name}")
async def get_training_data(
    author_name: str,
    db: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Aggregated training data for change point analysis."""
    path = await _get_path(db, "training")

    sql = f"""
        WITH age_data AS (
            SELECT author_age AS pub_year, older  AS counts, 'older'   AS age_category,
                   has_research_group, college, changing_rate
            FROM read_parquet('{path}') WHERE name = ? AND older > 0

            UNION ALL

            SELECT author_age, same,    'same',    has_research_group, college, changing_rate
            FROM read_parquet('{path}') WHERE name = ? AND same > 0

            UNION ALL

            SELECT author_age, younger, 'younger', has_research_group, college, changing_rate
            FROM read_parquet('{path}') WHERE name = ? AND younger > 0
        )
        SELECT pub_year, counts, age_category, has_research_group, college,
               COALESCE(changing_rate, 0) AS changing_rate
        FROM age_data
        ORDER BY pub_year, age_category
    """

    with handle_query_error("open-academic-analytics/training"):
        conn = get_duckdb_client().connect()
        rows = conn.execute(sql, [author_name, author_name, author_name]).fetchall()

    if not rows:
        raise HTTPException(status_code=404, detail=f"No training data found for: {author_name}")

    cols = ("pub_year", "counts", "age_category", "has_research_group", "college", "changing_rate")
    training_data = [
        {col: float(val) if val is not None and col not in ("age_category", "college") else val
         for col, val in zip(cols, row)}
        for row in rows
    ]

    return {"status": "success", "author": author_name, "training_data": training_data, "count": len(training_data)}
