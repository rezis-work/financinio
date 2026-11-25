from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.markets import MarketWatchlistItem, PaperPosition
from app.models.user import User
from app.schemas.news import (
    NewsArticleResponse,
    NewsBriefingRequest,
    NewsBriefingResponse,
    NewsCategory,
    NewsFeedResponse,
)
from app.services.news_service import fetch_global_finance_news, generate_luna_news_briefing
from app.services.quota_service import enforce_ai_quota

router = APIRouter(prefix="/news", tags=["Global Finance Newsroom"])


async def _user_portfolio_symbols(db: AsyncSession, user: User) -> list[str]:
    wl = (
        await db.scalars(
            select(MarketWatchlistItem.symbol).where(MarketWatchlistItem.user_id == user.id)
        )
    ).all()
    pos = (
        await db.scalars(select(PaperPosition.symbol).where(PaperPosition.user_id == user.id))
    ).all()
    ordered = list(dict.fromkeys([*pos, *wl]))
    return ordered[:10]


@router.get("/feed", response_model=NewsFeedResponse)
async def get_global_news_feed(
    category: NewsCategory = Query(default="all"),
    q: str = Query(default="", max_length=120),
    force_refresh: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NewsFeedResponse:
    """Fetch live global finance, Wall Street, macro/FX, Georgia/NBG, crypto & personalized portfolio news."""
    symbols = await _user_portfolio_symbols(db, current_user)
    all_articles = await fetch_global_finance_news(
        portfolio_symbols=symbols, force_refresh=force_refresh
    )

    sym_set = {s.upper() for s in symbols}

    def is_for_you(art: dict) -> bool:
        if art["category"] == "for_you":
            return True
        if any(t in sym_set for t in art.get("tickers", [])):
            return True
        if current_user.base_currency.upper() == "GEL" and art["category"] == "georgia":
            return True
        return False

    counts = {
        "all": len(all_articles),
        "for_you": sum(1 for a in all_articles if is_for_you(a)),
        "markets": sum(1 for a in all_articles if a["category"] == "markets"),
        "macro_fx": sum(1 for a in all_articles if a["category"] == "macro_fx"),
        "georgia": sum(1 for a in all_articles if a["category"] == "georgia"),
        "crypto_gold": sum(1 for a in all_articles if a["category"] == "crypto_gold"),
    }

    if category == "all":
        filtered = all_articles
    elif category == "for_you":
        filtered = [a for a in all_articles if is_for_you(a)]
    else:
        filtered = [a for a in all_articles if a["category"] == category]

    needle = q.strip().lower()
    if needle:
        filtered = [
            a
            for a in filtered
            if needle
            in f"{a['title']} {a['summary']} {a['source']} {' '.join(a.get('tickers', []))}".lower()
        ]

    return NewsFeedResponse(
        category=category,
        total=len(filtered),
        counts=counts,
        portfolio_symbols=symbols,
        updated_at=datetime.now(UTC).isoformat(),
        articles=[NewsArticleResponse(**a) for a in filtered[:60]],
    )


@router.post("/ai-briefing", response_model=NewsBriefingResponse)
async def get_luna_news_briefing(
    payload: NewsBriefingRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NewsBriefingResponse:
    """Generate Luna's 3-bullet executive Market Pulse from the latest live headlines."""
    enforce_ai_quota(current_user)
    symbols = await _user_portfolio_symbols(db, current_user)
    all_articles = await fetch_global_finance_news(portfolio_symbols=symbols)

    if payload.category == "all":
        scoped = all_articles
    elif payload.category == "for_you":
        sym_set = {s.upper() for s in symbols}
        scoped = [
            a
            for a in all_articles
            if a["category"] == "for_you"
            or any(t in sym_set for t in a.get("tickers", []))
            or (current_user.base_currency.upper() == "GEL" and a["category"] == "georgia")
        ]
    else:
        scoped = [a for a in all_articles if a["category"] == payload.category]

    briefing = await generate_luna_news_briefing(
        category=payload.category,
        articles=scoped or all_articles,
        base_currency=current_user.base_currency,
        portfolio_symbols=symbols,
    )
    return NewsBriefingResponse(**briefing)
