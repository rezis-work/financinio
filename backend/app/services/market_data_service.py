import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)

HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; FinancinioBot/1.0; +https://financinio.vercel.app)",
    "Accept": "application/json",
}

NBG_URL = "https://nbg.gov.ge/gw/api/ct/monetarypolicy/currencies/en/json/"
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
YAHOO_SEARCH_URL = "https://query1.finance.yahoo.com/v1/finance/search"


@dataclass
class MarketAssetMeta:
    symbol: str
    display_name: str
    asset_type: str  # stock | etf | forex | crypto | commodity
    sector: str


CURATED_UNIVERSE: list[MarketAssetMeta] = [
    # Core ETFs
    MarketAssetMeta("SPY", "SPDR S&P 500 ETF", "etf", "US Index"),
    MarketAssetMeta("QQQ", "Invesco Nasdaq 100 ETF", "etf", "US Tech Index"),
    MarketAssetMeta("VOO", "Vanguard S&P 500 ETF", "etf", "US Index"),
    MarketAssetMeta("SCHD", "Schwab US Dividend Equity", "etf", "Dividend"),
    # Top US Stocks
    MarketAssetMeta("NVDA", "NVIDIA Corp.", "stock", "Semiconductors"),
    MarketAssetMeta("AAPL", "Apple Inc.", "stock", "Technology"),
    MarketAssetMeta("MSFT", "Microsoft Corp.", "stock", "Technology"),
    MarketAssetMeta("AMZN", "Amazon.com Inc.", "stock", "Consumer / Cloud"),
    MarketAssetMeta("GOOGL", "Alphabet Inc.", "stock", "Technology"),
    MarketAssetMeta("META", "Meta Platforms Inc.", "stock", "Technology"),
    MarketAssetMeta("TSLA", "Tesla Inc.", "stock", "EV / AI"),
    MarketAssetMeta("JPM", "JPMorgan Chase & Co.", "stock", "Financials"),
    # Major Forex Pairs
    MarketAssetMeta("EURUSD=X", "EUR / USD", "forex", "Major FX"),
    MarketAssetMeta("GBPUSD=X", "GBP / USD", "forex", "Major FX"),
    MarketAssetMeta("USDJPY=X", "USD / JPY", "forex", "Major FX"),
    # Commodities & Crypto
    MarketAssetMeta("GC=F", "Gold Futures", "commodity", "Precious Metals"),
    MarketAssetMeta("BTC-USD", "Bitcoin (USD)", "crypto", "Crypto"),
    MarketAssetMeta("ETH-USD", "Ethereum (USD)", "crypto", "Crypto"),
]

UNIVERSE_BY_SYMBOL = {a.symbol.upper(): a for a in CURATED_UNIVERSE}


@dataclass
class Candle:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass
class MarketQuoteChart:
    symbol: str
    display_name: str
    asset_type: str
    currency: str
    price: float
    previous_close: float
    change: float
    change_pct: float
    day_high: float | None = None
    day_low: float | None = None
    fifty_two_week_high: float | None = None
    fifty_two_week_low: float | None = None
    candles: list[Candle] = field(default_factory=list)
    source: str = "yahoo_finance"
    fetched_at: str = ""


@dataclass
class NbgForexRate:
    code: str
    name: str
    quantity: int
    rate: float
    rate_per_unit: float
    diff: float
    diff_pct: float
    valid_from: str


# Lightweight in-memory TTL caches (keeps 512MB Fly.io fast & avoids API throttling)
_CHART_CACHE: dict[str, tuple[float, MarketQuoteChart]] = {}
_NBG_CACHE: tuple[float, list[NbgForexRate]] | None = None

CHART_TTL_SECONDS = 180.0  # 3 minutes
NBG_TTL_SECONDS = 900.0  # 15 minutes


def infer_asset_type(symbol: str, quote_type: str | None = None) -> str:
    s = symbol.upper()
    if s in UNIVERSE_BY_SYMBOL:
        return UNIVERSE_BY_SYMBOL[s].asset_type
    qt = (quote_type or "").upper()
    if qt == "ETF":
        return "etf"
    if qt in ("CURRENCY", "FOREX") or s.endswith("=X"):
        return "forex"
    if qt == "CRYPTOCURRENCY" or s.endswith("-USD"):
        return "crypto"
    if qt == "FUTURE" or s.endswith("=F"):
        return "commodity"
    return "stock"


def normalize_symbol(raw: str) -> str:
    s = raw.strip().upper()
    aliases = {
        "EUR/USD": "EURUSD=X",
        "EURUSD": "EURUSD=X",
        "GBP/USD": "GBPUSD=X",
        "GBPUSD": "GBPUSD=X",
        "USD/JPY": "USDJPY=X",
        "USDJPY": "USDJPY=X",
        "USD/GEL": "GEL=X",
        "USDGEL": "GEL=X",
        "EUR/GEL": "EURGEL=X",
        "EURGEL": "EURGEL=X",
        "GOLD": "GC=F",
        "XAUUSD": "GC=F",
        "XAU/USD": "GC=F",
        "BTC": "BTC-USD",
        "BITCOIN": "BTC-USD",
        "ETH": "ETH-USD",
        "ETHEREUM": "ETH-USD",
    }
    return aliases.get(s, s)


