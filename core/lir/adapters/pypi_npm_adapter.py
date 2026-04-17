"""
PyPI/npm LIR adapter — fetches recently published AI/ML packages.

Tier 2: Developer ecosystem, 6-18 month lead time.
Checks PyPI's new releases RSS and npm search for AI-related packages.
"""

import hashlib
import logging
from datetime import datetime, timezone
from typing import List

import feedparser
import httpx

from core.lir.models import LIRRawItem

logger = logging.getLogger("lir.adapters.pypi_npm")

# PyPI RSS feeds for new/updated packages in ML-related categories
PYPI_RSS_URLS = [
    "https://pypi.org/rss/packages.xml",  # All new packages
]

# Keywords to filter PyPI packages
PYPI_KEYWORDS = {
    "llm", "transformer", "neural", "embedding", "tokenizer",
    "diffusion", "attention", "gpt", "bert", "lora", "rag",
    "agent", "langchain", "llamaindex", "vector", "onnx",
    "quantization", "inference", "mlops", "fine-tune", "finetune",
}


class PyPINpmLIRAdapter:
    """Tier-2 adapter: PyPI and npm package ecosystem."""

    source_id: str = "pypi_npm"
    tier: str = "T2"
    lead_time_prior_days: int = 270  # ~9 months
    authority_prior: float = 0.65

    async def poll(
        self,
        since: datetime,
        max_results: int = 50,
    ) -> List[LIRRawItem]:
        """Fetch new AI/ML packages from PyPI RSS."""
        all_items: List[LIRRawItem] = []

        # PyPI new packages via RSS
        try:
            items = await self._fetch_pypi(since, max_results)
            all_items.extend(items)
        except Exception as e:
            logger.warning(f"PyPI fetch failed: {e}")

        logger.info(f"PyPI/npm LIR adapter: {len(all_items)} packages")
        return all_items[:max_results]

    async def _fetch_pypi(
        self,
        since: datetime,
        max_results: int,
    ) -> List[LIRRawItem]:
        """Fetch new AI/ML packages from PyPI RSS feed."""
        items: List[LIRRawItem] = []

        for url in PYPI_RSS_URLS:
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.get(url)
                    resp.raise_for_status()

                feed = feedparser.parse(resp.text)

                for entry in feed.entries[:200]:  # Scan more, filter down
                    title = entry.get("title", "").lower()
                    summary = entry.get("summary", "").lower()

                    # Filter: must match AI/ML keywords
                    text = f"{title} {summary}"
                    if not any(kw in text for kw in PYPI_KEYWORDS):
                        continue

                    link = entry.get("link", "")
                    pub_date = ""
                    if entry.get("published_parsed"):
                        try:
                            pub_dt = datetime(
                                *entry.published_parsed[:6],
                                tzinfo=timezone.utc,
                            )
                            if pub_dt < since:
                                continue
                            pub_date = pub_dt.isoformat()
                        except (ValueError, TypeError):
                            pass

                    item_id = f"pypi:{hashlib.sha256(link.encode()).hexdigest()[:12]}"
                    items.append(
                        LIRRawItem(
                            item_id=item_id,
                            source_id="pypi_npm",
                            tier="T2",
                            title=entry.get("title", ""),
                            url=link,
                            published_date=pub_date,
                            snippet=entry.get("summary", "")[:300],
                            content=entry.get("summary", "")[:1000],
                            categories="PyPI",
                        )
                    )

                    if len(items) >= max_results:
                        break

            except Exception as e:
                logger.warning(f"PyPI RSS fetch failed ({url}): {e}")

        return items
