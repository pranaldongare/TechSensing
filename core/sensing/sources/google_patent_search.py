"""
Google Patents Search — fetches recent patents via Tavily site-restricted search.

Uses the Tavily API to search patents.google.com for patent documents
matching domain-specific keywords.

Set TAVILY_API_KEY in .env to enable.
See: https://tavily.com/
"""

import asyncio
import logging
import os
from typing import List, Optional

from core.sensing.ingest import RawArticle

logger = logging.getLogger("sensing.sources.google_patents")

GOOGLE_PATENT_MAX_RESULTS = 10


def _get_tavily_key() -> str | None:
    """Get Tavily API key from environment."""
    return os.environ.get("TAVILY_API_KEY", "").strip() or None


async def _tavily_search(query: str, max_results: int = 5) -> list[dict]:
    """Run a single Tavily search with retry logic. Returns list of result dicts."""
    from tavily import TavilyClient

    api_key = _get_tavily_key()
    if not api_key:
        return []

    client = TavilyClient(api_key=api_key)
    attempts = 0

    while attempts < 3:
        try:
            response = await asyncio.to_thread(
                client.search,
                query=query,
                search_depth="advanced",
                max_results=max_results,
                include_answer=False,
            )
            return response.get("results", [])
        except Exception as e:
            attempts += 1
            logger.debug(f"Tavily search attempt {attempts} failed: {e}")
            if attempts >= 3:
                return []
            await asyncio.sleep(1)

    return []


async def search_google_patents(
    domain: str,
    lookback_days: int = 365,
    max_results: int = GOOGLE_PATENT_MAX_RESULTS,
    must_include: Optional[List[str]] = None,
) -> List[RawArticle]:
    """Fetch recent patents from Google Patents via Tavily.

    Args:
        domain: Target technology domain (e.g., "Generative AI").
        lookback_days: Not directly used (Tavily recency is approximate).
        max_results: Maximum patents to return.
        must_include: Additional keywords to include in the search.

    Returns:
        List of RawArticle objects representing patent filings.
    """
    api_key = _get_tavily_key()
    if not api_key:
        logger.info(
            "Google Patents search skipped: TAVILY_API_KEY not set in .env"
        )
        return []

    # Build keyword queries — domain + top must_include keywords
    keywords = [domain]
    if must_include:
        keywords.extend(must_include[:5])

    # Search in batches — each keyword gets a site-restricted query
    # Limit to 3 queries to stay within reasonable API usage
    search_keywords = keywords[:3]
    results_per_query = max(2, max_results // len(search_keywords))

    all_results: list[dict] = []
    seen_urls: set[str] = set()

    for kw in search_keywords:
        query = f"site:patents.google.com {kw}"
        logger.debug(f"Google Patents query: {query}")

        results = await _tavily_search(query, max_results=results_per_query)

        for r in results:
            url = r.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_results.append(r)

    # Convert to RawArticle objects
    articles: List[RawArticle] = []
    for r in all_results[:max_results]:
        title = r.get("title", "").strip()
        url = r.get("url", "").strip()
        content = r.get("content", "").strip()

        if not title or not url:
            continue

        # Skip non-patent URLs that may slip through
        if "patents.google.com" not in url:
            continue

        articles.append(RawArticle(
            title=title,
            url=url,
            source="Google Patent",
            published_date="",
            snippet=f"Patent found via Google Patents search",
            content=content,
        ))

    logger.info(f"Google Patents: fetched {len(articles)} patents for '{domain}'")
    return articles
