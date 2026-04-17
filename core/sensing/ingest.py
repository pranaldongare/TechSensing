"""
Data ingestion: RSS feeds + DuckDuckGo search.
Returns a list of RawArticle dataclass instances.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import feedparser
import trafilatura

from core.sensing.config import (
    LOOKBACK_DAYS,
    MAX_ARTICLES_PER_FEED,
    MAX_SEARCH_RESULTS,
    get_feeds_for_domain,
    get_search_queries_for_domain,
)

logger = logging.getLogger("sensing.ingest")

# Handle ddgs package rename: try new name first, fall back to old
try:
    from ddgs import DDGS  # type: ignore

    logger.info("Using 'ddgs' package for DuckDuckGo search")
except ImportError:
    from duckduckgo_search import DDGS  # type: ignore

    logger.info("Using 'duckduckgo_search' package for DuckDuckGo search")


@dataclass
class RawArticle:
    title: str
    url: str
    source: str
    published_date: Optional[str] = None  # ISO format
    content: str = ""  # Full extracted text
    snippet: str = ""  # Short excerpt


async def fetch_rss_feeds(
    feed_urls: Optional[List[str]] = None,
    lookback_days: int = LOOKBACK_DAYS,
    domain: str = "Generative AI",
) -> List[RawArticle]:
    """Parse RSS feeds and return articles from the last N days (0 = no limit)."""
    urls = feed_urls or get_feeds_for_domain(domain)
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days) if lookback_days > 0 else None
    articles: List[RawArticle] = []

    logger.info(f"[RSS] Fetching {len(urls)} feeds (lookback={'all' if not cutoff else f'{lookback_days}d'}, domain={domain})")

    for i, url in enumerate(urls):
        try:
            logger.info(f"[RSS {i+1}/{len(urls)}] Parsing: {url}")
            feed = await asyncio.to_thread(feedparser.parse, url)
            source_name = feed.feed.get("title", url)[:50]
            count_before = len(articles)

            for entry in feed.entries[:MAX_ARTICLES_PER_FEED]:
                pub_date = _parse_feed_date(entry)
                if cutoff and pub_date and pub_date < cutoff:
                    continue

                articles.append(
                    RawArticle(
                        title=entry.get("title", "Untitled"),
                        url=entry.get("link", ""),
                        source=source_name,
                        published_date=(
                            pub_date.isoformat() if pub_date else None
                        ),
                        snippet=entry.get("summary", "")[:500],
                    )
                )

            added = len(articles) - count_before
            logger.info(
                f"[RSS {i+1}/{len(urls)}] '{source_name}': {added} articles "
                f"(total entries: {len(feed.entries)})"
            )
        except Exception as e:
            logger.warning(f"[RSS {i+1}/{len(urls)}] FAILED ({url}): {e}")

    logger.info(f"[RSS] Done. Total articles from RSS: {len(articles)}")
    return articles


async def search_duckduckgo(
    queries: Optional[List[str]] = None,
    domain: str = "Generative AI",
    lookback_days: int = LOOKBACK_DAYS,
    must_include: Optional[List[str]] = None,
) -> List[RawArticle]:
    """Run DuckDuckGo searches and return results as RawArticle.

    Runs **both** the news endpoint (returns articles with publication
    dates) and the text endpoint (catches blogs, company announcements,
    and other non-news pages) for each query, then merges and deduplicates
    by URL.  News results are preferred when duplicates exist because they
    carry ``published_date``.
    """
    search_queries = queries or get_search_queries_for_domain(domain, must_include)

    # Map lookback_days to DDG timelimit (0 = no time filter)
    if lookback_days <= 0:
        timelimit = None  # no time restriction
    elif lookback_days <= 7:
        timelimit = "w"  # past week
    elif lookback_days <= 30:
        timelimit = "m"  # past month
    else:
        timelimit = "y"  # past year

    articles: List[RawArticle] = []
    seen_urls: set = set()

    logger.info(f"[DDG] Running {len(search_queries)} searches (timelimit={timelimit})")

    for i, query in enumerate(search_queries):
        try:
            logger.info(f"[DDG {i+1}/{len(search_queries)}] Query: '{query}'")

            # 1. News endpoint — returns articles WITH dates.
            news_results = await asyncio.to_thread(
                _ddgs_news, query, MAX_SEARCH_RESULTS, timelimit
            )
            for r in news_results:
                url = r.get("url", r.get("href", r.get("link", "")))
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                articles.append(
                    RawArticle(
                        title=r.get("title", "Untitled"),
                        url=url,
                        source=r.get("source", "DuckDuckGo News"),
                        snippet=r.get("body", "")[:500],
                        published_date=r.get("date", "")[:25] if r.get("date") else None,
                    )
                )

            # 2. Text endpoint — catches blogs, company pages, docs, etc.
            text_results = await asyncio.to_thread(
                _ddgs_search, query, MAX_SEARCH_RESULTS, timelimit
            )
            for r in text_results:
                url = r.get("href", r.get("link", ""))
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                articles.append(
                    RawArticle(
                        title=r.get("title", "Untitled"),
                        url=url,
                        source="DuckDuckGo",
                        snippet=r.get("body", "")[:500],
                    )
                )

            logger.info(
                f"[DDG {i+1}/{len(search_queries)}] "
                f"news={len(news_results)}, text={len(text_results)}, "
                f"unique_total={len(articles)}"
            )
        except Exception as e:
            logger.warning(
                f"[DDG {i+1}/{len(search_queries)}] FAILED ('{query}'): {e}"
            )

    logger.info(f"[DDG] Done. Total unique articles from DDG: {len(articles)}")
    return articles


async def extract_full_text(article: RawArticle) -> RawArticle:
    """Extract full article text and published date using trafilatura.

    Uses JSON output with metadata to also populate ``published_date``
    when the article doesn't already have one — this is critical for
    date filtering since DDG results arrive without dates.
    """
    if article.content and article.published_date:
        return article
    try:
        downloaded = await asyncio.to_thread(trafilatura.fetch_url, article.url)
        if downloaded:
            import json as _json
            raw = trafilatura.extract(
                downloaded,
                output_format="json",
                with_metadata=True,
            )
            if raw:
                meta = _json.loads(raw)
                text = meta.get("text", "")
                if text and not article.content:
                    article.content = text[:5000]
                # Populate published_date from page metadata if missing.
                if not article.published_date and meta.get("date"):
                    article.published_date = meta["date"]
                return article
    except Exception:
        pass

    # Fallback: use snippet
    if not article.content:
        article.content = article.snippet or article.title
    return article


def _ddgs_news(query: str, max_results: int, timelimit: Optional[str] = "w") -> list:
    """Synchronous DuckDuckGo **news** search — returns articles with dates."""
    try:
        with DDGS() as ddgs:
            return list(ddgs.news(query, max_results=max_results, timelimit=timelimit))
    except Exception as e:
        logger.debug(f"[DDG] news endpoint failed for '{query}': {e}")
        return []


def _ddgs_search(query: str, max_results: int, timelimit: Optional[str] = "w") -> list:
    """Synchronous DuckDuckGo **text** search — catches blogs/docs/announcements."""
    try:
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=max_results, timelimit=timelimit))
    except Exception as e:
        logger.debug(f"[DDG] text endpoint failed for '{query}': {e}")
        return []


def _parse_feed_date(entry) -> Optional[datetime]:
    """Parse feedparser entry date into UTC datetime."""
    for date_field in ("published_parsed", "updated_parsed"):
        parsed = entry.get(date_field)
        if parsed:
            try:
                return datetime(*parsed[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return None
