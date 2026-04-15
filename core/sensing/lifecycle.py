"""
Technology Lifecycle Stage Detection — infers lifecycle stage from source type distribution.

Heuristic mapping:
  - Only papers (arXiv, Semantic Scholar) → Research
  - Papers + GitHub repos → Prototype
  - Papers + repos + blog posts/news → Early Adoption
  - News + enterprise blogs + patents → Mainstream
  - Declining article count + legacy term matches → Legacy
"""

import logging
from typing import List

from core.llm.output_schemas.sensing_outputs import (
    ClassifiedArticle,
    TechSensingReport,
)

logger = logging.getLogger("sensing.lifecycle")

ACADEMIC_SOURCES = {"arXiv", "Semantic Scholar"}
CODE_SOURCES = {"GitHub"}
NEWS_SOURCES = {"TechCrunch", "VentureBeat", "The Verge", "Ars Technica", "Wired",
                "MIT Technology Review", "Hacker News", "Reddit", "DEV.to"}
PATENT_SOURCES = {"Google Patents", "USPTO Patent", "EPO Patent"}
ENTERPRISE_SOURCES = {"IEEE Spectrum", "Nature", "Science"}


def detect_lifecycle_stages(
    report: TechSensingReport,
    classified_articles: List[ClassifiedArticle],
) -> TechSensingReport:
    """Assign lifecycle stage to each radar item based on supporting source types."""

    # Build tech -> source type sets
    tech_sources: dict[str, set[str]] = {}
    for article in classified_articles:
        key = article.technology_name.lower().strip()
        tech_sources.setdefault(key, set()).add(article.source)

    assigned = 0
    for item in report.radar_items:
        key = item.name.lower().strip()
        sources = tech_sources.get(key, set())

        has_academic = bool(sources & ACADEMIC_SOURCES)
        has_code = bool(sources & CODE_SOURCES)
        has_news = bool(sources & NEWS_SOURCES)
        has_patents = bool(sources & PATENT_SOURCES)
        has_enterprise = bool(sources & ENTERPRISE_SOURCES)

        # Determine stage
        if has_news and has_patents and (has_enterprise or len(sources) >= 4):
            stage = "mainstream"
        elif has_news and (has_code or has_academic):
            stage = "early_adoption"
        elif has_academic and has_code:
            stage = "prototype"
        elif has_academic and not has_news and not has_code:
            stage = "research"
        elif has_news and not has_academic and not has_code:
            stage = "mainstream"  # news-only usually means established
        else:
            stage = "early_adoption"  # safe default

        item.lifecycle_stage = stage
        assigned += 1

    logger.info(f"Lifecycle detection: assigned stages to {assigned}/{len(report.radar_items)} items")
    return report
