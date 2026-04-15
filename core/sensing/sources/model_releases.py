"""
Model Releases Search — targeted web search for recent AI model announcements.

Used only for GenerativeAI-related domains. Searches for model releases,
launches, and announcements from major AI labs.
"""

import logging
from typing import List

from core.sensing.ingest import RawArticle, search_duckduckgo

logger = logging.getLogger("sensing.sources.model_releases")

MODEL_RELEASE_QUERIES = [
    "new AI model release 2026",
    "LLM launch open source model 2026",
    "foundation model release benchmark 2026",
    "diffusion model release 2026",
    "AI model announcement parameters open weight 2026",
]


async def search_model_releases(
    lookback_days: int = 30,
    max_results: int = 30,
) -> List[RawArticle]:
    """Search for recent AI model release announcements.

    Returns raw articles about model launches — these will be fed into
    the LLM extractor to produce structured ModelRelease entries.
    """
    try:
        articles = await search_duckduckgo(
            queries=MODEL_RELEASE_QUERIES,
            domain="Generative AI",
            lookback_days=lookback_days,
        )
        logger.info(f"Model releases search: {len(articles)} articles found")
        return articles[:max_results]
    except Exception as e:
        logger.warning(f"Model releases search failed: {e}")
        return []
