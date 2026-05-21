"""Health-check status endpoints — public, no auth required."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func as sa_func, literal_column
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..core.database import get_session
from ..models.health import HealthCheck

router = APIRouter()


@router.get("/status")
async def get_current_status(
    db: AsyncSession = Depends(get_session),
):
    """Current health status for all datasets.

    Returns the most recent probe result for each (domain, dataset_id).
    """
    latest = (
        select(
            HealthCheck.domain,
            HealthCheck.dataset_id,
            sa_func.max(HealthCheck.checked_at).label("max_checked_at"),
        )
        .group_by(HealthCheck.domain, HealthCheck.dataset_id)
        .subquery()
    )

    result = await db.execute(
        select(HealthCheck).join(
            latest,
            (HealthCheck.domain == latest.c.domain)
            & (HealthCheck.dataset_id == latest.c.dataset_id)
            & (HealthCheck.checked_at == latest.c.max_checked_at),
        )
    )
    checks = result.scalars().all()

    return {
        "datasets": [
            {
                "domain": c.domain,
                "dataset_id": c.dataset_id,
                "status": c.status,
                "latency_ms": c.latency_ms,
                "error": c.error,
                "checked_at": c.checked_at.isoformat() if c.checked_at else None,
            }
            for c in checks
        ],
        "summary": {
            "total": len(checks),
            "healthy": sum(1 for c in checks if c.status == "healthy"),
            "degraded": sum(1 for c in checks if c.status == "degraded"),
            "unhealthy": sum(1 for c in checks if c.status == "unhealthy"),
        },
    }


@router.get("/status/history")
async def get_status_history(
    days: int = Query(default=90, ge=1, le=365),
    db: AsyncSession = Depends(get_session),
):
    """Daily health history for all datasets over the past N days.

    Returns one row per (domain, dataset_id, day) with the worst status
    that day and the average latency.  Powers the heatmap grid.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)

    day_col = sa_func.date_trunc("day", HealthCheck.checked_at).label("day")

    severity = case(
        (HealthCheck.status == "unhealthy", literal_column("3")),
        (HealthCheck.status == "degraded", literal_column("2")),
        (HealthCheck.status == "healthy", literal_column("1")),
        else_=literal_column("0"),
    )

    result = await db.execute(
        select(
            HealthCheck.domain,
            HealthCheck.dataset_id,
            day_col,
            sa_func.max(severity).label("worst_severity"),
            sa_func.avg(HealthCheck.latency_ms).label("avg_latency_ms"),
            sa_func.count().label("check_count"),
        )
        .where(HealthCheck.checked_at >= since)
        .group_by(
            HealthCheck.domain,
            HealthCheck.dataset_id,
            day_col,
        )
        .order_by(
            HealthCheck.domain,
            HealthCheck.dataset_id,
            day_col,
        )
    )
    rows = result.all()

    severity_map = {3: "unhealthy", 2: "degraded", 1: "healthy", 0: "unknown"}

    return {
        "days": days,
        "since": since.isoformat(),
        "history": [
            {
                "domain": r.domain,
                "dataset_id": r.dataset_id,
                "day": r.day.isoformat() if r.day else None,
                "status": severity_map.get(r.worst_severity, "unknown"),
                "avg_latency_ms": (
                    round(r.avg_latency_ms, 1) if r.avg_latency_ms else None
                ),
                "check_count": r.check_count,
            }
            for r in rows
        ],
    }


@router.get("/status/{domain}/{dataset_id}")
async def get_dataset_health_detail(
    domain: str,
    dataset_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
    db: AsyncSession = Depends(get_session),
):
    """Recent check history for a single dataset."""
    result = await db.execute(
        select(HealthCheck)
        .where(
            HealthCheck.domain == domain,
            HealthCheck.dataset_id == dataset_id,
        )
        .order_by(HealthCheck.checked_at.desc())
        .limit(limit)
    )
    checks = result.scalars().all()

    return {
        "domain": domain,
        "dataset_id": dataset_id,
        "checks": [
            {
                "status": c.status,
                "latency_ms": c.latency_ms,
                "error": c.error,
                "checked_at": c.checked_at.isoformat() if c.checked_at else None,
            }
            for c in checks
        ],
    }
