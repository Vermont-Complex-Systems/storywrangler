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
    """Fetch a registry entry, defaulting to the mutable 'latest' slot.

    When version is None, the 'latest' slot serves if it exists; datasets that
    only publish immutable snapshots fall back to the most recently created
    one. Ordering by created_at alone is wrong here: cutting a semver snapshot
    creates a *newer* row, which must not shadow the mutable slot (upserts
    update latest's contents but never its created_at).
    When version is specified, returns that exact version or None.
    """
    q = select(RegistryEntry).where(
        RegistryEntry.domain == domain,
        RegistryEntry.dataset_id == dataset_id,
    )
    if version:
        q = q.where(RegistryEntry.version == version)
    else:
        q = q.order_by(
            (RegistryEntry.version != "latest"), RegistryEntry.created_at.desc()
        ).limit(1)
    result = await db.execute(q)
    return result.scalar_one_or_none()
