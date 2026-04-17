"""arXiv provider — company-focused academic paper search.

Wraps :func:`fetch_arxiv_papers` from ``sources/arxiv_search.py``. The
existing helper is domain-centric (``all:{domain}``); here we drive it
from the *company* name so Company Analysis surfaces papers authored
or affiliated with the target company.

Each query is the company name; the ``domain`` hint (when present) is
AND-ed in as a ``must_include`` keyword so results stay topically
relevant.
"""

from __future__ import annotations

import asyncio
import logging
from typing import List

from core.sensing.ingest import RawArticle
from core.sensing.sources.arxiv_search import fetch_arxiv_papers

logger = logging.getLogger("sensing.providers.arxiv")


class ArxivProvider:
    """arXiv search provider — returns recent papers mentioning the company."""

    name = "arxiv"

    async def search(
        self,
        company: str,
        *,
        queries: List[str],  # noqa: ARG002 — we query by company + domain
        domain: str = "",
        lookback_days: int = 30,
        max_results: int = 15,
    ) -> List[RawArticle]:
        if not company:
            return []

        # Query once per (company) and once per (company AND domain) to
        # broaden recall without flooding results.
        tasks = [
            fetch_arxiv_papers(
                domain=company,
                lookback_days=lookback_days,
                max_results=max_results,
            )
        ]
        if domain and domain.lower() not in {"technology", "general"}:
            tasks.append(
                fetch_arxiv_papers(
                    domain=company,
                    lookback_days=lookback_days,
                    max_results=max_results,
                    must_include=[domain],
                )
            )

        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            logger.warning(f"[arxiv] gather failed for {company!r}: {e}")
            return []

        merged: List[RawArticle] = []
        seen_urls: set = set()
        for batch in results:
            if isinstance(batch, BaseException):
                logger.warning(f"[arxiv] sub-query failed for {company!r}: {batch}")
                continue
            for art in batch:
                if art.url and art.url not in seen_urls:
                    seen_urls.add(art.url)
                    merged.append(art)

        logger.info(f"[arxiv] {company!r}: {len(merged)} paper(s)")
        return merged[:max_results]
