"""
Patent LIR adapter — wraps existing Google Patents search via Tavily.

Tier 1: Patent filings, 12-36 month lead time.
Requires TAVILY_API_KEY environment variable.
"""

import hashlib
import logging
import os
from datetime import datetime
from typing import List

from core.lir.models import LIRRawItem

logger = logging.getLogger("lir.adapters.patent")

# AI/ML patent search keywords
PATENT_KEYWORDS = [
    "artificial intelligence",
    "machine learning",
    "neural network",
    "large language model",
    "generative AI",
    "computer vision",
    "reinforcement learning",
    "transformer architecture",
]


class PatentLIRAdapter:
    """Tier-1 adapter: Patent filings from Google Patents via Tavily."""

    source_id: str = "patents"
    tier: str = "T1"
    lead_time_prior_days: int = 730  # ~24 months
    authority_prior: float = 0.80

    async def poll(
        self,
        since: datetime,
        max_results: int = 50,
    ) -> List[LIRRawItem]:
        """Fetch recent AI/ML patents via Tavily search."""
        api_key = os.environ.get("TAVILY_API_KEY", "").strip()
        if not api_key:
            logger.info("Patent adapter skipped: TAVILY_API_KEY not set")
            return []

        from core.sensing.sources.google_patent_search import _tavily_search

        all_items: List[LIRRawItem] = []
        seen_urls: set = set()

        per_keyword = max(2, max_results // max(len(PATENT_KEYWORDS), 1))
        keywords_to_search = PATENT_KEYWORDS[: max(3, max_results // per_keyword)]

        for keyword in keywords_to_search:
            try:
                query = f"site:patents.google.com {keyword}"
                results = await _tavily_search(query, max_results=per_keyword)

                for r in results:
                    url = r.get("url", "").strip()
                    title = r.get("title", "").strip()
                    content = r.get("content", "").strip()

                    if not url or not title:
                        continue
                    if "patents.google.com" not in url:
                        continue
                    if url in seen_urls:
                        continue

                    seen_urls.add(url)
                    item_id = f"patent:{hashlib.sha256(url.encode()).hexdigest()[:12]}"

                    all_items.append(
                        LIRRawItem(
                            item_id=item_id,
                            source_id="patents",
                            tier="T1",
                            title=title,
                            url=url,
                            published_date="",  # Patents don't have precise dates from Tavily
                            snippet=content[:500] if content else "",
                            content=content,
                            categories=keyword,
                        )
                    )
            except Exception as e:
                logger.warning(f"Patent search for '{keyword}' failed: {e}")

        logger.info(f"Patent adapter: {len(all_items)} patents found")
        return all_items[:max_results]

    async def backfill(
        self,
        start_date: str,
        end_date: str,
    ) -> List[LIRRawItem]:
        """Backfill patents for a date range.

        Note: Tavily doesn't support precise date filtering,
        so this returns the same as poll().
        """
        since = datetime.fromisoformat(start_date)
        return await self.poll(since, max_results=100)
