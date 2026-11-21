from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class AdminUserSummary(BaseModel):
    id: UUID
    email: EmailStr
    full_name: str
    base_currency: str
    role: Literal["user", "admin"]
    is_active: bool
    ai_token_limit: int
    ai_tokens_used: int
    has_unlimited_ai: bool
    accounts_count: int
    transactions_count: int
    created_at: datetime


class AdminUserAccessUpdate(BaseModel):
    has_unlimited_ai: bool | None = None
    ai_token_limit: int | None = Field(default=None, ge=0, le=100_000_000)
    reset_tokens_used: bool = False
    role: Literal["user", "admin"] | None = None
    is_active: bool | None = None


class AIUsageEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    user_email: str | None = None
    feature: str
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    created_at: datetime


class AdminOverviewResponse(BaseModel):
    total_users: int
    active_users: int
    admin_users: int
    unlimited_users: int
    suspended_users: int
    total_ai_tokens_used: int
    tokens_used_last_7d: int
    total_accounts: int
    total_transactions: int
    default_token_limit: int
    recent_ai_usage: list[AIUsageEventResponse]
