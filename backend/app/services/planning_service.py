import calendar
import math
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from statistics import median
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.finance import Account, Category, Transaction
from app.models.planning import Budget, FinancialGoal, NetWorthSnapshot, RecurringItem
from app.models.user import User
from app.schemas.planning import (
    BudgetOverviewResponse,
    BudgetStatusResponse,
    DebtInput,
    DebtPayoffComparisonResponse,
    DebtPayoffRequest,
    DebtStrategyResult,
    DetectRecurringResponse,
    GoalResponse,
    NetWorthAccountBreakdown,
    NetWorthOverviewResponse,
    NetWorthSnapshotResponse,
    RecurringItemResponse,
    RecurringOverviewResponse,
    WhatIfPoint,
    WhatIfRequest,
    WhatIfResponse,
)

CADENCE_TO_MONTHLY_MULTIPLIER: dict[str, Decimal] = {
    "weekly": Decimal("4.3333"),
    "biweekly": Decimal("2.1667"),
    "monthly": Decimal("1.0000"),
    "quarterly": Decimal("0.3333"),
    "yearly": Decimal("0.0833"),
}

CADENCE_TO_DAYS: dict[str, int] = {
    "weekly": 7,
    "biweekly": 14,
    "monthly": 30,
    "quarterly": 91,
    "yearly": 365,
}


def _month_bounds(year: int, month: int) -> tuple[date, date, int]:
    days_in_month = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, days_in_month), days_in_month


