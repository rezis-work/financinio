from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, JSONType, TimestampMixin, UUIDPrimaryKeyMixin, utcnow


class ChatThread(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "chat_threads"
    __table_args__ = (Index("ix_chat_threads_user_last", "user_id", "last_message_at"),)

    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    langgraph_thread_id: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), default="New Conversation", nullable=False)
    last_message_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    messages = relationship(
        "ChatMessage",
        back_populates="thread",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at.asc()",
    )


class ChatMessage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "chat_messages"
    __table_args__ = (Index("ix_chat_messages_thread_created", "thread_id", "created_at"),)

    thread_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("chat_threads.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # user | assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    active_agent: Mapped[str | None] = mapped_column(String(48), nullable=True)
    citations: Mapped[list[dict]] = mapped_column(JSONType, default=list, nullable=False)
    pending_action: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    action_status: Mapped[str] = mapped_column(
        String(16), default="none", nullable=False
    )  # none | pending | executed | rejected

    thread = relationship("ChatThread", back_populates="messages")


class ProactiveInsight(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "proactive_insights"
    __table_args__ = (Index("ix_insights_user_created", "user_id", "created_at"),)

    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    insight_type: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # anomaly | budget_alert | subscription_creep | weekly_digest | savings_tip
    severity: Mapped[str] = mapped_column(
        String(16), default="info", nullable=False
    )  # info | warning | alert
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_dismissed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
