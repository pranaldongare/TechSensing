"""
Reddit LIR adapter — subreddit-based open-ended discovery.

Tier 3: Community chatter, 1-6 month lead time.
Monitors top posts from diverse tech subreddits without keyword filters,
letting the LLM extraction step determine relevance.
"""

import hashlib
import logging
from datetime import datetime
from typing import List

from core.lir.models import LIRRawItem

logger = logging.getLogger("lir.adapters.reddit")

# Curated tech subreddits covering diverse domains
TECH_SUBREDDITS = [
    "programming",
    "technology",
    "MachineLearning",
    "compsci",
    "netsec",
    "devops",
    "rust",
    "golang",
    "webdev",
    "selfhosted",
    "datascience",
    "robotics",
]


class RedditLIRAdapter:
    """Tier-3 adapter: Reddit discussions (subreddit-based discovery)."""

    source_id: str = "reddit"
    tier: str = "T3"
    lead_time_prior_days: int = 60  # ~2 months
    authority_prior: float = 0.45

    async def poll(
        self,
        since: datetime,
        max_results: int = 50,
    ) -> List[LIRRawItem]:
        from core.sensing.sources.reddit_search import search_reddit

        lookback_days = max(1, (datetime.utcnow() - since.replace(tzinfo=None)).days)

        # Mix of subreddit browsing + broad queries
        # Subreddit names serve as queries to fetch top posts from each
        queries = TECH_SUBREDDITS[:8]  # Top 8 subreddits

        # Add a few broad cross-domain discovery queries
        queries.extend([
            "emerging technology",
            "new programming language",
            "open source project",
        ])

        all_items: List[LIRRawItem] = []
        seen_urls: set = set()

        per_query = max(3, max_results // len(queries))

        for query in queries:
            try:
                articles = await search_reddit(
                    domain=query,
                    lookback_days=lookback_days,
                    max_results=per_query,
                )
                for a in articles:
                    if a.url in seen_urls:
                        continue
                    seen_urls.add(a.url)

                    item_id = f"reddit:{hashlib.sha256(a.url.encode()).hexdigest()[:12]}"
                    all_items.append(
                        LIRRawItem(
                            item_id=item_id,
                            source_id="reddit",
                            tier="T3",
                            title=a.title,
                            url=a.url,
                            published_date=a.published_date or "",
                            snippet=a.snippet,
                            content=a.content or a.snippet,
                            categories="Reddit",
                        )
                    )
            except Exception as e:
                logger.warning(f"Reddit LIR query '{query}' failed: {e}")

        logger.info(f"Reddit LIR adapter: {len(all_items)} posts")
        return all_items[:max_results]

    async def backfill(self, start_date: str, end_date: str) -> List[LIRRawItem]:
        """Backfill Reddit posts for a date range."""
        since = datetime.fromisoformat(start_date)
        return await self.poll(since, max_results=200)
