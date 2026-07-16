"""Storywrangler SDK - Entity validation, standards, and registry client"""

from importlib.metadata import PackageNotFoundError, version as _pkg_version

try:
    __version__ = _pkg_version("storywrangler")
except PackageNotFoundError:  # running from source without an install
    __version__ = "0.0.0+unknown"

__standards_version__ = "0.0.3"
__standards_url__ = "https://github.com/vermont-complex-systems/Storywrangler-Specification"

from .client import Storywrangler as Storywrangler  # noqa: F401  # re-export
from .hashing import assign_bucket as assign_bucket  # noqa: F401  # re-export
from .registry import DatasetCreate as DatasetCreate, EndpointSchemaConfig as EndpointSchemaConfig, EntityMappingConfig as EntityMappingConfig  # noqa: F401

__all__ = ["Storywrangler", "assign_bucket", "DatasetCreate", "EndpointSchemaConfig", "EntityMappingConfig"]
