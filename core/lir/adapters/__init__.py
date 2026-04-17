"""
LIR source adapters — protocol and aggregation layer.

Each adapter wraps an existing source function or implements a new one,
returning LIRRawItem instances with source-tier metadata.
"""

import asyncio
import logging
from datetime import datetime
from typing import List, Protocol, runtime_checkable

from core.lir.models import LIRRawItem

logger = logging.getLogger("lir.adapters")


@runtime_checkable
class LIRAdapter(Protocol):
    """Protocol for LIR data source adapters."""

    source_id: str
    tier: str  # "T1", "T2", "T3", "T4"
    lead_time_prior_days: int
    authority_prior: float

    async def poll(
        self, since: datetime, max_results: int = 50
    ) -> List[LIRRawItem]: ...

    async def backfill(
        self, start_date: str, end_date: str
    ) -> List[LIRRawItem]: ...


def get_enabled_lir_adapters() -> List[LIRAdapter]:
    """Return adapter instances for all enabled LIR sources."""
    from core.constants import sensing_feature

    adapters: List[LIRAdapter] = []

    if sensing_feature("lir_arxiv"):
        from core.lir.adapters.arxiv_adapter import ArxivLIRAdapter
        adapters.append(ArxivLIRAdapter())

    if sensing_feature("lir_github"):
        from core.lir.adapters.github_adapter import GitHubLIRAdapter
        adapters.append(GitHubLIRAdapter())

    if sensing_feature("lir_hackernews"):
        from core.lir.adapters.hackernews_adapter import HackerNewsLIRAdapter
        adapters.append(HackerNewsLIRAdapter())

    if sensing_feature("lir_reddit"):
        from core.lir.adapters.reddit_adapter import RedditLIRAdapter
        adapters.append(RedditLIRAdapter())

    if sensing_feature("lir_semantic_scholar"):
        from core.lir.adapters.semantic_scholar_adapter import SemanticScholarLIRAdapter
        adapters.append(SemanticScholarLIRAdapter())

    if sensing_feature("lir_huggingface"):
        from core.lir.adapters.huggingface_adapter import HuggingFaceLIRAdapter
        adapters.append(HuggingFaceLIRAdapter())

    if sensing_feature("lir_pypi_npm"):
        from core.lir.adapters.pypi_npm_adapter import PyPINpmLIRAdapter
        adapters.append(PyPINpmLIRAdapter())

    if sensing_feature("lir_vendor_changelogs"):
        from core.lir.adapters.vendor_changelogs_adapter import VendorChangelogsLIRAdapter
        adapters.append(VendorChangelogsLIRAdapter())

    if sensing_feature("lir_standards"):
        from core.lir.adapters.standards_adapter import StandardsLIRAdapter
        adapters.append(StandardsLIRAdapter())

    if sensing_feature("lir_patents"):
        from core.lir.adapters.patent_adapter import PatentLIRAdapter
        adapters.append(PatentLIRAdapter())

    return adapters


async def aggregate_lir_sources(
    since: datetime,
    max_per_source: int = 50,
) -> List[LIRRawItem]:
    """Poll all enabled adapters concurrently and merge results."""
    adapters = get_enabled_lir_adapters()
    if not adapters:
        logger.warning("No LIR adapters enabled")
        return []

    logger.info(
        f"Polling {len(adapters)} LIR adapters: "
        f"{[a.source_id for a in adapters]}"
    )

    tasks = [a.poll(since, max_per_source) for a in adapters]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_items: List[LIRRawItem] = []
    for adapter, result in zip(adapters, results):
        if isinstance(result, Exception):
            logger.warning(f"[{adapter.source_id}] poll failed: {result}")
            continue
        logger.info(f"[{adapter.source_id}] returned {len(result)} items")
        all_items.extend(result)

    logger.info(f"LIR aggregation: {len(all_items)} total items from {len(adapters)} sources")
    return all_items
