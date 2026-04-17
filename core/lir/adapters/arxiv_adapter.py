"""
arXiv LIR adapter — wraps existing arXiv search with LIR-specific
category-based queries and returns LIRRawItem instances.
"""

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import feedparser
import httpx

from core.lir.config import ARXIV_CATEGORIES, LIR_LOOKBACK_DAYS
from core.lir.models import LIRRawItem

logger = logging.getLogger("lir.adapters.arxiv")

ARXIV_API_URL = "https://export.arxiv.org/api/query"
ARXIV_MAX_PER_CATEGORY = 30


class ArxivLIRAdapter:
    """Tier-1 adapter: arXiv academic preprints."""

    source_id: str = "arxiv"
    tier: str = "T1"
    lead_time_prior_days: int = 730  # ~24 months
    authority_prior: float = 0.85

    async def poll(
        self,
        since: datetime,
        max_results: int = 50,
    ) -> List[LIRRawItem]:
        """Fetch recent arXiv papers across configured categories."""
        all_items: List[LIRRawItem] = []
        seen_urls: set = set()

        per_cat = min(max_results // max(len(ARXIV_CATEGORIES), 1), ARXIV_MAX_PER_CATEGORY)

        for cat in ARXIV_CATEGORIES:
            try:
                items = await self._fetch_category(cat, since, per_cat)
                for item in items:
                    if item.url not in seen_urls:
                        seen_urls.add(item.url)
                        all_items.append(item)
            except Exception as e:
                logger.warning(f"arXiv category {cat} failed: {e}")

        logger.info(f"arXiv adapter: {len(all_items)} unique papers from {len(ARXIV_CATEGORIES)} categories")
        return all_items

    async def _fetch_category(
        self,
        category: str,
        since: datetime,
        max_results: int,
    ) -> List[LIRRawItem]:
        """Fetch papers from a single arXiv category."""
        search_query = f"cat:{category}"

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
        items: List[LIRRawItem] = []

        for entry in feed.entries:
            published = entry.get("published", "")
            try:
                pub_dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
                if pub_dt < since:
                    continue
            except (ValueError, TypeError):
                continue  # Skip entries without valid dates

            url = entry.get("link", "")
            title = entry.get("title", "").replace("\n", " ").strip()
            authors = ", ".join(
                a.get("name", "") for a in entry.get("authors", [])[:5]
            )
            categories = " | ".join(
                t.get("term", "") for t in entry.get("tags", [])
            )
            abstract = entry.get("summary", "").replace("\n", " ").strip()

            item_id = f"arxiv:{hashlib.sha256(url.encode()).hexdigest()[:12]}"

            items.append(
                LIRRawItem(
                    item_id=item_id,
                    source_id="arxiv",
                    tier="T1",
                    title=title,
                    url=url,
                    published_date=published,
                    snippet=abstract[:500],
                    content=abstract,
                    authors=authors,
                    categories=categories,
                )
            )

        logger.info(f"arXiv [{category}]: {len(items)} papers since {since.date()}")
        return items
