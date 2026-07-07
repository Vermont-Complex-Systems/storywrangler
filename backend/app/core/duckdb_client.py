"""DuckDB connection management with resource limits and query timeouts.

Two connection pools, each with its own budget:

  - **query**: handles user-facing requests (allotax, RTD, term-series).
    Uses DuckDB defaults for memory (80% of RAM) and threads (all cores).
    Protected by a 2-minute query timeout via ``conn.interrupt()``.

  - **admin**: handles registration introspection and health checks.
    Capped at 1 thread and 512 MB so a runaway introspection
    (e.g. recursive NFS walk) can't starve the query pool.

Both pools support query timeouts via ``conn.interrupt()`` — a timer
thread cancels any query that exceeds the deadline.

Note: DuckDBPyConnection is not thread-safe.  ``timed_connect`` therefore
hands each caller a fresh cursor — a duplicate connection to the shared
database — so concurrent requests (event loop + executor threads) never
share result state, and the timeout ``interrupt()`` only ever cancels its
own request's query.
"""

import asyncio
import contextvars
import logging
import os
import duckdb
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from functools import lru_cache
from typing import Any, Callable, Dict, Optional, TypeVar

from .config import settings

log = logging.getLogger(__name__)

T = TypeVar("T")

# Shared executor for blocking DuckDB work. Routers must never call
# conn.execute() on the event loop — a single slow query (up to
# QUERY_TIMEOUT_S) would freeze every other request, including health
# checks. Bounded so DuckDB concurrency stays controlled; timed_connect()
# hands each thread its own cursor, so parallel workers are safe.
_DUCKDB_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="duckdb")


async def run_blocking(fn: Callable[[], T]) -> T:
    """Run a blocking DuckDB workload off the event loop.

    Copies the caller's contextvars into the worker thread so per-request
    instrumentation (core.timing) keeps working inside the closure.
    """
    ctx = contextvars.copy_context()
    return await asyncio.get_running_loop().run_in_executor(
        _DUCKDB_EXECUTOR, lambda: ctx.run(fn)
    )

# ── Resource budgets ──────────────────────────────────────────────────────────

QUERY_TIMEOUT_S = 120  # 2 minutes — user-facing queries

ADMIN_MEMORY = "512MB"
ADMIN_THREADS = 1
ADMIN_TIMEOUT_S = 30  # 30 seconds — introspection / health probes


class DuckDBClient:
    """Lazy-init DuckDB connection with configurable limits and timeouts."""

    def __init__(
        self, *,
        config: Optional[Dict[str, Any]] = None,
        timeout_s: int = QUERY_TIMEOUT_S,
    ):
        self._config = config or {}
        self._timeout_s = timeout_s
        self.conn = None

    def connect(self):
        if self.conn is None:
            self.conn = duckdb.connect(config=self._config)
        return self.conn

    @contextmanager
    def timed_connect(self, timeout_s: int | None = None):
        """Context manager that auto-interrupts if the query exceeds *timeout_s*.

        Usage::

            with client.timed_connect() as conn:
                conn.execute("SELECT ...").fetchall()

        Yields a cursor — a duplicate connection to the shared database —
        so concurrent callers on different threads never share result state
        and the timeout only interrupts this caller's query.

        On timeout, ``interrupt()`` is called, which raises
        ``duckdb.InterruptException`` inside the executing query.
        """
        cur = self.connect().cursor()
        deadline = timeout_s if timeout_s is not None else self._timeout_s
        timer = threading.Timer(deadline, cur.interrupt)
        timer.start()
        try:
            yield cur
        finally:
            timer.cancel()
            cur.close()

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None


@lru_cache()
def get_duckdb_client() -> DuckDBClient:
    """Connection pool for user-facing queries.

    Uses DuckDB defaults for memory and threads (80% of RAM, all cores).
    Protected by a 2-minute query timeout.
    """
    config: Dict[str, Any] = {
        "enable_object_cache": True,        # cache parquet metadata (NFS)
        "preserve_insertion_order": False,   # saves memory when no ORDER BY
    }
    try:
        os.makedirs(settings.duckdb_temp_directory, exist_ok=True)
        config["temp_directory"] = settings.duckdb_temp_directory
    except OSError as e:
        log.warning(
            "duckdb_temp_directory %r unavailable (%s); "
            "falling back to DuckDB's default spill location",
            settings.duckdb_temp_directory, e,
        )
    return DuckDBClient(config=config, timeout_s=QUERY_TIMEOUT_S)


@lru_cache()
def get_admin_duckdb_client() -> DuckDBClient:
    """Connection pool for registration introspection and health checks.

    Limited to 1 thread, low memory, and short timeout so a misbehaving
    introspection cannot block or OOM the query path.
    """
    return DuckDBClient(
        config={
            "memory_limit": ADMIN_MEMORY,
            "threads": ADMIN_THREADS,
            "enable_object_cache": True,
            "preserve_insertion_order": False,
        },
        timeout_s=ADMIN_TIMEOUT_S,
    )
