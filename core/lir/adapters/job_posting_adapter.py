"""
Job Posting LIR adapter — enterprise demand signals via web search.

Tier 3: Enterprise demand, 6-12 month lead time.
Uses DuckDuckGo search (ddgs package, already installed) to detect
technology skill demand in job postings.
"""

import hashlib
import logging
from datetime import datetime, timezone
from typing import List

from core.lir.models import LIRRawItem

logger = logging.getLogger("lir.adapters.job_postings")

# Technology domains to scan for job demand (diverse, not AI-only)
JOB_SEARCH_TERMS = [
    "AI engineer",
    "machine learning engineer",
    "Rust developer",
    "Kubernetes engineer",
    "quantum computing",
    "blockchain developer",
    "robotics engineer",
    "MLOps",
    "data engineer",
    "cybersecurity analyst",
    "cloud native",
    "WebAssembly developer",
    "edge computing",
    "computer vision engineer",
    "NLP engineer",
]


class JobPostingLIRAdapter:
    """Tier-3 adapter: Job posting signals as technology demand indicators."""

    source_id: str = "job_postings"
    tier: str = "T3"
    lead_time_prior_days: int = 365  # ~12 months
    authority_prior: float = 0.55

    async def poll(
        self,
        since: datetime,
        max_results: int = 50,
    ) -> List[LIRRawItem]:
        """Search for job postings mentioning emerging technologies."""
        try:
            from ddgs import DDGS
        except ImportError:
            logger.info("Job posting adapter skipped: ddgs not installed")
            return []

        all_items: List[LIRRawItem] = []
        seen_urls: set = set()
        now_iso = datetime.now(timezone.utc).isoformat()

        per_term = max(2, max_results // len(JOB_SEARCH_TERMS))

        for term in JOB_SEARCH_TERMS:
            try:
                query = f"{term} hiring job posting 2024 2025 2026"

                with DDGS() as ddgs:
                    results = list(ddgs.text(
                        query,
                        max_results=per_term,
                        timelimit="m",  # Past month
                    ))

                for r in results:
                    url = r.get("href", "").strip()
                    title = r.get("title", "").strip()
                    body = r.get("body", "").strip()

                    if not url or not title:
                        continue
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)

                    item_id = f"job:{hashlib.sha256(url.encode()).hexdigest()[:12]}"

                    all_items.append(
                        LIRRawItem(
                            item_id=item_id,
                            source_id="job_postings",
                            tier="T3",
                            title=title,
                            url=url,
                            published_date=now_iso,
                            snippet=f"Job signal: {term} | {body[:200]}",
                            content=(
                                f"Job market signal for '{term}': {title}. {body}"
                            ),
                            categories=f"Job Postings | {term}",
                            metadata={"search_term": term},
                        )
                    )
            except Exception as e:
                logger.warning(f"Job search for '{term}' failed: {e}")

        logger.info(f"Job posting LIR adapter: {len(all_items)} signals")
        return all_items[:max_results]

    async def backfill(self, start_date: str, end_date: str) -> List[LIRRawItem]:
        """Backfill job postings for a date range."""
        since = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)
        return await self.poll(since, max_results=100)
