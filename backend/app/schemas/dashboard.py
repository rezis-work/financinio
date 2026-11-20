from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from app.schemas.transaction import TransactionResponse


class MonthlyCashFlowPoint(BaseModel):
    month: str  # YYYY-MM
    income: Decimal
    expenses: Decimal
    net: Decimal


class CategorySpendItem(BaseModel):
    category_id: UUID | None
    category_name: str
    color: str
    total: Decimal
    percentage: float
    transaction_count: int


class DashboardSummaryResponse(BaseModel):
    base_currency: str
    total_assets: Decimal
    total_liabilities: Decimal
    net_worth: Decimal
    period_income: Decimal
    period_expenses: Decimal
    period_net: Decimal
    savings_rate: float
    monthly_cash_flow: list[MonthlyCashFlowPoint]
    category_breakdown: list[CategorySpendItem]
    recent_transactions: list[TransactionResponse]
    pending_review_batches: int
