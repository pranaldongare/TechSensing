"""Unit tests for core.sensing.dedup — URL normalization and fuzzy title dedup."""

import pytest

from core.sensing.dedup import (
    _is_title_duplicate,
    _normalize_url,
    deduplicate_articles,
)
from core.sensing.ingest import RawArticle


@pytest.mark.unit
class TestNormalizeUrl:
    def test_strips_utm_params(self):
        url = "https://example.com/article?utm_source=twitter&utm_medium=social&id=123"
        result = _normalize_url(url)
        assert "utm_source" not in result
        assert "utm_medium" not in result
        assert "id=123" in result

    def test_strips_fbclid(self):
        url = "https://example.com/page?fbclid=abc123"
        result = _normalize_url(url)
        assert "fbclid" not in result

    def test_lowercases(self):
        url = "https://Example.COM/Article"
        result = _normalize_url(url)
        assert result == "https://example.com/article"

    def test_removes_trailing_slash(self):
        url = "https://example.com/article/"
        result = _normalize_url(url)
        assert not result.endswith("/")

    def test_removes_fragment(self):
        url = "https://example.com/article#section1"
        result = _normalize_url(url)
        assert "#" not in result

    def test_preserves_non_tracking_params(self):
        url = "https://example.com/search?q=AI&page=2"
        result = _normalize_url(url)
        assert "q=AI" in result or "q=ai" in result.lower()
        assert "page=2" in result

    def test_handles_malformed_url(self):
        url = "not a real url"
        result = _normalize_url(url)
        assert result == "not a real url"


@pytest.mark.unit
class TestIsTitleDuplicate:
    def test_exact_match(self):
        assert _is_title_duplicate("Hello World", ["hello world"]) is True

    def test_near_match(self):
        assert (
            _is_title_duplicate(
                "OpenAI releases GPT-5 model",
                ["openai releases gpt-5 model today"],
            )
            is True
        )

    def test_different_titles(self):
        assert (
            _is_title_duplicate(
                "New AI model released",
                ["quantum computing breakthrough"],
            )
            is False
        )

    def test_empty_seen_list(self):
        assert _is_title_duplicate("Any title", []) is False

    def test_case_insensitive(self):
        assert _is_title_duplicate("ALL CAPS TITLE", ["all caps title"]) is True


@pytest.mark.unit
class TestDeduplicateArticles:
    def _make_article(self, title="Test", url="https://example.com", source="Test"):
        return RawArticle(title=title, url=url, source=source)

    def test_removes_url_dupes(self):
        articles = [
            self._make_article(title="A", url="https://example.com/a"),
            self._make_article(title="B", url="https://example.com/a"),
        ]
        result = deduplicate_articles(articles)
        assert len(result) == 1
        assert result[0].title == "A"

    def test_removes_url_dupes_with_tracking(self):
        articles = [
            self._make_article(title="A", url="https://example.com/a"),
            self._make_article(
                title="B", url="https://example.com/a?utm_source=twitter"
            ),
        ]
        result = deduplicate_articles(articles)
        assert len(result) == 1

    def test_removes_title_dupes(self):
        articles = [
            self._make_article(
                title="OpenAI launches GPT-5", url="https://site1.com/a"
            ),
            self._make_article(
                title="OpenAI launches GPT-5 model", url="https://site2.com/b"
            ),
        ]
        result = deduplicate_articles(articles)
        assert len(result) == 1

    def test_preserves_unique(self):
        articles = [
            self._make_article(title="AI News", url="https://a.com/1"),
            self._make_article(title="Quantum Computing", url="https://b.com/2"),
            self._make_article(title="Robotics Update", url="https://c.com/3"),
        ]
        result = deduplicate_articles(articles)
        assert len(result) == 3

    def test_empty_list(self):
        assert deduplicate_articles([]) == []
