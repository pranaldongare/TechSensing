"""
Deduplication of collected articles.
Uses URL normalization + fuzzy title matching.
"""

from difflib import SequenceMatcher
from typing import List
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from core.sensing.config import DEDUP_SIMILARITY_THRESHOLD
from core.sensing.ingest import RawArticle


def deduplicate_articles(articles: List[RawArticle]) -> List[RawArticle]:
    """Remove duplicate articles by URL normalization + fuzzy title matching."""
    seen_urls: set[str] = set()
    seen_titles: list[str] = []
    unique: List[RawArticle] = []

    for article in articles:
        norm_url = _normalize_url(article.url)

        # URL-based dedup
        if norm_url in seen_urls:
            continue

        # Title-based fuzzy dedup
        if _is_title_duplicate(article.title, seen_titles):
            continue

        seen_urls.add(norm_url)
        seen_titles.append(article.title.lower().strip())
        unique.append(article)

    return unique


def _normalize_url(url: str) -> str:
    """Strip tracking params and normalize URL for comparison."""
    try:
        parsed = urlparse(url)
        # Remove common tracking parameters
        params = parse_qs(parsed.query)
        tracking_keys = {
            "utm_source",
            "utm_medium",
            "utm_campaign",
            "utm_content",
            "utm_term",
            "ref",
            "source",
            "fbclid",
            "gclid",
        }
        cleaned = {k: v for k, v in params.items() if k not in tracking_keys}
        clean_query = urlencode(cleaned, doseq=True)
        return (
            urlunparse(parsed._replace(query=clean_query, fragment=""))
            .rstrip("/")
            .lower()
        )
    except Exception:
        return url.lower().strip()


def _is_title_duplicate(title: str, seen_titles: list[str]) -> bool:
    """Check if a title is too similar to any previously seen title."""
    normalized = title.lower().strip()
    for seen in seen_titles:
        ratio = SequenceMatcher(None, normalized, seen).ratio()
        if ratio >= DEDUP_SIMILARITY_THRESHOLD:
            return True
    return False
