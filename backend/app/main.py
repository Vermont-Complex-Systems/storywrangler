import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from sqlmodel import select

from app.core.auth import get_password_hash
from app.core.config import settings
from app.core.database import async_session_factory, init_db
from app.models.auth import User
from app.routers import auth, babynames, open_academic_analytics, registry, storywrangler, wikimedia, zoning_bylaws

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
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(auth.admin_router, prefix="/admin/auth", tags=["admin"])
app.include_router(registry.router, prefix="/registry", tags=["registry"])
app.include_router(registry.admin_router, prefix="/admin/registry", tags=["admin"])
app.include_router(babynames.router, prefix="/babynames", tags=["babynames"])
app.include_router(storywrangler.router, prefix="/storywrangler", tags=["storywrangler"])
app.include_router(wikimedia.router, prefix="/wikimedia", tags=["wikimedia"])
app.include_router(open_academic_analytics.router, prefix="/open-academic-analytics", tags=["open-academic-analytics"])
app.include_router(zoning_bylaws.router, prefix="/vt-zoning-atlas", tags=["vt-zoning-atlas"])


@app.get("/")
async def root():
    return {
        "message": "Storywrangler API",
        "version": "1.0.0",
        "specification": "https://github.com/vermont-complex-systems/Storywrangler-Specification",
    }
