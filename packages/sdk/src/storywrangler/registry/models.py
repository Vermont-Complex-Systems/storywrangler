"""
Re-exported from storywrangler-schemas — single source of truth.

Previously defined here; now lives in packages/schemas/src/storywrangler_schemas/registry.py.
Submit scripts don't change: `from storywrangler.registry import DatasetCreate` still works.
"""

from storywrangler_schemas.registry import (  # noqa: F401
    DatasetCreate,
    EndpointSchemaConfig,
    EntityMappingConfig,
    EntityRow,
    HashBucketConfig,
    ManifestConfig,
    LineageConfig,
    OwnershipConfig,
    TransformConfig,
)

__all__ = [
    "DatasetCreate",
    "EndpointSchemaConfig",
    "EntityMappingConfig",
    "EntityRow",
    "HashBucketConfig",
    "ManifestConfig",
    "LineageConfig",
    "OwnershipConfig",
    "TransformConfig",
]
