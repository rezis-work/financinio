"""user_email_digests

Revision ID: 8c9d0e1f2a3b
Revises: 7b8c9d1e2f3a
Create Date: 2026-11-25 15:15:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8c9d0e1f2a3b"
down_revision: str | None = "7b8c9d1e2f3a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("email_weekly_briefing", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.add_column(
        "users",
        sa.Column("email_monthly_wrapped", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.add_column(
        "users",
        sa.Column("last_weekly_briefing_sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("last_monthly_wrapped_sent_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "last_monthly_wrapped_sent_at")
    op.drop_column("users", "last_weekly_briefing_sent_at")
    op.drop_column("users", "email_monthly_wrapped")
    op.drop_column("users", "email_weekly_briefing")
