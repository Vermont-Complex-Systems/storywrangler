"""Dataset health check probe — lightweight DuckDB read test.

Runs a minimal SELECT against each registered dataset to verify the data
files exist and are readable.  Results are stored in the health_checks table.
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone

from sqlmodel import select, delete

from ..core.database import async_session_factory
from ..core.duckdb_client import get_admin_duckdb_client
from ..core.parquet_introspect import _pinned_path_expr
from ..core.query_utils import _path_expr, _is_data_missing
from ..models.health import HealthCheck
from ..models.registry import RegistryEntry

log = logging.getLogger(__name__)

DEGRADED_THRESHOLD_MS = 10_000  # 10 seconds
RETENTION_DAYS = 90
CHECK_INTERVAL_SECONDS = 15 * 60  # 15 minutes


def probe_dataset(dataset_obj: RegistryEntry) -> dict:
    """Run a lightweight DuckDB probe against a single dataset.

    For parquet_hive with level_order, uses a pinned path (one specific
    partition) instead of the wildcard glob.  The wildcard path forces
    DuckDB to enumerate the entire directory tree over NFS before running
    the query — reddit/ngrams alone takes 26+ seconds.  The pinned path
    reads a single file footer and returns in milliseconds.

    Returns ``{"status": str, "latency_ms": float, "error": str | None}``.
    """
    try:
        level_order = getattr(dataset_obj, "level_order", None)
        if level_order and dataset_obj.data_format == "parquet_hive":
            from_clause = _pinned_path_expr(dataset_obj.data_location, level_order)
        else:
            from_clause = _path_expr(dataset_obj)
    except ValueError as e:
        return {"status": "unhealthy", "latency_ms": 0.0, "error": str(e)}

    start = time.perf_counter()
    try:
        with get_admin_duckdb_client().timed_connect() as conn:
            conn.execute(f"SELECT 1 FROM {from_clause} LIMIT 1").fetchone()
        latency_ms = (time.perf_counter() - start) * 1000

        if latency_ms > DEGRADED_THRESHOLD_MS:
            return {"status": "degraded", "latency_ms": latency_ms, "error": None}
        return {"status": "healthy", "latency_ms": latency_ms, "error": None}

    except Exception as exc:
        latency_ms = (time.perf_counter() - start) * 1000
        if _is_data_missing(exc):
            return {
                "status": "unhealthy",
                "latency_ms": latency_ms,
                "error": "Data files not found",
            }
        return {
            "status": "unhealthy",
            "latency_ms": latency_ms,
            "error": str(exc)[:500],
        }


async def run_all_checks():
    """Probe every registered dataset and store results.

    Fetches the latest version of each ``(domain, dataset_id)`` pair,
    runs ``probe_dataset()`` synchronously (DuckDB is not async), and
    writes results to PostgreSQL.
    """
    async with async_session_factory() as db:
        result = await db.execute(
            select(RegistryEntry)
            .distinct(RegistryEntry.domain, RegistryEntry.dataset_id)
            .order_by(
                RegistryEntry.domain,
                RegistryEntry.dataset_id,
                RegistryEntry.created_at.desc(),
            )
        )
        datasets = result.scalars().all()

    log.info("Health check: probing %d datasets", len(datasets))

    for ds in datasets:
        label = f"{ds.domain}/{ds.dataset_id}"
        try:
            probe_result = await asyncio.to_thread(probe_dataset, ds)
        except Exception as exc:
            log.error("Health check probe crashed for %s: %s", label, exc)
            probe_result = {
                "status": "unhealthy",
                "latency_ms": 0.0,
                "error": f"Probe crashed: {str(exc)[:200]}",
            }

        async with async_session_factory() as db:
            db.add(
                HealthCheck(
                    domain=ds.domain,
                    dataset_id=ds.dataset_id,
                    status=probe_result["status"],
                    latency_ms=probe_result["latency_ms"],
                    error=probe_result["error"],
                )
            )
            await db.commit()

        log.info(
            "  %s -> %s (%.0fms)", label, probe_result["status"],
            probe_result["latency_ms"],
        )


async def purge_old_checks():
    """Delete health check records older than RETENTION_DAYS."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
    async with async_session_factory() as db:
        await db.execute(
            delete(HealthCheck).where(HealthCheck.checked_at < cutoff)
        )
        await db.commit()
    log.info("Purged health checks older than %s", cutoff.date())


async def health_check_loop():
    """Background loop: run checks, purge old data, sleep, repeat."""
    while True:
        try:
            await run_all_checks()
            await purge_old_checks()
        except Exception as exc:
            log.error("Health check cycle failed: %s", exc)
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
