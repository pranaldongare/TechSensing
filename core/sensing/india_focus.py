"""
India Focus extras — the structured India section that accompanies an
India-scoped report.

When India Focus is enabled the whole report is already India-scoped (India
ingestion + separate India prompts). This pass adds the structured extras:

  - Four streams: Business, Technology, Implementation, Research
    (grounded in the India articles the report already gathered)
  - An India vs Global comparison (GenAI models + ecosystem), grounded in a
    DEDICATED global-frontier search run here — not the model's memory
  - A categorization of the problems India is focusing on

Strictly additive and non-fatal: returns ``None`` on any error and the caller
leaves ``report.india_focus`` unset.
"""

import asyncio
import json
import logging
import time
from typing import Optional

from core.constants import GPU_SENSING_REPORT_LLM
from core.llm.client import invoke_llm
from core.llm.output_schemas.sensing_outputs import IndiaFocus

logger = logging.getLogger("sensing.india_focus")

# Cap how much we feed the synthesis LLM.
MAX_INDIA_ARTICLES = 60
GLOBAL_MAX_ARTICLES = 10
GLOBAL_EXTRACT_CONCURRENCY = 5


def _digest(articles: list, url_content_map: Optional[dict], limit: int) -> list[dict]:
    """Compact, JSON-serializable digest of the most relevant articles."""
    content_map = url_content_map or {}
    ranked = sorted(
        articles,
        key=lambda a: getattr(a, "relevance_score", 0.0) or 0.0,
        reverse=True,
    )[:limit]
    out: list[dict] = []
    for a in ranked:
        url = getattr(a, "url", "") or ""
        entry = {
            "title": getattr(a, "title", ""),
            "technology_name": getattr(a, "technology_name", ""),
            "summary": getattr(a, "summary", "") or getattr(a, "snippet", ""),
            "source": getattr(a, "source", ""),
            "url": url,
            "date": getattr(a, "published_date", "") or "",
        }
        excerpt = content_map.get(url, "") or (getattr(a, "content", "") or "")
        if excerpt:
            entry["content_excerpt"] = excerpt[:500]
        out.append(entry)
    return out


async def _gather_global_sources(domain: str, lookback_days: int) -> list[dict]:
    """Dedicated global-frontier search to ground the India-vs-Global comparison."""
    try:
        from core.sensing.india_sources import get_global_comparison_queries
        from core.sensing.dedup import deduplicate_articles
        from core.sensing.ingest import extract_full_text, search_duckduckgo

        queries = get_global_comparison_queries(domain)
        raw = await search_duckduckgo(queries, domain, lookback_days=lookback_days)
        unique = deduplicate_articles(raw)[:GLOBAL_MAX_ARTICLES]

        sem = asyncio.Semaphore(GLOBAL_EXTRACT_CONCURRENCY)

        async def _ex(a):
            async with sem:
                return await extract_full_text(a)

        enriched = await asyncio.gather(*[_ex(a) for a in unique], return_exceptions=True)
        enriched = [a for a in enriched if not isinstance(a, Exception)]

        digest: list[dict] = []
        for a in enriched:
            digest.append({
                "title": getattr(a, "title", ""),
                "summary": (getattr(a, "summary", "") or getattr(a, "snippet", "")),
                "source": getattr(a, "source", ""),
                "url": getattr(a, "url", "") or "",
                "date": getattr(a, "published_date", "") or "",
                "content_excerpt": (getattr(a, "content", "") or "")[:500],
            })
        logger.info(f"[IndiaFocus] Global comparison sources gathered: {len(digest)}")
        return digest
    except Exception as e:
        logger.warning(f"[IndiaFocus] Global source gathering failed (comparison less grounded): {e}")
        return []


