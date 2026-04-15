"""
Funding Signal Enrichment — searches for recent funding/investment news
for radar technologies to strengthen signal scoring.

Uses DuckDuckGo search (no API key) to find recent funding announcements.
Runs as a post-processing enrichment step, not a source.
"""

import asyncio
import logging
import re
from typing import List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger("sensing.funding_signals")


class FundingSignal(BaseModel):
    """Funding information for a radar technology."""

    technology_name: str
    has_recent_funding: bool = False
    funding_summary: str = ""  # e.g., "Series B: $50M (Mar 2026)"
    funding_amount_usd: Optional[int] = None  # in USD, 0 if unknown
    source_url: str = ""


async def enrich_with_funding_signals(
    tech_names: List[str],
    domain: str,
) -> List[FundingSignal]:
    """Search for recent funding signals for radar technologies."""
    from core.sensing.ingest import _ddgs_search

    signals: List[FundingSignal] = []
    sem = asyncio.Semaphore(3)

    async def _search_funding(name: str) -> FundingSignal:
        async with sem:
            query = f"{name} funding investment raised 2025 2026"
            try:
                results = await asyncio.to_thread(
                    _ddgs_search, query, max_results=3
                )
                for r in results:
                    snippet = (r.get("body", "") + " " + r.get("title", "")).lower()
                    # Look for funding keywords
                    if any(kw in snippet for kw in [
                        "raised", "funding", "series", "investment",
                        "million", "billion", "seed round", "venture",
                    ]):
                        # Try to extract amount
                        amount = _extract_amount(snippet)
                        return FundingSignal(
                            technology_name=name,
                            has_recent_funding=True,
                            funding_summary=r.get("title", "")[:200],
                            funding_amount_usd=amount,
                            source_url=r.get("href", ""),
                        )
            except Exception as e:
                logger.debug(f"Funding search failed for {name}: {e}")

            return FundingSignal(technology_name=name)

    signals = await asyncio.gather(
        *[_search_funding(name) for name in tech_names[:15]]
    )

    funded_count = sum(1 for s in signals if s.has_recent_funding)
    logger.info(f"Funding signals: {funded_count}/{len(signals)} technologies have recent funding")
    return list(signals)


def _extract_amount(text: str) -> Optional[int]:
    """Extract dollar amount from text. Returns amount in USD or None."""
    # Match patterns like "$50M", "$1.2B", "$50 million"
    patterns = [
        r'\$(\d+(?:\.\d+)?)\s*b(?:illion)?',  # billions
        r'\$(\d+(?:\.\d+)?)\s*m(?:illion)?',  # millions
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            num = float(match.group(1))
            if 'b' in pattern:
                return int(num * 1_000_000_000)
            return int(num * 1_000_000)
    return None
