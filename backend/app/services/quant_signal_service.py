from dataclasses import dataclass, field
from typing import Literal

from app.services.market_data_service import Candle, MarketQuoteChart

SignalLabel = Literal["STRONG_BUY", "BUY", "HOLD", "WATCH_SELL", "AVOID"]
RiskProfile = Literal["conservative", "balanced", "aggressive"]


@dataclass
class QuantAnalysis:
    symbol: str
    display_name: str
    asset_type: str
    currency: str
    price: float
    change: float
    change_pct: float
    quant_score: int  # 0..100
    signal: SignalLabel
    trend_label: str  # Bullish | Neutral | Bearish
    rsi_14: float | None
    sma_20: float | None
    sma_50: float | None
    sma_200: float | None
    macd: float | None
    macd_signal: float | None
    macd_hist: float | None
    atr_14: float | None
    volatility_pct: float | None
    return_1w_pct: float | None
    return_1m_pct: float | None
    return_3m_pct: float | None
    fifty_two_week_high: float | None
    fifty_two_week_low: float | None
    entry_zone_low: float
    entry_zone_high: float
    stop_loss: float
    take_profit: float
    risk_reward_ratio: float
    risk_level: Literal["Low", "Medium", "High"]
    suggested_max_allocation_usd: float | None = None
    cfo_guardrail_note: str | None = None
    reasons: list[str] = field(default_factory=list)