def _prev_month(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


# --- Budgets ---


async def get_budget_overview(
    db: AsyncSession,
    user: User,
    target_month: str | None = None,
) -> BudgetOverviewResponse:
    today = date.today()
    if target_month:
        parts = target_month.split("-")
        year, month = int(parts[0]), int(parts[1])
    else:
        year, month = today.year, today.month

    month_start, month_end, days_in_month = _month_bounds(year, month)
    if (year, month) == (today.year, today.month):
        days_elapsed = today.day
    elif date(year, month, 1) < date(today.year, today.month, 1):
        days_elapsed = days_in_month
    else:
        days_elapsed = 0

    pace_pct = round((days_elapsed / days_in_month) * 100.0, 1) if days_in_month > 0 else 0.0

    budgets = (
        await db.scalars(
            select(Budget)
            .options(selectinload(Budget.category))
            .where(Budget.user_id == user.id, Budget.is_active.is_(True))
            .order_by(Budget.created_at.asc())
        )
    ).all()

    prev_y, prev_m = _prev_month(year, month)
    prev_start, prev_end, _ = _month_bounds(prev_y, prev_m)

    txs = (
        await db.scalars(
            select(Transaction).where(
                Transaction.user_id == user.id,
                Transaction.direction == "outflow",
                Transaction.is_transfer.is_(False),
                Transaction.parent_transaction_id.is_(None),
                Transaction.occurred_at >= prev_start,
                Transaction.occurred_at <= month_end,
            )
        )
    ).all()

    curr_spend_by_cat: dict[UUID, Decimal] = defaultdict(lambda: Decimal("0.00"))
    prev_spend_by_cat: dict[UUID, Decimal] = defaultdict(lambda: Decimal("0.00"))

    for tx in txs:
        if tx.category_id is None:
            continue
        if month_start <= tx.occurred_at <= month_end:
            curr_spend_by_cat[tx.category_id] += tx.base_amount
        elif prev_start <= tx.occurred_at <= prev_end:
            prev_spend_by_cat[tx.category_id] += tx.base_amount

    items: list[BudgetStatusResponse] = []
    total_budgeted = Decimal("0.00")
    total_spent = Decimal("0.00")

    for b in budgets:
        monthly_amount = b.amount
        if b.period == "quarterly":
            monthly_amount = (b.amount / Decimal("3")).quantize(Decimal("0.01"))
        elif b.period == "yearly":
            monthly_amount = (b.amount / Decimal("12")).quantize(Decimal("0.01"))

        rollover_carry = Decimal("0.00")
        if b.rollover:
            prev_spent = prev_spend_by_cat.get(b.category_id, Decimal("0.00"))
            unspent = monthly_amount - prev_spent
            if unspent > 0:
                rollover_carry = unspent.quantize(Decimal("0.01"))

        effective_limit = (monthly_amount + rollover_carry).quantize(Decimal("0.01"))
        spent = curr_spend_by_cat.get(b.category_id, Decimal("0.00")).quantize(Decimal("0.01"))
        remaining = (effective_limit - spent).quantize(Decimal("0.01"))
        pct_used = round(float(spent / effective_limit) * 100.0, 1) if effective_limit > 0 else 0.0

        if spent > effective_limit:
            status_val = "over_budget"
        elif pct_used >= b.alert_threshold_pct:
            status_val = "warning"
        elif days_elapsed >= 4 and pct_used > pace_pct + 12.0:
            status_val = "pacing_fast"
        else:
            status_val = "on_track"

        total_budgeted += effective_limit
        total_spent += spent

        items.append(
            BudgetStatusResponse(
                id=b.id,
                category_id=b.category_id,
                category_name=b.category.name if b.category else "Category",
                category_color=b.category.color if b.category else "#6366f1",
                period=b.period,  # type: ignore[arg-type]
                amount=b.amount,
                rollover=b.rollover,
                rollover_carry=rollover_carry,
                effective_limit=effective_limit,
                spent=spent,
                remaining=remaining,
                percent_used=pct_used,
                pace_pct=pace_pct,
                alert_threshold_pct=b.alert_threshold_pct,
                status=status_val,  # type: ignore[arg-type]
                is_active=b.is_active,
            )
        )

    return BudgetOverviewResponse(
        month=f"{year:04d}-{month:02d}",
        days_elapsed=days_elapsed,
        days_in_month=days_in_month,
        pace_pct=pace_pct,
        total_budgeted=total_budgeted.quantize(Decimal("0.01")),
        total_spent=total_spent.quantize(Decimal("0.01")),
        total_remaining=(total_budgeted - total_spent).quantize(Decimal("0.01")),
        budgets=items,
    )


async def apply_50_30_20_template(
    db: AsyncSession,
    user: User,
    monthly_income: Decimal,
) -> BudgetOverviewResponse:
    """Apply a smart 50/30/20 allocation across the user's standard expense categories."""
    allocations: list[tuple[str, Decimal]] = [
        # Needs (50%)
        ("Housing & Rent", Decimal("0.28")),
        ("Groceries", Decimal("0.10")),
        ("Utilities & Internet", Decimal("0.05")),
        ("Transportation & Transit", Decimal("0.05")),
        ("Healthcare & Pharmacy", Decimal("0.02")),
        # Wants (30%)
        ("Dining & Coffee", Decimal("0.10")),
        ("Shopping & Retail", Decimal("0.08")),
        ("Entertainment & Leisure", Decimal("0.06")),
        ("Subscriptions & Software", Decimal("0.03")),
        ("Travel & Lodging", Decimal("0.03")),
    ]

    categories = {
        c.name.lower(): c
        for c in (await db.scalars(select(Category).where(Category.user_id == user.id))).all()
    }
    existing = {
        b.category_id: b
        for b in (
            await db.scalars(
                select(Budget).where(Budget.user_id == user.id, Budget.period == "monthly")
            )
        ).all()
    }

    for cat_name, weight in allocations:
        cat = categories.get(cat_name.lower())
        if cat is None:
            continue
        amt = (monthly_income * weight).quantize(Decimal("0.01"))
        if amt <= 0:
            continue
        if cat.id in existing:
            existing[cat.id].amount = amt
            existing[cat.id].is_active = True
        else:
            db.add(
                Budget(
                    user_id=user.id,
                    category_id=cat.id,
                    amount=amt,
                    period="monthly",
                    rollover=False,
                    alert_threshold_pct=80,
                )
            )

    await db.commit()
    return await get_budget_overview(db, user)


# --- Recurring Bills & Subscription Detector ---


def _recurring_to_response(item: RecurringItem) -> RecurringItemResponse:
    mult = CADENCE_TO_MONTHLY_MULTIPLIER.get(item.cadence, Decimal("1.0"))
    monthly_eq = (item.amount * mult).quantize(Decimal("0.01"))
    resp = RecurringItemResponse.model_validate(item)
    resp.monthly_equivalent = monthly_eq
    return resp


async def get_recurring_overview(db: AsyncSession, user: User) -> RecurringOverviewResponse:
    rows = (
        await db.scalars(
            select(RecurringItem)
            .where(RecurringItem.user_id == user.id)
            .order_by(RecurringItem.is_active.desc(), RecurringItem.next_due_date.asc())
        )
    ).all()

    today = date.today()
    horizon = today + timedelta(days=30)

    items = [_recurring_to_response(r) for r in rows]
    monthly_exp = Decimal("0.00")
    monthly_inc = Decimal("0.00")
    upcoming_30d = Decimal("0.00")
    price_hikes: list[RecurringItemResponse] = []

    for it in items:
        if not it.is_active:
            continue
        if it.direction == "outflow":
            monthly_exp += it.monthly_equivalent
            if today <= it.next_due_date <= horizon:
                upcoming_30d += it.amount
            if it.price_change_pct is not None and it.price_change_pct > Decimal("1.00"):
                price_hikes.append(it)
        else:
            monthly_inc += it.monthly_equivalent

    return RecurringOverviewResponse(
        monthly_recurring_expenses=monthly_exp.quantize(Decimal("0.01")),
        annual_recurring_expenses=(monthly_exp * Decimal("12")).quantize(Decimal("0.01")),
        monthly_recurring_income=monthly_inc.quantize(Decimal("0.01")),
        upcoming_30d_total=upcoming_30d.quantize(Decimal("0.01")),
        price_hike_alerts=price_hikes,
        items=items,
    )


def _classify_cadence(median_days: float) -> str | None:
    if 6 <= median_days <= 8:
        return "weekly"
    if 12 <= median_days <= 16:
        return "biweekly"
    if 26 <= median_days <= 35:
        return "monthly"
    if 80 <= median_days <= 100:
        return "quarterly"
    if 350 <= median_days <= 380:
        return "yearly"
    return None


async def detect_recurring_from_ledger(db: AsyncSession, user: User) -> DetectRecurringResponse:
    """Scan transaction history to detect recurring bills, subscriptions, and price hikes."""
    cutoff = date.today() - timedelta(days=365)
    txs = (
        await db.scalars(
            select(Transaction)
            .where(
                Transaction.user_id == user.id,
                Transaction.is_transfer.is_(False),
                Transaction.parent_transaction_id.is_(None),
                Transaction.occurred_at >= cutoff,
            )
            .order_by(Transaction.occurred_at.asc())
        )
    ).all()

    grouped: dict[tuple[str, str], list[Transaction]] = defaultdict(list)
    for tx in txs:
        key = (tx.merchant_clean.lower().strip(), tx.direction)
        if key[0]:
            grouped[key].append(tx)

    existing_rows = (
        await db.scalars(select(RecurringItem).where(RecurringItem.user_id == user.id))
    ).all()
    existing_by_key = {(r.merchant_name.lower().strip(), r.direction): r for r in existing_rows}

    detected_new = 0
    updated_existing = 0
    price_hikes_found = 0
    today = date.today()

    for (m_key, direction), group in grouped.items():
        if len(group) < 2:
            continue
        # Deduplicate same-day charges when computing intervals
        unique_dates = sorted({t.occurred_at for t in group})
        if len(unique_dates) < 2:
            continue

        deltas = [(unique_dates[i] - unique_dates[i - 1]).days for i in range(1, len(unique_dates))]
        med_delta = median(deltas)
        cadence = _classify_cadence(med_delta)
        if cadence is None:
            continue

        # Check interval consistency (allow slight weekend/month-length drift)
        if any(abs(d - med_delta) > max(6, med_delta * 0.25) for d in deltas):
            continue

        latest = group[-1]
        prior_amounts = [t.amount for t in group[:-1]]
        prior_med = Decimal(str(median([float(a) for a in prior_amounts]))).quantize(Decimal("0.01"))

        # Must be reasonably stable in amount (within 40% variance — catches price hikes while ignoring random shopping)
        if prior_med > 0:
            ratio_diff = abs(latest.amount - prior_med) / prior_med
            if ratio_diff > Decimal("0.45"):
                continue

        price_change_pct: Decimal | None = None
        previous_amount: Decimal | None = None
        if prior_med > 0 and latest.amount != prior_med:
            pct = ((latest.amount - prior_med) / prior_med * Decimal("100")).quantize(Decimal("0.01"))
            if abs(pct) >= Decimal("1.00"):
                price_change_pct = pct
                previous_amount = prior_med
                if pct > Decimal("1.00") and direction == "outflow":
                    price_hikes_found += 1

        # Project next due date forward until >= today
        step_days = CADENCE_TO_DAYS[cadence]
        next_due = latest.occurred_at + timedelta(days=step_days)
        while next_due < today:
            next_due += timedelta(days=step_days)

        existing = existing_by_key.get((m_key, direction))
        if existing is not None:
            existing.amount = latest.amount
            existing.previous_amount = previous_amount
            existing.price_change_pct = price_change_pct
            existing.cadence = cadence
            existing.last_seen_date = latest.occurred_at
            existing.next_due_date = next_due
            updated_existing += 1
        else:
            db.add(
                RecurringItem(
                    user_id=user.id,
                    account_id=latest.account_id,
                    category_id=latest.category_id,
                    merchant_name=latest.merchant_clean,
                    amount=latest.amount,
                    previous_amount=previous_amount,
                    currency=latest.currency,
                    direction=direction,
                    cadence=cadence,
                    next_due_date=next_due,
                    last_seen_date=latest.occurred_at,
                    is_subscription=(direction == "outflow"),
                    is_active=True,
                    auto_detected=True,
                    price_change_pct=price_change_pct,
                )
            )
            detected_new += 1

    await db.commit()
    overview = await get_recurring_overview(db, user)
    return DetectRecurringResponse(
        detected_new=detected_new,
        updated_existing=updated_existing,
        price_hikes_found=price_hikes_found,
        overview=overview,
    )


# --- Net Worth ---


async def compute_current_net_worth(
    db: AsyncSession, user: User
) -> tuple[Decimal, Decimal, Decimal, list[NetWorthAccountBreakdown]]:
    accounts = (
        await db.scalars(
            select(Account)
            .where(Account.user_id == user.id, Account.is_archived.is_(False))
            .order_by(Account.type.asc(), Account.name.asc())
        )
    ).all()

    total_assets = Decimal("0.00")
    total_liabilities = Decimal("0.00")
    breakdowns: list[NetWorthAccountBreakdown] = []

    for acc in accounts:
        bal = acc.current_balance
        is_liab = (acc.type in ("credit", "loan") and bal < 0) or (
            acc.type not in ("credit", "loan") and bal < 0
        )
        if is_liab:
            total_liabilities += abs(bal)
            classification = "liability"
        else:
            total_assets += bal
            classification = "asset"

        breakdowns.append(
            NetWorthAccountBreakdown(
                account_id=acc.id,
                name=acc.name,
                type=acc.type,
                currency=acc.currency,
                balance=bal,
                classification=classification,  # type: ignore[arg-type]
            )
        )

    net_worth = (total_assets - total_liabilities).quantize(Decimal("0.01"))
    return (
        total_assets.quantize(Decimal("0.01")),
        total_liabilities.quantize(Decimal("0.01")),
        net_worth,
        breakdowns,
    )


async def capture_net_worth_snapshot(
    db: AsyncSession, user: User, snap_date: date | None = None
) -> NetWorthSnapshotResponse:
    target_date = snap_date or date.today()
    assets, liabilities, net_worth, breakdowns = await compute_current_net_worth(db, user)
    breakdown_dict = {
        str(b.account_id): {
            "name": b.name,
            "type": b.type,
            "balance": f"{b.balance:.2f}",
            "classification": b.classification,
        }
        for b in breakdowns
    }

    existing = await db.scalar(
        select(NetWorthSnapshot).where(
            NetWorthSnapshot.user_id == user.id,
            NetWorthSnapshot.snapshot_date == target_date,
        )
    )
    if existing is not None:
        existing.total_assets = assets
        existing.total_liabilities = liabilities
        existing.net_worth = net_worth
        existing.breakdown = breakdown_dict
        snap = existing
    else:
        snap = NetWorthSnapshot(
            user_id=user.id,
            snapshot_date=target_date,
            total_assets=assets,
            total_liabilities=liabilities,
            net_worth=net_worth,
            breakdown=breakdown_dict,
        )
        db.add(snap)

    await db.commit()
    await db.refresh(snap)
    return NetWorthSnapshotResponse.model_validate(snap)


async def get_net_worth_overview(db: AsyncSession, user: User) -> NetWorthOverviewResponse:
    assets, liabilities, net_worth, breakdowns = await compute_current_net_worth(db, user)
    snapshots = (
        await db.scalars(
            select(NetWorthSnapshot)
            .where(NetWorthSnapshot.user_id == user.id)
            .order_by(NetWorthSnapshot.snapshot_date.asc())
            .limit(36)
        )
    ).all()

    change_amount: Decimal | None = None
    change_pct: float | None = None
    if snapshots:
        baseline = snapshots[0].net_worth
        change_amount = (net_worth - baseline).quantize(Decimal("0.01"))
        if baseline != 0:
            change_pct = round(float(change_amount / abs(baseline)) * 100.0, 1)

    return NetWorthOverviewResponse(
        base_currency=user.base_currency,
        current_assets=assets,
        current_liabilities=liabilities,
        current_net_worth=net_worth,
        change_amount=change_amount,
        change_pct=change_pct,
        accounts=breakdowns,
        snapshots=[NetWorthSnapshotResponse.model_validate(s) for s in snapshots],
    )


# --- Financial Goals ---


def enrich_goal(goal: FinancialGoal) -> GoalResponse:
    remaining = max(Decimal("0.00"), goal.target_amount - goal.current_amount).quantize(
        Decimal("0.01")
    )
    progress_pct = (
        min(100.0, round(float(goal.current_amount / goal.target_amount) * 100.0, 1))
        if goal.target_amount > 0
        else 0.0
    )

    today = date.today()
    required_monthly: Decimal | None = None
    if goal.target_date and remaining > 0:
        months_left = max(
            1,
            (goal.target_date.year - today.year) * 12 + (goal.target_date.month - today.month),
        )
        required_monthly = (remaining / Decimal(str(months_left))).quantize(Decimal("0.01"))

    projected_date: date | None = None
    if remaining == 0:
        projected_date = today
    elif goal.monthly_contribution > 0:
        months_needed = math.ceil(float(remaining / goal.monthly_contribution))
        total_months = (today.year * 12 + (today.month - 1)) + months_needed
        proj_y, proj_m = total_months // 12, (total_months % 12) + 1
        proj_d = min(today.day, calendar.monthrange(proj_y, proj_m)[1])
        projected_date = date(proj_y, proj_m, proj_d)

    return GoalResponse(
        id=goal.id,
        linked_account_id=goal.linked_account_id,
        name=goal.name,
        goal_type=goal.goal_type,  # type: ignore[arg-type]
        target_amount=goal.target_amount,
        current_amount=goal.current_amount,
        monthly_contribution=goal.monthly_contribution,
        target_date=goal.target_date,
        color=goal.color,
        is_completed=goal.is_completed or remaining == 0,
        progress_pct=progress_pct,
        remaining_amount=remaining,
        required_monthly=required_monthly,
        projected_completion_date=projected_date,
    )


# --- Deterministic Financial Simulators (reusable as LangChain tools in Phase 4) ---


def _run_debt_strategy(
    debts: list[DebtInput],
    extra_monthly: Decimal,
    strategy: str,
) -> DebtStrategyResult:
    state = [
        {
            "name": d.name,
            "balance": d.balance.quantize(Decimal("0.01")),
            "monthly_rate": d.apr / Decimal("100") / Decimal("12"),
            "min_payment": d.min_payment.quantize(Decimal("0.01")),
        }
        for d in debts
    ]

    total_interest = Decimal("0.00")
    total_paid = Decimal("0.00")
    payoff_order: list[str] = []
    curve: list[dict] = [
        {
            "month": 0,
            "total_balance": float(sum((s["balance"] for s in state), Decimal("0.00"))),
        }
    ]

    # Fixed monthly budget = sum of all initial minimums + extra payment
    monthly_budget = sum((s["min_payment"] for s in state), Decimal("0.00")) + extra_monthly

    max_months = 360
    month = 0
    while any(s["balance"] > 0 for s in state) and month < max_months:
        month += 1

        # 1. Accrue monthly interest
        for s in state:
            if s["balance"] > 0:
                interest = (s["balance"] * s["monthly_rate"]).quantize(Decimal("0.01"))
                s["balance"] += interest
                total_interest += interest

        # 2. Pay minimum on every active debt
        remaining_budget = monthly_budget
        for s in state:
            if s["balance"] <= 0:
                continue
            pay = min(s["balance"], s["min_payment"], remaining_budget)
            s["balance"] -= pay
            remaining_budget -= pay
            total_paid += pay
            if s["balance"] <= Decimal("0.00") and s["name"] not in payoff_order:
                s["balance"] = Decimal("0.00")
                payoff_order.append(s["name"])

        # 3. Direct all leftover snowball/avalanche cash to prioritized debt
        active = [s for s in state if s["balance"] > 0]
        if strategy == "snowball":
            active.sort(key=lambda x: (x["balance"], -x["monthly_rate"]))
        else:
            active.sort(key=lambda x: (-x["monthly_rate"], x["balance"]))

        for target in active:
            if remaining_budget <= 0:
                break
            extra_pay = min(target["balance"], remaining_budget)
            target["balance"] -= extra_pay
            remaining_budget -= extra_pay
            total_paid += extra_pay
            if target["balance"] <= Decimal("0.00") and target["name"] not in payoff_order:
                target["balance"] = Decimal("0.00")
                payoff_order.append(target["name"])

        rem_total = sum((s["balance"] for s in state), Decimal("0.00"))
        if month <= 24 or month % 3 == 0 or rem_total == 0:
            curve.append({"month": month, "total_balance": float(rem_total)})

    return DebtStrategyResult(
        strategy=strategy,  # type: ignore[arg-type]
        months_to_payoff=month,
        total_interest_paid=total_interest.quantize(Decimal("0.01")),
        total_paid=total_paid.quantize(Decimal("0.01")),
        payoff_order=payoff_order,
        monthly_balance_curve=curve,
    )


def simulate_debt_payoff(payload: DebtPayoffRequest) -> DebtPayoffComparisonResponse:
    snowball = _run_debt_strategy(payload.debts, payload.extra_monthly_payment, "snowball")
    avalanche = _run_debt_strategy(payload.debts, payload.extra_monthly_payment, "avalanche")

    interest_saved = (snowball.total_interest_paid - avalanche.total_interest_paid).quantize(
        Decimal("0.01")
    )
    months_saved = snowball.months_to_payoff - avalanche.months_to_payoff
    recommended = "avalanche" if interest_saved >= 0 else "snowball"

    return DebtPayoffComparisonResponse(
        snowball=snowball,
        avalanche=avalanche,
        recommended_strategy=recommended,  # type: ignore[arg-type]
        interest_saved_by_avalanche=interest_saved,
        months_saved_by_avalanche=months_saved,
    )


def simulate_what_if(payload: WhatIfRequest) -> WhatIfResponse:
    base_net = (payload.monthly_income - payload.monthly_expenses).quantize(Decimal("0.01"))
    scen_income = max(Decimal("0.00"), payload.monthly_income + payload.income_delta_monthly)
    scen_expenses = max(Decimal("0.00"), payload.monthly_expenses + payload.expense_delta_monthly)
    scen_net = (scen_income - scen_expenses).quantize(Decimal("0.01"))

    monthly_rate = payload.annual_return_pct / Decimal("100") / Decimal("12")
    base_bal = payload.starting_savings.quantize(Decimal("0.01"))
    scen_bal = (payload.starting_savings + payload.one_time_impact).quantize(Decimal("0.01"))

    today = date.today()
    points: list[WhatIfPoint] = [
        WhatIfPoint(
            month_index=0,
            label="Now",
            baseline_balance=base_bal,
            scenario_balance=scen_bal,
            difference=(scen_bal - base_bal).quantize(Decimal("0.01")),
        )
    ]

    for m in range(1, payload.horizon_months + 1):
        if base_bal > 0:
            base_bal += base_bal * monthly_rate
        base_bal = (base_bal + base_net).quantize(Decimal("0.01"))

        if scen_bal > 0:
            scen_bal += scen_bal * monthly_rate
        scen_bal = (scen_bal + scen_net).quantize(Decimal("0.01"))

        total_m = (today.year * 12 + (today.month - 1)) + m
        y, mo = total_m // 12, (total_m % 12) + 1
        label = date(y, mo, 1).strftime("%b %Y")

        points.append(
            WhatIfPoint(
                month_index=m,
                label=label,
                baseline_balance=base_bal,
                scenario_balance=scen_bal,
                difference=(scen_bal - base_bal).quantize(Decimal("0.01")),
            )
        )

    runway: float | None = None
    if scen_net < 0:
        start_scen = payload.starting_savings + payload.one_time_impact
        runway = round(float(max(Decimal("0"), start_scen) / abs(scen_net)), 1)

    return WhatIfResponse(
        baseline_monthly_net=base_net,
        scenario_monthly_net=scen_net,
        baseline_end_balance=base_bal,
        scenario_end_balance=scen_bal,
        net_impact=(scen_bal - base_bal).quantize(Decimal("0.01")),
        scenario_runway_months=runway,
        points=points,
    )
