from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from market_research.ingestion.news import NewsAggregator, RssNewsSource


IST = ZoneInfo("Asia/Kolkata")


RSS_SAMPLE = """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<rss version=\"2.0\">
  <channel>
    <title>Sample Feed</title>
    <item>
      <title>Nifty 50 rallies as RBI signals liquidity support</title>
      <link>https://example.com/news/1</link>
      <description>Indian stock market gains on policy optimism.</description>
      <pubDate>Mon, 25 May 2026 10:10:00 +0530</pubDate>
    </item>
    <item>
      <title>Unrelated sports headline</title>
      <link>https://example.com/news/2</link>
      <description>Does not match market keywords.</description>
      <pubDate>Mon, 25 May 2026 10:05:00 +0530</pubDate>
    </item>
  </channel>
</rss>
"""


@pytest.mark.asyncio
async def test_rss_source_filters_by_keywords_and_since(monkeypatch: pytest.MonkeyPatch) -> None:
    source = RssNewsSource(feed_urls=["https://example.com/feed.xml"])

    class DummyResponse:
        def __init__(self, text: str):
            self.text = text

        def raise_for_status(self) -> None:
            return None

    class DummyClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, _url: str, headers: dict[str, str] | None = None):
            return DummyResponse(RSS_SAMPLE)

    monkeypatch.setattr("market_research.ingestion.news.httpx.AsyncClient", lambda timeout=8.0: DummyClient())

    since = datetime(2026, 5, 25, 9, 30, tzinfo=IST)
    items = await source.fetch(since=since, keywords=["nifty 50", "rbi", "india market"])

    assert len(items) == 1
    assert items[0].title.startswith("Nifty 50 rallies")
    assert items[0].relevance_score > 0.0


@pytest.mark.asyncio
async def test_news_aggregator_summary_has_catalysts(monkeypatch: pytest.MonkeyPatch) -> None:
    source = RssNewsSource(feed_urls=["https://example.com/feed.xml"])

    class DummyResponse:
        def __init__(self, text: str):
            self.text = text

        def raise_for_status(self) -> None:
            return None

    class DummyClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, _url: str, headers: dict[str, str] | None = None):
            return DummyResponse(RSS_SAMPLE)

    monkeypatch.setattr("market_research.ingestion.news.httpx.AsyncClient", lambda timeout=8.0: DummyClient())

    aggregator = NewsAggregator(sources=[source])
    since = datetime(2026, 5, 25, 9, 30, tzinfo=IST)
    items = await aggregator.collect(since=since, keywords=["nifty 50", "rbi", "india market"])
    summary = NewsAggregator.summarize(items)

    assert len(items) == 1
    assert summary.source_count == 1
    assert "Collected 1 trade-day news items" in summary.summary
