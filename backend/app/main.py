import asyncio
import logging
import time
from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError, version as pkg_version

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from sqlmodel import select

from app.core.auth import get_password_hash
from app.core.config import settings
from app.core.database import async_session_factory, init_db
from app.core.exceptions import DataNotAvailableError, QueryError, QueryTimeoutError
from app.core.mongo_client import close_mongo, ping_mongo
from app.core.openapi_menus import install_dynamic_openapi, refresh_weight_menus
from app.core.timing import get_timings, init_timings
from app.models.auth import User
from app.core.health_check import health_check_loop
from app.routers import auth, domain_root, health, open_academic_analytics, registry, scisciDB, storywrangler, twitter, wikimedia
from storywrangler_mcp.server import mcp as mcp_server

log = logging.getLogger(__name__)

# ── Remote MCP transport ──────────────────────────────────────────────────────
# Same tools as the uvx stdio server (storywrangler-mcp), served over
# streamable HTTP at /mcp. Stateless: each request is self-contained, so it
# works behind the reverse proxy without session affinity. The MCP's outbound
# calls are configured via STORYWRANGLER_DOCS_URL / STORYWRANGLER_URL in the
# server environment — point them at localhost to avoid looping back through
# the public proxy.
mcp_server.settings.streamable_http_path = "/"
mcp_server.settings.stateless_http = True
mcp_app = mcp_server.streamable_http_app()


async def seed_admin() -> None:
    """Create the admin user on first startup if it doesn't exist."""
    async with async_session_factory() as db:
        result = await db.execute(select(User).where(User.username == settings.admin_username))
        existing = result.scalar_one_or_none()
        if existing is None:
            admin = User(
                username=settings.admin_username,
                email=settings.admin_email,
                password_hash=get_password_hash(settings.admin_password),
                role="admin",
            )
            db.add(admin)
            await db.commit()
            await db.refresh(admin)
            log.warning("Admin user created. API key: %s", admin.api_key)
        else:
            log.info("Admin user '%s' already exists.", settings.admin_username)


def _warn_default_credentials() -> None:
    """Scream when shipping-default credentials are still in effect."""
    defaults = [
        name for name, value in (
            ("ADMIN_PASSWORD", settings.admin_password),
            ("POSTGRES_PASSWORD", settings.postgres_password),
        )
        if value == "changethis"
    ]
    if defaults:
        log.critical(
            "%s still set to the default 'changethis' — change before exposing "
            "this server beyond localhost.", ", ".join(defaults),
        )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _warn_default_credentials()
    await init_db()
    await seed_admin()
    # Optional — logs and continues when MONGODB_URI is unset or Mongo is down;
    # only mongodb pass-through datasets need it.
    await ping_mongo()
    # Snapshot registered count-column menus so the OpenAPI spec can enumerate
    # weight values straight from the registry (see core/openapi_menus.py).
    async with async_session_factory() as db:
        await refresh_weight_menus(db)
    health_task = asyncio.create_task(health_check_loop())
    async with mcp_server.session_manager.run():
        yield
    health_task.cancel()
    try:
        await health_task
    except asyncio.CancelledError:
        pass
    close_mongo()


