from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, JSONType, TimestampMixin, UUIDPrimaryKeyMixin


class Budget(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "budgets"
    __table_args__ = (
        UniqueConstraint("user_id", "category_id", "period", name="uq_budgets_user_cat_period"),
        Index("ix_budgets_user_active", "user_id", "is_active"),
    )

    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    category_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("categories.id", ondelete="CASCADE"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    period: Mapped[str] = mapped_column(
        String(16), default="monthly", nullable=False
    )  # monthly | quarterly | yearly
    rollover: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    alert_threshold_pct: Mapped[int] = mapped_column(Integer, default=80, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    category = relationship("Category")


class RecurringItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "recurring_items"
    __table_args__ = (Index("ix_recurring_user_due", "user_id", "next_due_date"),)

    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )
    category_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    merchant_name: Mapped[str] = mapped_column(String(160), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    previous_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    direction: Mapped[str] = mapped_column(
        String(16), default="outflow", nullable=False
    )  # outflow | inflow
    cadence: Mapped[str] = mapped_column(
        String(16), default="monthly", nullable=False
    )  # weekly | biweekly | monthly | quarterly | yearly
    next_due_date: Mapped[date] = mapped_column(Date, nullable=False)
    last_seen_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_subscription: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    auto_detected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    price_change_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)

    category = relationship("Category")


class NetWorthSnapshot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "net_worth_snapshots"
    __table_args__ = (
        UniqueConstraint("user_id", "snapshot_date", name="uq_nw_snapshots_user_date"),
        Index("ix_nw_snapshots_user_date", "user_id", "snapshot_date"),
    )

    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    total_assets: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    total_liabilities: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    net_worth: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    breakdown: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)


class FinancialGoal(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "financial_goals"
    __table_args__ = (Index("ix_goals_user_completed", "user_id", "is_completed"),)

    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    linked_account_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    goal_type: Mapped[str] = mapped_column(
        String(32), default="savings", nullable=False
    )  # emergency_fund | savings | debt_payoff | investment | purchase | retirement
    target_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    current_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0.00"), nullable=False
    )
    monthly_contribution: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0.00"), nullable=False
    )
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    color: Mapped[str] = mapped_column(String(16), default="#10b981", nullable=False)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
