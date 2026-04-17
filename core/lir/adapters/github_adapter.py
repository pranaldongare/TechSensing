"""
GitHub LIR adapter — wraps existing fetch_github_trending() for LIR.

Tier 2: Open-source repos, 6-18 month lead time.
"""

import hashlib
import logging
from datetime import datetime
from typing import List

from core.lir.models import LIRRawItem

logger = logging.getLogger("lir.adapters.github")


class GitHubLIRAdapter:
    """Tier-2 adapter: GitHub trending repositories."""

    source_id: str = "github"
    tier: str = "T2"
    lead_time_prior_days: int = 365  # ~12 months
    authority_prior: float = 0.70

    async def poll(
        self,
        since: datetime,
        max_results: int = 50,
    ) -> List[LIRRawItem]:
        from core.sensing.sources.github_trending import fetch_github_trending

        lookback_days = max(1, (datetime.utcnow() - since.replace(tzinfo=None)).days)

        # Use broad AI/ML queries for LIR discovery
        queries = [
            "machine learning",
            "large language model",
            "transformer neural network",
            "deep learning framework",
        ]

        all_items: List[LIRRawItem] = []
        seen_urls: set = set()

        per_query = max(5, max_results // len(queries))

        for query in queries:
            try:
                articles = await fetch_github_trending(
                    domain=query,
                    lookback_days=lookback_days,
                    max_results=per_query,
                )
                for a in articles:
                    if a.url in seen_urls:
                        continue
                    seen_urls.add(a.url)

                    item_id = f"github:{hashlib.sha256(a.url.encode()).hexdigest()[:12]}"
                    all_items.append(
                        LIRRawItem(
                            item_id=item_id,
                            source_id="github",
                            tier="T2",
                            title=a.title,
                            url=a.url,
                            published_date=a.published_date or "",
                            snippet=a.snippet,
                            content=a.content or a.snippet,
                            categories="GitHub",
                        )
                    )
            except Exception as e:
                logger.warning(f"GitHub LIR query '{query}' failed: {e}")

        logger.info(f"GitHub LIR adapter: {len(all_items)} repos")
        return all_items[:max_results]

    async def backfill(self, start_date: str, end_date: str) -> List[LIRRawItem]:
        """Backfill GitHub repos for a date range."""
        since = datetime.fromisoformat(start_date)
        return await self.poll(since, max_results=200)
