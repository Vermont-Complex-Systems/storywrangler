"""Auth endpoints — API key-based authentication (Label Studio pattern)."""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..core.auth import get_password_hash, verify_password
from ..core.config import settings
from ..core.database import get_session
from ..models.auth import User

log = logging.getLogger(__name__)

router = APIRouter()
admin_router = APIRouter()

_security = HTTPBearer()


# ── Dependencies ───────────────────────────────────────────────────────────────

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
    db: AsyncSession = Depends(get_session),
) -> User:
    """Validate Bearer token as an api_key and return the matching user."""
    result = await db.execute(
        select(User).where(User.api_key == credentials.credentials, User.is_active == True)
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_admin_user(current_user: User = Depends(get_current_user)) -> User:
    """Require admin role."""
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user


# ── Request / Response schemas ─────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    role: str
    api_key: str
    is_active: bool

    model_config = {"from_attributes": True}


class CreateUserRequest(BaseModel):
    username: str
    email: str
    password: str
    role: str = "user"


# ── Public endpoints ───────────────────────────────────────────────────────────

@router.post("/login", response_model=UserResponse)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_session),
):
    """Exchange username + password for the user's API key."""
    result = await db.execute(select(User).where(User.username == body.username))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")
    return user


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)):
    """Return the authenticated user's profile."""
    return current_user


# ── Admin endpoints ────────────────────────────────────────────────────────────

@admin_router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: CreateUserRequest,
    _: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_session),
):
    """Create a new user account (admin only). Returns the generated API key."""
    if body.role not in ("admin", "user"):
        raise HTTPException(status_code=400, detail="role must be 'admin' or 'user'")

    # Check uniqueness
    existing = await db.execute(
        select(User).where(
            (User.username == body.username) | (User.email == body.email)
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username or email already taken")

    user = User(
        username=body.username,
        email=body.email,
        password_hash=get_password_hash(body.password),
        role=body.role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    log.info("Created user '%s' (role=%s)", user.username, user.role)
    return user


@admin_router.get("/users", response_model=List[UserResponse])
async def list_users(
    _: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_session),
):
    """List all user accounts (admin only)."""
    result = await db.execute(select(User).order_by(User.created_at))
    return result.scalars().all()


@admin_router.put("/users/{user_id}/role", response_model=UserResponse)
async def update_user_role(
    user_id: int,
    role: str,
    _: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_session),
):
    """Promote or demote a user's role (admin only)."""
    if role not in ("admin", "user"):
        raise HTTPException(status_code=400, detail="role must be 'admin' or 'user'")

    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    user.role = role
    await db.commit()
    await db.refresh(user)
    return user