async def fetch_nbg_forex_rates(force_refresh: bool = False) -> list[NbgForexRate]:
    """Fetch official National Bank of Georgia (NBG) daily GEL exchange rates."""
    global _NBG_CACHE
    now = time.monotonic()
    if not force_refresh and _NBG_CACHE is not None and (now - _NBG_CACHE[0]) < NBG_TTL_SECONDS:
        return _NBG_CACHE[1]

    featured = ("USD", "EUR", "GBP", "CHF", "TRY", "AED", "JPY", "CAD", "AUD")
    try:
        async with httpx.AsyncClient(timeout=8.0, headers=HTTP_HEADERS) as client:
            resp = await client.get(NBG_URL)
            resp.raise_for_status()
            data = resp.json()

        raw_list = data[0].get("currencies", []) if isinstance(data, list) and data else []
        by_code: dict[str, NbgForexRate] = {}
        for item in raw_list:
            code = str(item.get("code") or "").upper()
            if code not in featured:
                continue
            qty = max(1, int(item.get("quantity") or 1))
            rate = float(item.get("rate") or 0.0)
            diff = float(item.get("diff") or 0.0)
            prev = rate - diff
            diff_pct = round((diff / prev) * 100.0, 3) if prev > 0 else 0.0
            by_code[code] = NbgForexRate(
                code=code,
                name=str(item.get("name") or code),
                quantity=qty,
                rate=round(rate, 4),
                rate_per_unit=round(rate / qty, 6),
                diff=round(diff, 4),
                diff_pct=diff_pct,
                valid_from=str(item.get("validFromDate") or item.get("date") or "")[:10],
            )

        ordered = [by_code[c] for c in featured if c in by_code]
        if ordered:
            _NBG_CACHE = (now, ordered)
            return ordered
    except Exception as exc:
        logger.warning("NBG Forex API fetch failed: %s", exc)

    if _NBG_CACHE is not None:
        return _NBG_CACHE[1]
    return []


async def fetch_symbol_chart(
    symbol: str,
    *,
    range_str: str = "6mo",
    interval: str = "1d",
    force_refresh: bool = False,
) -> MarketQuoteChart | None:
    """Fetch live quote + historical daily OHLCV candles from Yahoo Finance."""
    norm = normalize_symbol(symbol)
    cache_key = f"{norm}:{range_str}:{interval}"
    now = time.monotonic()

    if not force_refresh and cache_key in _CHART_CACHE:
        ts, cached = _CHART_CACHE[cache_key]
        if (now - ts) < CHART_TTL_SECONDS:
            return cached

    url = YAHOO_CHART_URL.format(symbol=norm)
    try:
        async with httpx.AsyncClient(timeout=8.0, headers=HTTP_HEADERS) as client:
            resp = await client.get(url, params={"range": range_str, "interval": interval})
            if resp.status_code != 200:
                logger.warning("Yahoo chart HTTP %s for %s", resp.status_code, norm)
                return None
            payload = resp.json()

        results = payload.get("chart", {}).get("result") or []
        if not results:
            return None
        res = results[0]
        meta = res.get("meta") or {}
        timestamps = res.get("timestamp") or []
        quote_block = (res.get("indicators", {}).get("quote") or [{}])[0]
        opens = quote_block.get("open") or []
        highs = quote_block.get("high") or []
        lows = quote_block.get("low") or []
        closes = quote_block.get("close") or []
        volumes = quote_block.get("volume") or []

        candles: list[Candle] = []
        for idx, ts_val in enumerate(timestamps):
            c_val = closes[idx] if idx < len(closes) else None
            if c_val is None:
                continue
            o_val = opens[idx] if idx < len(opens) and opens[idx] is not None else c_val
            h_val = highs[idx] if idx < len(highs) and highs[idx] is not None else max(o_val, c_val)
            l_val = lows[idx] if idx < len(lows) and lows[idx] is not None else min(o_val, c_val)
            v_val = volumes[idx] if idx < len(volumes) and volumes[idx] is not None else 0.0
            dt_str = datetime.fromtimestamp(int(ts_val), tz=UTC).strftime("%Y-%m-%d")
            candles.append(
                Candle(
                    date=dt_str,
                    open=round(float(o_val), 4),
                    high=round(float(h_val), 4),
                    low=round(float(l_val), 4),
                    close=round(float(c_val), 4),
                    volume=float(v_val),
                )
            )

        price = meta.get("regularMarketPrice")
        if price is None and candles:
            price = candles[-1].close
        if price is None:
            return None
        price_f = float(price)

        prev_close = meta.get("chartPreviousClose") or meta.get("previousClose")
        if len(candles) >= 2:
            # Prefer prior daily candle close for accurate 1-day delta
            prev_close = candles[-2].close
        elif prev_close is None:
            prev_close = price_f
        prev_f = float(prev_close) if float(prev_close) > 0 else price_f

        change = price_f - prev_f
        change_pct = (change / prev_f) * 100.0 if prev_f > 0 else 0.0

        known = UNIVERSE_BY_SYMBOL.get(norm)
        display_name = (
            known.display_name
            if known
            else str(meta.get("shortName") or meta.get("longName") or norm)
        )
        asset_type = infer_asset_type(norm, meta.get("instrumentType"))

        chart = MarketQuoteChart(
            symbol=norm,
            display_name=display_name[:120],
            asset_type=asset_type,
            currency=str(meta.get("currency") or "USD").upper(),
            price=round(price_f, 4),
            previous_close=round(prev_f, 4),
            change=round(change, 4),
            change_pct=round(change_pct, 2),
            day_high=(
                round(float(meta["regularMarketDayHigh"]), 4)
                if meta.get("regularMarketDayHigh") is not None
                else (candles[-1].high if candles else None)
            ),
            day_low=(
                round(float(meta["regularMarketDayLow"]), 4)
                if meta.get("regularMarketDayLow") is not None
                else (candles[-1].low if candles else None)
            ),
            fifty_two_week_high=(
                round(float(meta["fiftyTwoWeekHigh"]), 4)
                if meta.get("fiftyTwoWeekHigh") is not None
                else (max(c.high for c in candles) if candles else None)
            ),
            fifty_two_week_low=(
                round(float(meta["fiftyTwoWeekLow"]), 4)
                if meta.get("fiftyTwoWeekLow") is not None
                else (min(c.low for c in candles) if candles else None)
            ),
            candles=candles,
            source="yahoo_finance",
            fetched_at=datetime.now(UTC).isoformat(),
        )
        _CHART_CACHE[cache_key] = (now, chart)
        return chart
    except Exception as exc:
        logger.warning("Yahoo chart fetch failed for %s: %s", norm, exc)
        return None


