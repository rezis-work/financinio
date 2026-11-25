from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

DigestType = Literal["weekly", "monthly"]


class EmailPreferencesResponse(BaseModel):
    email: str
    email_weekly_briefing: bool
    email_monthly_wrapped: bool
    last_weekly_briefing_sent_at: datetime | None = None
    last_monthly_wrapped_sent_at: datetime | None = None
    resend_configured: bool
    sender_address: str


class EmailPreferencesUpdate(BaseModel):
    email_weekly_briefing: bool | None = None
    email_monthly_wrapped: bool | None = None


class EmailDigestPreviewResponse(BaseModel):
    digest_type: DigestType
    subject: str
    preheader: str
    html: str
    metrics: dict[str, Any] = Field(default_factory=dict)


class SendEmailDigestRequest(BaseModel):
    digest_type: DigestType = "weekly"


class SendEmailDigestResponse(BaseModel):
    sent: bool
    digest_type: DigestType
    recipient: str
    subject: str
    resend_email_id: str | None = None
    detail: str


class ScheduledDispatchRequest(BaseModel):
    digest_type: DigestType
    force: bool = False


class ScheduledDispatchResponse(BaseModel):
    digest_type: DigestType
    total_eligible: int
    sent_count: int
    skipped_count: int
    failed_count: int
