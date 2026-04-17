"""
LIR scoring engine — computes the 5-component score for each concept.

Phase 1: convergence + velocity active; novelty + authority use priors;
          pattern_match stubbed at 0.0.
"""

import logging
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List

from core.lir.config import (
    CONVERGENCE_TIER_BONUS,
    MAX_CONVERGENCE_BONUS,
    SCORE_WEIGHTS,
    SOURCE_TIER_AUTHORITY,
    VELOCITY_BASELINE_WEEKS,
    VELOCITY_SIGMOID_K,
    VELOCITY_SIGMOID_X0,
)
from core.lir.models import LIRConcept, LIRScoreSet, LIRSignalRecord

logger = logging.getLogger("lir.scoring")


def compute_scores(
    concepts: Dict[str, LIRConcept],
    signals: Dict[str, LIRSignalRecord],
    concept_signals: Dict[str, List[str]],
) -> Dict[str, LIRScoreSet]:
    """Compute 5-component scores for all concepts.

    Args:
        concepts: Concept registry.
        signals: All signal records.
        concept_signals: concept_id -> [signal_ids] mapping.

    Returns:
        concept_id -> LIRScoreSet mapping.
    """
    scores: Dict[str, LIRScoreSet] = {}

    for cid, concept in concepts.items():
        sig_ids = concept_signals.get(cid, [])
        concept_sigs = [signals[sid] for sid in sig_ids if sid in signals]

        if not concept_sigs:
            scores[cid] = LIRScoreSet()
            continue

        convergence = _compute_convergence(concept_sigs)
        velocity = _compute_velocity(concept_sigs)
        novelty = _compute_novelty(concept_sigs)
        authority = _compute_authority(concept_sigs)
        pattern_match = 0.0  # Phase 3

        scores[cid] = LIRScoreSet(
            convergence=convergence,
            velocity=velocity,
            novelty=novelty,
            authority=authority,
            pattern_match=pattern_match,
        )

    logger.info(f"Scored {len(scores)} concepts")
    return scores


def _compute_convergence(signals: List[LIRSignalRecord]) -> float:
    """Convergence score: evidence from multiple independent source tiers.

    Base score from signal count (log-scaled), plus bonus for tier diversity.
    """
    if not signals:
        return 0.0

    # Base: log-scaled signal count (1 signal = ~0.3, 10 = ~0.7, 30+ = ~0.9)
    count = len(signals)
    base = min(1.0, math.log(count + 1) / math.log(35))

    # Tier diversity bonus
    unique_tiers = set(s.tier for s in signals)
    tier_bonus = min(
        MAX_CONVERGENCE_BONUS,
        (len(unique_tiers) - 1) * CONVERGENCE_TIER_BONUS,
    )

    # Source diversity: unique source_ids
    unique_sources = set(s.source_id for s in signals)
    source_bonus = min(0.1, (len(unique_sources) - 1) * 0.05)

    return min(1.0, base + tier_bonus + source_bonus)


def _compute_velocity(signals: List[LIRSignalRecord]) -> float:
    """Velocity score: acceleration of signal count over time.

    Uses sigmoid function over MAD (median absolute deviation) baseline.
    """
    if len(signals) < 2:
        return 0.0

    # Bin signals into weeks
    now = datetime.now(timezone.utc)
    weekly_counts: Dict[int, int] = defaultdict(int)

    for sig in signals:
        try:
            pub = datetime.fromisoformat(
                sig.published_date.replace("Z", "+00:00")
            )
            weeks_ago = max(0, (now - pub).days // 7)
            weekly_counts[weeks_ago] = weekly_counts.get(weeks_ago, 0) + 1
        except (ValueError, TypeError):
            continue

    if not weekly_counts:
        return 0.0

    # Get recent vs baseline counts
    recent_weeks = 4
    baseline_weeks = min(VELOCITY_BASELINE_WEEKS, max(weekly_counts.keys()) + 1)

    recent_total = sum(
        weekly_counts.get(w, 0) for w in range(recent_weeks)
    )
    baseline_total = sum(
        weekly_counts.get(w, 0) for w in range(recent_weeks, baseline_weeks)
    )

    baseline_avg = baseline_total / max(1, baseline_weeks - recent_weeks)
    recent_avg = recent_total / max(1, recent_weeks)

    if baseline_avg == 0:
        # No baseline — use simple count-based score
        return min(1.0, recent_avg / 5.0)

    # MADs above baseline
    ratio = recent_avg / baseline_avg
    mads_above = max(0.0, ratio - 1.0)

    # Sigmoid mapping
    velocity = 1.0 / (1.0 + math.exp(-VELOCITY_SIGMOID_K * (mads_above - VELOCITY_SIGMOID_X0)))

    return min(1.0, velocity)


def _compute_novelty(signals: List[LIRSignalRecord]) -> float:
    """Novelty score: aggregate stated_novelty from extraction.

    Takes the weighted average of stated_novelty across signals,
    biased toward higher values (max contributes 40%).
    """
    if not signals:
        return 0.5  # Default prior

    novelties = [s.stated_novelty for s in signals if s.stated_novelty > 0]
    if not novelties:
        return 0.5

    avg = sum(novelties) / len(novelties)
    max_val = max(novelties)

    # Blend: 60% average, 40% max (rewards breakthrough signals)
    return min(1.0, 0.6 * avg + 0.4 * max_val)


def _compute_authority(signals: List[LIRSignalRecord]) -> float:
    """Authority score: weighted by source tier authority priors.

    Higher-tier sources (T1 = academic) contribute more authority.
    """
    if not signals:
        return 0.5  # Default prior

    total_weight = 0.0
    weighted_authority = 0.0

    for sig in signals:
        tier_auth = SOURCE_TIER_AUTHORITY.get(sig.tier, 0.5)
        relevance = max(0.1, sig.relevance_score)
        weight = relevance
        weighted_authority += tier_auth * weight
        total_weight += weight

    if total_weight == 0:
        return 0.5

    return min(1.0, weighted_authority / total_weight)
