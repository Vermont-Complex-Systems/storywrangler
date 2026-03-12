"""Storywrangler SDK - Entity validation, standards, and registry client"""

__version__ = "0.0.1"
__standards_version__ = "0.0.1"
__standards_url__ = "https://github.com/vermont-complex-systems/Storywrangler-Specification"

from .registry import register as register, DatasetCreate as DatasetCreate, EndpointSchemaConfig as EndpointSchemaConfig, EntityMappingConfig as EntityMappingConfig  # noqa: F401

__all__ = ["register", "DatasetCreate", "EndpointSchemaConfig", "EntityMappingConfig"]
