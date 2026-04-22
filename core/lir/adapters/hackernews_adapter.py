"""
HackerNews LIR adapter — open-ended discovery from front page and Show HN.

Tier 3: Community chatter, 1-6 month lead time.
Fetches top/new/Show HN stories without keyword filters, letting the
LLM extraction step determine tech relevance.
"""

import hashlib
import logging
from datetime import datetime
from typing import List

import httpx

from core.lir.models import LIRRawItem

logger = logging.getLogger("lir.adapters.hackernews")

HN_API_BASE = "https://hacker-news.firebaseio.com/v0"
HN_ALGOLIA = "https://hn.algolia.com/api/v1"


class HackerNewsLIRAdapter:
    """Tier-3 adapter: Hacker News stories (open-ended discovery)."""

    source_id: str = "hackernews"
    tier: str = "T3"
    lead_time_prior_days: int = 90  # ~3 months
    authority_prior: float = 0.50

    async def poll(
        self,
        since: datetime,
        max_results: int = 50,
    ) -> List[LIRRawItem]:
        all_items: List[LIRRawItem] = []
        seen_urls: set = set()

        # Strategy 1: Algolia "Show HN" posts (builder-made projects)
        try:
            show_hn = await self._fetch_algolia_stories(
                "show_hn", since, max_results=max_results // 3
            )
            for item in show_hn:
                if item.url not in seen_urls:
                    seen_urls.add(item.url)
                    all_items.append(item)
        except Exception as e:
            logger.warning(f"HN Show HN fetch failed: {e}")

        # Strategy 2: Recent front-page stories (broad tech signal)
        try:
            front_page = await self._fetch_algolia_stories(
                "front_page", since, max_results=max_results // 3
            )
            for item in front_page:
                if item.url not in seen_urls:
                    seen_urls.add(item.url)
                    all_items.append(item)
        except Exception as e:
            logger.warning(f"HN front page fetch failed: {e}")

        # Strategy 3: Fallback — use existing fetch_hackernews with broad queries
        remaining = max_results - len(all_items)
        if remaining > 5:
            try:
                from core.sensing.sources.hackernews import fetch_hackernews
                lookback_days = max(1, (datetime.utcnow() - since.replace(tzinfo=None)).days)
                # Broad queries covering diverse tech domains
                for query in ["programming", "startup", "open source"]:
                    articles = await fetch_hackernews(
                        domain=query,
                        lookback_days=lookback_days,
                        max_results=remaining // 3,
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
                logger.warning(f"HN fallback queries failed: {e}")

        logger.info(f"HN LIR adapter: {len(all_items)} stories")
        return all_items[:max_results]

    async def _fetch_algolia_stories(
        self,
        tag: str,
        since: datetime,
        max_results: int = 20,
    ) -> List[LIRRawItem]:
        """Fetch stories from HN Algolia API by tag (no keyword filter)."""
        since_ts = int(since.timestamp())

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{HN_ALGOLIA}/search_by_date",
                params={
                    "tags": tag,
                    "numericFilters": f"created_at_i>{since_ts}",
                    "hitsPerPage": min(max_results, 50),
                },
            )
            resp.raise_for_status()
            data = resp.json()

        items: List[LIRRawItem] = []
        for hit in data.get("hits", []):
            title = hit.get("title", "")
            url = hit.get("url", "")
            if not title:
                continue
            # Use HN story URL as fallback if no external URL
            if not url:
                story_id = hit.get("objectID", "")
                url = f"https://news.ycombinator.com/item?id={story_id}"

            created_at = hit.get("created_at", "")
            points = hit.get("points", 0)
            num_comments = hit.get("num_comments", 0)
            author = hit.get("author", "")

            item_id = f"hn:{hashlib.sha256(url.encode()).hexdigest()[:12]}"
            items.append(
                LIRRawItem(
                    item_id=item_id,
                    source_id="hackernews",
                    tier="T3",
                    title=title,
                    url=url,
                    published_date=created_at,
                    snippet=f"{points} points | {num_comments} comments | by {author}",
                    content=title,  # HN stories have minimal content
                    categories="Hacker News",
                    metadata={"points": points, "comments": num_comments},
                )
            )

        return items

    async def backfill(self, start_date: str, end_date: str) -> List[LIRRawItem]:
        """Backfill HN stories for a date range."""
        since = datetime.fromisoformat(start_date)
        return await self.poll(since, max_results=200)
