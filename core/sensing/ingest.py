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
from core.sensing.date_filter import title_mentions_old_year

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

                entry_title = entry.get("title", "Untitled")

                # Early stale-title detection: RSS aggregators (Google News)
                # re-surface old articles with fresh pub dates.  If the title
                # references an old year, skip it.
                if title_mentions_old_year(entry_title, max_age_days=max(lookback_days * 3, 180)):
                    logger.debug(f"[RSS] Skipping stale-titled entry: {entry_title[:80]}")
                    continue

                articles.append(
                    RawArticle(
                        title=entry_title,
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

            stale_age = max(lookback_days * 3, 180)

            # 1. News endpoint — returns articles WITH dates.
            news_results = await asyncio.to_thread(
                _ddgs_news, query, MAX_SEARCH_RESULTS, timelimit
            )
            for r in news_results:
                url = r.get("url", r.get("href", r.get("link", "")))
                if not url or url in seen_urls:
                    continue
                r_title = r.get("title", "Untitled")
                # Skip re-syndicated old news
                if title_mentions_old_year(r_title, max_age_days=stale_age):
                    logger.debug(f"[DDG] Skipping stale-titled news: {r_title[:80]}")
                    continue
                seen_urls.add(url)
                articles.append(
                    RawArticle(
                        title=r_title,
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
                r_title = r.get("title", "Untitled")
                if title_mentions_old_year(r_title, max_age_days=stale_age):
                    logger.debug(f"[DDG] Skipping stale-titled text: {r_title[:80]}")
                    continue
                seen_urls.add(url)
                articles.append(
                    RawArticle(
                        title=r_title,
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

    Also cross-validates the source-provided date against the page's
    actual metadata date.  If they differ significantly (>90 days) and
    the page date is older, the page date is preferred — this catches
    re-syndicated old content served with fresh aggregator dates.
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

                page_date = meta.get("date", "")

                if not article.published_date and page_date:
                    # No source date — use page metadata date
                    article.published_date = page_date
                elif article.published_date and page_date:
                    # Cross-validate: prefer the OLDER of the two dates
                    # because aggregators assign fresh dates to old content.
                    try:
                        from core.sensing.date_filter import parse_iso_date
                        source_dt = parse_iso_date(article.published_date)
                        page_dt = parse_iso_date(page_date)
                        if source_dt and page_dt:
                            diff = abs((source_dt - page_dt).days)
                            if diff > 90 and page_dt < source_dt:
                                logger.debug(
                                    f"[extract] Date mismatch for {article.title[:60]}: "
                                    f"source={article.published_date}, page={page_date} "
                                    f"— using page date"
                                )
                                article.published_date = page_date
                    except Exception:
                        pass

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