async def generate_india_focus(
    report,
    classified: list,
    domain: str,
    date_range: str = "",
    lookback_days: int = 7,
    url_content_map: Optional[dict[str, str]] = None,
) -> Optional[IndiaFocus]:
    """
    Build the India Focus extras for an already India-scoped report.

    Streams are grounded in ``classified`` (the India article pool); the
    India-vs-Global comparison is grounded in a dedicated global-frontier search.

    Returns an ``IndiaFocus`` on success, or ``None`` on failure.
    """
    start = time.time()

    india_digest = _digest(classified, url_content_map, MAX_INDIA_ARTICLES)
    global_digest = await _gather_global_sources(domain, lookback_days)

    logger.info(
        f"[IndiaFocus] Synthesizing for domain='{domain}' from "
        f"{len(india_digest)} India + {len(global_digest)} global articles..."
    )

    prompt = [
        {
            "role": "system",
            "parts": (
                f"You are a senior technology analyst producing the structured INDIA FOCUS "
                f"extras for a report about '{domain}' covering {date_range}.\n\n"
                "You are given two evidence sets:\n"
                "  - INDIA ARTICLES: developments by Indian organizations (use for the streams).\n"
                "  - GLOBAL ARTICLES: latest global-frontier developments, incl. US & China "
                "(use ONLY to ground the comparison).\n\n"
                "Produce:\n"
                "1) Four streams from the INDIA articles:\n"
                "   - business: funding, commercialization, partnerships, policy and market moves\n"
                "   - technology: model/system releases, hardware/chips, infrastructure\n"
                "   - implementation: agentic AI and other real-world deployments, products\n"
                "   - research: novel/incremental research, open-source/GitHub, benchmarks\n"
                "   Each item: cite its source_url and name the Indian organizations involved.\n"
                "2) india_vs_global: a brief comparison focused on GenAI models (frontier + open-weight) "
                "and the broader ecosystem (compute/chips, capital, talent, open-source, deployment). "
                "Ground it in BOTH evidence sets and list the URLs you used in india_vs_global.sources.\n"
                "3) problem_categories: the key problems/priorities India is focusing on, with examples.\n\n"
                "GROUNDING RULES:\n"
                "- Stream items MUST come from the INDIA articles. Do NOT invent specific numbers, "
                "dates, model names, or events not supported by the evidence.\n"
                "- The comparison must reflect the GLOBAL ARTICLES for the global side (not memory). If "
                "that set is thin, keep the comparison qualitative and say so rather than fabricating.\n"
                "- Keep each stream to at most 6 items.\n\n"
                "OUTPUT RULES:\n"
                "- Return ONLY valid JSON matching the IndiaFocus schema.\n"
                "- Do NOT include schema definitions, $defs, $ref, properties, or type metadata.\n"
                "- Newlines inside string values MUST be written as \\n (escaped).\n"
                '- Double quotes inside string values MUST be escaped as \\".\n'
            ),
        },
        {
            "role": "user",
            "parts": (
                f"DOMAIN: {domain}\n"
                f"DATE RANGE: {date_range}\n\n"
                f"INDIA ARTICLES ({len(india_digest)}):\n"
                f"{json.dumps(india_digest, indent=2, ensure_ascii=False)}\n\n"
                f"GLOBAL ARTICLES ({len(global_digest)}):\n"
                f"{json.dumps(global_digest, indent=2, ensure_ascii=False)}\n\n"
                "Produce the India Focus extras. Return ONLY valid JSON."
            ),
        },
    ]

    try:
        result = await invoke_llm(
            gpu_model=GPU_SENSING_REPORT_LLM.model,
            response_schema=IndiaFocus,
            contents=prompt,
            port=GPU_SENSING_REPORT_LLM.port,
        )
        india = IndiaFocus.model_validate(result)
        elapsed = time.time() - start
        logger.info(
            f"[IndiaFocus] COMPLETE in {elapsed:.1f}s — "
            f"business={len(india.business)}, technology={len(india.technology)}, "
            f"implementation={len(india.implementation)}, research={len(india.research)}, "
            f"problem_categories={len(india.problem_categories)}, "
            f"comparison_sources={len(india.india_vs_global.sources)}"
        )
        return india
    except Exception as e:
        logger.warning(f"[IndiaFocus] Failed (skipping section): {e}")
        return None
