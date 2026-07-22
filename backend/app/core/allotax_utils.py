"""Shared helpers for the storywrangler instruments.

The generic instrument endpoints (routers/storywrangler.py) load two
type-frequency systems and hand them to a Rust/PyO3 library — ``allotax`` for
rank-turbulence divergence, ``wordshift`` for weighted-average sentiment word
shift. Only the data loading differs by backend; the JSON-sanitisation and
version reporting are identical, so they live here.
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


def wordshift_version() -> str:
    try:
        return pkg_version("wordshift")
    except PackageNotFoundError:
        try:
            import wordshift
            return getattr(wordshift, "__version__", "unknown")
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
