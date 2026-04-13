"""Unit tests for core.sensing.ingest — RSS feeds, DuckDuckGo, text extraction."""

import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.sensing.ingest import (
    RawArticle,
    _parse_feed_date,
    extract_full_text,
    fetch_rss_feeds,
    search_duckduckgo,
)


@pytest.mark.unit
class TestParseFeedDate:
    def test_valid_published_parsed(self):
        entry = {"published_parsed": time.struct_time((2026, 3, 25, 12, 0, 0, 0, 84, 0))}
        result = _parse_feed_date(entry)
        assert result is not None
        assert result.year == 2026
        assert result.month == 3
        assert result.day == 25

    def test_fallback_updated_parsed(self):
        entry = {"updated_parsed": time.struct_time((2026, 3, 20, 8, 0, 0, 0, 79, 0))}
        result = _parse_feed_date(entry)
        assert result is not None
        assert result.day == 20

    def test_no_date_returns_none(self):
        entry = {"title": "No date here"}
        result = _parse_feed_date(entry)
        assert result is None

    def test_invalid_date_returns_none(self):
        entry = {"published_parsed": "not a struct"}
        result = _parse_feed_date(entry)
        assert result is None


@pytest.mark.unit
class TestFetchRssFeeds:
    @pytest.mark.asyncio
    @patch("core.sensing.ingest.feedparser.parse")
    async def test_returns_articles_within_lookback(self, mock_parse):
        now = datetime.now(timezone.utc)
        mock_feed = MagicMock()
        mock_feed.feed.get.return_value = "Test Feed"
        mock_entry = {
            "title": "Test Article",
            "link": "https://example.com/article",
            "summary": "A test article",
            "published_parsed": now.timetuple(),
        }
        mock_feed.entries = [mock_entry]
        mock_parse.return_value = mock_feed

        articles = await fetch_rss_feeds(
            feed_urls=["https://test.com/rss"], lookback_days=7
        )
        assert len(articles) == 1
        assert articles[0].title == "Test Article"
        assert articles[0].url == "https://example.com/article"

    @pytest.mark.asyncio
    @patch("core.sensing.ingest.feedparser.parse")
    async def test_filters_old_articles(self, mock_parse):
        mock_feed = MagicMock()
        mock_feed.feed.get.return_value = "Old Feed"
        old_entry = {
            "title": "Old Article",
            "link": "https://example.com/old",
            "summary": "Old",
            "published_parsed": time.struct_time((2020, 1, 1, 0, 0, 0, 0, 1, 0)),
        }
        mock_feed.entries = [old_entry]
        mock_parse.return_value = mock_feed

        articles = await fetch_rss_feeds(
            feed_urls=["https://test.com/rss"], lookback_days=7
        )
        assert len(articles) == 0

    @pytest.mark.asyncio
    @patch("core.sensing.ingest.feedparser.parse")
    async def test_handles_feed_error(self, mock_parse):
        mock_parse.side_effect = Exception("Network error")
        articles = await fetch_rss_feeds(
            feed_urls=["https://broken.com/rss"], lookback_days=7
        )
        assert articles == []


@pytest.mark.unit
class TestSearchDuckduckgo:
    @pytest.mark.asyncio
    @patch("core.sensing.ingest._ddgs_search")
    async def test_returns_articles(self, mock_ddgs):
        mock_ddgs.return_value = [
            {
                "title": "DDG Result",
                "href": "https://example.com/ddg",
                "body": "Search result snippet",
            }
        ]
        articles = await search_duckduckgo(
            queries=["test query"], domain="AI"
        )
        assert len(articles) == 1
        assert articles[0].title == "DDG Result"
        assert articles[0].source == "DuckDuckGo"

    @pytest.mark.asyncio
    @patch("core.sensing.ingest._ddgs_search")
    async def test_handles_search_error(self, mock_ddgs):
        mock_ddgs.side_effect = Exception("Rate limited")
        articles = await search_duckduckgo(
            queries=["test query"], domain="AI"
        )
        assert articles == []


@pytest.mark.unit
class TestExtractFullText:
    @pytest.mark.asyncio
    @patch("core.sensing.ingest.trafilatura")
    async def test_extracts_text(self, mock_traf):
        mock_traf.fetch_url.return_value = "<html>content</html>"
        mock_traf.extract.return_value = "Extracted article text here."

        article = RawArticle(
            title="Test", url="https://example.com", source="Test"
        )
        result = await extract_full_text(article)
        assert result.content == "Extracted article text here."

    @pytest.mark.asyncio
    @patch("core.sensing.ingest.trafilatura")
    async def test_fallback_to_snippet(self, mock_traf):
        mock_traf.fetch_url.return_value = None

        article = RawArticle(
            title="Test",
            url="https://example.com",
            source="Test",
            snippet="Fallback snippet",
        )
        result = await extract_full_text(article)
        assert result.content == "Fallback snippet"

    @pytest.mark.asyncio
    @patch("core.sensing.ingest.trafilatura")
    async def test_fallback_to_title(self, mock_traf):
        mock_traf.fetch_url.side_effect = Exception("Failed")

        article = RawArticle(
            title="Only Title", url="https://example.com", source="Test"
        )
        result = await extract_full_text(article)
        assert result.content == "Only Title"

    @pytest.mark.asyncio
    async def test_skips_if_content_already_present(self):
        article = RawArticle(
            title="Test",
            url="https://example.com",
            source="Test",
            content="Already has content",
        )
        result = await extract_full_text(article)
        assert result.content == "Already has content"
