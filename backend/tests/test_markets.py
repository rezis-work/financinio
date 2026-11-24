from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.services.market_data_service import Candle, MarketQuoteChart, NbgForexRate
from app.services.quant_signal_service import analyze_asset_quant


def _make_uptrend_chart(symbol: str = "NVDA", start: float = 100.0, step: float = 0.8) -> MarketQuoteChart:
    candles: list[Candle] = []
    price = start
    for i in range(90):
        # Healthy rising trend with gentle oscillation so RSI stays bullish (~58-64)
        delta = step if i % 4 != 0 else -step * 0.6
        open_p = price
        close_p = max(1.0, price + delta)
        high_p = max(open_p, close_p) + 1.2
        low_p = min(open_p, close_p) - 1.0
        candles.append(
            Candle(
                date=f"2026-09-{(i % 28) + 1:02d}",
                open=round(open_p, 2),
                high=round(high_p, 2),
                low=round(low_p, 2),
                close=round(close_p, 2),
                volume=1_000_000.0,
            )
        )
        price = close_p

    last = candles[-1].close
    prev = candles[-2].close
    return MarketQuoteChart(
        symbol=symbol,
        display_name=f"{symbol} Corp.",
        asset_type="stock",
        currency="USD",
        price=last,
        previous_close=prev,
        change=round(last - prev, 2),
        change_pct=round(((last - prev) / prev) * 100.0, 2),
        day_high=candles[-1].high,
        day_low=candles[-1].low,
        fifty_two_week_high=round(last * 1.15, 2),
        fifty_two_week_low=round(start * 0.9, 2),
        candles=candles,
        fetched_at="2026-11-24T15:00:00Z",
    )


def test_quant_signal_engine_uptrend_and_cfo_guardrail() -> None:
    chart = _make_uptrend_chart("NVDA")
    qa_healthy = analyze_asset_quant(
        chart, risk_profile="balanced", liquid_cash_usd=20000.0, emergency_runway_months=6.0
    )
    assert qa_healthy.quant_score >= 58
    assert qa_healthy.signal in ("BUY", "STRONG_BUY")
    assert qa_healthy.rsi_14 is not None
    assert qa_healthy.sma_20 is not None
    assert qa_healthy.sma_50 is not None
    assert qa_healthy.stop_loss < qa_healthy.price < qa_healthy.take_profit
    assert qa_healthy.suggested_max_allocation_usd == 1000.0  # 5% of $20,000

    qa_low_runway = analyze_asset_quant(
        chart, risk_profile="balanced", liquid_cash_usd=2000.0, emergency_runway_months=1.2
    )
    assert qa_low_runway.suggested_max_allocation_usd == 0.0
    assert qa_low_runway.cfo_guardrail_note and "Paper Trading" in qa_low_runway.cfo_guardrail_note


