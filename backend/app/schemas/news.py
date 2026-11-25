from typing import Literal

from pydantic import BaseModel, Field

NewsCategory = Literal["all", "for_you", "markets", "macro_fx", "georgia", "crypto_gold"]
NewsSentiment = Literal["bullish", "bearish", "neutral"]


class NewsArticleResponse(BaseModel):
    id: str
    title: str
    summary: str
    url: str
    source: str
    category: Literal["markets", "macro_fx", "georgia", "crypto_gold", "for_you"]
    sentiment: NewsSentiment = "neutral"
    tickers: list[str] = Field(default_factory=list)
    published_at: str
    image_url: str | None = None


class NewsFeedResponse(BaseModel):
    category: NewsCategory
    total: int
    counts: dict[str, int]
    portfolio_symbols: list[str] = Field(default_factory=list)
    updated_at: str
    articles: list[NewsArticleResponse]


class NewsBriefingRequest(BaseModel):
    category: NewsCategory = "all"


class NewsBriefingResponse(BaseModel):
    category: NewsCategory
    headline: str
    bullets: list[str]
    personal_takeaway: str
    articles_analyzed: int
    generated_at: str
