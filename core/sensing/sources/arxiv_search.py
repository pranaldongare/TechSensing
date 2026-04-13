"""
arXiv Paper Search — fetches recent papers matching a domain query.

Uses the arXiv Atom API with feedparser.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import feedparser
import httpx

from core.sensing.ingest import RawArticle

logger = logging.getLogger("sensing.sources.arxiv")

ARXIV_MAX_RESULTS = 20
ARXIV_API_URL = "https://export.arxiv.org/api/query"


async def fetch_arxiv_papers(
    domain: str,
    lookback_days: int = 7,
    max_results: int = ARXIV_MAX_RESULTS,
    must_include: Optional[list[str]] = None,
) -> List[RawArticle]:
    """Fetch recent arXiv papers for a domain."""
    query_parts = [f"all:{domain}"]
    if must_include:
        for kw in must_include[:3]:
            query_parts.append(f"all:{kw}")
    search_query = " AND ".join(query_parts)

    articles: List[RawArticle] = []

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                ARXIV_API_URL,
                params={
                    "search_query": search_query,
                    "sortBy": "submittedDate",
                    "sortOrder": "descending",
                    "max_results": max_results,
                },
            )
            resp.raise_for_status()

        feed = feedparser.parse(resp.text)
        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days) if lookback_days > 0 else None

        for entry in feed.entries:
            # Parse published date
            published = entry.get("published", "")
            if cutoff:
                try:
                    pub_dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
                    if pub_dt < cutoff:
                        continue
                except (ValueError, TypeError):
                    pass

            authors = ", ".join(a.get("name", "") for a in entry.get("authors", [])[:3])
            categories = " | ".join(t.get("term", "") for t in entry.get("tags", [])[:3])

            articles.append(RawArticle(
                title=entry.get("title", "").replace("\n", " ").strip(),
                url=entry.get("link", ""),
                source="arXiv",
                published_date=published,
                snippet=f"{authors} | {categories}",
                content=entry.get("summary", "").replace("\n", " ").strip(),
            ))

        logger.info(f"arXiv: fetched {len(articles)} papers for '{domain}'")

    except Exception as e:
        logger.warning(f"arXiv fetch failed: {e}")

    return articles
