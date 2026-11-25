import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.database import get_db
from app.models.base import utcnow
from app.models.user import User
from app.schemas.email import (
    DigestType,
    EmailDigestPreviewResponse,
    EmailPreferencesResponse,
    EmailPreferencesUpdate,
    ScheduledDispatchRequest,
    ScheduledDispatchResponse,
    SendEmailDigestRequest,
    SendEmailDigestResponse,
)
from app.services.email_service import (
    build_monthly_wrapped_digest,
    build_weekly_briefing_digest,
    send_via_resend,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/emails", tags=["Email Digests & Reports"])


def _prefs_response(user: User) -> EmailPreferencesResponse:
    settings = get_settings()
    return EmailPreferencesResponse(
        email=user.email,
        email_weekly_briefing=user.email_weekly_briefing,
        email_monthly_wrapped=user.email_monthly_wrapped,
        last_weekly_briefing_sent_at=user.last_weekly_briefing_sent_at,
        last_monthly_wrapped_sent_at=user.last_monthly_wrapped_sent_at,
        resend_configured=settings.resend_configured,
        sender_address=settings.email_from,
    )


@router.get("/preferences", response_model=EmailPreferencesResponse)
async def get_email_preferences(
    current_user: User = Depends(get_current_user),
) -> EmailPreferencesResponse:
    return _prefs_response(current_user)


@router.patch("/preferences", response_model=EmailPreferencesResponse)
async def update_email_preferences(
    payload: EmailPreferencesUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailPreferencesResponse:
    if payload.email_weekly_briefing is not None:
        current_user.email_weekly_briefing = payload.email_weekly_briefing
    if payload.email_monthly_wrapped is not None:
        current_user.email_monthly_wrapped = payload.email_monthly_wrapped
    await db.commit()
    await db.refresh(current_user)
    return _prefs_response(current_user)


@router.get("/preview", response_model=EmailDigestPreviewResponse)
async def preview_email_digest(
    digest_type: DigestType = Query(default="weekly"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailDigestPreviewResponse:
    built = (
        await build_weekly_briefing_digest(db, current_user)
        if digest_type == "weekly"
        else await build_monthly_wrapped_digest(db, current_user)
    )
    return EmailDigestPreviewResponse(**built)


@router.post("/send-test", response_model=SendEmailDigestResponse)
async def send_email_digest_now(
    payload: SendEmailDigestRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SendEmailDigestResponse:
    """Render and send your Weekly Briefing or Monthly CFO Wrapped email right now via Resend."""
    built = (
        await build_weekly_briefing_digest(db, current_user)
        if payload.digest_type == "weekly"
        else await build_monthly_wrapped_digest(db, current_user)
    )
    try:
        resend_id = await send_via_resend(
            to_email=current_user.email,
            subject=built["subject"],
            html_body=built["html"],
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    now = utcnow()
    if payload.digest_type == "weekly":
        current_user.last_weekly_briefing_sent_at = now
    else:
        current_user.last_monthly_wrapped_sent_at = now
    await db.commit()

    return SendEmailDigestResponse(
        sent=True,
        digest_type=payload.digest_type,
        recipient=current_user.email,
        subject=built["subject"],
        resend_email_id=resend_id,
        detail=f"Sent {payload.digest_type} digest to {current_user.email}.",
    )


@router.post("/dispatch-scheduled", response_model=ScheduledDispatchResponse)
async def dispatch_scheduled_digests(
    payload: ScheduledDispatchRequest,
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
    db: AsyncSession = Depends(get_db),
) -> ScheduledDispatchResponse:
    """Cron-protected batch dispatcher for Monday 9 AM Weekly Briefings & 1st-of-Month CFO Wrapped."""
    settings = get_settings()
    if not settings.cron_secret or x_cron_secret != settings.cron_secret:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Valid X-Cron-Secret header required for scheduled dispatch.",
        )

    flag_col = (
        User.email_weekly_briefing
        if payload.digest_type == "weekly"
        else User.email_monthly_wrapped
    )
    users = (
        await db.scalars(
            select(User).where(User.is_active.is_(True), flag_col.is_(True))
        )
    ).all()

    now = utcnow()
    cooldown = timedelta(days=5) if payload.digest_type == "weekly" else timedelta(days=25)
    sent = 0
    skipped = 0
    failed = 0

    for u in users:
        last_sent = (
            u.last_weekly_briefing_sent_at
            if payload.digest_type == "weekly"
            else u.last_monthly_wrapped_sent_at
        )
        if not payload.force and last_sent is not None and (now - last_sent) < cooldown:
            skipped += 1
            continue

        try:
            built = (
                await build_weekly_briefing_digest(db, u)
                if payload.digest_type == "weekly"
                else await build_monthly_wrapped_digest(db, u)
            )
            await send_via_resend(
                to_email=u.email,
                subject=built["subject"],
                html_body=built["html"],
            )
            if payload.digest_type == "weekly":
                u.last_weekly_briefing_sent_at = now
            else:
                u.last_monthly_wrapped_sent_at = now
            sent += 1
        except Exception as exc:
            logger.warning("Scheduled %s email failed for %s: %s", payload.digest_type, u.email, exc)
            failed += 1

    await db.commit()
    return ScheduledDispatchResponse(
        digest_type=payload.digest_type,
        total_eligible=len(users),
        sent_count=sent,
        skipped_count=skipped,
        failed_count=failed,
    )
