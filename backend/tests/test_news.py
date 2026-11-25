from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.services.news_service import (
    classify_headline_sentiment,
    extract_headline_tickers,
    parse_rss_xml,
)


def test_rss_parsing_sentiment_and_ticker_tagging() -> None:
    sample_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <item>
          <title>NVIDIA surges to record high on strong AI chip growth - CNBC</title>
          <link>https://www.cnbc.com/2026/11/25/nvda-record.html</link>
          <pubDate>Wed, 25 Nov 2026 10:15:00 GMT</pubDate>
          <source>CNBC</source>
          <description>&lt;p&gt;Nvidia beats quarterly revenue estimates as S&amp;amp;P 500 climbs.&lt;/p&gt;</description>
        </item>
        <item>
          <title>National Bank of Georgia holds key rate steady as GEL strengthens</title>
          <link>https://agenda.ge/en/news/nbg-rate</link>
          <pubDate>Wed, 25 Nov 2026 09:00:00 GMT</pubDate>
          <description>Bank of Georgia and TBC Bank report resilient lari deposits.</description>
        </item>
      </channel>
    </rss>"""

    items = parse_rss_xml(sample_xml, category="markets", default_source="Yahoo Finance")
    assert len(items) == 2
    assert items[0]["title"] == "NVIDIA surges to record high on strong AI chip growth"
    assert items[0]["source"] == "CNBC"
    assert items[0]["sentiment"] == "bullish"
    assert "NVDA" in items[0]["tickers"]
    assert "<p>" not in items[0]["summary"]
    assert "USD/GEL" in items[1]["tickers"]

    assert classify_headline_sentiment("Tech stocks plunge on recession fears") == "bearish"
    assert "BTC-USD" in extract_headline_tickers("Bitcoin breaks higher alongside Gold")
    assert "GC=F" in extract_headline_tickers("Bitcoin breaks higher alongside Gold")


@pytest.mark.asyncio
async def test_news_feed_and_ai_briefing_endpoints(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    fake_articles = [
        {
            "id": "art1",
            "title": "NVIDIA surges on AI demand",
            "summary": "Strong data center guidance lifts semiconductor stocks.",
            "url": "https://example.com/nvda",
            "source": "CNBC",
            "category": "markets",
            "sentiment": "bullish",
            "tickers": ["NVDA"],
            "published_at": "2026-11-25T11:00:00+00:00",
            "image_url": None,
        },
        {
            "id": "art2",
            "title": "National Bank of Georgia publishes new GEL outlook",
            "summary": "Lari stability supported by strong remittances and tourism.",
            "url": "https://example.com/nbg",
            "source": "Georgia Economy & NBG",
            "category": "georgia",
            "sentiment": "neutral",
            "tickers": ["USD/GEL"],
            "published_at": "2026-11-25T10:30:00+00:00",
            "image_url": None,
        },
    ]

    with (
        patch(
            "app.api.v1.news.fetch_global_finance_news",
            new=AsyncMock(return_value=fake_articles),
        ),
        patch("app.services.news_service.get_chat_model", return_value=None),
    ):
        r1 = await client.get("/api/v1/news/feed?category=all", headers=auth_headers)
        assert r1.status_code == 200, r1.text
        d1 = r1.json()
        assert d1["total"] == 2
        assert d1["counts"]["markets"] == 1
        assert d1["counts"]["georgia"] == 1

        r2 = await client.get("/api/v1/news/feed?category=georgia", headers=auth_headers)
        assert r2.status_code == 200
        assert r2.json()["total"] == 1
        assert r2.json()["articles"][0]["id"] == "art2"

        br = await client.post(
            "/api/v1/news/ai-briefing",
            headers=auth_headers,
            json={"category": "all"},
        )
        assert br.status_code == 200, br.text
        bdata = br.json()
        assert bdata["articles_analyzed"] == 2
        assert len(bdata["bullets"]) == 3
        assert bdata["personal_takeaway"]
