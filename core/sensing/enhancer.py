"""
Enhancer agent — second-pass gap filling for tech sensing reports.

Finds classified articles not covered in the first-pass report and asks a
lightweight LLM to determine which are genuinely important.  Strictly
additive: never modifies existing report content, only appends new items.

Runs between verification and movement detection in the pipeline.
"""

import json
import logging
import re
import time
from typing import List, Optional

from core.constants import GPU_SENSING_CLASSIFY_LLM
from core.llm.client import invoke_llm
from core.llm.output_schemas.sensing_outputs import (
    EnhancerOutput,
    TechSensingReport,
)

logger = logging.getLogger("sensing.enhancer")


# ── Helpers ──────────────────────────────────────────────────────────────

def _normalize(name: str) -> str:
    """Lowercase and strip whitespace/punctuation for comparison."""
    return re.sub(r"[^a-z0-9 .]", "", name.lower()).strip()


def _word_set(name: str) -> set[str]:
    """Return the set of meaningful words in a name."""
    return {w for w in _normalize(name).split() if len(w) > 1}


def _is_covered(tech_name: str, covered_names: set[str], covered_words: set[str]) -> bool:
    """Check if a technology name is already represented in the report."""
    norm = _normalize(tech_name)

    # Exact or substring match
    if norm in covered_names:
        return True
    for cn in covered_names:
        if norm in cn or cn in norm:
            return True

    # Word-overlap: >50% of words in tech_name appear in covered words
    words = _word_set(tech_name)
    if words and len(words & covered_words) / len(words) > 0.5:
        return True

    return False


# ── Gap detection ────────────────────────────────────────────────────────

def _detect_gaps(
    report: TechSensingReport,
    classified_articles: list,
    min_relevance: float = 0.5,
    max_orphans: int = 20,
    min_orphans_to_enhance: int = 3,
) -> Optional[list]:
    """
    Find classified articles whose technology isn't covered in the report.

    Returns top orphan articles sorted by relevance_score,
    or None if there are too few gaps to justify an LLM call.
    """
    # Build covered technology names from report
    covered_names: set[str] = set()
    covered_words: set[str] = set()

    for item in report.radar_items:
        covered_names.add(_normalize(item.name))
        covered_words |= _word_set(item.name)

    for event in report.top_events:
        covered_names.add(_normalize(event.headline))
        covered_words |= _word_set(event.headline)
        if event.actor:
            covered_names.add(_normalize(event.actor))
            covered_words |= _word_set(event.actor)

    for trend in report.key_trends:
        covered_names.add(_normalize(trend.trend_name))
        covered_words |= _word_set(trend.trend_name)

    for article in (report.notable_articles or []):
        covered_names.add(_normalize(article.technology_name))
        covered_words |= _word_set(article.technology_name)

    # Find orphan articles
    orphans = []
    for article in classified_articles:
        if article.relevance_score < min_relevance:
            continue
        if _is_covered(article.technology_name, covered_names, covered_words):
            continue
        orphans.append(article)

    # Sort by relevance descending, cap at max_orphans
    orphans.sort(key=lambda a: a.relevance_score, reverse=True)
    orphans = orphans[:max_orphans]

    logger.info(
        f"[Enhancement] Gap detection: {len(orphans)} orphan articles "
        f"(covered: {len(covered_names)} technologies)"
    )

    if len(orphans) < min_orphans_to_enhance:
        logger.info(
            f"[Enhancement] Below threshold of {min_orphans_to_enhance}, skipping"
        )
        return None

    return orphans


# ── Main entry point ─────────────────────────────────────────────────────

