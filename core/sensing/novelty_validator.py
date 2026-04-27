"""
Novelty validator — checks each radar item to determine if it deserves a
Technology Deep Dive by verifying genuine novelty.

Runs between Phase 2 (radar generation) and Phase 4 (deep dive generation)
to avoid wasting LLM calls on established/generic/superseded technologies.

Uses a lightweight classify LLM for fast turnaround.
"""

import json
import logging
import time
from typing import List

from pydantic import Field

from core.constants import GPU_SENSING_CLASSIFY_LLM
from core.llm.client import invoke_llm
from core.llm.output_schemas.base import LLMOutputBase

logger = logging.getLogger("sensing.novelty_validator")


class NoveltyVerdict(LLMOutputBase):
    """LLM output: per-item novelty classification."""

    genuinely_new: List[str] = Field(
        description=(
            "Names of radar items that represent genuinely NEW technologies — "
            "first released/appeared within the lookback period, new versions of "
            "existing tech, or novel cross-technology developments."
        ),
    )
    established_or_generic: List[str] = Field(
        description=(
            "Names of radar items that are established patterns, well-known "
            "concepts, generic categories, superseded versions, or hardware "
            "platforms. These should NOT receive deep dives."
        ),
    )
    reasoning: List[str] = Field(
        default_factory=list,
        description=(
            "Brief reasoning for each item classified as established_or_generic. "
            "Format: 'item_name | reason'. "
            "E.g., 'Agentic RAG | well-known pattern since 2023, not a new technology'."
        ),
    )


async def validate_novelty(
    radar_items: list,
    classified_articles: list,
    domain: str = "Technology",
) -> set[str]:
    """
    Validate which radar items are genuinely novel and deserve deep dives.

    Returns a SET of radar item names that are genuinely new.
    Items not in this set should have is_new set to False.
    """
    if not radar_items:
        return set()

    validate_start = time.time()

    # Build compact summary for the validator
    items_for_review = []
    for item in radar_items:
        # Find supporting articles for context
        item_articles = []
        item_name_lower = item.name.lower()
        for art in classified_articles:
            if (
                item_name_lower in art.title.lower()
                or item_name_lower in art.summary.lower()
                or item_name_lower in getattr(art, "technology_name", "").lower()
            ):
                item_articles.append({
                    "title": art.title[:100],
                    "date": getattr(art, "published_date", ""),
                })
                if len(item_articles) >= 3:
                    break

        items_for_review.append({
            "name": item.name,
            "quadrant": item.quadrant,
            "ring": item.ring,
            "description": item.description,
            "is_new": item.is_new,
            "supporting_articles": item_articles,
        })

    prompt = [
        {
            "role": "system",
            "parts": (
                "You are a technology novelty classifier. Your task is to determine which "
                "radar items represent GENUINELY NEW technologies that deserve an in-depth "
                f"deep dive in a '{domain}' tech sensing report.\n\n"
                "CLASSIFY EACH ITEM into one of two categories:\n\n"
                "genuinely_new — KEEP for deep dive:\n"
                "- Technology that was FIRST RELEASED or FIRST APPEARED within the last few weeks/months\n"
                "- A genuinely new VERSION of an existing technology (e.g., DeepSeek V4 is new even "
                "though DeepSeek existed before)\n"
                "- A novel cross-technology collaboration or integration that didn't exist before\n"
                "- A new specific tool, framework, or model with a distinct name\n"
                "- When in doubt, classify as genuinely_new (err toward inclusion)\n\n"
                "established_or_generic — EXCLUDE from deep dive:\n"
                "- Well-known patterns or techniques that have existed for 6+ months "
                "(e.g., 'RAG', 'Agentic RAG', 'Self-RAG', 'Chain of Thought', 'RLHF', "
                "'Prompt Engineering', 'Fine-tuning', 'AI Agents')\n"
                "- Generic category names rather than specific technologies "
                "(e.g., 'AI Agent Frameworks', 'AI Agent Interaction Infrastructure', "
                "'LLM Confidence Calibration', 'Agentic World Modeling')\n"
                "- SUPERSEDED model versions when a newer version exists in the same list "
                "(e.g., if both Qwen3.5 and Qwen3.6 appear, exclude Qwen3.5)\n"
                "- Hardware platforms that are not domain-specific technologies "
                "(e.g., 'Mac Mini', 'NVIDIA H100', 'TPU v5')\n"
                "- Old APIs or products that have new tutorials/guides but were released "
                "long ago (e.g., 'GPT-4o Realtime API' released in 2024)\n"
                "- Broad research areas without a specific novel output "
                "(e.g., 'World Modeling', 'Confidence Calibration')\n\n"
                "IMPORTANT: Err on the side of INCLUSION. If you're unsure whether something "
                "is new, classify it as genuinely_new. Only exclude clear cases.\n\n"
                "OUTPUT RULES:\n"
                "- Return valid JSON with keys: genuinely_new, established_or_generic, reasoning.\n"
                "- Every radar item name must appear in exactly one of the two lists.\n"
                "- Provide reasoning ONLY for items classified as established_or_generic.\n"
                "- Do NOT include schema definitions, $defs, $ref, properties, or type metadata.\n"
            ),
        },
        {
            "role": "user",
            "parts": (
                f"DOMAIN: {domain}\n\n"
                f"RADAR ITEMS TO CLASSIFY:\n{json.dumps(items_for_review, indent=2, ensure_ascii=False)}\n\n"
                "Classify each item. Remember: when in doubt, include it as genuinely_new."
            ),
        },
    ]

    try:
        logger.info(
            f"Novelty validation: checking {len(radar_items)} radar items..."
        )

        result = await invoke_llm(
            gpu_model=GPU_SENSING_CLASSIFY_LLM.model,
            response_schema=NoveltyVerdict,
            contents=prompt,
            port=GPU_SENSING_CLASSIFY_LLM.port,
        )

        verdict = NoveltyVerdict.model_validate(result)

        # Log reasoning for excluded items
        for reason in verdict.reasoning:
            logger.info(f"Novelty exclusion: {reason}")

        elapsed = time.time() - validate_start
        logger.info(
            f"Novelty validation complete in {elapsed:.1f}s — "
            f"genuinely_new: {len(verdict.genuinely_new)}, "
            f"established: {len(verdict.established_or_generic)}"
        )

        return set(verdict.genuinely_new)

    except Exception as e:
        logger.warning(
            f"Novelty validation failed (treating all as new): {e}"
        )
        # On failure, treat all as new (conservative — don't lose items)
        return {item.name for item in radar_items}
