import json
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from statistics import median

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.llm_factory import get_chat_model
from app.models.advisor import ProactiveInsight
from app.models.finance import Transaction
from app.models.user import User
from app.services.dashboard_service import get_dashboard_summary
from app.services.financial_health_service import compute_financial_health_profile
from app.services.planning_service import get_budget_overview, get_recurring_overview


async def generate_proactive_insights(
    db: AsyncSession,
    user: User,
    llm: BaseChatModel | None = None,
) -> list[ProactiveInsight]:
    """Run deterministic anomaly detection + budget/subscription alerts + AI Weekly Digest."""
    today = date.today()
    cutoff_90d = today - timedelta(days=90)
    cutoff_14d = today - timedelta(days=14)

    txs = (
        await db.scalars(
            select(Transaction)
            .where(
                Transaction.user_id == user.id,
                Transaction.direction == "outflow",
                Transaction.is_transfer.is_(False),
                Transaction.parent_transaction_id.is_(None),
                Transaction.occurred_at >= cutoff_90d,
            )
            .order_by(Transaction.occurred_at.desc())
        )
    ).all()

    new_insights: list[ProactiveInsight] = []

    # 1. Anomaly Detection: unusually large single outflow (>= 2.2x median & >= 75)
    if len(txs) >= 4:
        amounts = [float(t.base_amount) for t in txs]
        med = Decimal(str(median(amounts)))
        threshold = max(Decimal("75.00"), med * Decimal("2.2"))
        for tx in txs:
            if tx.occurred_at >= cutoff_14d and tx.base_amount >= threshold:
                new_insights.append(
                    ProactiveInsight(
                        user_id=user.id,
                        insight_type="anomaly",
                        severity="warning",
                        title=f"Unusually large charge at {tx.merchant_clean}",
                        summary=(
                            f"You spent {user.base_currency} {tx.base_amount:.2f} at {tx.merchant_clean} on "
                            f"{tx.occurred_at.isoformat()}, which is over 2.2x your typical transaction median "
                            f"({user.base_currency} {med:.2f})."
                        ),
                        data={
                            "transaction_id": str(tx.id),
                            "amount": f"{tx.base_amount:.2f}",
                            "median": f"{med:.2f}",
                        },
                    )
                )
                break  # keep top anomaly crisp

    # 2. Potential Duplicate Charge Detection (same merchant + exact amount within 2 days)
    by_merchant_amt: dict[tuple[str, Decimal], list[Transaction]] = defaultdict(list)
    for tx in txs:
        if tx.occurred_at >= cutoff_14d:
            by_merchant_amt[(tx.merchant_clean.lower(), tx.base_amount)].append(tx)

    for (_m, amt), group in by_merchant_amt.items():
        if len(group) >= 2:
            group_sorted = sorted(group, key=lambda t: t.occurred_at)
            if (group_sorted[-1].occurred_at - group_sorted[-2].occurred_at).days <= 2:
                new_insights.append(
                    ProactiveInsight(
                        user_id=user.id,
                        insight_type="anomaly",
                        severity="alert",
                        title=f"Possible duplicate charge: {group_sorted[-1].merchant_clean}",
                        summary=(
                            f"Two identical charges of {user.base_currency} {amt:.2f} appeared at "
                            f"{group_sorted[-1].merchant_clean} within 48 hours."
                        ),
                        data={"merchant": group_sorted[-1].merchant_clean, "amount": f"{amt:.2f}"},
                    )
                )
                break

    # 3. Budget Overrun / Pacing Alerts
    budgets = await get_budget_overview(db, user)
    for b in budgets.budgets:
        if b.status == "over_budget":
            new_insights.append(
                ProactiveInsight(
                    user_id=user.id,
                    insight_type="budget_alert",
                    severity="alert",
                    title=f"{b.category_name} is over budget",
                    summary=(
                        f"You've spent {user.base_currency} {b.spent:.2f} against your "
                        f"{user.base_currency} {b.effective_limit:.2f} limit ({b.percent_used}%)."
                    ),
                    data={"category": b.category_name, "percent_used": b.percent_used},
                )
            )
        elif b.status in ("warning", "pacing_fast"):
            new_insights.append(
                ProactiveInsight(
                    user_id=user.id,
                    insight_type="budget_alert",
                    severity="warning",
                    title=f"{b.category_name} pacing ahead ({b.percent_used}%)",
                    summary=(
                        f"You've used {b.percent_used}% of {b.category_name} with "
                        f"{budgets.days_in_month - budgets.days_elapsed} days left in the month."
                    ),
                    data={"category": b.category_name, "percent_used": b.percent_used},
                )
            )

    # 4. Subscription Price Hike Alerts
    recurring = await get_recurring_overview(db, user)
    for hike in recurring.price_hike_alerts[:2]:
        new_insights.append(
            ProactiveInsight(
                user_id=user.id,
                insight_type="subscription_creep",
                severity="warning",
                title=f"Price hike on {hike.merchant_name} (+{hike.price_change_pct}%)",
                summary=(
                    f"{hike.merchant_name} increased from {hike.currency} {hike.previous_amount} "
                    f"to {hike.currency} {hike.amount}."
                ),
                data={"merchant": hike.merchant_name, "change_pct": str(hike.price_change_pct)},
            )
        )

    # 5. Weekly AI Financial Digest (Senior CFO Diagnostic lens)
    dash = await get_dashboard_summary(db, user, months=3)
    health = await compute_financial_health_profile(db, user)
    digest_payload = {
        "base_currency": user.base_currency,
        "health_score": health["health_score"]["overall"],
        "health_grade": health["health_score"]["grade"],
        "top_priority": health["health_score"]["top_priority"],
        "emergency_runway_months": health["cash_flow_ratios"]["emergency_runway_months"],
        "net_worth": f"{dash.net_worth:.2f}",
        "month_income": f"{dash.period_income:.2f}",
        "month_expenses": f"{dash.period_expenses:.2f}",
        "savings_rate_pct": dash.savings_rate,
        "spending_leaks_mom": health["spending_leaks_mom"][:3],
        "top_categories": [
            {"name": c.category_name, "total": f"{c.total:.2f}", "pct": c.percentage}
            for c in dash.category_breakdown[:4]
        ],
        "monthly_recurring_burn": f"{recurring.monthly_recurring_expenses:.2f}",
    }

    model = llm if llm is not None else get_chat_model("fast", temperature=0.3)
    if model is not None:
        try:
            res = await model.ainvoke(
                [
                    SystemMessage(
                        content=(
                            "You are Luna, a Senior Financial Advisor & Personal CFO. Write a sharp, "
                            "executive 3-bullet financial digest in clean Markdown (**1 Key Win**, "
                            "**1 Risk / Spending Leak**, **1 High-Impact Action This Week**) using ONLY the exact verified numbers provided."
                        )
                    ),
                    HumanMessage(content=json.dumps(digest_payload)),
                ]
            )
            digest_text = str(res.content)
        except Exception:
            digest_text = _fallback_digest_text(digest_payload)
    else:
        digest_text = _fallback_digest_text(digest_payload)

    new_insights.insert(
        0,
        ProactiveInsight(
            user_id=user.id,
            insight_type="weekly_digest",
            severity="info",
            title=f"Luna's Financial Digest ({today.strftime('%b %d')})",
            summary=digest_text,
            data=digest_payload,
        ),
    )

    db.add_all(new_insights)
    await db.commit()
    for item in new_insights:
        await db.refresh(item)
    return new_insights


def _fallback_digest_text(d: dict) -> str:
    ccy = d["base_currency"]
    return (
        f"Net worth stands at {ccy} {d['net_worth']} with a {d['savings_rate_pct']}% savings rate this month "
        f"({ccy} {d['month_income']} income vs. {ccy} {d['month_expenses']} expenses). "
        f"Recurring commitments total {ccy} {d['monthly_recurring_burn']}/mo."
    )
