"""
Semantic Scholar LIR adapter — broad academic discovery with citation data.

Tier 1: Academic papers from all disciplines, 12-36 month lead time.
Uses broad category queries instead of AI-only keywords, and captures
citation counts for authority scoring.
"""

import hashlib
import logging
from datetime import datetime
from typing import List

from core.lir.models import LIRRawItem

logger = logging.getLogger("lir.adapters.semantic_scholar")


class SemanticScholarLIRAdapter:
    """Tier-1 adapter: Semantic Scholar academic papers (broad discovery)."""

    source_id: str = "semantic_scholar"
    tier: str = "T1"
    lead_time_prior_days: int = 730  # ~24 months
    authority_prior: float = 0.85

    async def poll(
        self,
        since: datetime,
        max_results: int = 50,
    ) -> List[LIRRawItem]:
        from core.sensing.sources.semantic_scholar import fetch_semantic_scholar

        lookback_days = max(1, (datetime.utcnow() - since.replace(tzinfo=None)).days)

        # Broad queries covering diverse research domains
        # (not just AI/ML — let the LLM determine relevance)
        queries = [
            "artificial intelligence",
            "quantum computing",
            "robotics automation",
            "biotechnology computational",
            "cybersecurity",
            "distributed systems",
            "edge computing",
            "computer vision",
            "natural language processing",
            "reinforcement learning",
        ]

        all_items: List[LIRRawItem] = []
        seen_urls: set = set()

        per_query = max(3, max_results // len(queries))

        for query in queries:
            try:
                articles = await fetch_semantic_scholar(
                    domain=query,
                    lookback_days=lookback_days,
                    max_results=per_query,
                )
                for a in articles:
                    if a.url in seen_urls:
                        continue
                    seen_urls.add(a.url)

                    # Extract citation count from snippet if available
                    citation_count = 0
                    if a.snippet and "citations:" in a.snippet.lower():
                        try:
                            parts = a.snippet.split("|")
                            for part in parts:
                                if "citation" in part.lower():
                                    citation_count = int(
                                        "".join(c for c in part if c.isdigit()) or "0"
                                    )
                        except (ValueError, IndexError):
                            pass

                    item_id = f"s2:{hashlib.sha256(a.url.encode()).hexdigest()[:12]}"
                    all_items.append(
                        LIRRawItem(
                            item_id=item_id,
                            source_id="semantic_scholar",
                            tier="T1",
                            title=a.title,
                            url=a.url,
                            published_date=a.published_date or "",
                            snippet=a.snippet,
                            content=a.content or a.snippet,
                            authors=a.snippet.split(" | ")[0] if " | " in a.snippet else "",
                            categories="Semantic Scholar",
                            metadata={"citation_count": citation_count},
                        )
                    )
            except Exception as e:
                logger.warning(f"S2 LIR query '{query}' failed: {e}")

        logger.info(f"Semantic Scholar LIR adapter: {len(all_items)} papers")
        return all_items[:max_results]

    async def backfill(self, start_date: str, end_date: str) -> List[LIRRawItem]:
        """Backfill Semantic Scholar papers for a date range."""
        since = datetime.fromisoformat(start_date)
        return await self.poll(since, max_results=200)
