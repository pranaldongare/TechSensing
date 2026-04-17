"""
Deep Dive — focused analysis on a single technology.

Performs targeted search, extraction, and LLM analysis for a single technology.
"""

import asyncio
import json
import logging
import time
from typing import Callable, List, Optional

from core.constants import GPU_SENSING_REPORT_LLM
from core.llm.client import invoke_llm
from core.llm.output_schemas.sensing_outputs import DeepDiveReport
from core.llm.prompts.shared import tense_rules_block
from core.sensing.ingest import RawArticle, extract_full_text, search_duckduckgo

logger = logging.getLogger("sensing.deep_dive")


def _deep_dive_prompt(
    technology_name: str,
    domain: str,
    articles_json: str,
) -> list[dict]:
    """Build deep dive analysis prompt."""
    schema_json = json.dumps(DeepDiveReport.model_json_schema(), indent=2)

    return [
        {
            "role": "system",
            "parts": (
                f"You are a senior technology analyst performing a deep dive analysis "
                f"on '{technology_name}' in the {domain} domain.\n\n"
                "Based on the collected articles and your knowledge, produce a "
                "comprehensive deep dive report covering:\n"
                "1. A detailed analysis (500-1000 words) of the technology\n"
                "2. Technical architecture and how it works\n"
                "3. Competitive landscape (3-6 alternatives)\n"
                "4. Adoption roadmap for organizations\n"
                "5. Risk assessment and mitigation\n"
                "6. Key resources (papers, repos, docs)\n"
                "7. Actionable recommendations\n\n"
                "Be thorough, specific, and actionable. Use markdown formatting "
                "in text fields.\n\n"
                + tense_rules_block()
                + "OUTPUT REQUIREMENT:\n"
                "Return the entire response strictly as a valid JSON object matching the schema below.\n"
                "Do NOT include markdown, comments, or text outside the JSON object.\n\n"
                f"OUTPUT SCHEMA:\n```json\n{schema_json}\n```\n\n"
                "OUTPUT RULES:\n"
                "- Output must be valid JSON only, no markdown fencing or trailing commas.\n"
                "- Newlines inside string values MUST be written as \\n (escaped).\n"
                '- Double quotes inside string values MUST be escaped as \\".\n'
            ),
        },
        {
            "role": "user",
            "parts": (
                f"TECHNOLOGY: {technology_name}\n"
                f"DOMAIN: {domain}\n\n"
                f"COLLECTED ARTICLES:\n\n{articles_json}\n\n"
                "Generate a comprehensive deep dive report. Return ONLY valid JSON."
            ),
        },
    ]


async def run_deep_dive(
    technology_name: str,
    domain: str,
    user_id: str = "",
    progress_callback: Optional[Callable] = None,
    *,
    seed_question: str = "",
    seed_urls: Optional[List[str]] = None,
) -> DeepDiveReport:
    """
    Run a focused deep dive on a single technology.

    Stages:
    1. Targeted search (DDG) for the technology
    2. Extract full text from top results
    3. LLM deep analysis

    When *seed_question* is set, the search queries are biased toward
    that question. When *seed_urls* is provided, those URLs are fetched
    first (before DDG searches) so they always appear in the evidence
    set (#17 follow-up deep dive).
    """
    start = time.time()

    async def _emit(pct: int, msg: str):
        if progress_callback:
            await progress_callback("deep_dive", pct, msg)

    logger.info(f"Deep dive starting for '{technology_name}' in {domain}")

    # Stage 1: Targeted search
    await _emit(10, f"Searching for {technology_name}...")

    # If seed_urls, pre-populate articles from those URLs.
    articles: List[RawArticle] = []
    if seed_urls:
        for url in seed_urls[:5]:
            articles.append(RawArticle(
                title=url.split("/")[-1][:120] or url,
                url=url,
                source="seed",
                snippet=seed_question or "",
            ))

    focus = seed_question.strip() if seed_question else ""
    search_queries = [
        f"{technology_name} {focus or domain}",
        f"{technology_name} {'detailed analysis' if focus else 'tutorial guide'}",
        f"{technology_name} comparison alternatives",
    ]
    for query in search_queries:
        try:
            results = await search_duckduckgo(
                queries=[query],
                domain=domain,
                lookback_days=30,
            )
            articles.extend(results)
        except Exception as e:
            logger.warning(f"Search failed for '{query}': {e}")

    logger.info(f"Deep dive search found {len(articles)} articles")

    # Stage 2: Extract full text
    await _emit(40, "Extracting article content...")
    sem = asyncio.Semaphore(5)

    async def _extract(a: RawArticle) -> RawArticle:
        async with sem:
            return await extract_full_text(a)

    enriched = await asyncio.gather(*[_extract(a) for a in articles[:15]])
    content_count = sum(1 for a in enriched if a.content and len(a.content) > 50)
    logger.info(f"Extracted content from {content_count}/{len(enriched)} articles")

    # Stage 3: LLM analysis
    await _emit(60, "Analyzing with LLM...")
    articles_json = json.dumps(
        [
            {
                "title": a.title,
                "source": a.source,
                "url": a.url,
                "snippet": a.snippet,
                "content": (a.content or "")[:2000],
            }
            for a in enriched
            if a.content and len(a.content) > 50
        ],
        indent=2,
        ensure_ascii=False,
    )

    prompt = _deep_dive_prompt(technology_name, domain, articles_json)

    result = await invoke_llm(
        gpu_model=GPU_SENSING_REPORT_LLM.model,
        response_schema=DeepDiveReport,
        contents=prompt,
        port=GPU_SENSING_REPORT_LLM.port,
    )

    report = DeepDiveReport.model_validate(result)
    elapsed = time.time() - start

    await _emit(100, "Deep dive complete")
    logger.info(
        f"Deep dive complete for '{technology_name}' in {elapsed:.1f}s — "
        f"{len(report.competitive_landscape)} competitors, "
        f"{len(report.key_resources)} resources"
    )

    return report
