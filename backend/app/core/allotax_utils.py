"""Shared helpers for the allotaxonometer instruments.

Both the parquet-backed generic endpoints (routers/storywrangler.py) and the
mongodb-backed twitter endpoints (routers/twitter.py) load two type-frequency
systems and hand them to the same ``allotax`` (Rust/PyO3) library. Only the
data loading differs by backend; the JSON-sanitisation, version reporting, and
import guard are identical, so they live here.
"""

import math
from importlib.metadata import PackageNotFoundError, version as pkg_version

from fastapi import HTTPException


def sanitize_floats(obj):
    """Replace NaN → null, ±Infinity → string, so json.dumps won't choke."""
    if isinstance(obj, float):
        if math.isnan(obj):
            return None
        if math.isinf(obj):
            return "Infinity" if obj > 0 else "-Infinity"
        return obj
    if isinstance(obj, dict):
        return {k: sanitize_floats(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_floats(v) for v in obj]
    return obj


def allotax_version() -> str:
    try:
        return pkg_version("allotax")
    except PackageNotFoundError:
        try:
            import allotax
            return getattr(allotax, "__version__", "unknown")
        except ImportError:
            return "not installed"


def require_allotax():
    """Import the allotax module or raise 503 with an install hint."""
    try:
        import allotax
        return allotax
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="allotax module not available. Install via: pip install allotax",
        )