async def fetch_multiple_charts(
    symbols: list[str],
    *,
    range_str: str = "6mo",
    max_concurrency: int = 6,
) -> dict[str, MarketQuoteChart]:
    """Fetch multiple symbol charts concurrently with bounded concurrency."""
    sem = asyncio.Semaphore(max_concurrency)
    out: dict[str, MarketQuoteChart] = {}

    async def _one(sym: str) -> None:
        async with sem:
            ch = await fetch_symbol_chart(sym, range_str=range_str)
            if ch is not None:
                out[ch.symbol] = ch

    await asyncio.gather(*[_one(s) for s in dict.fromkeys(symbols)])
    return out


async def search_market_symbols(query: str, limit: int = 8) -> list[dict[str, Any]]:
    """Search global stocks, ETFs, forex pairs, and crypto symbols."""
    q = query.strip()
    if not q:
        return [
            {
                "symbol": a.symbol,
                "display_name": a.display_name,
                "asset_type": a.asset_type,
                "exchange": a.sector,
            }
            for a in CURATED_UNIVERSE[:limit]
        ]

    # First check curated universe matches
    q_low = q.lower()
    local_hits = [
        {
            "symbol": a.symbol,
            "display_name": a.display_name,
            "asset_type": a.asset_type,
            "exchange": a.sector,
        }
        for a in CURATED_UNIVERSE
        if q_low in a.symbol.lower() or q_low in a.display_name.lower()
    ]

    remote_hits: list[dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(timeout=6.0, headers=HTTP_HEADERS) as client:
            resp = await client.get(
                YAHOO_SEARCH_URL,
                params={"q": q, "quotesCount": limit, "newsCount": 0},
            )
            if resp.status_code == 200:
                for item in resp.json().get("quotes") or []:
                    sym = str(item.get("symbol") or "").upper()
                    if not sym:
                        continue
                    remote_hits.append(
                        {
                            "symbol": sym,
                            "display_name": str(
                                item.get("shortname") or item.get("longname") or sym
                            )[:120],
                            "asset_type": infer_asset_type(sym, item.get("quoteType")),
                            "exchange": str(item.get("exchDisp") or item.get("exchange") or ""),
                        }
                    )
    except Exception as exc:
        logger.warning("Yahoo symbol search failed for '%s': %s", q, exc)

    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for hit in [*local_hits, *remote_hits]:
        if hit["symbol"] not in seen:
            seen.add(hit["symbol"])
            merged.append(hit)
        if len(merged) >= limit:
            break
    return merged
