"""
HackerNews LIR adapter — wraps existing fetch_hackernews() for LIR.

Tier 3: Community chatter, 1-6 month lead time.
"""

import hashlib
import logging
from datetime import datetime
from typing import List

from core.lir.models import LIRRawItem

logger = logging.getLogger("lir.adapters.hackernews")


class HackerNewsLIRAdapter:
    """Tier-3 adapter: Hacker News stories."""

    source_id: str = "hackernews"
    tier: str = "T3"
    lead_time_prior_days: int = 90  # ~3 months
    authority_prior: float = 0.50

    async def poll(
        self,
        since: datetime,
        max_results: int = 50,
    ) -> List[LIRRawItem]:
        from core.sensing.sources.hackernews import fetch_hackernews

        lookback_days = max(1, (datetime.utcnow() - since.replace(tzinfo=None)).days)

        queries = [
            "AI",
            "machine learning",
            "LLM",
            "open source AI",
        ]

        all_items: List[LIRRawItem] = []
        seen_urls: set = set()

        per_query = max(5, max_results // len(queries))

        for query in queries:
            try:
                articles = await fetch_hackernews(
                    domain=query,
                    lookback_days=lookback_days,
                    max_results=per_query,
                )
                for a in articles:
                    if a.url in seen_urls:
                        continue
                    seen_urls.add(a.url)

                    item_id = f"hn:{hashlib.sha256(a.url.encode()).hexdigest()[:12]}"
                    all_items.append(
                        LIRRawItem(
                            item_id=item_id,
                            source_id="hackernews",
                            tier="T3",
                            title=a.title,
                            url=a.url,
                            published_date=a.published_date or "",
                            snippet=a.snippet,
                            content=a.content or a.snippet,
                            categories="Hacker News",
                        )
                    )
            except Exception as e:
                logger.warning(f"HN LIR query '{query}' failed: {e}")

        logger.info(f"HN LIR adapter: {len(all_items)} stories")
        return all_items[:max_results]

    async def backfill(self, start_date: str, end_date: str) -> List[LIRRawItem]:
        """Backfill HN stories for a date range."""
        since = datetime.fromisoformat(start_date)
        return await self.poll(since, max_results=200)
