"""Patents provider — recent patent filings assigned to the company.

Primary path wraps :func:`search_google_patents` (Tavily-backed site
search against ``patents.google.com``). When Tavily is unavailable we
fall back to a DuckDuckGo site-restricted search against
``patents.google.com`` so the pipeline still surfaces *something*.

Company Analysis is the main consumer; patents are too noisy for the
weekly Key Companies brief.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List

from core.sensing.ingest import RawArticle, search_duckduckgo
from core.sensing.sources.google_patent_search import (
    _get_tavily_key,
    search_google_patents,
)

logger = logging.getLogger("sensing.providers.patents")


async def _ddg_patent_fallback(
    company: str, *, lookback_days: int, max_results: int
) -> List[RawArticle]:
    """When Tavily is unset, run a DDG site-search for patents."""
    queries = [
        f'site:patents.google.com "{company}"',
        f'site:patents.google.com assignee:"{company}"',
    ]
    try:
        results = await search_duckduckgo(
            queries=queries,
            domain="Technology",
            lookback_days=lookback_days,
        )
    except Exception as e:
        logger.warning(f"[patents] DDG fallback failed for {company!r}: {e}")
        return []

    filtered: List[RawArticle] = []
    seen: set = set()
    for art in results:
        if not art.url or "patents.google.com" not in art.url:
            continue
        if art.url in seen:
            continue
        seen.add(art.url)
        filtered.append(
            RawArticle(
                title=art.title,
                url=art.url,
                source="Google Patent",
                published_date=art.published_date
                or datetime.now(timezone.utc).isoformat(),
                snippet="Patent (DDG fallback)",
                content=art.content,
            )
        )
    return filtered[:max_results]


class PatentsProvider:
    """Google Patents search provider (company-as-assignee)."""

    name = "patents"

    async def search(
        self,
        company: str,
        *,
        queries: List[str],  # noqa: ARG002 — company drives the query
        domain: str = "",
        lookback_days: int = 365,
        max_results: int = 10,
    ) -> List[RawArticle]:
        if not company:
            return []

        must_include = [company]
        if domain:
            must_include.append(domain)

        if _get_tavily_key():
            try:
                articles = await search_google_patents(
                    domain=company,
                    lookback_days=lookback_days,
                    max_results=max_results,
                    must_include=must_include,
                )
                logger.info(
                    f"[patents] {company!r}: {len(articles)} patent(s) via Tavily"
                )
                return articles
            except Exception as e:
                logger.warning(
                    f"[patents] Tavily path failed for {company!r}: {e}"
                )

        articles = await _ddg_patent_fallback(
            company, lookback_days=lookback_days, max_results=max_results
        )
        logger.info(
            f"[patents] {company!r}: {len(articles)} patent(s) via DDG fallback"
        )
        return articles
