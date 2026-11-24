from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.finance import Account, Category, Transaction
from app.models.planning import FinancialGoal
from app.models.user import User
from app.services.planning_service import (
    enrich_goal,
    get_budget_overview,
    get_recurring_overview,
)


def _d(val: Decimal) -> str:
    return f"{val.quantize(Decimal('0.01')):.2f}"


async def compute_financial_health_profile(db: AsyncSession, user: User) -> dict[str, Any]:
    """Compute a comprehensive, deterministic Senior CFP financial health diagnostic.

    All metrics are computed strictly from the user's verified Neon ledger — zero LLM math.
    """
    today = date.today()
    month_start = date(today.year, today.month, 1)
    prev_month_end = month_start - timedelta(days=1)
    prev_month_start = date(prev_month_end.year, prev_month_end.month, 1)
    start_90d = today - timedelta(days=90)

    accounts = (
        await db.scalars(
            select(Account).where(Account.user_id == user.id, Account.is_archived.is_(False))
        )
    ).all()
    categories = {
        c.id: c.name
        for c in (await db.scalars(select(Category).where(Category.user_id == user.id))).all()
    }
    txs = (
        await db.scalars(
            select(Transaction)
            .where(
                Transaction.user_id == user.id,
                Transaction.is_transfer.is_(False),
                Transaction.parent_transaction_id.is_(None),
                Transaction.occurred_at >= start_90d,
            )
            .order_by(Transaction.occurred_at.desc())
        )
    ).all()

    # 1. Balance sheet classification
    liquid_cash = Decimal("0.00")  # checking + savings + cash
    invested_assets = Decimal("0.00")
    total_assets = Decimal("0.00")
    total_debt = Decimal("0.00")
    credit_card_debt = Decimal("0.00")

    for acc in accounts:
        bal = acc.current_balance
        if bal < 0:
            total_debt += abs(bal)
            if acc.type == "credit":
                credit_card_debt += abs(bal)
        else:
            total_assets += bal
            if acc.type in ("checking", "savings", "cash"):
                liquid_cash += bal
            elif acc.type == "investment":
                invested_assets += bal

    net_worth = total_assets - total_debt

    # 2. Cash flow velocity (90d rolling + MTD vs Prior Month)
    total_in_90d = Decimal("0.00")
    total_out_90d = Decimal("0.00")
    mtd_in = Decimal("0.00")
    mtd_out = Decimal("0.00")
    prev_out = Decimal("0.00")

    cat_mtd: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    cat_prev: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    cat_90d: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    merchant_90d: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    merchant_counts_90d: dict[str, int] = defaultdict(int)

    for tx in txs:
        cname = categories.get(tx.category_id, "Uncategorized") if tx.category_id else "Uncategorized"
        if tx.direction == "inflow":
            total_in_90d += tx.base_amount
            if tx.occurred_at >= month_start:
                mtd_in += tx.base_amount
        else:
            total_out_90d += tx.base_amount
            cat_90d[cname] += tx.base_amount
            merchant_90d[tx.merchant_clean] += tx.base_amount
            merchant_counts_90d[tx.merchant_clean] += 1
            if tx.occurred_at >= month_start:
                mtd_out += tx.base_amount
                cat_mtd[cname] += tx.base_amount
            elif prev_month_start <= tx.occurred_at <= prev_month_end:
                prev_out += tx.base_amount
                cat_prev[cname] += tx.base_amount

    # Determine active months of data in window (avoid under-dividing brand-new users)
    months_observed = max(1, len({tx.occurred_at.strftime("%Y-%m") for tx in txs}))
    avg_monthly_income = (total_in_90d / Decimal(str(months_observed))).quantize(Decimal("0.01"))
    avg_monthly_expenses = (total_out_90d / Decimal(str(months_observed))).quantize(Decimal("0.01"))
    avg_monthly_surplus = avg_monthly_income - avg_monthly_expenses

    savings_rate_pct = (
        round(float(avg_monthly_surplus / avg_monthly_income) * 100.0, 1)
        if avg_monthly_income > 0
        else 0.0
    )

    emergency_runway_months = (
        round(float(liquid_cash / avg_monthly_expenses), 1)
        if avg_monthly_expenses > 0
        else (12.0 if liquid_cash > 0 else 0.0)
    )

    # 3. Budgets, Recurring & Goals
    budgets = await get_budget_overview(db, user)
    recurring = await get_recurring_overview(db, user)
    goals_rows = (
        await db.scalars(select(FinancialGoal).where(FinancialGoal.user_id == user.id))
    ).all()
    goals = [enrich_goal(g) for g in goals_rows]
    total_goal_monthly = sum((g.monthly_contribution for g in goals if not g.is_completed), Decimal("0.00"))

    fixed_obligation_ratio_pct = (
        round(float(recurring.monthly_recurring_expenses / avg_monthly_income) * 100.0, 1)
        if avg_monthly_income > 0
        else 0.0
    )

    # Safe-to-spend remaining this month
    expected_income_this_month = max(mtd_in, avg_monthly_income)
    safe_to_spend_remaining = (
        expected_income_this_month - mtd_out - total_goal_monthly
    ).quantize(Decimal("0.01"))

    # Category MoM spikes (potential spending leaks)
    spending_leaks: list[dict[str, Any]] = []
    for cname, cur_amt in sorted(cat_mtd.items(), key=lambda x: x[1], reverse=True):
        prev_amt = cat_prev.get(cname, Decimal("0.00"))
        if prev_amt > Decimal("25.00") and cur_amt > prev_amt * Decimal("1.15"):
            pct_up = round(float((cur_amt - prev_amt) / prev_amt) * 100.0, 1)
            spending_leaks.append(
                {
                    "category": cname,
                    "current_month": _d(cur_amt),
                    "previous_month": _d(prev_amt),
                    "increase_pct": pct_up,
                }
            )

    # High-frequency discretionary merchants (e.g. >= 4 charges in 90d)
    frequent_merchants = [
        {
            "merchant": m,
            "total_90d": _d(amt),
            "visits_90d": merchant_counts_90d[m],
            "monthly_avg": _d(amt / Decimal(str(months_observed))),
        }
        for m, amt in sorted(merchant_90d.items(), key=lambda x: x[1], reverse=True)[:6]
    ]

    # 4. Compute 0–100 Financial Health Score across 4 CFP pillars
    # Pillar A: Cash Flow & Savings Rate (0-30 pts)
    if avg_monthly_income == 0 and avg_monthly_expenses == 0:
        cashflow_score = 15
    elif savings_rate_pct >= 25:
        cashflow_score = 30
    elif savings_rate_pct >= 20:
        cashflow_score = 27
    elif savings_rate_pct >= 10:
        cashflow_score = 20
    elif savings_rate_pct > 0:
        cashflow_score = 12
    else:
        cashflow_score = 4

    # Pillar B: Emergency Runway (0-25 pts) — benchmark 6 months
    if emergency_runway_months >= 6:
        runway_score = 25
    elif emergency_runway_months >= 3:
        runway_score = 19
    elif emergency_runway_months >= 1:
        runway_score = 11
    else:
        runway_score = 3

    # Pillar C: Debt Health (0-25 pts)
    if total_debt == 0:
        debt_score = 25
    elif credit_card_debt == 0 and total_debt <= total_assets * Decimal("0.5"):
        debt_score = 20
    elif credit_card_debt <= liquid_cash * Decimal("0.3"):
        debt_score = 14
    else:
        debt_score = 6

    # Pillar D: Budget Discipline & Goals (0-20 pts)
    over_budget_count = sum(1 for b in budgets.budgets if b.status == "over_budget")
    discipline_score = 10
    if budgets.budgets:
        discipline_score = max(4, 14 - over_budget_count * 4)
    if goals:
        discipline_score = min(20, discipline_score + 6)

    overall_score = min(100, cashflow_score + runway_score + debt_score + discipline_score)
    if overall_score >= 80:
        grade = "Excellent"
    elif overall_score >= 65:
        grade = "Strong"
    elif overall_score >= 45:
        grade = "Fair — Needs Attention"
    else:
        grade = "At Risk — Action Needed"

    # Prioritized deterministic top recommendation
    if credit_card_debt > Decimal("500.00") and emergency_runway_months >= 1:
        top_priority = (
            f"Eliminate {user.base_currency} {_d(credit_card_debt)} in high-APR credit card debt "
            f"using the Avalanche method before increasing discretionary spend."
        )
    elif emergency_runway_months < 3 and avg_monthly_expenses > 0:
        target_3m = avg_monthly_expenses * Decimal("3")
        gap = max(Decimal("0.00"), target_3m - liquid_cash)
        top_priority = (
            f"Build your emergency fund from {emergency_runway_months} mo to 3 months "
            f"({user.base_currency} {_d(gap)} gap)."
        )
    elif over_budget_count > 0:
        over_names = ", ".join(b.category_name for b in budgets.budgets if b.status == "over_budget")
        top_priority = f"Rebalance over-budget categories ({over_names}) to protect your monthly savings rate."
    elif savings_rate_pct < 20 and avg_monthly_income > 0:
        top_priority = (
            f"Boost your savings rate from {savings_rate_pct}% toward the 20% benchmark by trimming "
            f"top discretionary categories."
        )
    else:
        top_priority = (
            f"Strong fundamentals ({savings_rate_pct}% savings rate, {emergency_runway_months} mo runway) — "
            f"automate surplus into long-term wealth goals or investments."
        )

    return {
        "as_of": today.isoformat(),
        "base_currency": user.base_currency,
        "health_score": {
            "overall": overall_score,
            "grade": grade,
            "pillars": {
                "cash_flow_and_savings": {"score": cashflow_score, "max": 30},
                "emergency_runway": {"score": runway_score, "max": 25},
                "debt_health": {"score": debt_score, "max": 25},
                "budget_and_goals": {"score": discipline_score, "max": 20},
            },
            "top_priority": top_priority,
        },
        "balance_sheet": {
            "liquid_cash": _d(liquid_cash),
            "invested_assets": _d(invested_assets),
            "total_assets": _d(total_assets),
            "total_debt": _d(total_debt),
            "credit_card_debt": _d(credit_card_debt),
            "net_worth": _d(net_worth),
        },
        "cash_flow_ratios": {
            "months_analyzed": months_observed,
            "avg_monthly_income": _d(avg_monthly_income),
            "avg_monthly_expenses": _d(avg_monthly_expenses),
            "avg_monthly_surplus": _d(avg_monthly_surplus),
            "savings_rate_pct": savings_rate_pct,
            "emergency_runway_months": emergency_runway_months,
            "fixed_recurring_ratio_pct": fixed_obligation_ratio_pct,
            "monthly_recurring_burn": _d(recurring.monthly_recurring_expenses),
            "safe_to_spend_remaining_this_month": _d(safe_to_spend_remaining),
            "mtd_income": _d(mtd_in),
            "mtd_expenses": _d(mtd_out),
            "prev_month_expenses": _d(prev_out),
        },
        "spending_leaks_mom": spending_leaks[:5],
        "top_categories_90d": {
            k: _d(v) for k, v in sorted(cat_90d.items(), key=lambda x: x[1], reverse=True)[:8]
        },
        "frequent_merchants_90d": frequent_merchants,
        "over_budget_categories": [
            {
                "category": b.category_name,
                "spent": _d(b.spent),
                "limit": _d(b.effective_limit),
                "percent_used": b.percent_used,
            }
            for b in budgets.budgets
            if b.status in ("over_budget", "warning", "pacing_fast")
        ],
        "subscription_price_hikes": [
            {
                "merchant": h.merchant_name,
                "previous": _d(h.previous_amount) if h.previous_amount else None,
                "current": _d(h.amount),
                "increase_pct": str(h.price_change_pct),
            }
            for h in recurring.price_hike_alerts
        ],
        "active_goals_count": sum(1 for g in goals if not g.is_completed),
        "total_goal_monthly_commitment": _d(total_goal_monthly),
    }


