"""Server-Timing support — lightweight per-request instrumentation.

Endpoints wrap interesting sections with `timed()`:

    from ..core.timing import timed

    async def term_series(...):
        with timed("resolve", "Entity resolution"):
            local_id = ...
        with timed("query", "DuckDB sparkline read"):
            rows = conn.execute(...).fetchall()

The middleware in main.py collects all segments and emits a standard
Server-Timing HTTP header that Chrome DevTools renders natively in
the Network tab → Timing section.
"""

import time
from contextlib import contextmanager
from contextvars import ContextVar

# Each async request gets its own list via contextvars (no cross-request leaks).
_timings: ContextVar[list | None] = ContextVar("server_timings", default=None)


def init_timings():
    """Call at the start of each request (from middleware)."""
    _timings.set([])


def get_timings() -> list:
    """Retrieve all recorded segments for the current request."""
    return _timings.get() or []


@contextmanager
def timed(name: str, desc: str = ""):
    """Record a named timing segment for the current request.

    No-op if init_timings() was never called (e.g. in tests without middleware).
    """
    timings = _timings.get()
    if timings is None:
        yield
        return
    start = time.perf_counter()
    yield
    dur_ms = (time.perf_counter() - start) * 1000
    timings.append((name, desc, dur_ms))
