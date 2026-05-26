"""
LLM-based article classification for Technology Radar placement.
"""

import logging
import time
from typing import List

from core.constants import GPU_SENSING_CLASSIFY_LLM
from core.llm.client import invoke_llm
from core.llm.output_schemas.sensing_outputs import (
    ArticleBatchClassification,
    ClassifiedArticle,
)
from core.llm.prompts.sensing_prompts import sensing_classify_prompt
from core.constants import SWITCHES
from core.sensing.cache import cache_classification, get_cached_classification
from core.sensing.config import ARTICLE_BATCH_SIZE, MIN_RELEVANCE_SCORE, get_preset_for_domain
from core.sensing.ingest import RawArticle

logger = logging.getLogger("sensing.classify")

# When routing through the corporate INTERNAL LLM, large batches occasionally
# trip the content filter (FR-201) — the bigger prompt has more surface area
# for a filter to flag. Drop to 3 articles per batch in that case. The Ollama
# / Gemini / OpenAI paths keep the default ARTICLE_BATCH_SIZE (6).
_INTERNAL_BATCH_SIZE = 3


async def classify_articles(
    articles: List[RawArticle],
    domain: str = "Generative AI",
    custom_requirements: str = "",
    key_people: list[str] | None = None,
    custom_quadrant_names: list[str] | None = None,
    preset=None,
    date_range: str = "",
) -> List[ClassifiedArticle]:
    """
    Classify articles into Technology Radar quadrants/rings via LLM.
    Processes in batches to stay within context window.
    """
    all_classified: List[ClassifiedArticle] = []

    # Check cache for already-classified articles
    uncached_articles: List[RawArticle] = []
    cache_hits = 0
    for article in articles:
        cached = await get_cached_classification(article.url)
        if cached and cached.relevance_score >= MIN_RELEVANCE_SCORE:
            all_classified.append(cached)
            cache_hits += 1
        else:
            uncached_articles.append(article)

    # Effective batch size: smaller when going through INTERNAL to reduce
    # filter-block (FR-201) risk; default otherwise.
    effective_batch_size = (
        _INTERNAL_BATCH_SIZE
        if SWITCHES.get("USE_INTERNAL", False)
        else ARTICLE_BATCH_SIZE
    )

    logger.info(
        f"Cache: {cache_hits}/{len(articles)} hits, "
        f"{len(uncached_articles)} articles need LLM classification "
        f"(batch_size={effective_batch_size}, "
        f"USE_INTERNAL={SWITCHES.get('USE_INTERNAL', False)})"
    )

    total_batches = (len(uncached_articles) + effective_batch_size - 1) // effective_batch_size if uncached_articles else 0

    if preset is None:
        preset = get_preset_for_domain(domain)

    for i in range(0, len(uncached_articles), effective_batch_size):
        batch_num = i // effective_batch_size + 1
        batch = uncached_articles[i : i + effective_batch_size]
        articles_text = _format_batch_for_prompt(batch)

        prompt = sensing_classify_prompt(
            articles_text=articles_text,
            domain=domain,
            custom_requirements=custom_requirements,
            key_people=key_people,
            topic_categories_text=preset.topic_categories,
            industry_segments_text=preset.industry_segments,
            custom_quadrant_names=custom_quadrant_names,
            date_range=date_range,
        )

        try:
            batch_start = time.time()
            logger.info(
                f"[Batch {batch_num}/{total_batches}] Sending {len(batch)} articles to LLM..."
            )

            result = await invoke_llm(
                gpu_model=GPU_SENSING_CLASSIFY_LLM.model,
                response_schema=ArticleBatchClassification,
                contents=prompt,
                port=GPU_SENSING_CLASSIFY_LLM.port,
            )

            validated = ArticleBatchClassification.model_validate(result)
            batch_classified = 0

            for article in validated.articles:
                # Cache every classified article (regardless of score)
                await cache_classification(article)
                if article.relevance_score >= MIN_RELEVANCE_SCORE:
                    all_classified.append(article)
                    batch_classified += 1

            batch_time = time.time() - batch_start
            logger.info(
                f"[Batch {batch_num}/{total_batches}] Done in {batch_time:.1f}s — "
                f"{batch_classified} classified (total so far: {len(all_classified)})"
            )

        except Exception as e:
            logger.error(
                f"[Batch {batch_num}/{total_batches}] FAILED: {e}"
            )
            continue

    logger.info(f"Classification complete: {len(all_classified)} total classified articles")
    return all_classified


def _format_batch_for_prompt(articles: List[RawArticle]) -> str:
    """Format a batch of articles for the classification prompt."""
    parts = []
    for idx, a in enumerate(articles, 1):
        parts.append(
            f"--- Article {idx} ---\n"
            f"Title: {a.title}\n"
            f"Source: {a.source}\n"
            f"URL: {a.url}\n"
            f"Date: {a.published_date or 'Unknown'}\n"
            f"Content:\n{(a.content or a.snippet or a.title)[:2000]}\n"
        )
    return "\n".join(parts)