async def enhance_report(
    report: TechSensingReport,
    classified: list,
    domain: str,
    url_content_map: Optional[dict[str, str]] = None,
) -> TechSensingReport:
    """
    Second-pass enhancement: find gaps in the report and add missed items.

    Additive only — never modifies existing report content.
    Returns the report with any additions appended.
    """
    enhance_start = time.time()

    # Step 1: Programmatic gap detection
    orphans = _detect_gaps(report, classified)
    if orphans is None:
        logger.info("[Enhancement] COMPLETE (no enhancement needed)")
        return report

    # Build covered topics list for the prompt
    covered_topics = sorted({
        item.name for item in report.radar_items
    } | {
        event.headline for event in report.top_events
    } | {
        trend.trend_name for trend in report.key_trends
    })

    # Build compact orphan data for the prompt
    content_map = url_content_map or {}
    orphan_data = []
    for art in orphans:
        entry = {
            "title": art.title,
            "technology_name": art.technology_name,
            "summary": art.summary,
            "relevance_score": art.relevance_score,
            "source": art.source,
            "url": art.url,
        }
        excerpt = content_map.get(art.url, "")
        if excerpt:
            entry["content_excerpt"] = excerpt[:500]
        orphan_data.append(entry)

    # Step 2: Single LLM call
    prompt = [
        {
            "role": "system",
            "parts": (
                f"You are an enhancement agent for a tech sensing report about '{domain}'.\n\n"
                "A first-pass report has already been generated. You are given classified "
                "articles that were NOT covered in the report.\n\n"
                "Your task: identify ONLY genuinely important developments that the report "
                "missed and generate additional entries.\n\n"
                "RULES:\n"
                "- Be CONSERVATIVE. Only add items that represent significant, distinct developments.\n"
                "- Do NOT add items that overlap with or duplicate existing report coverage.\n"
                "- Do NOT add generic or broad category items (e.g., 'AI', 'Machine Learning', "
                "'RAG', 'AI Agents').\n"
                "- Each additional_event must be about a specific, newsworthy development.\n"
                "- Each additional_radar_item must name a SPECIFIC technology, tool, or framework.\n"
                "- If an orphan article is about a minor update, opinion piece, or tangential "
                "topic, add its title to skipped_articles.\n"
                "- It is perfectly fine to add NOTHING. If the report already has good coverage, "
                "return empty lists and set enhancement_summary to 'No enhancements needed'.\n\n"
                "LIMITS:\n"
                "- additional_events: maximum 3\n"
                "- additional_radar_items: maximum 5\n"
                "- additional_recommendations: maximum 2\n\n"
                "OUTPUT RULES:\n"
                "- Return ONLY valid JSON.\n"
                "- Do NOT include schema definitions, $defs, $ref, properties, or type metadata.\n"
                "- Newlines inside string values MUST be written as \\n (escaped).\n"
                '- Double quotes inside string values MUST be escaped as \\".\n'
            ),
        },
        {
            "role": "user",
            "parts": (
                f"DOMAIN: {domain}\n\n"
                f"ALREADY COVERED IN REPORT:\n"
                + "\n".join(f"- {t}" for t in covered_topics)
                + f"\n\nORPHAN ARTICLES ({len(orphan_data)} articles not covered):\n"
                f"{json.dumps(orphan_data, indent=2, ensure_ascii=False)}\n\n"
                "Identify genuinely important developments and generate additional entries. "
                "Return ONLY valid JSON."
            ),
        },
    ]

    try:
        logger.info(
            f"[Enhancement] Sending {len(orphans)} orphan articles to LLM..."
        )

        result = await invoke_llm(
            gpu_model=GPU_SENSING_CLASSIFY_LLM.model,
            response_schema=EnhancerOutput,
            contents=prompt,
            port=GPU_SENSING_CLASSIFY_LLM.port,
        )

        enhanced = EnhancerOutput.model_validate(result)

        # Step 3: Additive merge with dedup safety net
        existing_radar_names = {_normalize(item.name) for item in report.radar_items}
        existing_event_headlines = {_normalize(e.headline) for e in report.top_events}

        added_events = 0
        for event in enhanced.additional_events:
            if _normalize(event.headline) not in existing_event_headlines:
                report.top_events.append(event)
                existing_event_headlines.add(_normalize(event.headline))
                added_events += 1
                logger.info(f"[Enhancement] Added event: \"{event.headline}\"")

        added_radar = 0
        for item in enhanced.additional_radar_items:
            if _normalize(item.name) not in existing_radar_names:
                report.radar_items.append(item)
                existing_radar_names.add(_normalize(item.name))
                added_radar += 1
                logger.info(
                    f"[Enhancement] Added radar item: \"{item.name}\" "
                    f"({item.ring}, {item.quadrant})"
                )

        added_recs = 0
        for rec in enhanced.additional_recommendations:
            report.recommendations.append(rec)
            added_recs += 1
            logger.info(f"[Enhancement] Added recommendation: \"{rec.title}\"")

        elapsed = time.time() - enhance_start
        logger.info(
            f"[Enhancement] LLM returned: {added_events} events, "
            f"{added_radar} radar items, {added_recs} recommendations, "
            f"{len(enhanced.skipped_articles)} skipped"
        )
        if enhanced.enhancement_summary:
            logger.info(f"[Enhancement] Summary: {enhanced.enhancement_summary}")
        logger.info(f"[Enhancement] COMPLETE in {elapsed:.1f}s")

    except Exception as e:
        logger.warning(f"[Enhancement] Failed (keeping original report): {e}")

    return report
