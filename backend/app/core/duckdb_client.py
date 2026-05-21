"""DuckDB connection management with resource limits and query timeouts.

Two connection pools, each with its own memory/thread budget:

  - **query**: handles user-facing requests (allotax, RTD, term-series).
    Gets most of the resources since these are the latency-sensitive path.

  - **admin**: handles registration introspection and health checks.
    Capped at 1 thread and low memory so a runaway introspection
    (e.g. recursive NFS walk) can't starve the query pool.

Both pools support query timeouts via ``conn.interrupt()`` — a timer
thread cancels any query that exceeds the deadline.
"""

import duckdb
import threading
from contextlib import contextmanager
from functools import lru_cache

# ── Resource budgets ──────────────────────────────────────────────────────────
# Tune these if the machine changes.  Current target: 48 GB / 12 cores.

QUERY_MEMORY = "4GB"
QUERY_THREADS = 4
QUERY_TIMEOUT_S = 120  # 2 minutes — user-facing queries

ADMIN_MEMORY = "512MB"
ADMIN_THREADS = 1
ADMIN_TIMEOUT_S = 30  # 30 seconds — introspection / health probes


class DuckDBClient:
    """Lazy-init DuckDB connection with configurable limits and timeouts."""

    def __init__(
        self, *,
        memory_limit: str = QUERY_MEMORY,
        threads: int = QUERY_THREADS,
        timeout_s: int = QUERY_TIMEOUT_S,
    ):
        self._memory_limit = memory_limit
        self._threads = threads
        self._timeout_s = timeout_s
        self.conn = None

    def connect(self):
        if self.conn is None:
            self.conn = duckdb.connect()
            self.conn.execute(f"SET memory_limit = '{self._memory_limit}'")
            self.conn.execute(f"SET threads = {self._threads}")
        return self.conn

    @contextmanager
    def timed_connect(self, timeout_s: int | None = None):
        """Context manager that auto-interrupts if the query exceeds *timeout_s*.

        Usage::

            with client.timed_connect() as conn:
                conn.execute("SELECT ...").fetchall()

        On timeout, ``conn.interrupt()`` is called, which raises
        ``duckdb.InterruptException`` inside the executing query.
        """
        conn = self.connect()
        deadline = timeout_s if timeout_s is not None else self._timeout_s
        timer = threading.Timer(deadline, conn.interrupt)
        timer.start()
        try:
            yield conn
        finally:
            timer.cancel()

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None


@lru_cache()
def get_duckdb_client() -> DuckDBClient:
    """Connection pool for user-facing queries."""
    return DuckDBClient(
        memory_limit=QUERY_MEMORY,
        threads=QUERY_THREADS,
        timeout_s=QUERY_TIMEOUT_S,
    )


@lru_cache()
def get_admin_duckdb_client() -> DuckDBClient:
    """Connection pool for registration introspection and health checks.

    Limited to 1 thread, low memory, and short timeout so a misbehaving
    introspection cannot block or OOM the query path.
    """
    return DuckDBClient(
        memory_limit=ADMIN_MEMORY,
        threads=ADMIN_THREADS,
        timeout_s=ADMIN_TIMEOUT_S,
    )
