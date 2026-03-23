"""
Open Academic Analytics endpoints.

Two datasets registered under domain="open-academic-analytics":

  dataset_id="oaa"
    data_format: "duckdb"
    data_location: ~/open-academic-analytics/oaa.duckdb
    tables: papers, coauthors, training
    produced by: ~/open-academic-analytics/ Dagster pipeline

  dataset_id="academic-research-groups"
    data_format: "parquet"
    data_location: ~/academic-research-groups/academic-research-groups.parquet
    produced by: ~/academic-research-groups/ annotation pipeline

Each request opens a fresh read-only connection — DuckDB supports concurrent readers.
"""

from typing import Any, Dict, List, Optional

import duckdb
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..core.database import get_session
from ..models.registry import RegistryEntry

router = APIRouter()

_OAAEntry = (
    select(RegistryEntry)
    .where(RegistryEntry.domain == "open-academic-analytics")
    .where(RegistryEntry.dataset_id == "oaa")
)


def _conn(data_location: str) -> duckdb.DuckDBPyConnection:
    """Open a fresh read-only connection to the OAA DuckDB file."""
    return duckdb.connect(data_location, read_only=True)


async def _get_dataset(db: AsyncSession) -> RegistryEntry:
    result = await db.execute(_OAAEntry)
    dataset = result.scalar_one_or_none()
    if not dataset:
        raise HTTPException(
            status_code=404,
            detail="Dataset 'open-academic-analytics/oaa' not found. Register it first.",
        )
    return dataset


# ── /papers/{author_name} ──────────────────────────────────────────────────────

@router.get("/papers/{author_name}")
async def get_papers_for_author(
    author_name: str,
    filter_big_papers: bool = Query(False, description="Filter out papers with >25 coauthors"),
    limit: Optional[int] = Query(None, description="Limit number of results"),
    db: AsyncSession = Depends(get_session),
) -> List[Dict[str, Any]]:
    """Get processed papers for a specific author."""
    dataset = await _get_dataset(db)

    where = "WHERE ego_display_name = ?"
    params: list = [author_name]
    if filter_big_papers:
        where += " AND nb_coauthors < 25"

    sql = f"""
        SELECT *
        FROM papers
        {where}
        ORDER BY publication_date DESC
        {"LIMIT ?" if limit else ""}
    """
    if limit:
        params.append(limit)

    try:
        conn = _conn(dataset.data_location)
        rows = conn.execute(sql, params).fetchall()
        cols = [d[0] for d in conn.execute(f"DESCRIBE SELECT * FROM papers LIMIT 0").description]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {e}")

    return [dict(zip(cols, row)) for row in rows]


# ── /authors ───────────────────────────────────────────────────────────────────

@router.get("/authors")
async def get_all_authors(
    db: AsyncSession = Depends(get_session),
) -> List[Dict[str, Any]]:
    """Get all authors with current age, last publication year, and research group status."""
    dataset = await _get_dataset(db)

    sql = """
        SELECT
            c.ego_display_name,
            MAX(c.ego_age)          AS current_age,
            MAX(c.publication_year) AS last_pub_year,
            COALESCE(MAX(CAST(t.has_research_group AS INTEGER)), 0) AS has_research_group
        FROM coauthors c
        LEFT JOIN training t ON c.ego_display_name = t.name
        WHERE c.ego_display_name IS NOT NULL
          AND c.ego_age IS NOT NULL
        GROUP BY c.ego_display_name
        ORDER BY c.ego_display_name
    """

    try:
        conn = _conn(dataset.data_location)
        rows = conn.execute(sql).fetchall()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {e}")

    return [
        {
            "ego_display_name": r[0],
            "current_age": r[1],
            "last_pub_year": r[2],
            "has_research_group": bool(r[3]),
        }
        for r in rows
    ]


# ── /coauthors/{author_name} ───────────────────────────────────────────────────

@router.get("/coauthors/{author_name}")
async def get_coauthors_for_author(
    author_name: str,
    filter_big_papers: bool = Query(False, description="Filter out papers with >25 coauthors"),
    limit: Optional[int] = Query(None, description="Limit number of results"),
    db: AsyncSession = Depends(get_session),
) -> List[Dict[str, Any]]:
    """Get coauthor data for a specific author."""
    dataset = await _get_dataset(db)

    where = "WHERE ego_display_name = ?"
    params: list = [author_name]
    if filter_big_papers:
        where += " AND nb_coauthors < 25"

    sql = f"""
        SELECT *
        FROM coauthors
        {where}
        ORDER BY publication_date DESC
        {"LIMIT ?" if limit else ""}
    """
    if limit:
        params.append(limit)

    try:
        conn = _conn(dataset.data_location)
        rows = conn.execute(sql, params).fetchall()
        cols = [d[0] for d in conn.execute("DESCRIBE SELECT * FROM coauthors LIMIT 0").description]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {e}")

    return [dict(zip(cols, row)) for row in rows]


# ── /embeddings ────────────────────────────────────────────────────────────────

