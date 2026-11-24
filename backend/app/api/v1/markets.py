from dataclasses import asdict
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.markets import MarketWatchlistItem, PaperPortfolio, PaperPosition, PaperTrade
from app.models.user import User
from app.schemas.markets import (
    CandlePointResponse,
    MarketsOverviewResponse,
    NbgForexRateResponse,
    PaperPortfolioResponse,
    PaperPositionResponse,
    PaperSettingsUpdate,
    PaperTradeRequest,
    PaperTradeResponse,
    QuantSignalResponse,
    QuoteDetailResponse,
    ScannerResponse,
    SymbolSearchHit,
    WatchlistItemCreate,
    WatchlistItemResponse,
    WatchlistItemUpdate,
)
from app.services.financial_health_service import compute_financial_health_profile
from app.services.market_data_service import (
    CURATED_UNIVERSE,
    UNIVERSE_BY_SYMBOL,
    fetch_multiple_charts,
    fetch_nbg_forex_rates,
    fetch_symbol_chart,
    infer_asset_type,
    normalize_symbol,
    search_market_symbols,
)
from app.services.quant_signal_service import (
    RiskProfile,
    analyze_asset_quant,
    compute_sma_series,
)

router = APIRouter(prefix="/markets", tags=["Markets, Forex & AI Trader Bot"])

TICKER_SYMBOLS = ["SPY", "QQQ", "NVDA", "AAPL", "EURUSD=X", "GC=F", "BTC-USD"]


async def _get_or_create_portfolio(db: AsyncSession, user: User) -> PaperPortfolio:
    portfolio = await db.scalar(
        select(PaperPortfolio).where(PaperPortfolio.user_id == user.id)
    )
    if portfolio is None:
        portfolio = PaperPortfolio(
            user_id=user.id,
            starting_cash=Decimal("10000.00"),
            cash_balance=Decimal("10000.00"),
            currency="USD",
            risk_profile="balanced",
        )
        db.add(portfolio)
        await db.commit()
        await db.refresh(portfolio)
    return portfolio


async def _get_cfo_context(db: AsyncSession, user: User) -> tuple[float, float]:
    try:
        profile = await compute_financial_health_profile(db, user)
        liquid = float(Decimal(str(profile["balance_sheet"]["liquid_cash"])))
        runway = float(profile["cash_flow_ratios"]["emergency_runway_months"])
        return liquid, runway
    except Exception:
        return 0.0, 0.0


async def _enrich_watchlist(
    items: list[MarketWatchlistItem],
    *,
    risk_profile: RiskProfile,
    liquid_cash: float,
    runway_months: float,
) -> list[WatchlistItemResponse]:
    if not items:
        return []
    charts = await fetch_multiple_charts([i.symbol for i in items], range_str="6mo")
    enriched: list[WatchlistItemResponse] = []
    for item in items:
        ch = charts.get(item.symbol)
        live_price: float | None = None
        change_pct: float | None = None
        currency = "USD"
        q_score: int | None = None
        signal: str | None = None
        alert_status: Literal["none", "buy_target_hit", "sell_target_hit"] = "none"

        if ch is not None:
            qa = analyze_asset_quant(
                ch,
                risk_profile=risk_profile,
                liquid_cash_usd=liquid_cash,
                emergency_runway_months=runway_months,
            )
            live_price = qa.price
            change_pct = qa.change_pct
            currency = qa.currency
            q_score = qa.quant_score
            signal = qa.signal
            if item.alert_enabled:
                if item.target_buy_price is not None and live_price <= float(item.target_buy_price):
                    alert_status = "buy_target_hit"
                elif item.target_sell_price is not None and live_price >= float(
                    item.target_sell_price
                ):
                    alert_status = "sell_target_hit"

        enriched.append(
            WatchlistItemResponse(
                id=item.id,
                symbol=item.symbol,
                display_name=item.display_name,
                asset_type=item.asset_type,
                target_buy_price=item.target_buy_price,
                target_sell_price=item.target_sell_price,
                alert_enabled=item.alert_enabled,
                notes=item.notes,
                live_price=live_price,
                change_pct=change_pct,
                currency=currency,
                quant_score=q_score,
                signal=signal,
                alert_triggered=alert_status,
                created_at=item.created_at,
            )
        )
    return enriched


