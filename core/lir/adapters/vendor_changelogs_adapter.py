"""
Vendor changelogs LIR adapter — curated RSS feeds from major AI/ML vendors.

Tier 2: Official vendor announcements, 6-18 month lead time.
"""

import hashlib
import logging
from datetime import datetime, timezone
from typing import List

import feedparser
import httpx

from core.lir.models import LIRRawItem

logger = logging.getLogger("lir.adapters.vendor_changelogs")

# Curated vendor blog/changelog RSS feeds
VENDOR_FEEDS = [
    ("OpenAI", "https://openai.com/blog/rss.xml"),
    ("Google AI", "https://blog.google/technology/ai/rss/"),
    ("Meta AI", "https://ai.meta.com/blog/rss/"),
    ("Anthropic", "https://www.anthropic.com/rss.xml"),
    ("Microsoft Research", "https://www.microsoft.com/en-us/research/feed/"),
    ("NVIDIA AI", "https://blogs.nvidia.com/feed/"),
    ("Hugging Face", "https://huggingface.co/blog/feed.xml"),
    ("DeepMind", "https://deepmind.google/blog/rss.xml"),
]


class VendorChangelogsLIRAdapter:
    """Tier-2 adapter: Major AI vendor blogs and changelogs."""

    source_id: str = "vendor_changelogs"
    tier: str = "T2"
    lead_time_prior_days: int = 180  # ~6 months
    authority_prior: float = 0.75

    async def poll(
        self,
        since: datetime,
        max_results: int = 50,
    ) -> List[LIRRawItem]:
        """Fetch recent entries from vendor RSS feeds."""
        all_items: List[LIRRawItem] = []
        seen_urls: set = set()

        per_feed = max(3, max_results // max(len(VENDOR_FEEDS), 1))

        for vendor_name, feed_url in VENDOR_FEEDS:
            try:
                items = await self._fetch_feed(
                    vendor_name, feed_url, since, per_feed
                )
                for item in items:
                    if item.url not in seen_urls:
                        seen_urls.add(item.url)
                        all_items.append(item)
            except Exception as e:
                logger.warning(f"Vendor feed '{vendor_name}' failed: {e}")

        logger.info(
            f"Vendor changelogs LIR adapter: {len(all_items)} entries "
            f"from {len(VENDOR_FEEDS)} feeds"
        )
        return all_items[:max_results]

    async def _fetch_feed(
        self,
        vendor_name: str,
        feed_url: str,
        since: datetime,
        max_results: int,
    ) -> List[LIRRawItem]:
        """Parse a single vendor RSS feed."""
        items: List[LIRRawItem] = []

        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
                resp = await client.get(feed_url)
                resp.raise_for_status()
        except Exception as e:
            logger.debug(f"Feed fetch failed for {vendor_name}: {e}")
            return items

        feed = feedparser.parse(resp.text)

        for entry in feed.entries[:max_results]:
            link = entry.get("link", "")
            if not link:
                continue

            pub_date = ""
            for date_field in ("published_parsed", "updated_parsed"):
                parsed = entry.get(date_field)
                if parsed:
                    try:
                        pub_dt = datetime(*parsed[:6], tzinfo=timezone.utc)
                        if pub_dt < since:
                            continue
                        pub_date = pub_dt.isoformat()
                        break
                    except (ValueError, TypeError):
                        pass

            title = entry.get("title", "").strip()
            summary = entry.get("summary", "")[:500]

            item_id = f"vendor:{hashlib.sha256(link.encode()).hexdigest()[:12]}"
            items.append(
                LIRRawItem(
                    item_id=item_id,
                    source_id="vendor_changelogs",
                    tier="T2",
                    title=f"[{vendor_name}] {title}",
                    url=link,
                    published_date=pub_date,
                    snippet=summary,
                    content=summary,
                    categories=vendor_name,
                )
            )

        return items
