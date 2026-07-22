"""
Domain root endpoints — GET /{domain} lists what the domain serves.

One generic handler, mounted by main.py for every entry in DOMAIN_ROUTERS,
so a new domain gets its root listing automatically. The endpoint list is
read from the app's own route table (including each route's ``x-dataset``
annotation — the registered dataset the route serves); the dataset list
comes from the registry. This is the API-level mirror of the SDK's
discovery surface: /registry/ answers "what data exists", /{domain}
answers "what can I call here".
"""

from fastapi import Depends, Request
from fastapi.routing import APIRoute
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..core.database import get_session
from ..models.registry import RegistryEntry


def make_endpoint(domain: str):
    """Build the GET /{domain} handler for one domain."""

    async def domain_root(
        request: Request,
        db: AsyncSession = Depends(get_session),
    ):
        prefix = f"/{domain}/"
        endpoints = {}
        for route in request.app.routes:
            if not isinstance(route, APIRoute) or not route.path.startswith(prefix):
                continue
            extra = route.openapi_extra or {}
            endpoints[route.path] = {
                "summary": route.summary or route.name.replace("_", " ").title(),
                "dataset": extra.get("x-dataset"),
            }

        result = await db.execute(
            select(RegistryEntry.dataset_id)
            .where(RegistryEntry.domain == domain)
            .distinct()
        )
        datasets = sorted(row[0] for row in result)

        return {"domain": domain, "endpoints": endpoints, "datasets": datasets}

    # Distinct names keep OpenAPI operation ids unique across domains.
    domain_root.__name__ = f"{domain.replace('-', '_')}_root"
    domain_root.__doc__ = f"List the endpoints and registered datasets of the '{domain}' domain."
    return domain_root
