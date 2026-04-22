"""
Stack Exchange LIR adapter — developer adoption signals from tag growth.

Tier 3: Developer adoption, 6-18 month lead time.
Tracks Stack Overflow tag growth rates and new tag creation as
leading indicators of technology adoption.
No API key required (10,000 req/day).
"""

import hashlib
import logging
from datetime import datetime, timezone
from typing import List

import httpx

from core.lir.models import LIRRawItem

logger = logging.getLogger("lir.adapters.stackexchange")

SE_API = "https://api.stackexchange.com/2.3"


class StackExchangeLIRAdapter:
    """Tier-3 adapter: Stack Overflow tag growth as adoption signal."""

    source_id: str = "stackexchange"
    tier: str = "T3"
    lead_time_prior_days: int = 270  # ~9 months
    authority_prior: float = 0.55

    async def poll(
        self,
        since: datetime,
        max_results: int = 50,
    ) -> List[LIRRawItem]:
        """Fetch fast-growing Stack Overflow tags as tech adoption signals."""
        all_items: List[LIRRawItem] = []
        seen_tags: set = set()
        now_iso = datetime.now(timezone.utc).isoformat()

        # Strategy 1: Popular tags (high question count = established tech)
        try:
            popular = await self._fetch_tags(
                sort="popular", page_size=min(max_results, 50)
            )
            for item in popular:
                if item.item_id not in seen_tags:
                    seen_tags.add(item.item_id)
                    all_items.append(item)
        except Exception as e:
            logger.warning(f"SE popular tags failed: {e}")

        # Strategy 2: Recently active tags (recent activity = growing interest)
        try:
            active = await self._fetch_tags(
                sort="activity", page_size=min(max_results, 50)
            )
            for item in active:
                if item.item_id not in seen_tags:
                    seen_tags.add(item.item_id)
                    all_items.append(item)
        except Exception as e:
            logger.warning(f"SE active tags failed: {e}")

        # Strategy 3: Recent questions with new/emerging tags
        try:
            recent = await self._fetch_recent_questions(
                since, max_results=max_results // 3
            )
            for item in recent:
                if item.item_id not in seen_tags:
                    seen_tags.add(item.item_id)
                    all_items.append(item)
        except Exception as e:
            logger.warning(f"SE recent questions failed: {e}")

        logger.info(f"Stack Exchange LIR adapter: {len(all_items)} signals")
        return all_items[:max_results]

    async def _fetch_tags(
        self,
        sort: str = "popular",
        page_size: int = 30,
    ) -> List[LIRRawItem]:
        """Fetch tags from Stack Overflow API."""
        items: List[LIRRawItem] = []
        now_iso = datetime.now(timezone.utc).isoformat()

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{SE_API}/tags",
                params={
                    "order": "desc",
                    "sort": sort,
                    "site": "stackoverflow",
                    "pagesize": page_size,
                    "filter": "default",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        for tag_data in data.get("items", []):
            tag_name = tag_data.get("name", "")
            if not tag_name:
                continue

            count = tag_data.get("count", 0)
            is_moderator_only = tag_data.get("is_moderator_only", False)
            is_required = tag_data.get("is_required", False)

            # Skip meta/system tags
            if is_moderator_only or is_required:
                continue

            item_id = f"se_tag:{hashlib.sha256(tag_name.encode()).hexdigest()[:12]}"
            url = f"https://stackoverflow.com/questions/tagged/{tag_name}"

            items.append(
                LIRRawItem(
                    item_id=item_id,
                    source_id="stackexchange",
                    tier="T3",
                    title=f"SO Tag: {tag_name}",
                    url=url,
                    published_date=now_iso,
                    snippet=f"{count:,} questions | sort: {sort}",
                    content=(
                        f"Stack Overflow tag '{tag_name}' has {count:,} questions. "
                        f"Sorted by {sort}, indicating {'high adoption' if sort == 'popular' else 'recent activity surge'}."
                    ),
                    categories=f"Stack Overflow | {sort}",
                    metadata={"question_count": count, "sort": sort},
                )
            )

        return items

    async def _fetch_recent_questions(
        self,
        since: datetime,
        max_results: int = 15,
    ) -> List[LIRRawItem]:
        """Fetch recent highly-voted questions to discover emerging topics."""
        items: List[LIRRawItem] = []
        since_ts = int(since.timestamp())

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{SE_API}/questions",
                params={
                    "order": "desc",
                    "sort": "votes",
                    "fromdate": since_ts,
                    "site": "stackoverflow",
                    "pagesize": min(max_results, 30),
                    "filter": "withbody",
                    "tagged": "",  # No tag filter — open discovery
                },
            )
            resp.raise_for_status()
            data = resp.json()

        for q in data.get("items", []):
            title = q.get("title", "")
            if not title:
                continue

            tags = q.get("tags", [])
            score = q.get("score", 0)
            answer_count = q.get("answer_count", 0)
            view_count = q.get("view_count", 0)
            link = q.get("link", "")
            creation_date = q.get("creation_date", 0)

            pub_date = ""
            if creation_date:
                pub_date = datetime.fromtimestamp(
                    creation_date, tz=timezone.utc
                ).isoformat()

            item_id = f"se_q:{hashlib.sha256(link.encode()).hexdigest()[:12]}"

            items.append(
                LIRRawItem(
                    item_id=item_id,
                    source_id="stackexchange",
                    tier="T3",
                    title=title,
                    url=link,
                    published_date=pub_date,
                    snippet=f"Score: {score} | {answer_count} answers | {view_count:,} views | Tags: {', '.join(tags)}",
                    content=title,
                    categories=" | ".join(tags[:5]),
                    metadata={
                        "score": score,
                        "tags": tags,
                        "view_count": view_count,
                    },
                )
            )

        return items

    async def backfill(self, start_date: str, end_date: str) -> List[LIRRawItem]:
        """Backfill Stack Exchange data for a date range."""
        since = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)
        return await self.poll(since, max_results=200)
