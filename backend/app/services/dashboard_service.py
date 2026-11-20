from collections import defaultdict
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.finance import Account, Category, Transaction
from app.models.ingestion import ImportBatch
from app.models.user import User
from app.schemas.dashboard import (
    CategorySpendItem,
    DashboardSummaryResponse,
    MonthlyCashFlowPoint,
)
from app.schemas.transaction import TransactionResponse


def _month_shift(year: int, month: int, delta_months: int) -> tuple[int, int]:
    total = (year * 12 + (month - 1)) + delta_months
    return total // 12, (total % 12) + 1


async def get_dashboard_summary(
    db: AsyncSession,
    user: User,
    months: int = 6,
) -> DashboardSummaryResponse:
    today = date.today()
    period_start = date(today.year, today.month, 1)

    # 1. Accounts -> Assets / Liabilities / Net Worth
    accounts = (
        await db.scalars(
            select(Account).where(Account.user_id == user.id, Account.is_archived.is_(False))
        )
    ).all()

    total_assets = Decimal("0.00")
    total_liabilities = Decimal("0.00")
    for acc in accounts:
        bal = acc.current_balance
        if acc.type in ("credit", "loan"):
            if bal < 0:
                total_liabilities += abs(bal)
            else:
                total_assets += bal
        else:
            if bal >= 0:
                total_assets += bal
            else:
                total_liabilities += abs(bal)

    net_worth = total_assets - total_liabilities

    # 2. Fetch non-transfer transactions for the rolling window
    start_year, start_month = _month_shift(today.year, today.month, -(months - 1))
    window_start = date(start_year, start_month, 1)

    tx_rows = (
        await db.scalars(
            select(Transaction)
            .where(
                Transaction.user_id == user.id,
                Transaction.is_transfer.is_(False),
                Transaction.parent_transaction_id.is_(None),
                Transaction.occurred_at >= window_start,
            )
            .order_by(Transaction.occurred_at.desc(), Transaction.created_at.desc())
        )
    ).all()

    categories = {
        c.id: c
        for c in (await db.scalars(select(Category).where(Category.user_id == user.id))).all()
    }

    # Build monthly buckets
    month_keys: list[str] = []
    for offset in range(-(months - 1), 1):
        y, m = _month_shift(today.year, today.month, offset)
        month_keys.append(f"{y:04d}-{m:02d}")

    monthly_in: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    monthly_out: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))

    period_income = Decimal("0.00")
    period_expenses = Decimal("0.00")
    cat_totals: dict[UUID | None, Decimal] = defaultdict(lambda: Decimal("0.00"))
    cat_counts: dict[UUID | None, int] = defaultdict(int)

    for tx in tx_rows:
        m_key = tx.occurred_at.strftime("%Y-%m")
        if tx.direction == "inflow":
            monthly_in[m_key] += tx.base_amount
            if tx.occurred_at >= period_start:
                period_income += tx.base_amount
        else:
            monthly_out[m_key] += tx.base_amount
            if tx.occurred_at >= period_start:
                period_expenses += tx.base_amount
                cat_totals[tx.category_id] += tx.base_amount
                cat_counts[tx.category_id] += 1

    period_net = period_income - period_expenses
    savings_rate = (
        round(float(period_net / period_income) * 100.0, 1) if period_income > 0 else 0.0
    )

    monthly_cash_flow = [
        MonthlyCashFlowPoint(
            month=mk,
            income=monthly_in[mk],
            expenses=monthly_out[mk],
            net=monthly_in[mk] - monthly_out[mk],
        )
        for mk in month_keys
    ]

    # Category breakdown for current period (or fallback to full window if current month empty)
    if period_expenses == 0 and tx_rows:
        for tx in tx_rows:
            if tx.direction == "outflow":
                cat_totals[tx.category_id] += tx.base_amount
                cat_counts[tx.category_id] += 1

    total_cat_spend = sum(cat_totals.values(), Decimal("0.00"))
    category_breakdown: list[CategorySpendItem] = []
    for cid, total in sorted(cat_totals.items(), key=lambda kv: kv[1], reverse=True):
        cat = categories.get(cid) if cid else None
        pct = round(float(total / total_cat_spend) * 100.0, 1) if total_cat_spend > 0 else 0.0
        category_breakdown.append(
            CategorySpendItem(
                category_id=cid,
                category_name=cat.name if cat else "Uncategorized",
                color=cat.color if cat else "#94a3b8",
                total=total,
                percentage=pct,
                transaction_count=cat_counts[cid],
            )
        )

    # Recent transactions (all types, latest 8)
    recent = (
        await db.scalars(
            select(Transaction)
            .where(Transaction.user_id == user.id, Transaction.parent_transaction_id.is_(None))
            .order_by(Transaction.occurred_at.desc(), Transaction.created_at.desc())
            .limit(8)
        )
    ).all()

    pending_review_batches = (
        await db.scalar(
            select(func.count(ImportBatch.id)).where(
                ImportBatch.user_id == user.id,
                ImportBatch.status == "needs_review",
            )
        )
        or 0
    )

    return DashboardSummaryResponse(
        base_currency=user.base_currency,
        total_assets=total_assets,
        total_liabilities=total_liabilities,
        net_worth=net_worth,
        period_income=period_income,
        period_expenses=period_expenses,
        period_net=period_net,
        savings_rate=savings_rate,
        monthly_cash_flow=monthly_cash_flow,
        category_breakdown=category_breakdown[:8],
        recent_transactions=[TransactionResponse.model_validate(t) for t in recent],
        pending_review_batches=pending_review_batches,
    )
