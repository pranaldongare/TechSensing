"""
Model Releases Search — targeted web search for recent AI model announcements.

Used only for GenerativeAI-related domains. Searches for model releases,
launches, and announcements from major AI labs.
"""

import logging
from datetime import datetime, timezone
from typing import List

from core.sensing.date_filter import filter_articles_by_date
from core.sensing.ingest import RawArticle, search_duckduckgo

logger = logging.getLogger("sensing.sources.model_releases")


def _model_release_queries() -> List[str]:
    """Generate model release search queries with the current year."""
    year = datetime.now(timezone.utc).year
    return [
        f"new AI model release {year}",
        f"LLM launch open source model {year}",
        f"foundation model release benchmark {year}",
        f"diffusion model release {year}",
        f"AI model announcement parameters open weight {year}",
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
            queries=_model_release_queries(),
            domain="Generative AI",
            lookback_days=lookback_days,
        )
        logger.info(f"Model releases search: {len(articles)} raw articles found")

        # Pre-filter stale articles before expensive LLM extraction.
        # Uses snippet/content date extraction to catch old articles that
        # DDG returned with fresh syndication dates.
        before = len(articles)
        articles = filter_articles_by_date(
            articles, lookback_days,
            buffer_multiplier=1.5,
            drop_undated=False,
            label="model-releases",
        )
        if len(articles) < before:
            logger.info(
                f"Model releases pre-filter: {before} -> {len(articles)} "
                f"(removed {before - len(articles)} stale)"
            )

        return articles[:max_results]
    except Exception as e:
        logger.warning(f"Model releases search failed: {e}")
        return []
