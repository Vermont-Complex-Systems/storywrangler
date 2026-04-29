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
from app.core.exceptions import DataNotAvailableError, QueryError
from app.core.timing import get_timings, init_timings
from app.models.auth import User
from app.routers import auth, babynames, open_academic_analytics, registry, scisciDB, storywrangler, wikimedia, zoning_bylaws

log = logging.getLogger(__name__)


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


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await init_db()
    await seed_admin()
    yield


app = FastAPI(
    title="Storywrangler API",
    version="1.0.0",
    description="Text analysis platform API",
    lifespan=lifespan,
)

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


app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(auth.admin_router, prefix="/admin/auth", tags=["admin"])
app.include_router(registry.router, prefix="/registry", tags=["registry"])
app.include_router(registry.admin_router, prefix="/admin/registry", tags=["admin"])
app.include_router(babynames.router, prefix="/babynames", tags=["babynames"])
app.include_router(storywrangler.router, prefix="/storywrangler", tags=["storywrangler"])
app.include_router(wikimedia.router, prefix="/wikimedia", tags=["wikimedia"])
app.include_router(open_academic_analytics.router, prefix="/open-academic-analytics", tags=["open-academic-analytics"])
app.include_router(scisciDB.router, prefix="/scisciDB", tags=["scisciDB"])
app.include_router(zoning_bylaws.router, prefix="/vt-zoning-atlas", tags=["vt-zoning-atlas"])


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
    effect; `duckdb` and `allotax` versions govern query results.
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

    return {
        "api": app.version,
        "schemas": schemas_ver,
        "duckdb": duckdb.__version__,
        "allotax": allotax_ver,
    }
