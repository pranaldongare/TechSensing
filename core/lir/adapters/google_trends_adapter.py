"""
Google Trends LIR adapter — search interest signals via pytrends.

Tier 3: Search interest, 6-12 month lead time.
Detects breakout search terms and rising queries for open-ended discovery.
Requires pytrends package (optional dependency).
"""

import hashlib
import logging
import time
from datetime import datetime, timezone
from typing import List

from core.lir.models import LIRRawItem

logger = logging.getLogger("lir.adapters.google_trends")

# Seed keywords for trend discovery (diverse domains)
SEED_KEYWORDS = [
    "AI agent",
    "quantum computing",
    "edge AI",
    "rust programming",
    "WebAssembly",
    "autonomous vehicle",
    "digital twin",
    "zero trust",
    "generative AI",
    "spatial computing",
]


class GoogleTrendsLIRAdapter:
    """Tier-3 adapter: Google Trends search interest signals."""

    source_id: str = "google_trends"
    tier: str = "T3"
    lead_time_prior_days: int = 180  # ~6 months
    authority_prior: float = 0.45

    async def poll(
        self,
        since: datetime,
        max_results: int = 50,
    ) -> List[LIRRawItem]:
        """Fetch trending search terms and interest data."""
        try:
            from pytrends.request import TrendReq
        except ImportError:
            logger.info(
                "Google Trends adapter skipped: pytrends not installed. "
                "Run: pip install pytrends"
            )
            return []

        all_items: List[LIRRawItem] = []
        seen_terms: set = set()
        now_iso = datetime.now(timezone.utc).isoformat()

        try:
            pytrends = TrendReq(hl="en-US", tz=360, timeout=(10, 25))
        except Exception as e:
            logger.warning(f"Failed to initialize pytrends: {e}")
            return []

        # Strategy 1: Check interest for seed keywords and find related rising queries
        for batch_start in range(0, len(SEED_KEYWORDS), 5):
            batch = SEED_KEYWORDS[batch_start:batch_start + 5]

            try:
                pytrends.build_payload(batch, timeframe="today 3-m")
                time.sleep(2)  # Rate limit protection

                # Get related queries (rising = breakout potential)
                related = pytrends.related_queries()

                for keyword in batch:
                    if keyword in related and related[keyword].get("rising") is not None:
                        rising_df = related[keyword]["rising"]
                        if rising_df is not None and not rising_df.empty:
                            for _, row in rising_df.head(5).iterrows():
                                term = str(row.get("query", "")).strip()
                                value = row.get("value", 0)

                                if not term or term.lower() in seen_terms:
                                    continue
                                seen_terms.add(term.lower())

                                item_id = f"gtrend:{hashlib.sha256(term.encode()).hexdigest()[:12]}"
                                all_items.append(
                                    LIRRawItem(
                                        item_id=item_id,
                                        source_id="google_trends",
                                        tier="T3",
                                        title=f"Rising search: {term}",
                                        url=f"https://trends.google.com/trends/explore?q={term.replace(' ', '+')}",
                                        published_date=now_iso,
                                        snippet=f"Rising query for '{keyword}' — growth: {value}%",
                                        content=f"Google Trends rising query '{term}' related to '{keyword}' with {value}% growth in interest over the past 3 months.",
                                        categories=f"Google Trends | {keyword}",
                                        metadata={"growth_pct": value, "seed_keyword": keyword},
                                    )
                                )
            except Exception as e:
                logger.warning(f"Google Trends batch {batch} failed: {e}")

            time.sleep(1)  # Rate limit between batches

        # Strategy 2: Trending searches (real-time trending topics)
        try:
            trending = pytrends.trending_searches(pn="united_states")
            if trending is not None and not trending.empty:
                for term in trending[0].head(10):
                    term = str(term).strip()
                    if not term or term.lower() in seen_terms:
                        continue
                    seen_terms.add(term.lower())

                    item_id = f"gtrend:{hashlib.sha256(term.encode()).hexdigest()[:12]}"
                    all_items.append(
                        LIRRawItem(
                            item_id=item_id,
                            source_id="google_trends",
                            tier="T3",
                            title=f"Trending: {term}",
                            url=f"https://trends.google.com/trends/explore?q={term.replace(' ', '+')}",
                            published_date=now_iso,
                            snippet="Currently trending on Google",
                            content=f"'{term}' is currently trending in Google searches in the United States.",
                            categories="Google Trends | Trending",
                        )
                    )
        except Exception as e:
            logger.warning(f"Google Trends trending searches failed: {e}")

        logger.info(f"Google Trends LIR adapter: {len(all_items)} signals")
        return all_items[:max_results]

    async def backfill(self, start_date: str, end_date: str) -> List[LIRRawItem]:
        """Backfill not supported for Google Trends (real-time only)."""
        since = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)
        return await self.poll(since, max_results=50)
