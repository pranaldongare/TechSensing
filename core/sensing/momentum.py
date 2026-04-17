"""Per-company momentum scoring for Key Companies (#8).

Momentum is a coarse 0-100 score derived from the weighted count and mix
of notable updates in a briefing window. It's deterministic, runs
post-LLM, and costs nothing.
"""

from __future__ import annotations

from typing import List

from core.llm.output_schemas.analysis_extensions import MomentumSnapshot
from core.llm.output_schemas.key_companies import CompanyBriefing, CompanyUpdate


_CATEGORY_WEIGHTS = {
    "Product Launch": 3.0,
    "Funding": 4.0,
    "Acquisition": 4.0,
    "Partnership": 2.0,
    "Research": 2.0,
    "Regulatory": 2.5,
    "Technical": 1.5,
    "People": 1.0,
    "Other": 1.0,
}

_SENTIMENT_MULTIPLIER = {
    "positive": 1.25,
    "neutral": 1.0,
    "negative": 0.75,
}


def _score_update(u: CompanyUpdate) -> float:
    w = _CATEGORY_WEIGHTS.get(u.category or "Other", 1.0)
    s = _SENTIMENT_MULTIPLIER.get(getattr(u, "sentiment", "neutral"), 1.0)
    return w * s


def compute_momentum(briefing: CompanyBriefing) -> MomentumSnapshot:
    """Return a MomentumSnapshot populated from briefing updates."""
    updates = briefing.updates or []
    count = len(updates)
    weighted = round(sum(_score_update(u) for u in updates), 2)

    # Normalize to 0-100 via a soft ceiling: 10 weighted points → ~100.
    raw_score = min(weighted / 10.0, 1.0) * 100.0

    # Surface the top 3 categories driving the score.
    by_cat: dict[str, float] = {}
    for u in updates:
        by_cat[u.category or "Other"] = (
            by_cat.get(u.category or "Other", 0.0) + _score_update(u)
        )
    top = sorted(by_cat.items(), key=lambda kv: kv[1], reverse=True)[:3]
    drivers: List[str] = [f"{k} (×{round(v, 1)})" for k, v in top]

    return MomentumSnapshot(
        score=round(raw_score, 1),
        update_count=count,
        weighted_score=weighted,
        top_drivers=drivers,
    )