@router.get("/overview", response_model=MarketsOverviewResponse)
async def markets_overview(
    force_refresh: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MarketsOverviewResponse:
    portfolio = await _get_or_create_portfolio(db, current_user)
    risk_prof: RiskProfile = (
        portfolio.risk_profile
        if portfolio.risk_profile in ("conservative", "balanced", "aggressive")
        else "balanced"
    )  # type: ignore[assignment]
    liquid_cash, runway_months = await _get_cfo_context(db, current_user)

    nbg_rates = await fetch_nbg_forex_rates(force_refresh=force_refresh)
    ticker_charts = await fetch_multiple_charts(TICKER_SYMBOLS, range_str="6mo")
    ticker_quotes = [
        QuantSignalResponse(
            **asdict(
                analyze_asset_quant(
                    ticker_charts[sym],
                    risk_profile=risk_prof,
                    liquid_cash_usd=liquid_cash,
                    emergency_runway_months=runway_months,
                )
            )
        )
        for sym in TICKER_SYMBOLS
        if sym in ticker_charts
    ]

    wl_rows = (
        await db.scalars(
            select(MarketWatchlistItem)
            .where(MarketWatchlistItem.user_id == current_user.id)
            .order_by(MarketWatchlistItem.created_at.desc())
        )
    ).all()
    wl_enriched = await _enrich_watchlist(
        list(wl_rows),
        risk_profile=risk_prof,
        liquid_cash=liquid_cash,
        runway_months=runway_months,
    )
    triggered = [w for w in wl_enriched if w.alert_triggered != "none"]

    return MarketsOverviewResponse(
        nbg_forex_rates=[NbgForexRateResponse(**asdict(r)) for r in nbg_rates],
        ticker_quotes=ticker_quotes,
        triggered_alerts=triggered,
        cfo_runway_months=runway_months,
        cfo_liquid_cash=liquid_cash,
        base_currency=current_user.base_currency,
        risk_profile=risk_prof,
    )


@router.get("/scanner", response_model=ScannerResponse)
async def ai_trader_bot_scanner(
    category: Literal["all", "stock", "etf", "forex", "crypto", "commodity"] = Query(default="all"),
    risk_profile: RiskProfile | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ScannerResponse:
    """AI Trader Bot Scanner: evaluates curated stocks, ETFs, forex & crypto with deterministic Python quant signals."""
    portfolio = await _get_or_create_portfolio(db, current_user)
    eff_risk: RiskProfile = risk_profile or (
        portfolio.risk_profile
        if portfolio.risk_profile in ("conservative", "balanced", "aggressive")
        else "balanced"
    )  # type: ignore[assignment]
    liquid_cash, runway_months = await _get_cfo_context(db, current_user)

    assets = (
        CURATED_UNIVERSE
        if category == "all"
        else [a for a in CURATED_UNIVERSE if a.asset_type == category]
    )
    charts = await fetch_multiple_charts([a.symbol for a in assets], range_str="6mo")

    analyses = [
        QuantSignalResponse(
            **asdict(
                analyze_asset_quant(
                    charts[a.symbol],
                    risk_profile=eff_risk,
                    liquid_cash_usd=liquid_cash,
                    emergency_runway_months=runway_months,
                )
            )
        )
        for a in assets
        if a.symbol in charts
    ]
    analyses.sort(key=lambda x: (x.quant_score, x.return_1m_pct or 0.0), reverse=True)

    return ScannerResponse(
        risk_profile=eff_risk,
        category=category,
        cfo_runway_months=runway_months,
        cfo_liquid_cash=liquid_cash,
        items=analyses,
    )


@router.get("/quote/{symbol}", response_model=QuoteDetailResponse)
async def get_symbol_quote_detail(
    symbol: str,
    range_str: Literal["1mo", "3mo", "6mo", "1y"] = Query(default="6mo"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> QuoteDetailResponse:
    portfolio = await _get_or_create_portfolio(db, current_user)
    eff_risk: RiskProfile = (
        portfolio.risk_profile
        if portfolio.risk_profile in ("conservative", "balanced", "aggressive")
        else "balanced"
    )  # type: ignore[assignment]
    liquid_cash, runway_months = await _get_cfo_context(db, current_user)

    chart = await fetch_symbol_chart(symbol, range_str=range_str)
    if chart is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No live market data found for symbol '{symbol.upper()}'.",
        )

    qa = analyze_asset_quant(
        chart,
        risk_profile=eff_risk,
        liquid_cash_usd=liquid_cash,
        emergency_runway_months=runway_months,
    )
    sma20_series = compute_sma_series(chart.candles, 20)
    sma50_series = compute_sma_series(chart.candles, 50)
    candles_out = [
        CandlePointResponse(
            date=c.date,
            open=c.open,
            high=c.high,
            low=c.low,
            close=c.close,
            volume=c.volume,
            sma_20=sma20_series[idx],
            sma_50=sma50_series[idx],
        )
        for idx, c in enumerate(chart.candles)
    ]

    return QuoteDetailResponse(
        analysis=QuantSignalResponse(**asdict(qa)),
        candles=candles_out,
        fetched_at=chart.fetched_at,
    )


@router.get("/search", response_model=list[SymbolSearchHit])
async def search_symbols(
    q: str = Query(default="", max_length=60),
    _current_user: User = Depends(get_current_user),
) -> list[SymbolSearchHit]:
    hits = await search_market_symbols(q, limit=8)
    return [SymbolSearchHit(**h) for h in hits]


# --- Watchlist & Price Target Alerts ---


@router.get("/watchlist", response_model=list[WatchlistItemResponse])
async def list_watchlist(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[WatchlistItemResponse]:
    portfolio = await _get_or_create_portfolio(db, current_user)
    eff_risk: RiskProfile = (
        portfolio.risk_profile
        if portfolio.risk_profile in ("conservative", "balanced", "aggressive")
        else "balanced"
    )  # type: ignore[assignment]
    liquid_cash, runway_months = await _get_cfo_context(db, current_user)
    rows = (
        await db.scalars(
            select(MarketWatchlistItem)
            .where(MarketWatchlistItem.user_id == current_user.id)
            .order_by(MarketWatchlistItem.created_at.desc())
        )
    ).all()
    return await _enrich_watchlist(
        list(rows),
        risk_profile=eff_risk,
        liquid_cash=liquid_cash,
        runway_months=runway_months,
    )


@router.post("/watchlist", response_model=WatchlistItemResponse, status_code=status.HTTP_201_CREATED)
async def add_watchlist_item(
    payload: WatchlistItemCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WatchlistItemResponse:
    sym = normalize_symbol(payload.symbol)
    existing = await db.scalar(
        select(MarketWatchlistItem).where(
            MarketWatchlistItem.user_id == current_user.id,
            MarketWatchlistItem.symbol == sym,
        )
    )
    if existing is not None:
        if payload.target_buy_price is not None:
            existing.target_buy_price = payload.target_buy_price
        if payload.target_sell_price is not None:
            existing.target_sell_price = payload.target_sell_price
        existing.alert_enabled = payload.alert_enabled
        if payload.notes is not None:
            existing.notes = payload.notes
        await db.commit()
        await db.refresh(existing)
        item = existing
    else:
        meta = UNIVERSE_BY_SYMBOL.get(sym)
        chart = await fetch_symbol_chart(sym, range_str="1mo")
        display = payload.display_name or (meta.display_name if meta else (chart.display_name if chart else sym))
        asset_type = payload.asset_type or (meta.asset_type if meta else (chart.asset_type if chart else infer_asset_type(sym)))
        item = MarketWatchlistItem(
            user_id=current_user.id,
            symbol=sym,
            display_name=display[:120],
            asset_type=asset_type,
            target_buy_price=payload.target_buy_price,
            target_sell_price=payload.target_sell_price,
            alert_enabled=payload.alert_enabled,
            notes=payload.notes,
        )
        db.add(item)
        await db.commit()
        await db.refresh(item)

    portfolio = await _get_or_create_portfolio(db, current_user)
    eff_risk: RiskProfile = (
        portfolio.risk_profile
        if portfolio.risk_profile in ("conservative", "balanced", "aggressive")
        else "balanced"
    )  # type: ignore[assignment]
    liquid_cash, runway_months = await _get_cfo_context(db, current_user)
    enriched = await _enrich_watchlist(
        [item], risk_profile=eff_risk, liquid_cash=liquid_cash, runway_months=runway_months
    )
    return enriched[0]


@router.patch("/watchlist/{item_id}", response_model=WatchlistItemResponse)
async def update_watchlist_item(
    item_id: UUID,
    payload: WatchlistItemUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WatchlistItemResponse:
    item = await db.scalar(
        select(MarketWatchlistItem).where(
            MarketWatchlistItem.id == item_id, MarketWatchlistItem.user_id == current_user.id
        )
    )
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watchlist item not found.")

    fields_set = payload.model_fields_set
    if "target_buy_price" in fields_set:
        item.target_buy_price = payload.target_buy_price
    if "target_sell_price" in fields_set:
        item.target_sell_price = payload.target_sell_price
    if payload.alert_enabled is not None:
        item.alert_enabled = payload.alert_enabled
    if "notes" in fields_set:
        item.notes = payload.notes

    await db.commit()
    await db.refresh(item)
    portfolio = await _get_or_create_portfolio(db, current_user)
    eff_risk: RiskProfile = (
        portfolio.risk_profile
        if portfolio.risk_profile in ("conservative", "balanced", "aggressive")
        else "balanced"
    )  # type: ignore[assignment]
    liquid_cash, runway_months = await _get_cfo_context(db, current_user)
    enriched = await _enrich_watchlist(
        [item], risk_profile=eff_risk, liquid_cash=liquid_cash, runway_months=runway_months
    )
    return enriched[0]


@router.delete("/watchlist/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_watchlist_item(
    item_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    item = await db.scalar(
        select(MarketWatchlistItem).where(
            MarketWatchlistItem.id == item_id, MarketWatchlistItem.user_id == current_user.id
        )
    )
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watchlist item not found.")
    await db.delete(item)
    await db.commit()


# --- Virtual $10,000 Paper-Trading Bot Portfolio ---


async def _build_paper_portfolio_response(
    db: AsyncSession, user: User, portfolio: PaperPortfolio
) -> PaperPortfolioResponse:
    positions = (
        await db.scalars(
            select(PaperPosition)
            .where(PaperPosition.portfolio_id == portfolio.id)
            .order_by(PaperPosition.updated_at.desc())
        )
    ).all()
    trades = (
        await db.scalars(
            select(PaperTrade)
            .where(PaperTrade.portfolio_id == portfolio.id)
            .order_by(PaperTrade.executed_at.desc())
            .limit(40)
        )
    ).all()

    charts = (
        await fetch_multiple_charts([p.symbol for p in positions], range_str="6mo")
        if positions
        else {}
    )
    eff_risk: RiskProfile = (
        portfolio.risk_profile
        if portfolio.risk_profile in ("conservative", "balanced", "aggressive")
        else "balanced"
    )  # type: ignore[assignment]

    pos_out: list[PaperPositionResponse] = []
    invested_value = Decimal("0.00")

    for p in positions:
        ch = charts.get(p.symbol)
        live_price_f = ch.price if ch is not None else float(p.avg_entry_price)
        live_price_d = Decimal(str(live_price_f))
        mv = (p.quantity * live_price_d).quantize(Decimal("0.01"))
        cost = (p.quantity * p.avg_entry_price).quantize(Decimal("0.01"))
        upnl = (mv - cost).quantize(Decimal("0.01"))
        upnl_pct = round(float(upnl / cost) * 100.0, 2) if cost > 0 else 0.0
        invested_value += mv

        sig: str | None = None
        q_score: int | None = None
        if ch is not None:
            qa = analyze_asset_quant(ch, risk_profile=eff_risk)
            sig = qa.signal
            q_score = qa.quant_score

        pos_out.append(
            PaperPositionResponse(
                id=p.id,
                symbol=p.symbol,
                display_name=p.display_name,
                asset_type=p.asset_type,
                quantity=p.quantity,
                avg_entry_price=p.avg_entry_price,
                live_price=round(live_price_f, 4),
                market_value=mv,
                cost_basis=cost,
                unrealized_pnl=upnl,
                unrealized_pnl_pct=upnl_pct,
                stop_loss=p.stop_loss,
                take_profit=p.take_profit,
                signal=sig,
                quant_score=q_score,
            )
        )

    total_equity = (portfolio.cash_balance + invested_value).quantize(Decimal("0.01"))
    total_pnl = (total_equity - portfolio.starting_cash).quantize(Decimal("0.01"))
    total_return_pct = (
        round(float(total_pnl / portfolio.starting_cash) * 100.0, 2)
        if portfolio.starting_cash > 0
        else 0.0
    )

    closed_sells = [t for t in trades if t.side == "sell" and t.realized_pnl is not None]
    realized_total = sum((t.realized_pnl or Decimal("0.00") for t in closed_sells), Decimal("0.00"))
    wins = sum(1 for t in closed_sells if (t.realized_pnl or Decimal("0.00")) > 0)
    win_rate = round((wins / len(closed_sells)) * 100.0, 1) if closed_sells else None

    return PaperPortfolioResponse(
        id=portfolio.id,
        currency=portfolio.currency,
        risk_profile=portfolio.risk_profile,
        starting_cash=portfolio.starting_cash,
        cash_balance=portfolio.cash_balance,
        invested_value=invested_value,
        total_equity=total_equity,
        total_pnl=total_pnl,
        total_return_pct=total_return_pct,
        realized_pnl_total=realized_total.quantize(Decimal("0.01")),
        win_rate_pct=win_rate,
        closed_trades_count=len(closed_sells),
        positions=pos_out,
        recent_trades=[PaperTradeResponse.model_validate(t) for t in trades],
    )


@router.get("/paper/portfolio", response_model=PaperPortfolioResponse)
async def get_paper_portfolio(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PaperPortfolioResponse:
    portfolio = await _get_or_create_portfolio(db, current_user)
    return await _build_paper_portfolio_response(db, current_user, portfolio)


@router.post("/paper/trade", response_model=PaperPortfolioResponse, status_code=status.HTTP_201_CREATED)
async def execute_paper_trade(
    payload: PaperTradeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PaperPortfolioResponse:
    if payload.usd_amount is None and payload.quantity is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide either usd_amount or quantity for the paper trade.",
        )

    portfolio = await _get_or_create_portfolio(db, current_user)
    sym = normalize_symbol(payload.symbol)
    chart = await fetch_symbol_chart(sym, range_str="6mo")
    if chart is None or chart.price <= 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unable to fetch live market price for '{sym}'.",
        )

    eff_risk: RiskProfile = (
        portfolio.risk_profile
        if portfolio.risk_profile in ("conservative", "balanced", "aggressive")
        else "balanced"
    )  # type: ignore[assignment]
    qa = analyze_asset_quant(chart, risk_profile=eff_risk)
    live_price = Decimal(str(chart.price)).quantize(Decimal("0.0001"))

    if payload.quantity is not None:
        qty = payload.quantity.quantize(Decimal("0.000001"))
        total_val = (qty * live_price).quantize(Decimal("0.01"))
    else:
        assert payload.usd_amount is not None
        total_val = payload.usd_amount.quantize(Decimal("0.01"))
        qty = (total_val / live_price).quantize(Decimal("0.000001"))

    if qty <= 0 or total_val <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Trade size must be greater than zero."
        )

    position = await db.scalar(
        select(PaperPosition).where(
            PaperPosition.portfolio_id == portfolio.id,
            PaperPosition.symbol == sym,
        )
    )

    realized_pnl: Decimal | None = None

    if payload.side == "buy":
        if total_val > portfolio.cash_balance:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Insufficient virtual paper cash (${portfolio.cash_balance:.2f} available).",
            )
        portfolio.cash_balance = (portfolio.cash_balance - total_val).quantize(Decimal("0.01"))
        if position is None:
            position = PaperPosition(
                portfolio_id=portfolio.id,
                user_id=current_user.id,
                symbol=sym,
                display_name=chart.display_name,
                asset_type=chart.asset_type,
                quantity=qty,
                avg_entry_price=live_price,
                stop_loss=payload.stop_loss or Decimal(str(qa.stop_loss)),
                take_profit=payload.take_profit or Decimal(str(qa.take_profit)),
            )
            db.add(position)
        else:
            old_cost = position.quantity * position.avg_entry_price
            new_qty = (position.quantity + qty).quantize(Decimal("0.000001"))
            new_avg = ((old_cost + (qty * live_price)) / new_qty).quantize(Decimal("0.0001"))
            position.quantity = new_qty
            position.avg_entry_price = new_avg
            if payload.stop_loss is not None:
                position.stop_loss = payload.stop_loss
            if payload.take_profit is not None:
                position.take_profit = payload.take_profit
    else:
        if position is None or position.quantity <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"You do not hold any open paper position in {sym}.",
            )
        # Allow tiny rounding tolerance when selling full position
        sell_qty = min(qty, position.quantity)
        total_val = (sell_qty * live_price).quantize(Decimal("0.01"))
        cost_basis_sold = (sell_qty * position.avg_entry_price).quantize(Decimal("0.01"))
        realized_pnl = (total_val - cost_basis_sold).quantize(Decimal("0.01"))
        portfolio.cash_balance = (portfolio.cash_balance + total_val).quantize(Decimal("0.01"))
        remaining = (position.quantity - sell_qty).quantize(Decimal("0.000001"))
        if remaining <= Decimal("0.000010"):
            await db.delete(position)
        else:
            position.quantity = remaining
        qty = sell_qty

    trade = PaperTrade(
        portfolio_id=portfolio.id,
        user_id=current_user.id,
        symbol=sym,
        display_name=chart.display_name,
        asset_type=chart.asset_type,
        side=payload.side,
        quantity=qty,
        price=live_price,
        total_value=total_val,
        realized_pnl=realized_pnl,
        signal_at_trade=qa.signal,
        rationale=payload.rationale or (qa.reasons[0] if qa.reasons else None),
    )
    db.add(trade)
    await db.commit()
    await db.refresh(portfolio)

    return await _build_paper_portfolio_response(db, current_user, portfolio)


@router.patch("/paper/settings", response_model=PaperPortfolioResponse)
async def update_paper_settings(
    payload: PaperSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PaperPortfolioResponse:
    portfolio = await _get_or_create_portfolio(db, current_user)
    portfolio.risk_profile = payload.risk_profile
    await db.commit()
    await db.refresh(portfolio)
    return await _build_paper_portfolio_response(db, current_user, portfolio)


@router.post("/paper/reset", response_model=PaperPortfolioResponse)
async def reset_paper_portfolio(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PaperPortfolioResponse:
    portfolio = await _get_or_create_portfolio(db, current_user)
    positions = (
        await db.scalars(select(PaperPosition).where(PaperPosition.portfolio_id == portfolio.id))
    ).all()
    for p in positions:
        await db.delete(p)
    trades = (
        await db.scalars(select(PaperTrade).where(PaperTrade.portfolio_id == portfolio.id))
    ).all()
    for t in trades:
        await db.delete(t)
    portfolio.starting_cash = Decimal("10000.00")
    portfolio.cash_balance = Decimal("10000.00")
    await db.commit()
    await db.refresh(portfolio)
    return await _build_paper_portfolio_response(db, current_user, portfolio)
