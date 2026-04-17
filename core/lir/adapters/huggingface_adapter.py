"""
HuggingFace LIR adapter — fetches trending models from HuggingFace Hub API.

Tier 2: Open-source model ecosystem, 6-18 month lead time.
"""

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import List

import httpx

from core.lir.models import LIRRawItem

logger = logging.getLogger("lir.adapters.huggingface")

HF_API_URL = "https://huggingface.co/api/models"


class HuggingFaceLIRAdapter:
    """Tier-2 adapter: HuggingFace trending models."""

    source_id: str = "huggingface"
    tier: str = "T2"
    lead_time_prior_days: int = 270  # ~9 months
    authority_prior: float = 0.70

    async def poll(
        self,
        since: datetime,
        max_results: int = 50,
    ) -> List[LIRRawItem]:
        """Fetch recently updated/trending models from HuggingFace Hub."""
        all_items: List[LIRRawItem] = []

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                # Fetch trending models sorted by recent downloads
                resp = await client.get(
                    HF_API_URL,
                    params={
                        "sort": "trending",
                        "direction": "-1",
                        "limit": min(max_results, 100),
                        "full": "false",
                    },
                )
                resp.raise_for_status()
                models = resp.json()

                for model in models:
                    model_id = model.get("modelId") or model.get("id", "")
                    if not model_id:
                        continue

                    # Filter by date
                    created = model.get("createdAt", "")
                    if created:
                        try:
                            created_dt = datetime.fromisoformat(
                                created.replace("Z", "+00:00")
                            )
                            if created_dt < since:
                                continue
                        except (ValueError, TypeError):
                            pass

                    url = f"https://huggingface.co/{model_id}"
                    downloads = model.get("downloads", 0)
                    likes = model.get("likes", 0)
                    pipeline_tag = model.get("pipeline_tag", "")
                    tags = model.get("tags", [])

                    snippet_parts = []
                    if pipeline_tag:
                        snippet_parts.append(pipeline_tag)
                    if downloads:
                        snippet_parts.append(f"{downloads:,} downloads")
                    if likes:
                        snippet_parts.append(f"{likes} likes")

                    item_id = f"hf:{hashlib.sha256(model_id.encode()).hexdigest()[:12]}"
                    all_items.append(
                        LIRRawItem(
                            item_id=item_id,
                            source_id="huggingface",
                            tier="T2",
                            title=model_id,
                            url=url,
                            published_date=created,
                            snippet=" | ".join(snippet_parts),
                            content=f"HuggingFace model: {model_id}. Tags: {', '.join(tags[:10])}",
                            categories=pipeline_tag or "model",
                            metadata={"downloads": downloads, "likes": likes},
                        )
                    )

            logger.info(f"HuggingFace LIR adapter: {len(all_items)} models")

        except Exception as e:
            logger.warning(f"HuggingFace fetch failed: {e}")

        return all_items[:max_results]
