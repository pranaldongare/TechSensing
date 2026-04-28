"""
Feedback Consolidator — aggregates existing user feedback into learning signals.

Reads from:
- source_feedback.py — source quality votes (upvotes/downvotes)
- topic_preferences.py — user topic interest preferences
- annotations.py — user notes on report items

Produces a compact text block for injection into report generation prompts.
No LLM call required — pure data aggregation.
"""

import logging
from typing import Optional

from core.sensing.source_feedback import load_source_feedback

logger = logging.getLogger("sensing.feedback_consolidator")


async def consolidate_feedback(user_id: str, domain: str) -> str:
    """Aggregate user feedback into a compact prompt block.

    Returns an empty string if no meaningful feedback exists.
    """
    if not user_id:
        return ""

    parts = []

    # --- Source quality feedback ---
    try:
        source_fb = await load_source_feedback(user_id)
        if source_fb:
            preferred = []
            distrusted = []
            for source_name, info in source_fb.items():
                ups = info.get("upvotes", 0)
                downs = info.get("downvotes", 0)
                modifier = info.get("user_authority_modifier", 0.0)
                if modifier > 0.05:
                    preferred.append(f"{source_name} (+{ups})")
                elif modifier < -0.05:
                    distrusted.append(f"{source_name} (-{downs})")

            if preferred or distrusted:
                lines = []
                if preferred:
                    lines.append(f"  Preferred sources: {', '.join(preferred)}")
                if distrusted:
                    lines.append(f"  Distrusted sources: {', '.join(distrusted)}")
                parts.append("Source quality feedback:\n" + "\n".join(lines))
    except Exception as e:
        logger.debug(f"[FeedbackConsolidator] Source feedback unavailable: {e}")

    # --- Topic preferences ---
    try:
        from core.sensing.topic_preferences import load_topic_preferences

        prefs = await load_topic_preferences(user_id, domain)
        if prefs.interested or prefs.not_interested:
            lines = []
            if prefs.interested:
                lines.append(f"  Interested in: {', '.join(prefs.interested)}")
            if prefs.not_interested:
                lines.append(f"  Not interested in: {', '.join(prefs.not_interested)}")
            parts.append("Topic preferences:\n" + "\n".join(lines))
    except Exception as e:
        logger.debug(f"[FeedbackConsolidator] Topic preferences unavailable: {e}")

    # --- Annotation patterns ---
    try:
        from core.sensing.annotations import load_annotations

        annotations = await load_annotations(user_id)
        if annotations:
            # Count annotation types to summarize
            ann_count = len(annotations)
            parts.append(f"User has {ann_count} annotations across reports.")
    except Exception as e:
        logger.debug(f"[FeedbackConsolidator] Annotations unavailable: {e}")

    if not parts:
        return ""

    block = "USER FEEDBACK SIGNALS:\n" + "\n".join(f"- {p}" for p in parts)
    logger.info(f"[FeedbackConsolidator] Built feedback block ({len(parts)} signals)")
    return block
