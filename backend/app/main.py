import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlmodel import select

from app.core.auth import get_password_hash
from app.core.config import settings
from app.core.database import async_session_factory, init_db
from app.models.auth import User
from app.routers import auth, babynames, registry, storywrangler, wikimedia

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

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(auth.admin_router, prefix="/admin/auth", tags=["admin"])
app.include_router(registry.router, prefix="/registry", tags=["registry"])
app.include_router(registry.admin_router, prefix="/admin/registry", tags=["admin"])
app.include_router(babynames.router, prefix="/babynames", tags=["babynames"])
app.include_router(storywrangler.router, prefix="/storywrangler", tags=["storywrangler"])
app.include_router(wikimedia.router, prefix="/wikimedia", tags=["wikimedia"])


@app.get("/")
async def root():
    return {
        "message": "Storywrangler API",
        "version": "1.0.0",
        "specification": "https://github.com/vermont-complex-systems/Storywrangler-Specification",
    }
