"""Registry-driven OpenAPI enrichment — no hand-declared enums.

Datasets that register a count-column *menu* (endpoint_schema.count_column as
a list) get their domain router's `weight` query parameters enriched in the
OpenAPI spec at build time: the parameter schema gains an enum (Swagger
dropdown) and the description gains the enumerated values (which the docs
site renders into the api-reference markdown).

The snapshot loads at startup and refreshes on every successful registration
(which also invalidates FastAPI's cached openapi_schema), so the reference
cannot drift from the registry. Behavior never depends on this module —
weight validation is resolve_count_column() against the registry row.
"""

import logging

from sqlalchemy import select

log = logging.getLogger(__name__)

# domain -> ordered count-column menu, only for datasets registering one.
# A domain's routers query its own datasets, so domain granularity is enough.
_weight_menus: dict = {}


async def refresh_weight_menus(db) -> None:
    """Rebuild the domain → count-column-menu snapshot from the registry."""
    from ..models.registry import RegistryEntry

    rows = (await db.execute(select(RegistryEntry))).scalars().all()
    menus: dict = {}
    for row in rows:
        cc = (row.endpoint_schema or {}).get("count_column")
        if isinstance(cc, list) and len(cc) > 1:
            menus.setdefault(row.domain, cc)
    _weight_menus.clear()
    _weight_menus.update(menus)
    if menus:
        log.info("weight menus loaded for domains: %s", sorted(menus))


def install_dynamic_openapi(app) -> None:
    """Wrap app.openapi() so every (re)build gets menu enrichment applied."""
    base = app.openapi

    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        schema = base()
        _patch_weight_params(schema)
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi


def _patch_weight_params(schema: dict) -> None:
    for path, ops in (schema.get("paths") or {}).items():
        domain = path.strip("/").split("/", 1)[0]
        menu = _weight_menus.get(domain)
        if not menu:
            continue
        for op in ops.values():
            if not isinstance(op, dict):
                continue
            for param in op.get("parameters") or []:
                if param.get("name") != "weight":
                    continue
                base_desc = (param.get("description") or "").rstrip()
                enum_desc = f"One of: {' | '.join(str(c) for c in menu)}. Defaults to {menu[0]}."
                param["description"] = f"{base_desc} {enum_desc}".strip()
                sub = param.get("schema") or {}
                sub["description"] = param["description"]
                # Optional[str] renders as anyOf [string, null]; the enum
                # belongs on the string member for Swagger's dropdown.
                for member in sub.get("anyOf") or [sub]:
                    if member.get("type") == "string":
                        member["enum"] = list(menu)
