from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin_user
from app.api.v1.account_data import record_audit
from app.core.config import get_settings
from app.core.database import get_db
from app.models.finance import Account, Transaction
from app.models.user import AIUsageEvent, RefreshToken, User
from app.schemas.admin import (
    AdminOverviewResponse,
    AdminUserAccessUpdate,
    AdminUserSummary,
    AIUsageEventResponse,
)

router = APIRouter(prefix="/admin", tags=["Admin Dashboard"])


async def _build_user_summary(db: AsyncSession, user: User) -> AdminUserSummary:
    acc_count = (
        await db.scalar(select(func.count(Account.id)).where(Account.user_id == user.id)) or 0
    )
    tx_count = (
        await db.scalar(select(func.count(Transaction.id)).where(Transaction.user_id == user.id))
        or 0
    )
    return AdminUserSummary(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        base_currency=user.base_currency,
        role=user.role,  # type: ignore[arg-type]
        is_active=user.is_active,
        ai_token_limit=user.ai_token_limit,
        ai_tokens_used=user.ai_tokens_used,
        has_unlimited_ai=user.has_unlimited_ai,
        accounts_count=acc_count,
        transactions_count=tx_count,
        created_at=user.created_at,
    )


@router.get("/overview", response_model=AdminOverviewResponse)
async def admin_overview(
    _admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> AdminOverviewResponse:
    settings = get_settings()
    total_users = await db.scalar(select(func.count(User.id))) or 0
    active_users = await db.scalar(select(func.count(User.id)).where(User.is_active.is_(True))) or 0
    admin_users = await db.scalar(select(func.count(User.id)).where(User.role == "admin")) or 0
    unlimited_users = (
        await db.scalar(select(func.count(User.id)).where(User.has_unlimited_ai.is_(True))) or 0
    )
    suspended_users = total_users - active_users
    total_tokens = await db.scalar(select(func.coalesce(func.sum(User.ai_tokens_used), 0))) or 0

    cutoff_7d = datetime.now(UTC) - timedelta(days=7)
    tokens_7d = (
        await db.scalar(
            select(func.coalesce(func.sum(AIUsageEvent.total_tokens), 0)).where(
                AIUsageEvent.created_at >= cutoff_7d
            )
        )
        or 0
    )
    total_accounts = await db.scalar(select(func.count(Account.id))) or 0
    total_transactions = await db.scalar(select(func.count(Transaction.id))) or 0

    recent_rows = (
        await db.execute(
            select(AIUsageEvent, User.email)
            .join(User, User.id == AIUsageEvent.user_id)
            .order_by(AIUsageEvent.created_at.desc())
            .limit(25)
        )
    ).all()

    recent_usage = [
        AIUsageEventResponse(
            id=ev.id,
            user_id=ev.user_id,
            user_email=email,
            feature=ev.feature,
            provider=ev.provider,
            model=ev.model,
            prompt_tokens=ev.prompt_tokens,
            completion_tokens=ev.completion_tokens,
            total_tokens=ev.total_tokens,
            created_at=ev.created_at,
        )
        for ev, email in recent_rows
    ]

    return AdminOverviewResponse(
        total_users=total_users,
        active_users=active_users,
        admin_users=admin_users,
        unlimited_users=unlimited_users,
        suspended_users=suspended_users,
        total_ai_tokens_used=int(total_tokens),
        tokens_used_last_7d=int(tokens_7d),
        total_accounts=total_accounts,
        total_transactions=total_transactions,
        default_token_limit=settings.default_user_ai_token_limit,
        recent_ai_usage=recent_usage,
    )


@router.get("/users", response_model=list[AdminUserSummary])
async def list_users(
    search: str | None = Query(default=None),
    tier: Literal["all", "standard", "unlimited", "admin", "suspended"] = Query(default="all"),
    _admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> list[AdminUserSummary]:
    filters = []
    if search and search.strip():
        pat = f"%{search.strip()}%"
        filters.append(or_(User.email.ilike(pat), User.full_name.ilike(pat)))
    if tier == "standard":
        filters.append(User.has_unlimited_ai.is_(False))
    elif tier == "unlimited":
        filters.append(User.has_unlimited_ai.is_(True))
    elif tier == "admin":
        filters.append(User.role == "admin")
    elif tier == "suspended":
        filters.append(User.is_active.is_(False))

    users = (
        await db.scalars(
            select(User).where(*filters).order_by(User.created_at.desc()).limit(200)
        )
    ).all()

    # Aggregate account & transaction counts in 2 efficient grouped queries
    acc_counts = dict(
        (
            await db.execute(select(Account.user_id, func.count(Account.id)).group_by(Account.user_id))
        ).all()
    )
    tx_counts = dict(
        (
            await db.execute(
                select(Transaction.user_id, func.count(Transaction.id)).group_by(Transaction.user_id)
            )
        ).all()
    )

    return [
        AdminUserSummary(
            id=u.id,
            email=u.email,
            full_name=u.full_name,
            base_currency=u.base_currency,
            role=u.role,  # type: ignore[arg-type]
            is_active=u.is_active,
            ai_token_limit=u.ai_token_limit,
            ai_tokens_used=u.ai_tokens_used,
            has_unlimited_ai=u.has_unlimited_ai,
            accounts_count=int(acc_counts.get(u.id, 0)),
            transactions_count=int(tx_counts.get(u.id, 0)),
            created_at=u.created_at,
        )
        for u in users
    ]


@router.patch("/users/{user_id}/access", response_model=AdminUserSummary)
async def update_user_access(
    user_id: UUID,
    payload: AdminUserAccessUpdate,
    request: Request,
    admin_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> AdminUserSummary:
    target = await db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    # Self-lockout safety guard
    if target.id == admin_user.id:
        if payload.role == "user":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot demote your own admin account.",
            )
        if payload.is_active is False:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot suspend your own admin account.",
            )

    changes: dict = {}
    if payload.has_unlimited_ai is not None:
        target.has_unlimited_ai = payload.has_unlimited_ai
        changes["has_unlimited_ai"] = payload.has_unlimited_ai
    if payload.ai_token_limit is not None:
        target.ai_token_limit = payload.ai_token_limit
        changes["ai_token_limit"] = payload.ai_token_limit
    if payload.reset_tokens_used:
        target.ai_tokens_used = 0
        changes["reset_tokens_used"] = True
    if payload.role is not None:
        target.role = payload.role
        changes["role"] = payload.role
    if payload.is_active is not None:
        target.is_active = payload.is_active
        changes["is_active"] = payload.is_active
        if not payload.is_active:
            # Immediately revoke active refresh tokens when suspending a user
            await db.execute(
                update(RefreshToken)
                .where(RefreshToken.user_id == target.id, RefreshToken.revoked_at.is_(None))
                .values(revoked_at=datetime.now(UTC))
            )

    await db.commit()
    await db.refresh(target)

    await record_audit(
        db,
        user_id=admin_user.id,
        action="admin.update_user_access",
        resource_type="user",
        resource_id=str(target.id),
        ip_address=request.client.host if request.client else None,
        details={"target_email": target.email, **changes},
    )

    return await _build_user_summary(db, target)


@router.get("/users/{user_id}/usage", response_model=list[AIUsageEventResponse])
async def get_user_usage_history(
    user_id: UUID,
    _admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> list[AIUsageEventResponse]:
    target = await db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    events = (
        await db.scalars(
            select(AIUsageEvent)
            .where(AIUsageEvent.user_id == target.id)
            .order_by(AIUsageEvent.created_at.desc())
            .limit(50)
        )
    ).all()
    return [
        AIUsageEventResponse(
            id=ev.id,
            user_id=ev.user_id,
            user_email=target.email,
            feature=ev.feature,
            provider=ev.provider,
            model=ev.model,
            prompt_tokens=ev.prompt_tokens,
            completion_tokens=ev.completion_tokens,
            total_tokens=ev.total_tokens,
            created_at=ev.created_at,
        )
        for ev in events
    ]