@pytest.mark.asyncio
async def test_markets_scanner_watchlist_alerts_and_paper_trading(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    nvda_chart = _make_uptrend_chart("NVDA", start=120.0, step=0.6)
    spy_chart = _make_uptrend_chart("SPY", start=500.0, step=0.5)
    spy_chart.asset_type = "etf"

    fake_nbg = [
        NbgForexRate(
            code="USD",
            name="US Dollar",
            quantity=1,
            rate=2.5922,
            rate_per_unit=2.5922,
            diff=-0.0004,
            diff_pct=-0.015,
            valid_from="2026-11-25",
        ),
        NbgForexRate(
            code="EUR",
            name="Euro",
            quantity=1,
            rate=2.8343,
            rate_per_unit=2.8343,
            diff=-0.008,
            diff_pct=-0.281,
            valid_from="2026-11-25",
        ),
    ]

    async def fake_fetch_single(sym: str, **kwargs):
        s = sym.upper()
        if s == "NVDA":
            return nvda_chart
        if s == "SPY":
            return spy_chart
        return None

    async def fake_fetch_multi(syms: list[str], **kwargs):
        res = {}
        for s in syms:
            u = s.upper()
            if u == "NVDA":
                res["NVDA"] = nvda_chart
            elif u == "SPY":
                res["SPY"] = spy_chart
        return res

    with (
        patch("app.api.v1.markets.fetch_nbg_forex_rates", new=AsyncMock(return_value=fake_nbg)),
        patch("app.api.v1.markets.fetch_symbol_chart", side_effect=fake_fetch_single),
        patch("app.api.v1.markets.fetch_multiple_charts", side_effect=fake_fetch_multi),
    ):
        # 1. Overview & Scanner
        ov = await client.get("/api/v1/markets/overview", headers=auth_headers)
        assert ov.status_code == 200, ov.text
        ov_data = ov.json()
        assert len(ov_data["nbg_forex_rates"]) == 2
        assert ov_data["nbg_forex_rates"][0]["code"] == "USD"

        sc = await client.get("/api/v1/markets/scanner?category=all", headers=auth_headers)
        assert sc.status_code == 200, sc.text
        assert len(sc.json()["items"]) == 2

        # 2. Quote Detail with candles & SMA overlays
        qd = await client.get("/api/v1/markets/quote/NVDA", headers=auth_headers)
        assert qd.status_code == 200, qd.text
        assert qd.json()["analysis"]["symbol"] == "NVDA"
        assert len(qd.json()["candles"]) == 90

        # 3. Watchlist + Triggered Buy Alert (set target_buy_price above live price)
        wl_add = await client.post(
            "/api/v1/markets/watchlist",
            headers=auth_headers,
            json={
                "symbol": "NVDA",
                "target_buy_price": str(round(nvda_chart.price + 20.0, 2)),
                "alert_enabled": True,
                "notes": "AI leader watch",
            },
        )
        assert wl_add.status_code == 201, wl_add.text
        wl_item = wl_add.json()
        assert wl_item["alert_triggered"] == "buy_target_hit"

        # 4. Paper Portfolio: Start with $10,000, Buy $2,000 NVDA, Sell half, Reset
        p0 = await client.get("/api/v1/markets/paper/portfolio", headers=auth_headers)
        assert p0.status_code == 200
        assert float(p0.json()["cash_balance"]) == 10000.0

        buy = await client.post(
            "/api/v1/markets/paper/trade",
            headers=auth_headers,
            json={"symbol": "NVDA", "side": "buy", "usd_amount": "2000.00"},
        )
        assert buy.status_code == 201, buy.text
        p1 = buy.json()
        assert float(p1["cash_balance"]) == 8000.0
        assert len(p1["positions"]) == 1
        assert p1["positions"][0]["symbol"] == "NVDA"

        # Sell half the shares
        half_qty = float(p1["positions"][0]["quantity"]) / 2
        sell = await client.post(
            "/api/v1/markets/paper/trade",
            headers=auth_headers,
            json={"symbol": "NVDA", "side": "sell", "quantity": f"{half_qty:.6f}"},
        )
        assert sell.status_code == 201, sell.text
        p2 = sell.json()
        assert p2["closed_trades_count"] == 1
        assert len(p2["recent_trades"]) == 2

        # Update risk profile
        upd = await client.patch(
            "/api/v1/markets/paper/settings",
            headers=auth_headers,
            json={"risk_profile": "aggressive"},
        )
        assert upd.status_code == 200
        assert upd.json()["risk_profile"] == "aggressive"

        # Reset portfolio
        rst = await client.post("/api/v1/markets/paper/reset", headers=auth_headers)
        assert rst.status_code == 200
        assert float(rst.json()["cash_balance"]) == 10000.0
        assert len(rst.json()["positions"]) == 0


@pytest.mark.asyncio
async def test_luna_market_analyst_route(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    nvda_chart = _make_uptrend_chart("NVDA", start=130.0, step=0.5)

    with (
        patch("app.ai.graphs.advisor_graph.get_chat_model", return_value=None),
        patch(
            "app.ai.graphs.advisor_graph.fetch_multiple_charts",
            new=AsyncMock(return_value={"NVDA": nvda_chart}),
        ),
        patch("app.ai.graphs.advisor_graph.fetch_nbg_forex_rates", new=AsyncMock(return_value=[])),
    ):
        th = (await client.post("/api/v1/advisor/threads", headers=auth_headers, json={})).json()
        resp = await client.post(
            f"/api/v1/advisor/threads/{th['id']}/stream",
            headers=auth_headers,
            json={"message": "What is NVDA stock price and should I buy it right now?"},
        )
        assert resp.status_code == 200
        assert '"active_agent": "market_analyst"' in resp.text
        assert "NVDA" in resp.text
        assert "Python Quant Engine" in resp.text
