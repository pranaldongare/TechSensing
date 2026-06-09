"""
China Focus extras — the structured China section that accompanies a
China-scoped report.

When China Focus is enabled the whole report is already China-scoped (China
ingestion + separate China prompts). This pass adds the structured extras:

  - Four streams: Business, Technology, Implementation, Research
    (grounded in the China articles the report already gathered)
  - A China vs US comparison (GenAI models + ecosystem), grounded in a
    DEDICATED US search run here — not the model's memory
  - A categorization of the problems China is focusing on

Strictly additive and non-fatal: returns ``None`` on any error and the caller
leaves ``report.china_focus`` unset.
"""

import asyncio
import json
import logging
import time
from typing import Optional

from core.constants import GPU_SENSING_REPORT_LLM
from core.llm.client import invoke_llm
from core.llm.output_schemas.sensing_outputs import ChinaFocus

logger = logging.getLogger("sensing.china_focus")

# Cap how much we feed the synthesis LLM.
MAX_CHINA_ARTICLES = 60
US_MAX_ARTICLES = 10
US_EXTRACT_CONCURRENCY = 5


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


async def _gather_us_sources(domain: str, lookback_days: int) -> list[dict]:
    """Dedicated US search to ground the China-vs-US comparison."""
    try:
        from core.sensing.china_sources import get_us_comparison_queries
        from core.sensing.dedup import deduplicate_articles
        from core.sensing.ingest import extract_full_text, search_duckduckgo

        queries = get_us_comparison_queries(domain)
        raw = await search_duckduckgo(queries, domain, lookback_days=lookback_days)
        unique = deduplicate_articles(raw)[:US_MAX_ARTICLES]

        sem = asyncio.Semaphore(US_EXTRACT_CONCURRENCY)

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
        logger.info(f"[ChinaFocus] US comparison sources gathered: {len(digest)}")
        return digest
    except Exception as e:
        logger.warning(f"[ChinaFocus] US source gathering failed (comparison less grounded): {e}")
        return []


async def generate_china_focus(
    report,
    classified: list,
    domain: str,
    date_range: str = "",
    lookback_days: int = 7,
    url_content_map: Optional[dict[str, str]] = None,
) -> Optional[ChinaFocus]:
    """
    Build the China Focus extras for an already China-scoped report.

    Streams are grounded in ``classified`` (the China article pool); the
    China-vs-US comparison is grounded in a dedicated US search.

    Returns a ``ChinaFocus`` on success, or ``None`` on failure.
    """
    start = time.time()

    china_digest = _digest(classified, url_content_map, MAX_CHINA_ARTICLES)
    us_digest = await _gather_us_sources(domain, lookback_days)

    logger.info(
        f"[ChinaFocus] Synthesizing for domain='{domain}' from "
        f"{len(china_digest)} China + {len(us_digest)} US articles..."
    )

    prompt = [
        {
            "role": "system",
            "parts": (
                f"You are a senior technology analyst producing the structured CHINA FOCUS "
                f"extras for a report about '{domain}' covering {date_range}.\n\n"
                "You are given two evidence sets:\n"
                "  - CHINA ARTICLES: developments by Chinese organizations (use for the streams).\n"
                "  - US ARTICLES: latest US developments (use ONLY to ground the comparison).\n\n"
                "Produce:\n"
                "1) Four streams from the CHINA articles:\n"
                "   - business: funding, commercialization, partnerships, policy and market moves\n"
                "   - technology: model/system releases, hardware/chips, infrastructure\n"
                "   - implementation: agentic AI and other real-world deployments, products\n"
                "   - research: novel/incremental research, open-source/GitHub, benchmarks\n"
                "   Each item: cite its source_url and name the Chinese organizations involved.\n"
                "2) china_vs_us: a brief comparison focused on GenAI models (frontier + open-weight) "
                "and the broader ecosystem (compute/chips, capital, talent, open-source, deployment). "
                "Ground it in BOTH evidence sets and list the URLs you used in china_vs_us.sources.\n"
                "3) problem_categories: the key problems/priorities China is focusing on, with examples.\n\n"
                "GROUNDING RULES:\n"
                "- Stream items MUST come from the CHINA articles. Do NOT invent specific numbers, "
                "dates, model names, or events not supported by the evidence.\n"
                "- The comparison must reflect the US ARTICLES for the US side (not memory). If the US "
                "set is thin, keep the comparison qualitative and say so rather than fabricating.\n"
                "- Keep each stream to at most 6 items.\n\n"
                "OUTPUT RULES:\n"
                "- Return ONLY valid JSON matching the ChinaFocus schema.\n"
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
                f"CHINA ARTICLES ({len(china_digest)}):\n"
                f"{json.dumps(china_digest, indent=2, ensure_ascii=False)}\n\n"
                f"US ARTICLES ({len(us_digest)}):\n"
                f"{json.dumps(us_digest, indent=2, ensure_ascii=False)}\n\n"
                "Produce the China Focus extras. Return ONLY valid JSON."
            ),
        },
    ]

    try:
        result = await invoke_llm(
            gpu_model=GPU_SENSING_REPORT_LLM.model,
            response_schema=ChinaFocus,
            contents=prompt,
            port=GPU_SENSING_REPORT_LLM.port,
        )
        china = ChinaFocus.model_validate(result)
        elapsed = time.time() - start
        logger.info(
            f"[ChinaFocus] COMPLETE in {elapsed:.1f}s — "
            f"business={len(china.business)}, technology={len(china.technology)}, "
            f"implementation={len(china.implementation)}, research={len(china.research)}, "
            f"problem_categories={len(china.problem_categories)}, "
            f"comparison_sources={len(china.china_vs_us.sources)}"
        )
        return china
    except Exception as e:
        logger.warning(f"[ChinaFocus] Failed (skipping section): {e}")
        return None