@router.get("/embeddings")
async def get_embeddings_data(
    db: AsyncSession = Depends(get_session),
) -> List[Dict[str, Any]]:
    """Papers with UMAP embeddings joined with training metadata for visualization."""
    dataset = await _get_dataset(db)

    # Note: DuckDB uses string_split (not PostgreSQL's string_to_array)
    sql = """
        WITH exploded_depts AS (
            SELECT DISTINCT
                t.name,
                t.oa_uid,
                t.has_research_group,
                trim(unnest(string_split(t.host_dept, ';'))) AS host_dept,
                t.college
            FROM training t
            WHERE t.oa_uid IS NOT NULL
        )
        SELECT
            p.doi,
            p.id,
            p.ego_author_id,
            p.ego_display_name,
            p.title,
            p.publication_year,
            p.publication_date,
            p.cited_by_count,
            p.umap_1,
            p.umap_2,
            p.abstract,
            p.s2FieldsOfStudy,
            p.fieldsOfStudy,
            p.coauthor_names,
            e.host_dept,
            e.college
        FROM papers p
        LEFT JOIN exploded_depts e ON (
            p.ego_author_id = 'https://openalex.org/' || e.oa_uid
            OR p.ego_author_id = e.oa_uid
        )
        WHERE p.umap_1 IS NOT NULL
        ORDER BY
            CASE WHEN p.ego_author_id = 'https://openalex.org/A5040821463' THEN 0 ELSE 1 END,
            random()
        LIMIT 6000
    """

    try:
        conn = _conn(dataset.data_location)
        rows = conn.execute(sql).fetchall()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {e}")

    return [
        {
            "doi": r[0],
            "id": r[1],
            "ego_author_id": r[2],
            "ego_display_name": r[3],
            "title": r[4],
            "publication_year": r[5],
            "publication_date": r[6].isoformat() if r[6] else None,
            "cited_by_count": r[7],
            "umap_1": r[8],
            "umap_2": r[9],
            "abstract": r[10],
            "s2FieldsOfStudy": r[11],
            "fieldsOfStudy": r[12],
            "coauthor_names": r[13],
            "host_dept": r[14],
            "college": r[15],
        }
        for r in rows
    ]


# ── /training/{author_name} ────────────────────────────────────────────────────

@router.get("/training/{author_name}")
async def get_training_data(
    author_name: str,
    db: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Aggregated training data for change point analysis."""
    dataset = await _get_dataset(db)

    sql = """
        WITH age_data AS (
            SELECT author_age AS pub_year, older  AS counts, 'older'   AS age_category,
                   has_research_group, college, changing_rate
            FROM training WHERE name = ? AND older > 0

            UNION ALL

            SELECT author_age, same,    'same',    has_research_group, college, changing_rate
            FROM training WHERE name = ? AND same > 0

            UNION ALL

            SELECT author_age, younger, 'younger', has_research_group, college, changing_rate
            FROM training WHERE name = ? AND younger > 0
        )
        SELECT pub_year, counts, age_category, has_research_group, college,
               COALESCE(changing_rate, 0) AS changing_rate
        FROM age_data
        ORDER BY pub_year, age_category
    """

    try:
        conn = _conn(dataset.data_location)
        rows = conn.execute(sql, [author_name, author_name, author_name]).fetchall()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {e}")

    if not rows:
        raise HTTPException(status_code=404, detail=f"No training data found for: {author_name}")

    cols = ("pub_year", "counts", "age_category", "has_research_group", "college", "changing_rate")
    training_data = [
        {col: float(val) if val is not None and col not in ("age_category", "college") else val
         for col, val in zip(cols, row)}
        for row in rows
    ]

    return {"status": "success", "author": author_name, "training_data": training_data, "count": len(training_data)}


# ── /academic-research-groups ──────────────────────────────────────────────────

_RosterEntry = (
    select(RegistryEntry)
    .where(RegistryEntry.domain == "open-academic-analytics")
    .where(RegistryEntry.dataset_id == "academic-research-groups")
)


async def _get_roster_dataset(db: AsyncSession) -> RegistryEntry:
    result = await db.execute(_RosterEntry)
    dataset = result.scalar_one_or_none()
    if not dataset:
        raise HTTPException(
            status_code=404,
            detail="Dataset 'open-academic-analytics/academic-research-groups' not found. Register it first.",
        )
    return dataset


@router.get("/academic-research-groups")
async def get_academic_research_groups(
    inst_ipeds_id: Optional[str] = Query(None, description="Filter by institution IPEDS ID, e.g. '231174' for UVM"),
    payroll_year: Optional[int] = Query(None, description="Filter by payroll year, e.g. 2023"),
    db: AsyncSession = Depends(get_session),
) -> List[Dict[str, Any]]:
    """Get the UVM faculty roster with OpenAlex IDs and research group metadata."""
    dataset = await _get_roster_dataset(db)

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
        FROM read_parquet('{dataset.data_location}')
        {where}
        ORDER BY payroll_name
    """

    try:
        conn = duckdb.connect()
        rows = conn.execute(sql, params).fetchall()
        cols = [d[0] for d in conn.execute(
            f"DESCRIBE SELECT * FROM read_parquet('{dataset.data_location}') LIMIT 0"
        ).description]
        conn.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {e}")

    return [dict(zip(cols, row)) for row in rows]
