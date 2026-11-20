from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.models.finance import Category
from app.models.user import RefreshToken, User
from app.schemas.auth import AuthTokenResponse, LoginRequest, RegisterRequest, UserResponse

DEFAULT_CATEGORIES: list[tuple[str, str, str, str]] = [
    # (name, kind, icon, color)
    ("Salary & Payroll", "income", "briefcase", "#10b981"),
    ("Freelance & Side Income", "income", "sparkles", "#06b6d4"),
    ("Investments & Dividends", "income", "trending-up", "#3b82f6"),
    ("Housing & Rent", "expense", "home", "#6366f1"),
    ("Groceries", "expense", "shopping-cart", "#22c55e"),
    ("Dining & Coffee", "expense", "utensils", "#f59e0b"),
    ("Transportation & Transit", "expense", "car", "#0ea5e9"),
    ("Utilities & Internet", "expense", "zap", "#eab308"),
    ("Subscriptions & Software", "expense", "repeat", "#a855f7"),
    ("Shopping & Retail", "expense", "shopping-bag", "#ec4899"),
    ("Healthcare & Pharmacy", "expense", "heart-pulse", "#ef4444"),
    ("Entertainment & Leisure", "expense", "film", "#f97316"),
    ("Travel & Lodging", "expense", "plane", "#14b8a6"),
    ("Education", "expense", "graduation-cap", "#8b5cf6"),
    ("Taxes & Fees", "expense", "landmark", "#64748b"),
    ("Uncategorized", "expense", "help-circle", "#94a3b8"),
    ("Internal Transfer", "transfer", "arrow-left-right", "#64748b"),
]


async def seed_default_categories(db: AsyncSession, user_id) -> list[Category]:
    categories = [
        Category(
            user_id=user_id,
            name=name,
            kind=kind,
            icon=icon,
            color=color,
            is_system=True,
        )
        for name, kind, icon, color in DEFAULT_CATEGORIES
    ]
    db.add_all(categories)
    await db.flush()
    return categories


async def issue_tokens(db: AsyncSession, user: User) -> AuthTokenResponse:
    access_token, expires_in = create_access_token(user.id, user.email)
    raw_refresh, refresh_hash, expires_at = create_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=refresh_hash,
            expires_at=expires_at,
        )
    )
    await db.commit()
    await db.refresh(user)
    return AuthTokenResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
        expires_in=expires_in,
        user=UserResponse.model_validate(user),
    )


async def register_user(db: AsyncSession, payload: RegisterRequest) -> AuthTokenResponse:
    normalized_email = payload.email.lower().strip()
    existing = await db.scalar(select(User).where(User.email == normalized_email))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    user = User(
        email=normalized_email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name.strip(),
        base_currency=payload.base_currency.upper(),
    )
    db.add(user)
    await db.flush()
    await seed_default_categories(db, user.id)
    return await issue_tokens(db, user)


async def login_user(db: AsyncSession, payload: LoginRequest) -> AuthTokenResponse:
    normalized_email = payload.email.lower().strip()
    user = await db.scalar(select(User).where(User.email == normalized_email))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )
    return await issue_tokens(db, user)


async def rotate_refresh_token(db: AsyncSession, raw_refresh_token: str) -> AuthTokenResponse:
    token_hash = hash_token(raw_refresh_token)
    stored = await db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    now = datetime.now(UTC)
    if stored is None or stored.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token is invalid or revoked.",
        )

    expires_at = (
        stored.expires_at.replace(tzinfo=UTC)
        if stored.expires_at.tzinfo is None
        else stored.expires_at
    )
    if expires_at < now:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired.",
        )

    stored.revoked_at = now
    user = await db.get(User, stored.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists.",
        )
    return await issue_tokens(db, user)


async def revoke_refresh_token(db: AsyncSession, raw_refresh_token: str) -> None:
    token_hash = hash_token(raw_refresh_token)
    stored = await db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    if stored is not None and stored.revoked_at is None:
        stored.revoked_at = datetime.now(UTC)
        await db.commit()
