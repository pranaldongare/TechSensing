"""Press-release wire provider — BusinessWire / PRNewswire / GlobeNewswire.

No API keys. Strategy: run a DDG site-restricted search against each
wire for ``"{company}"`` and filter the URL host to match. Press
releases add a lot of Phase-2 recall because companies often post
funding, acquisition, certification, and launch news on wires before
tech blogs pick them up.
"""

from __future__ import annotations

import asyncio
import logging
from typing import List
from urllib.parse import urlparse

from core.sensing.ingest import RawArticle, search_duckduckgo

logger = logging.getLogger("sensing.providers.press_wire")

_WIRE_HOSTS = (
    "businesswire.com",
    "prnewswire.com",
    "globenewswire.com",
    "newswire.com",
    "accesswire.com",
)


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower().replace("www.", "")
    except Exception:
        return ""


async def _search_one_wire(
    company: str, host: str, *, lookback_days: int
) -> List[RawArticle]:
    queries = [
        f'site:{host} "{company}"',
        f'site:{host} "{company}" announces',
    ]
    try:
        return await search_duckduckgo(
            queries=queries,
            domain="Technology",
            lookback_days=lookback_days,
        )
    except Exception as e:
        logger.warning(
            f"[press_wire] DDG failed for {host} / {company!r}: {e}"
        )
        return []


class PressWireProvider:
    """Business press-release wires aggregator via DDG site search."""

    name = "press_wire"

    async def search(
        self,
        company: str,
        *,
        queries: List[str],  # noqa: ARG002 — wire-specific queries built here
        domain: str = "",  # noqa: ARG002
        lookback_days: int = 30,
        max_results: int = 15,
    ) -> List[RawArticle]:
        if not company:
            return []

        batches = await asyncio.gather(
            *[
                _search_one_wire(
                    company, h, lookback_days=lookback_days
                )
                for h in _WIRE_HOSTS
            ],
            return_exceptions=True,
        )

        merged: List[RawArticle] = []
        seen: set = set()
        for batch in batches:
            if isinstance(batch, BaseException):
                continue
            for art in batch:
                host = _host(art.url)
                if not host or not any(host.endswith(h) for h in _WIRE_HOSTS):
                    continue
                if art.url in seen:
                    continue
                seen.add(art.url)
                # Re-tag the source so downstream UI can filter/badge it.
                merged.append(
                    RawArticle(
                        title=art.title,
                        url=art.url,
                        source=f"PressWire ({host})",
                        published_date=art.published_date,
                        snippet=art.snippet,
                        content=art.content,
                    )
                )

        logger.info(
            f"[press_wire] {company!r}: {len(merged)} release(s) "
            f"across {len(_WIRE_HOSTS)} wire(s)"
        )
        return merged[:max_results]
