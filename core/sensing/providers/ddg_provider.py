"""DuckDuckGo provider — wraps the existing ``search_duckduckgo`` call.

This is the default, always-on provider. Its existence lets the aggregator
treat DDG as just another source and gives us a single seam where other
providers layer in.
"""

from __future__ import annotations

import logging
from typing import List

from core.sensing.ingest import RawArticle, search_duckduckgo

logger = logging.getLogger("sensing.providers.ddg")


class DDGProvider:
    """Async DuckDuckGo text-search provider."""

    name = "duckduckgo"

    async def search(
        self,
        company: str,  # noqa: ARG002 — queries are already company-scoped
        *,
        queries: List[str],
        domain: str = "",
        lookback_days: int = 30,
        max_results: int = 15,  # noqa: ARG002 — handled inside DDGS
    ) -> List[RawArticle]:
        if not queries:
            return []
        try:
            return await search_duckduckgo(
                queries=queries,
                domain=domain or "Technology",
                lookback_days=lookback_days,
            )
        except Exception as e:
            logger.warning(f"[ddg] search failed for {company!r}: {e}")
            return []