app = FastAPI(
    title="Storywrangler API",
    version="1.0.0",
    description="Text analysis platform API",
    lifespan=lifespan,
)
install_dynamic_openapi(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Server-Timing"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)


# ── Server-Timing middleware ──────────────────────────────────────────────────

@app.middleware("http")
async def server_timing_middleware(request: Request, call_next):
    init_timings()
    start = time.perf_counter()
    response = await call_next(request)
    total_ms = (time.perf_counter() - start) * 1000

    parts = []
    for name, desc, dur in get_timings():
        if desc:
            parts.append(f'{name};desc="{desc}";dur={dur:.1f}')
        else:
            parts.append(f"{name};dur={dur:.1f}")
    parts.append(f"total;dur={total_ms:.1f}")

    response.headers["Server-Timing"] = ", ".join(parts)
    return response


# ── Global exception handlers (FastAPI recommended pattern) ───────────────────

@app.exception_handler(DataNotAvailableError)
async def data_not_available_handler(request: Request, exc: DataNotAvailableError):
    return JSONResponse(
        status_code=404,
        content={
            "detail": {
                "code": "DATA_NOT_AVAILABLE",
                "message": (
                    f"Data files for '{exc.dataset}' are not available on this server. "
                    "The dataset is registered but its underlying data has not been loaded yet."
                ),
                "dataset": exc.dataset,
            }
        },
    )


@app.exception_handler(QueryError)
async def query_error_handler(request: Request, exc: QueryError):
    return JSONResponse(
        status_code=500,
        content={
            "detail": {
                "code": "QUERY_FAILED",
                "message": f"An internal error occurred while querying '{exc.dataset}'.",
                "dataset": exc.dataset,
            }
        },
    )


@app.exception_handler(QueryTimeoutError)
async def query_timeout_handler(request: Request, exc: QueryTimeoutError):
    return JSONResponse(
        status_code=504,
        content={
            "detail": {
                "code": "QUERY_TIMEOUT",
                "message": (
                    f"Query timed out for '{exc.dataset}'. "
                    "The dataset may be too large or have inefficient partitioning."
                ),
                "dataset": exc.dataset,
            }
        },
    )


app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(auth.admin_router, prefix="/admin/auth", tags=["admin"])
app.include_router(registry.router, prefix="/registry", tags=["registry"])
app.include_router(registry.admin_router, prefix="/admin/registry", tags=["admin"])

# Dataset-domain routers. Single source of truth: the keys double as the
# accepted `domain` values for dataset registration (registry.VALID_DOMAINS).
# A None router means the domain has no bespoke routes — its datasets are
# served entirely by the generic /storywrangler endpoints; it still gets a
# GET /{domain} root and stays registrable.
DOMAIN_ROUTERS = {
    "babynames": None,
    "storywrangler": storywrangler.router,
    "reddit": None,
    "bluesky": None,
    "wikimedia": wikimedia.router,
    "open-academic-analytics": open_academic_analytics.router,
    "scisciDB": scisciDB.router,
    "twitter": twitter.router,
    "vt-zoning-atlas": None,
}
for _domain, _router in DOMAIN_ROUTERS.items():
    if _router is not None:
        app.include_router(_router, prefix=f"/{_domain}", tags=[_domain])
    # GET /{domain} — generic root listing the domain's endpoints + datasets.
    # Hidden from the OpenAPI schema (include_in_schema=False): it's a discovery
    # mechanism (SDK .endpoints / client repr, or a guessed GET), not a
    # documented data contract — one near-identical entry per domain would just
    # clutter the api-reference. The route still serves normally.
    app.add_api_route(
        f"/{_domain}", domain_root.make_endpoint(_domain),
        tags=[_domain], include_in_schema=False,
    )
registry.VALID_DOMAINS = set(DOMAIN_ROUTERS)

app.include_router(health.router, prefix="/health", tags=["health"])

app.mount("/mcp", mcp_app)


@app.get("/")
async def root():
    return {
        "message": "Storywrangler API",
        "version": "1.0.0",
        "specification": "https://github.com/vermont-complex-systems/Storywrangler-Specification",
    }


@app.get("/version", tags=["platform"])
async def platform_version():
    """Return the versions of all platform components.

    Useful for debugging, reproducibility, and pinning API clients to a known
    software stack. The `schemas` version records the registration contract in
    effect; `duckdb`, `allotax`, and `wordshift` versions govern query results.
    """
    import duckdb

    try:
        schemas_ver = pkg_version("storywrangler-schemas")
    except PackageNotFoundError:
        schemas_ver = "unknown"

    try:
        allotax_ver = pkg_version("allotax")
    except PackageNotFoundError:
        try:
            import allotax
            allotax_ver = getattr(allotax, "__version__", "unknown")
        except ImportError:
            allotax_ver = "not installed"

    try:
        wordshift_ver = pkg_version("wordshift")
    except PackageNotFoundError:
        try:
            import wordshift
            wordshift_ver = getattr(wordshift, "__version__", "unknown")
        except ImportError:
            wordshift_ver = "not installed"

    return {
        "api": app.version,
        "schemas": schemas_ver,
        "duckdb": duckdb.__version__,
        "allotax": allotax_ver,
        "wordshift": wordshift_ver,
    }
