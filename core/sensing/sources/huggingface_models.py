"""
HuggingFace models — fetches recently-updated models for a domain.

Uses the public HuggingFace Hub API (no auth required). Sorted by last
modification so builder-oriented readers see the freshest open-weight models.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import List

import httpx

from core.sensing.ingest import RawArticle

logger = logging.getLogger("sensing.sources.huggingface")

HF_MAX_RESULTS = 15
HF_API_URL = "https://huggingface.co/api/models"


async def fetch_huggingface_models(
    domain: str,
    lookback_days: int = 7,
    max_results: int = HF_MAX_RESULTS,
) -> List[RawArticle]:
    """Fetch recently-updated HuggingFace models for a domain.

    0 lookback_days = no date filter. Non-fatal on error (returns []).
    """
    articles: List[RawArticle] = []
    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=lookback_days)
        if lookback_days > 0
        else None
    )

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                HF_API_URL,
                params={
                    "search": domain,
                    "sort": "lastModified",
                    "direction": "-1",
                    "limit": max_results,
                },
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()

        for m in data if isinstance(data, list) else []:
            if not isinstance(m, dict):
                continue
            model_id = m.get("id") or m.get("modelId") or ""
            if not model_id:
                continue
            last_modified = m.get("lastModified") or ""
            if cutoff and last_modified:
                try:
                    lm_dt = datetime.fromisoformat(last_modified.replace("Z", "+00:00"))
                    if lm_dt < cutoff:
                        continue
                except (ValueError, TypeError):
                    pass

            downloads = m.get("downloads") or 0
            likes = m.get("likes") or 0
            pipeline_tag = m.get("pipeline_tag") or ""
            meta_bits = []
            if pipeline_tag:
                meta_bits.append(pipeline_tag)
            meta_bits.append(f"{downloads:,} downloads")
            meta_bits.append(f"{likes} likes")

            articles.append(RawArticle(
                title=model_id,
                url=f"https://huggingface.co/{model_id}",
                source="HuggingFace",
                published_date=last_modified,
                snippet=" | ".join(meta_bits),
                content=pipeline_tag,
            ))

        logger.info(f"HuggingFace: fetched {len(articles)} models for '{domain}'")

    except Exception as e:
        logger.warning(f"HuggingFace fetch failed: {e}")

    return articles
