"""
Standards LIR adapter — W3C and IETF drafts via RSS.

Tier 2: Standards bodies, 6-18 month lead time.
Protocol standardization is a strong leading indicator.
"""

import hashlib
import logging
from datetime import datetime, timezone
from typing import List

import feedparser
import httpx

from core.lir.models import LIRRawItem

logger = logging.getLogger("lir.adapters.standards")

# W3C and IETF RSS feeds
STANDARDS_FEEDS = [
    ("W3C", "https://www.w3.org/blog/news/feed/"),
    ("IETF", "https://www.ietf.org/blog/feed/"),
    ("W3C TR", "https://www.w3.org/TR/tr-technology-stds.rss"),
]

# Keywords to filter for AI/tech-relevant standards
STANDARDS_KEYWORDS = {
    "ai", "machine learning", "web", "privacy", "security", "identity",
    "credential", "api", "protocol", "http", "webrtc", "wasm",
    "webassembly", "gpu", "compute", "model", "inference",
    "federated", "decentralized", "encryption", "tls", "quic",
}


class StandardsLIRAdapter:
    """Tier-2 adapter: W3C and IETF standards drafts."""

    source_id: str = "standards"
    tier: str = "T2"
    lead_time_prior_days: int = 545  # ~18 months
    authority_prior: float = 0.80

    async def poll(
        self,
        since: datetime,
        max_results: int = 50,
    ) -> List[LIRRawItem]:
        """Fetch recent standards drafts/news from W3C and IETF."""
        all_items: List[LIRRawItem] = []
        seen_urls: set = set()

        per_feed = max(5, max_results // max(len(STANDARDS_FEEDS), 1))

        for org_name, feed_url in STANDARDS_FEEDS:
            try:
                items = await self._fetch_feed(org_name, feed_url, since, per_feed)
                for item in items:
                    if item.url not in seen_urls:
                        seen_urls.add(item.url)
                        all_items.append(item)
            except Exception as e:
                logger.warning(f"Standards feed '{org_name}' failed: {e}")

        logger.info(
            f"Standards LIR adapter: {len(all_items)} items "
            f"from {len(STANDARDS_FEEDS)} feeds"
        )
        return all_items[:max_results]

    async def _fetch_feed(
        self,
        org_name: str,
        feed_url: str,
        since: datetime,
        max_results: int,
    ) -> List[LIRRawItem]:
        """Parse a single standards RSS feed."""
        items: List[LIRRawItem] = []

        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
                resp = await client.get(feed_url)
                resp.raise_for_status()
        except Exception as e:
            logger.debug(f"Standards feed fetch failed for {org_name}: {e}")
            return items

        feed = feedparser.parse(resp.text)

        for entry in feed.entries[:50]:  # Scan more, filter by keyword
            link = entry.get("link", "")
            if not link:
                continue

            title = entry.get("title", "").strip()
            summary = entry.get("summary", "")[:500]

            # Keyword filter
            text = f"{title} {summary}".lower()
            if not any(kw in text for kw in STANDARDS_KEYWORDS):
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

            item_id = f"std:{hashlib.sha256(link.encode()).hexdigest()[:12]}"
            items.append(
                LIRRawItem(
                    item_id=item_id,
                    source_id="standards",
                    tier="T2",
                    title=f"[{org_name}] {title}",
                    url=link,
                    published_date=pub_date,
                    snippet=summary,
                    content=summary,
                    categories=org_name,
                )
            )

        return items

    async def backfill(self, start_date: str, end_date: str) -> List[LIRRawItem]:
        """Backfill standards drafts for a date range."""
        since = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)
        return await self.poll(since, max_results=200)
