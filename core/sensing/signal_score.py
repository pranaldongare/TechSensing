"""
Signal Strength Scoring — computes composite confidence for each radar item
based on number of distinct sources, source authority, and relevance scores.
"""

import logging
from typing import List, Optional

from core.llm.output_schemas.sensing_outputs import (
    ClassifiedArticle,
    TechSensingReport,
)

logger = logging.getLogger("sensing.signal_score")

SOURCE_AUTHORITY: dict[str, float] = {
    "arXiv": 0.9,
    "GitHub": 0.85,
    "Hacker News": 0.7,
    "MIT Technology Review": 0.9,
    "TechCrunch": 0.8,
    "VentureBeat": 0.75,
    "The Verge": 0.7,
    "Ars Technica": 0.75,
    "IEEE Spectrum": 0.85,
    "Nature": 0.95,
    "Science": 0.95,
    "Google Patents": 0.85,
}
DEFAULT_AUTHORITY = 0.5


async def compute_signal_strengths(
    report: TechSensingReport,
    classified_articles: List[ClassifiedArticle],
    user_id: Optional[str] = None,
) -> TechSensingReport:
    """
    For each radar item, compute a signal_strength score (0.0-1.0) based on
    supporting articles' sources, count, and relevance.
    """
    # Load user feedback if available
    user_feedback = {}
    if user_id:
        try:
            from core.sensing.source_feedback import load_source_feedback
            user_feedback = await load_source_feedback(user_id)
        except Exception:
            pass

    from core.sensing.source_feedback import get_adjusted_authority

    # Build tech_name -> list of supporting articles
    article_map: dict[str, list[ClassifiedArticle]] = {}
    for article in classified_articles:
        key = article.technology_name.lower().strip()
        article_map.setdefault(key, []).append(article)

    scored = 0
    for item in report.radar_items:
        key = item.name.lower().strip()
        supporting = article_map.get(key, [])

        if not supporting:
            item.signal_strength = 0.2  # baseline for items without direct article match
            item.source_count = 0
            continue

        # Distinct sources
        sources = set(a.source for a in supporting)
        source_count = len(sources)

        # Count patent articles
        patent_articles = [a for a in supporting if a.source == "Google Patents"]
        item.patent_count = len(patent_articles)

        # Weighted authority (with user feedback adjustment)
        authority_scores = [
            get_adjusted_authority(
                SOURCE_AUTHORITY.get(a.source, DEFAULT_AUTHORITY),
                a.source,
                user_feedback,
            )
            for a in supporting
        ]
        avg_authority = sum(authority_scores) / len(authority_scores)

        # Average relevance
        avg_relevance = sum(a.relevance_score for a in supporting) / len(supporting)

        # Composite: 40% authority + 30% source diversity + 30% relevance
        diversity_score = min(source_count / 4.0, 1.0)  # Cap at 4 sources = 1.0
        strength = (
            0.4 * avg_authority
            + 0.3 * diversity_score
            + 0.3 * avg_relevance
        )
        strength = max(0.0, min(1.0, strength))

        item.signal_strength = round(strength, 2)
        item.source_count = source_count
        scored += 1

    logger.info(f"Signal scoring: {scored}/{len(report.radar_items)} items scored")
    return report
