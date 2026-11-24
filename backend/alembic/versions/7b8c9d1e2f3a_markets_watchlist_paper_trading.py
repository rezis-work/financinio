"""markets_watchlist_paper_trading

Revision ID: 7b8c9d1e2f3a
Revises: 6404066de411
Create Date: 2026-11-24 19:42:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7b8c9d1e2f3a"
down_revision: str | None = "6404066de411"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "market_watchlist_items",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("symbol", sa.String(length=24), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("asset_type", sa.String(length=20), nullable=False, server_default="stock"),
        sa.Column("target_buy_price", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("target_sell_price", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("alert_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "symbol", name="uq_watchlist_user_symbol"),
    )
    op.create_index("ix_watchlist_user", "market_watchlist_items", ["user_id"], unique=False)

    op.create_table(
        "paper_portfolios",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "starting_cash",
            sa.Numeric(precision=14, scale=2),
            nullable=False,
            server_default="10000.00",
        ),
        sa.Column(
            "cash_balance",
            sa.Numeric(precision=14, scale=2),
            nullable=False,
            server_default="10000.00",
        ),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column("risk_profile", sa.String(length=20), nullable=False, server_default="balanced"),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_paper_portfolio_user"),
    )

    op.create_table(
        "paper_positions",
        sa.Column("portfolio_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("symbol", sa.String(length=24), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("asset_type", sa.String(length=20), nullable=False, server_default="stock"),
        sa.Column("quantity", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("avg_entry_price", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("stop_loss", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("take_profit", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["portfolio_id"], ["paper_portfolios.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("portfolio_id", "symbol", name="uq_paper_position_portfolio_symbol"),
    )
    op.create_index("ix_paper_position_user", "paper_positions", ["user_id"], unique=False)

    op.create_table(
        "paper_trades",
        sa.Column("portfolio_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("symbol", sa.String(length=24), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("asset_type", sa.String(length=20), nullable=False, server_default="stock"),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("price", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("total_value", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("realized_pnl", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("signal_at_trade", sa.String(length=24), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["portfolio_id"], ["paper_portfolios.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_paper_trade_user_exec", "paper_trades", ["user_id", "executed_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_paper_trade_user_exec", table_name="paper_trades")
    op.drop_table("paper_trades")
    op.drop_index("ix_paper_position_user", table_name="paper_positions")
    op.drop_table("paper_positions")
    op.drop_table("paper_portfolios")
    op.drop_index("ix_watchlist_user", table_name="market_watchlist_items")
    op.drop_table("market_watchlist_items")
