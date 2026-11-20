from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# --- Budgets ---

BudgetPeriod = Literal["monthly", "quarterly", "yearly"]


class BudgetCreate(BaseModel):
    category_id: UUID
    amount: Decimal = Field(gt=Decimal("0"))
    period: BudgetPeriod = "monthly"
    rollover: bool = False
    alert_threshold_pct: int = Field(default=80, ge=10, le=100)


class BudgetUpdate(BaseModel):
    amount: Decimal | None = Field(default=None, gt=Decimal("0"))
    rollover: bool | None = None
    alert_threshold_pct: int | None = Field(default=None, ge=10, le=100)
    is_active: bool | None = None


class BudgetStatusResponse(BaseModel):
    id: UUID
    category_id: UUID
    category_name: str
    category_color: str
    period: BudgetPeriod
    amount: Decimal
    rollover: bool
    rollover_carry: Decimal
    effective_limit: Decimal
    spent: Decimal
    remaining: Decimal
    percent_used: float
    pace_pct: float
    alert_threshold_pct: int
    status: Literal["on_track", "pacing_fast", "warning", "over_budget"]
    is_active: bool


class BudgetOverviewResponse(BaseModel):
    month: str  # YYYY-MM
    days_elapsed: int
    days_in_month: int
    pace_pct: float
    total_budgeted: Decimal
    total_spent: Decimal
    total_remaining: Decimal
    budgets: list[BudgetStatusResponse]


class ApplyBudgetTemplateRequest(BaseModel):
    monthly_income: Decimal = Field(gt=Decimal("0"))


# --- Recurring & Subscriptions ---

RecurringCadence = Literal["weekly", "biweekly", "monthly", "quarterly", "yearly"]


class RecurringCreate(BaseModel):
    merchant_name: str = Field(min_length=1, max_length=160)
    amount: Decimal = Field(gt=Decimal("0"))
    currency: str = Field(default="USD", min_length=3, max_length=3)
    direction: Literal["outflow", "inflow"] = "outflow"
    cadence: RecurringCadence = "monthly"
    next_due_date: date
    account_id: UUID | None = None
    category_id: UUID | None = None
    is_subscription: bool = True


class RecurringUpdate(BaseModel):
    merchant_name: str | None = Field(default=None, min_length=1, max_length=160)
    amount: Decimal | None = Field(default=None, gt=Decimal("0"))
    cadence: RecurringCadence | None = None
    next_due_date: date | None = None
    category_id: UUID | None = None
    is_subscription: bool | None = None
    is_active: bool | None = None


class RecurringItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    account_id: UUID | None
    category_id: UUID | None
    merchant_name: str
    amount: Decimal
    previous_amount: Decimal | None
    currency: str
    direction: Literal["outflow", "inflow"]
    cadence: RecurringCadence
    next_due_date: date
    last_seen_date: date | None
    is_subscription: bool
    is_active: bool
    auto_detected: bool
    price_change_pct: Decimal | None
    monthly_equivalent: Decimal = Decimal("0.00")


class RecurringOverviewResponse(BaseModel):
    monthly_recurring_expenses: Decimal
    annual_recurring_expenses: Decimal
    monthly_recurring_income: Decimal
    upcoming_30d_total: Decimal
    price_hike_alerts: list[RecurringItemResponse]
    items: list[RecurringItemResponse]


class DetectRecurringResponse(BaseModel):
    detected_new: int
    updated_existing: int
    price_hikes_found: int
    overview: RecurringOverviewResponse


# --- Net Worth ---


class NetWorthSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    snapshot_date: date
    total_assets: Decimal
    total_liabilities: Decimal
    net_worth: Decimal
    breakdown: dict
    created_at: datetime


class NetWorthAccountBreakdown(BaseModel):
    account_id: UUID
    name: str
    type: str
    currency: str
    balance: Decimal
    classification: Literal["asset", "liability"]


class NetWorthOverviewResponse(BaseModel):
    base_currency: str
    current_assets: Decimal
    current_liabilities: Decimal
    current_net_worth: Decimal
    change_amount: Decimal | None
    change_pct: float | None
    accounts: list[NetWorthAccountBreakdown]
    snapshots: list[NetWorthSnapshotResponse]


# --- Financial Goals ---

GoalType = Literal[
    "emergency_fund", "savings", "debt_payoff", "investment", "purchase", "retirement"
]


class GoalCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    goal_type: GoalType = "savings"
    target_amount: Decimal = Field(gt=Decimal("0"))
    current_amount: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0"))
    monthly_contribution: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0"))
    target_date: date | None = None
    linked_account_id: UUID | None = None
    color: str = Field(default="#10b981", max_length=16)


class GoalUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    goal_type: GoalType | None = None
    target_amount: Decimal | None = Field(default=None, gt=Decimal("0"))
    current_amount: Decimal | None = Field(default=None, ge=Decimal("0"))
    monthly_contribution: Decimal | None = Field(default=None, ge=Decimal("0"))
    target_date: date | None = None
    linked_account_id: UUID | None = None
    color: str | None = Field(default=None, max_length=16)
    is_completed: bool | None = None


class GoalContributeRequest(BaseModel):
    amount: Decimal = Field(gt=Decimal("0"))


class GoalResponse(BaseModel):
    id: UUID
    linked_account_id: UUID | None
    name: str
    goal_type: GoalType
    target_amount: Decimal
    current_amount: Decimal
    monthly_contribution: Decimal
    target_date: date | None
    color: str
    is_completed: bool
    progress_pct: float
    remaining_amount: Decimal
    required_monthly: Decimal | None
    projected_completion_date: date | None


# --- Deterministic Simulators ---


class DebtInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    balance: Decimal = Field(gt=Decimal("0"))
    apr: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    min_payment: Decimal = Field(gt=Decimal("0"))


class DebtPayoffRequest(BaseModel):
    debts: list[DebtInput] = Field(min_length=1, max_length=20)
    extra_monthly_payment: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0"))


class DebtStrategyResult(BaseModel):
    strategy: Literal["snowball", "avalanche"]
    months_to_payoff: int
    total_interest_paid: Decimal
    total_paid: Decimal
    payoff_order: list[str]
    monthly_balance_curve: list[dict]


class DebtPayoffComparisonResponse(BaseModel):
    snowball: DebtStrategyResult
    avalanche: DebtStrategyResult
    recommended_strategy: Literal["snowball", "avalanche"]
    interest_saved_by_avalanche: Decimal
    months_saved_by_avalanche: int


class WhatIfRequest(BaseModel):
    starting_savings: Decimal = Field(default=Decimal("0.00"))
    monthly_income: Decimal = Field(ge=Decimal("0"))
    monthly_expenses: Decimal = Field(ge=Decimal("0"))
    income_delta_monthly: Decimal = Field(default=Decimal("0.00"))
    expense_delta_monthly: Decimal = Field(default=Decimal("0.00"))
    one_time_impact: Decimal = Field(default=Decimal("0.00"))
    annual_return_pct: Decimal = Field(default=Decimal("4.50"), ge=Decimal("0"), le=Decimal("30"))
    horizon_months: int = Field(default=24, ge=1, le=120)


class WhatIfPoint(BaseModel):
    month_index: int
    label: str
    baseline_balance: Decimal
    scenario_balance: Decimal
    difference: Decimal


class WhatIfResponse(BaseModel):
    baseline_monthly_net: Decimal
    scenario_monthly_net: Decimal
    baseline_end_balance: Decimal
    scenario_end_balance: Decimal
    net_impact: Decimal
    scenario_runway_months: float | None
    points: list[WhatIfPoint]
