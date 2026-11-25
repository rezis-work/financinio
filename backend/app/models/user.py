from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    base_currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    fiscal_start_day: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Admin & AI Token Quota fields
    role: Mapped[str] = mapped_column(
        String(16), default="user", server_default="user", nullable=False
    )  # user | admin
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
    ai_token_limit: Mapped[int] = mapped_column(
        Integer, default=50_000, server_default="50000", nullable=False
    )
    ai_tokens_used: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    has_unlimited_ai: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )

    # Scheduled Email Digest Preferences
    email_weekly_briefing: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
    email_monthly_wrapped: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
    last_weekly_briefing_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_monthly_wrapped_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    refresh_tokens = relationship(
        "RefreshToken", back_populates="user", cascade="all, delete-orphan"
    )
    accounts = relationship("Account", back_populates="user", cascade="all, delete-orphan")
    categories = relationship("Category", back_populates="user", cascade="all, delete-orphan")


class RefreshToken(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "refresh_tokens"

    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="refresh_tokens")


class AIUsageEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_usage_events"
    __table_args__ = (Index("ix_ai_usage_user_created", "user_id", "created_at"),)

    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    feature: Mapped[str] = mapped_column(
        String(48), nullable=False
    )  # advisor_chat | document_ingestion | proactive_insights
    provider: Mapped[str] = mapped_column(String(32), default="openai", nullable=False)
    model: Mapped[str] = mapped_column(String(64), default="unknown", nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    user = relationship("User")
