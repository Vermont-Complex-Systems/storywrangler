"""
Registry query helpers — shared across all domain routers.
"""

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..models.registry import RegistryEntry


async def get_latest_entry(
    db: AsyncSession,
    domain: str,
    dataset_id: str,
    version: Optional[str] = None,
) -> Optional[RegistryEntry]:
    """Fetch a registry entry, defaulting to the most recently created version.

    When version is None, returns the entry with the latest created_at timestamp
    (which is the 'latest' mutable slot if one exists, or the most recent snapshot).
    When version is specified, returns that exact version or None.
    """
    q = select(RegistryEntry).where(
        RegistryEntry.domain == domain,
        RegistryEntry.dataset_id == dataset_id,
    )
    if version:
        q = q.where(RegistryEntry.version == version)
    else:
        q = q.order_by(RegistryEntry.created_at.desc()).limit(1)
    result = await db.execute(q)
    return result.scalar_one_or_none()