def evaluate_purchase_decision(
    profile: dict[str, Any],
    *,
    amount: Decimal,
    is_recurring_monthly: bool = False,
) -> dict[str, Any]:
    """Deterministic affordability & opportunity-cost analysis for a spending decision."""
    bs = profile["balance_sheet"]
    cf = profile["cash_flow_ratios"]

    liquid_cash = Decimal(bs["liquid_cash"])
    avg_income = Decimal(cf["avg_monthly_income"])
    avg_expenses = Decimal(cf["avg_monthly_expenses"])
    avg_surplus = Decimal(cf["avg_monthly_surplus"])
    cc_debt = Decimal(bs["credit_card_debt"])

    verdict: Literal["AFFORDABLE", "PROCEED_WITH_CAUTION", "HOLD_OFF"] = "AFFORDABLE"
    reasons: list[str] = []

    if is_recurring_monthly:
        new_expenses = avg_expenses + amount
        new_surplus = avg_income - new_expenses
        new_savings_rate = (
            round(float(new_surplus / avg_income) * 100.0, 1) if avg_income > 0 else 0.0
        )
        new_runway = round(float(liquid_cash / new_expenses), 1) if new_expenses > 0 else 0.0
        annual_cost = amount * Decimal("12")
        # 5-year compounded opportunity cost at 7% annual return (monthly contributions)
        r = Decimal("0.07") / Decimal("12")
        opp_cost_5y = (amount * (((Decimal("1") + r) ** 60 - Decimal("1")) / r)).quantize(
            Decimal("0.01")
        )

        if new_surplus < 0:
            verdict = "HOLD_OFF"
            reasons.append("This monthly commitment would push your monthly cash flow negative.")
        elif new_savings_rate < 10.0 or new_runway < 3.0:
            verdict = "PROCEED_WITH_CAUTION"
            reasons.append(
                f"Leaves a thin savings rate ({new_savings_rate}%) or under 3 months of runway ({new_runway} mo)."
            )
        else:
            reasons.append(
                f"Fits cleanly within your monthly cash flow (new savings rate: {new_savings_rate}%)."
            )

        return {
            "decision_type": "recurring_monthly",
            "proposed_monthly_cost": _d(amount),
            "annual_cost": _d(annual_cost),
            "verdict": verdict,
            "reasons": reasons,
            "new_monthly_surplus": _d(new_surplus),
            "new_savings_rate_pct": new_savings_rate,
            "new_emergency_runway_months": new_runway,
            "five_year_opportunity_cost_at_7pct": _d(opp_cost_5y),
        }

    # One-time purchase evaluation
    post_cash = liquid_cash - amount
    post_runway = round(float(max(Decimal("0"), post_cash) / avg_expenses), 1) if avg_expenses > 0 else 0.0
    pct_of_liquid = round(float(amount / liquid_cash) * 100.0, 1) if liquid_cash > 0 else 100.0
    months_of_surplus = round(float(amount / avg_surplus), 1) if avg_surplus > 0 else None
    opp_cost_5y = (amount * (Decimal("1.07") ** 5)).quantize(Decimal("0.01"))

    if post_cash < 0:
        verdict = "HOLD_OFF"
        reasons.append("Exceeds your available liquid cash — would require taking on debt.")
    elif post_runway < 2.0 and avg_expenses > 0:
        verdict = "HOLD_OFF"
        reasons.append(f"Would drop your emergency runway to {post_runway} months (below 3-month floor).")
    elif cc_debt > Decimal("500.00") and amount > Decimal("250.00"):
        verdict = "PROCEED_WITH_CAUTION"
        reasons.append(f"You carry {profile['base_currency']} {_d(cc_debt)} in credit card debt.")
    elif post_runway < 3.0 or pct_of_liquid > 25.0:
        verdict = "PROCEED_WITH_CAUTION"
        reasons.append(
            f"Uses {pct_of_liquid}% of liquid cash and leaves {post_runway} months of emergency runway."
        )
    else:
        reasons.append(
            f"Well-cushioned: leaves {profile['base_currency']} {_d(post_cash)} liquid ({post_runway} months runway)."
        )

    return {
        "decision_type": "one_time_purchase",
        "proposed_amount": _d(amount),
        "verdict": verdict,
        "reasons": reasons,
        "liquid_cash_before": _d(liquid_cash),
        "liquid_cash_after": _d(post_cash),
        "pct_of_liquid_cash": pct_of_liquid,
        "emergency_runway_after_months": post_runway,
        "months_of_surplus_to_recoup": months_of_surplus,
        "five_year_opportunity_cost_at_7pct": _d(opp_cost_5y),
    }
