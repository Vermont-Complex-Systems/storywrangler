"""Import all ORM models so SQLModel.metadata knows every table."""
from .auth import User  # noqa: F401
from .registry import RegistryEntry, EntityMapping, EntityGraph  # noqa: F401
