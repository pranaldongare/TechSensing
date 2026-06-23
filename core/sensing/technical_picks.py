"""
Technical Picks — a deterministic, builder-oriented section appended to the
report for technical roles: the latest GitHub repos, arXiv papers, and
HuggingFace models, drawn straight from the raw ingested sources (so fresh
artifacts surface even if they didn't make the main report).

No LLM. Runs after the report is generated. Gated by role.
"""

import logging
from typing import List, Optional

from core.llm.output_schemas.sensing_outputs import TechnicalItem, TechnicalPicks

logger = logging.getLogger("sensing.technical_picks")

# Roles for whom GitHub/arXiv/HuggingFace artifacts add the most value.
TECHNICAL_ROLES = {"developer", "engineering_lead"}

_PER_BUCKET = 5


def is_technical_role(role: Optional[str]) -> bool:
    return (role or "").strip().lower() in TECHNICAL_ROLES


def _to_items(raw_articles: list, limit: int = _PER_BUCKET) -> List[TechnicalItem]:
    """Sort raw articles newest-first and map to TechnicalItem."""
    items = [a for a in (raw_articles or []) if getattr(a, "title", "") and getattr(a, "url", "")]
    # Newest first; undated sink to the bottom but are still kept.
    items.sort(key=lambda a: (getattr(a, "published_date", "") or ""), reverse=True)
    out: List[TechnicalItem] = []
    for a in items[:limit]:
        out.append(TechnicalItem(
            title=(getattr(a, "title", "") or "")[:160],
            url=getattr(a, "url", "") or "",
            summary=(getattr(a, "content", "") or getattr(a, "snippet", "") or "")[:240],
            meta=(getattr(a, "snippet", "") or "")[:120],
            published=getattr(a, "published_date", "") or "",
        ))
    return out


def build_technical_picks(
    github_raw: list,
    arxiv_raw: list,
    huggingface_raw: list,
    per_bucket: int = _PER_BUCKET,
) -> Optional[TechnicalPicks]:
    """Build the TechnicalPicks section, or None if every bucket is empty."""
    github = _to_items(github_raw, per_bucket)
    arxiv = _to_items(arxiv_raw, per_bucket)
    huggingface = _to_items(huggingface_raw, per_bucket)
    if not (github or arxiv or huggingface):
        return None
    logger.info(
        f"[TechnicalPicks] github={len(github)}, arxiv={len(arxiv)}, "
        f"huggingface={len(huggingface)}"
    )
    return TechnicalPicks(github=github, arxiv=arxiv, huggingface=huggingface)
