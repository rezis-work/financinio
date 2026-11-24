from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utcnow


class MarketWatchlistItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "market_watchlist_items"
    __table_args__ = (
        UniqueConstraint("user_id", "symbol", name="uq_watchlist_user_symbol"),
        Index("ix_watchlist_user", "user_id"),
    )

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    symbol: Mapped[str] = mapped_column(String(24), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(20), default="stock", nullable=False)
    target_buy_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    target_sell_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    alert_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class PaperPortfolio(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "paper_portfolios"
    __table_args__ = (UniqueConstraint("user_id", name="uq_paper_portfolio_user"),)

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    starting_cash: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("10000.00"), nullable=False
    )
    cash_balance: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("10000.00"), nullable=False
    )
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    risk_profile: Mapped[str] = mapped_column(String(20), default="balanced", nullable=False)


class PaperPosition(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "paper_positions"
    __table_args__ = (
        UniqueConstraint("portfolio_id", "symbol", name="uq_paper_position_portfolio_symbol"),
        Index("ix_paper_position_user", "user_id"),
    )

    portfolio_id: Mapped[UUID] = mapped_column(
        ForeignKey("paper_portfolios.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    symbol: Mapped[str] = mapped_column(String(24), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(20), default="stock", nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    avg_entry_price: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    stop_loss: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    take_profit: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)


class PaperTrade(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "paper_trades"
    __table_args__ = (Index("ix_paper_trade_user_exec", "user_id", "executed_at"),)

    portfolio_id: Mapped[UUID] = mapped_column(
        ForeignKey("paper_portfolios.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    symbol: Mapped[str] = mapped_column(String(24), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(20), default="stock", nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)  # buy | sell
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    total_value: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    realized_pnl: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    signal_at_trade: Mapped[str | None] = mapped_column(String(24), nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