def _sma(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def _ema_series(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    k = 2.0 / (period + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1.0 - k))
    return out


def _rsi_14(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(d, 0.0) for d in deltas]
    losses = [max(-d, 0.0) for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100.0 - (100.0 / (1.0 + rs)), 2)


def _atr_14(candles: list[Candle], period: int = 14) -> float | None:
    if len(candles) < period + 1:
        return None
    trs: list[float] = []
    for i in range(1, len(candles)):
        prev_close = candles[i - 1].close
        c = candles[i]
        tr = max(c.high - c.low, abs(c.high - prev_close), abs(c.low - prev_close))
        trs.append(tr)
    atr = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return atr


def _pct_return(closes: list[float], lookback: int) -> float | None:
    if len(closes) <= lookback:
        return None
    past = closes[-(lookback + 1)]
    if past <= 0:
        return None
    return round(((closes[-1] - past) / past) * 100.0, 2)


def compute_sma_series(candles: list[Candle], period: int) -> list[float | None]:
    closes = [c.close for c in candles]
    series: list[float | None] = []
    for i in range(len(closes)):
        if i + 1 < period:
            series.append(None)
        else:
            series.append(round(sum(closes[i + 1 - period : i + 1]) / period, 4))
    return series


def analyze_asset_quant(
    chart: MarketQuoteChart,
    *,
    risk_profile: RiskProfile = "balanced",
    liquid_cash_usd: float | None = None,
    emergency_runway_months: float | None = None,
) -> QuantAnalysis:
    """Compute deterministic technical indicators, Quant Score (0-100), trade levels, and CFO sizing."""
    candles = chart.candles
    closes = [c.close for c in candles] if candles else [chart.price]
    price = chart.price if chart.price > 0 else closes[-1]

    sma20 = _sma(closes, 20)
    sma50 = _sma(closes, 50)
    sma200 = _sma(closes, 200)
    rsi = _rsi_14(closes, 14)
    atr = _atr_14(candles, 14) if candles else None

    macd_val: float | None = None
    macd_sig: float | None = None
    macd_hist: float | None = None
    if len(closes) >= 26:
        ema12 = _ema_series(closes, 12)
        ema26 = _ema_series(closes, 26)
        macd_line = [a - b for a, b in zip(ema12, ema26, strict=False)]
        sig_line = _ema_series(macd_line, 9)
        macd_val = round(macd_line[-1], 4)
        macd_sig = round(sig_line[-1], 4)
        macd_hist = round(macd_line[-1] - sig_line[-1], 4)

    ret_1w = _pct_return(closes, 5)
    ret_1m = _pct_return(closes, 21)
    ret_3m = _pct_return(closes, 63)

    vol_pct = round((atr / price) * 100.0, 2) if (atr and price > 0) else None

    # --- Composite Quant Score (0..100, neutral baseline 50) ---
    score = 50.0
    reasons: list[str] = []

    # 1. Trend Structure (up to +/- 22 pts)
    if sma20 is not None and sma50 is not None:
        if price > sma20 > sma50:
            score += 16
            reasons.append(f"Bullish uptrend: price above SMA 20 ({sma20:.2f}) & SMA 50 ({sma50:.2f})")
        elif price > sma50:
            score += 9
            reasons.append(f"Constructive trend: holding above 50-day average ({sma50:.2f})")
        elif price < sma20 < sma50:
            score -= 14
            reasons.append(f"Downtrend pressure: trading below SMA 20 & SMA 50 ({sma50:.2f})")
        else:
            score -= 5
            reasons.append("Mixed short-term moving average alignment")

    if sma200 is not None:
        if price > sma200:
            score += 6
        else:
            score -= 6
            reasons.append(f"Below 200-day long-term trend ({sma200:.2f})")

    # 2. RSI Momentum & Mean Reversion (up to +/- 14 pts)
    if rsi is not None:
        if rsi < 32:
            score += 12
            reasons.append(f"RSI ({rsi:.1f}) oversold — potential bounce/accumulation zone")
        elif 45 <= rsi <= 64:
            score += 8
            reasons.append(f"Healthy bullish RSI momentum ({rsi:.1f}) without being overextended")
        elif rsi > 74:
            score -= 10
            reasons.append(f"RSI ({rsi:.1f}) overbought — wait for pullback before chasing")
        elif rsi < 45:
            score -= 3

    # 3. MACD Momentum (up to +/- 10 pts)
    if macd_hist is not None:
        if macd_hist > 0 and (macd_val or 0) > 0:
            score += 10
            reasons.append("Positive MACD bullish momentum expansion")
        elif macd_hist > 0:
            score += 5
            reasons.append("MACD turning upward — early momentum recovery")
        elif macd_hist < 0 and (macd_val or 0) < 0:
            score -= 9
            reasons.append("Bearish MACD momentum — sellers currently in control")
        else:
            score -= 4

    # 4. 52-Week Context & Multi-Month Strength (up to +/- 8 pts)
    if chart.fifty_two_week_high and chart.fifty_two_week_low and chart.fifty_two_week_high > chart.fifty_two_week_low:
        pos_52w = (price - chart.fifty_two_week_low) / (
            chart.fifty_two_week_high - chart.fifty_two_week_low
        )
        if 0.35 <= pos_52w <= 0.85:
            score += 5
        elif pos_52w > 0.95:
            score -= 3
            reasons.append("Trading right near 52-week high — size entries gradually")

    if ret_1m is not None:
        if ret_1m > 5:
            score += 4
        elif ret_1m < -10:
            score -= 4

    # Risk-profile preference adjustment
    risk_level: Literal["Low", "Medium", "High"] = "Medium"
    if chart.asset_type in ("crypto",) or (vol_pct is not None and vol_pct >= 3.2):
        risk_level = "High"
    elif chart.asset_type in ("etf", "forex", "commodity") and (vol_pct is None or vol_pct < 1.6):
        risk_level = "Low"

    if risk_profile == "conservative":
        if risk_level == "High":
            score -= 10
            reasons.append("High volatility asset — penalized under Conservative risk profile")
        elif risk_level == "Low":
            score += 5
    elif risk_profile == "aggressive" and risk_level == "High" and (ret_1m or 0) > 0:
        score += 4

    final_score = max(5, min(98, int(round(score))))

    if final_score >= 72:
        signal: SignalLabel = "STRONG_BUY"
    elif final_score >= 58:
        signal = "BUY"
    elif final_score >= 42:
        signal = "HOLD"
    elif final_score >= 28:
        signal = "WATCH_SELL"
    else:
        signal = "AVOID"

    trend_label = "Bullish" if final_score >= 58 else ("Bearish" if final_score <= 40 else "Neutral")

    # Trade levels derived deterministically from ATR (or 2% fallback)
    unit_atr = atr if (atr and atr > 0) else (price * 0.02)
    decimals = 4 if chart.asset_type == "forex" else 2
    entry_low = round(max(0.0001, price - 0.35 * unit_atr), decimals)
    entry_high = round(price + 0.2 * unit_atr, decimals)
    stop_loss = round(max(0.0001, price - 1.5 * unit_atr), decimals)
    take_profit = round(price + 3.0 * unit_atr, decimals)
    risk_unit = max(0.0001, price - stop_loss)
    reward_unit = max(0.0001, take_profit - price)
    rr_ratio = round(reward_unit / risk_unit, 2)

    # Personal CFO Position Sizing Guardrail
    suggested_alloc: float | None = None
    cfo_note: str | None = None
    if liquid_cash_usd is not None:
        max_pct_map = {"conservative": 0.03, "balanced": 0.05, "aggressive": 0.08}
        base_pct = max_pct_map[risk_profile]
        if risk_level == "High":
            base_pct *= 0.6
        if emergency_runway_months is not None and emergency_runway_months < 3.0:
            suggested_alloc = 0.0
            cfo_note = (
                f"CFO Guardrail: Your emergency runway is {emergency_runway_months:.1f} mo (<3 mo). "
                "Practice in Paper Trading first and build 3+ months of cash before deploying real capital."
            )
        else:
            suggested_alloc = round(max(0.0, liquid_cash_usd * base_pct), 2)
            cfo_note = (
                f"Prudent starter size ({int(base_pct * 100)}% of liquid cash under {risk_profile} profile): "
                f"up to {suggested_alloc:,.2f} (educational sizing)."
            )

    if not reasons:
        reasons.append("Price action currently trading in a balanced consolidation range.")

    return QuantAnalysis(
        symbol=chart.symbol,
        display_name=chart.display_name,
        asset_type=chart.asset_type,
        currency=chart.currency,
        price=round(price, decimals),
        change=round(chart.change, decimals),
        change_pct=round(chart.change_pct, 2),
        quant_score=final_score,
        signal=signal,
        trend_label=trend_label,
        rsi_14=rsi,
        sma_20=round(sma20, decimals) if sma20 is not None else None,
        sma_50=round(sma50, decimals) if sma50 is not None else None,
        sma_200=round(sma200, decimals) if sma200 is not None else None,
        macd=macd_val,
        macd_signal=macd_sig,
        macd_hist=macd_hist,
        atr_14=round(atr, decimals) if atr is not None else None,
        volatility_pct=vol_pct,
        return_1w_pct=ret_1w,
        return_1m_pct=ret_1m,
        return_3m_pct=ret_3m,
        fifty_two_week_high=chart.fifty_two_week_high,
        fifty_two_week_low=chart.fifty_two_week_low,
        entry_zone_low=entry_low,
        entry_zone_high=entry_high,
        stop_loss=stop_loss,
        take_profit=take_profit,
        risk_reward_ratio=rr_ratio,
        risk_level=risk_level,
        suggested_max_allocation_usd=suggested_alloc,
        cfo_guardrail_note=cfo_note,
        reasons=reasons[:4],
    )
