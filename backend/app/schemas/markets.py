from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class NbgForexRateResponse(BaseModel):
    code: str
    name: str
    quantity: int
    rate: float
    rate_per_unit: float
    diff: float
    diff_pct: float
    valid_from: str


class CandlePointResponse(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    sma_20: float | None = None
    sma_50: float | None = None


class QuantSignalResponse(BaseModel):
    symbol: str
    display_name: str
    asset_type: str
    currency: str
    price: float
    change: float
    change_pct: float
    quant_score: int
    signal: Literal["STRONG_BUY", "BUY", "HOLD", "WATCH_SELL", "AVOID"]
    trend_label: str
    rsi_14: float | None = None
    sma_20: float | None = None
    sma_50: float | None = None
    sma_200: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    macd_hist: float | None = None
    atr_14: float | None = None
    volatility_pct: float | None = None
    return_1w_pct: float | None = None
    return_1m_pct: float | None = None
    return_3m_pct: float | None = None
    fifty_two_week_high: float | None = None
    fifty_two_week_low: float | None = None
    entry_zone_low: float
    entry_zone_high: float
    stop_loss: float
    take_profit: float
    risk_reward_ratio: float
    risk_level: Literal["Low", "Medium", "High"]
    suggested_max_allocation_usd: float | None = None
    cfo_guardrail_note: str | None = None
    reasons: list[str] = Field(default_factory=list)


class QuoteDetailResponse(BaseModel):
    analysis: QuantSignalResponse
    candles: list[CandlePointResponse]
    fetched_at: str


class SymbolSearchHit(BaseModel):
    symbol: str
    display_name: str
    asset_type: str
    exchange: str


class WatchlistItemCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=24)
    display_name: str | None = Field(default=None, max_length=120)
    asset_type: str | None = Field(default=None, max_length=20)
    target_buy_price: Decimal | None = Field(default=None, gt=Decimal("0"))
    target_sell_price: Decimal | None = Field(default=None, gt=Decimal("0"))
    alert_enabled: bool = True
    notes: str | None = Field(default=None, max_length=500)


class WatchlistItemUpdate(BaseModel):
    target_buy_price: Decimal | None = Field(default=None, gt=Decimal("0"))
    target_sell_price: Decimal | None = Field(default=None, gt=Decimal("0"))
    alert_enabled: bool | None = None
    notes: str | None = Field(default=None, max_length=500)


class WatchlistItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    symbol: str
    display_name: str
    asset_type: str
    target_buy_price: Decimal | None
    target_sell_price: Decimal | None
    alert_enabled: bool
    notes: str | None
    live_price: float | None = None
    change_pct: float | None = None
    currency: str = "USD"
    quant_score: int | None = None
    signal: str | None = None
    alert_triggered: Literal["none", "buy_target_hit", "sell_target_hit"] = "none"
    created_at: datetime


class MarketsOverviewResponse(BaseModel):
    nbg_forex_rates: list[NbgForexRateResponse]
    ticker_quotes: list[QuantSignalResponse]
    triggered_alerts: list[WatchlistItemResponse]
    cfo_runway_months: float
    cfo_liquid_cash: float
    base_currency: str
    risk_profile: str


class ScannerResponse(BaseModel):
    risk_profile: str
    category: str
    cfo_runway_months: float
    cfo_liquid_cash: float
    items: list[QuantSignalResponse]


class PaperTradeRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=24)
    side: Literal["buy", "sell"]
    usd_amount: Decimal | None = Field(default=None, gt=Decimal("0"))
    quantity: Decimal | None = Field(default=None, gt=Decimal("0"))
    stop_loss: Decimal | None = Field(default=None, gt=Decimal("0"))
    take_profit: Decimal | None = Field(default=None, gt=Decimal("0"))
    rationale: str | None = Field(default=None, max_length=400)


class PaperSettingsUpdate(BaseModel):
    risk_profile: Literal["conservative", "balanced", "aggressive"]


class PaperPositionResponse(BaseModel):
    id: UUID
    symbol: str
    display_name: str
    asset_type: str
    quantity: Decimal
    avg_entry_price: Decimal
    live_price: float
    market_value: Decimal
    cost_basis: Decimal
    unrealized_pnl: Decimal
    unrealized_pnl_pct: float
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None
    signal: str | None = None
    quant_score: int | None = None


class PaperTradeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    symbol: str
    display_name: str
    asset_type: str
    side: Literal["buy", "sell"]
    quantity: Decimal
    price: Decimal
    total_value: Decimal
    realized_pnl: Decimal | None
    signal_at_trade: str | None
    rationale: str | None
    executed_at: datetime


class PaperPortfolioResponse(BaseModel):
    id: UUID
    currency: str
    risk_profile: str
    starting_cash: Decimal
    cash_balance: Decimal
    invested_value: Decimal
    total_equity: Decimal
    total_pnl: Decimal
    total_return_pct: float
    realized_pnl_total: Decimal
    win_rate_pct: float | None
    closed_trades_count: int
    positions: list[PaperPositionResponse]
    recent_trades: list[PaperTradeResponse]
