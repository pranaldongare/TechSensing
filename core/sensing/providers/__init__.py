"""
SourceProvider abstraction — pluggable per-company article providers.

Every provider implements the same async ``search`` contract and returns a
list of :class:`RawArticle`. The :func:`aggregate_sources` helper runs a
sequence of providers in parallel, merges their output, and dedups by URL.

Providers are gated by feature flags in ``core.constants.SENSING_FEATURES``
so they can be rolled out incrementally. The always-on default provider is
:class:`DDGProvider` which wraps the existing ``search_duckduckgo`` call
that Company Analysis and Key Companies use today.
"""

from __future__ import annotations

import asyncio
import logging
from typing import List, Protocol, Sequence

from core.sensing.ingest import RawArticle

logger = logging.getLogger("sensing.providers")


class SourceProvider(Protocol):
    """Protocol every source provider implements.

    Implementations MUST be safe to call concurrently from asyncio tasks.
    """

    name: str

    async def search(
        self,
        company: str,
        *,
        queries: List[str],
        domain: str = "",
        lookback_days: int = 30,
        max_results: int = 15,
    ) -> List[RawArticle]:
        """Return candidate articles for the given company.

        Providers that are not query-driven (e.g. RSS auto-discovery,
        SEC EDGAR by ticker) may ignore ``queries`` and drive their
        search purely from ``company``. Providers that are domain-scoped
        (e.g. arXiv categories) may use ``domain``. All providers SHOULD
        respect ``lookback_days`` and ``max_results`` as upper bounds.
        """
        ...


def _dedup_articles(articles: List[RawArticle]) -> List[RawArticle]:
    """Deduplicate by URL, preserving first-seen order."""
    seen: set = set()
    unique: List[RawArticle] = []
    for a in articles:
        if not a.url or a.url in seen:
            continue
        seen.add(a.url)
        unique.append(a)
    return unique


async def aggregate_sources(
    providers: Sequence[SourceProvider],
    company: str,
    *,
    queries: List[str],
    domain: str = "",
    lookback_days: int = 30,
    max_results_per_provider: int = 15,
) -> List[RawArticle]:
    """Run all providers in parallel, merge their results, dedup by URL.

    Per-provider failures are logged and swallowed so one flaky source
    can't take down an entire company run.
    """
    if not providers:
        return []

    async def _safe_call(p: SourceProvider) -> List[RawArticle]:
        try:
            return await p.search(
                company,
                queries=queries,
                domain=domain,
                lookback_days=lookback_days,
                max_results=max_results_per_provider,
            )
        except Exception as e:
            logger.warning(
                f"[providers] {p.name} failed for {company!r}: {e}"
            )
            return []

    results = await asyncio.gather(*[_safe_call(p) for p in providers])
    merged: List[RawArticle] = []
    for batch in results:
        merged.extend(batch)
    unique = _dedup_articles(merged)
    logger.info(
        f"[providers] {company}: {len(unique)} unique articles from "
        f"{len(providers)} provider(s) "
        f"({', '.join(p.name for p in providers)})"
    )
    return unique


def get_enabled_providers(
    *,
    user_id: str = "",
    include_ddg: bool = True,
    include_rss: bool = False,
    include_github: bool = False,
    include_arxiv: bool = False,
    include_press_wire: bool = False,
    include_youtube: bool = False,
    include_edgar: bool = False,
    include_patents: bool = False,
) -> List[SourceProvider]:
    """Instantiate the set of providers requested by the caller.

    Callers (Company Analysis / Key Companies) pass booleans derived from
    ``core.constants.SENSING_FEATURES`` so the feature-flag registry is
    the single source of truth. ``user_id`` is forwarded to providers
    that cache per-user state (e.g. RSS feed auto-discovery).
    """
    providers: List[SourceProvider] = []
    if include_ddg:
        from core.sensing.providers.ddg_provider import DDGProvider
        providers.append(DDGProvider())
    if include_rss:
        try:
            from core.sensing.providers.rss_provider import RSSProvider
            providers.append(RSSProvider(user_id=user_id))
        except Exception as e:
            logger.warning(f"[providers] RSS provider unavailable: {e}")
    if include_github:
        try:
            from core.sensing.providers.github_provider import GitHubProvider
            providers.append(GitHubProvider())
        except Exception as e:
            logger.warning(f"[providers] GitHub provider unavailable: {e}")
    if include_arxiv:
        try:
            from core.sensing.providers.arxiv_provider import ArxivProvider
            providers.append(ArxivProvider())
        except Exception as e:
            logger.warning(f"[providers] arXiv provider unavailable: {e}")
    if include_press_wire:
        try:
            from core.sensing.providers.press_wire_provider import (
                PressWireProvider,
            )
            providers.append(PressWireProvider())
        except Exception as e:
            logger.warning(f"[providers] Press-wire provider unavailable: {e}")
    if include_youtube:
        try:
            from core.sensing.providers.youtube_provider import (
                YouTubeProvider,
            )
            providers.append(YouTubeProvider())
        except Exception as e:
            logger.warning(f"[providers] YouTube provider unavailable: {e}")
    if include_edgar:
        try:
            from core.sensing.providers.edgar_provider import EdgarProvider
            providers.append(EdgarProvider())
        except Exception as e:
            logger.warning(f"[providers] EDGAR provider unavailable: {e}")
    if include_patents:
        try:
            from core.sensing.providers.patents_provider import (
                PatentsProvider,
            )
            providers.append(PatentsProvider())
        except Exception as e:
            logger.warning(f"[providers] Patents provider unavailable: {e}")
    return providers


__all__ = [
    "SourceProvider",
    "aggregate_sources",
    "get_enabled_providers",
]
