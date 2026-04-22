"""
LIR scoring engine — computes the 7-component score for each concept.

Components: convergence, velocity, novelty, authority, pattern_match,
persistence (EScore-inspired), cross_platform (multi-source confirmation).
"""

import logging
import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from core.lir.config import (
    CONVERGENCE_TIER_BONUS,
    CROSS_PLATFORM_FULL_SOURCES,
    CROSS_PLATFORM_MIN_SOURCES,
    CROSS_PLATFORM_TIER_BONUS,
    ESCORE_NOVELTY_WEIGHT,
    GLOBAL_VELOCITY_BASELINE,
    LLM_NOVELTY_WEIGHT,
    MAX_CONVERGENCE_BONUS,
    PERSISTENCE_FULL_MONTHS,
    PERSISTENCE_FULL_SIGNALS,
    PERSISTENCE_MIN_MONTHS,
    PERSISTENCE_MIN_SIGNALS,
    SCORE_WEIGHTS,
    SOURCE_TIER_AUTHORITY,
    VELOCITY_BASELINE_WEEKS,
    VELOCITY_DECAY_PENALTY,
    VELOCITY_DECAY_THRESHOLD,
    VELOCITY_DECAY_WINDOW_WEEKS,
    VELOCITY_SIGMOID_K,
    VELOCITY_SIGMOID_X0,
)
from core.lir.models import LIRConcept, LIRScoreSet, LIRSignalRecord
from core.lir.patterns import Fingerprint, compute_pattern_match

logger = logging.getLogger("lir.scoring")


def compute_scores(
    concepts: Dict[str, LIRConcept],
    signals: Dict[str, LIRSignalRecord],
    concept_signals: Dict[str, List[str]],
    fingerprints: Optional[Dict[str, Fingerprint]] = None,
) -> Dict[str, LIRScoreSet]:
    """Compute 7-component scores for all concepts.

    Args:
        concepts: Concept registry.
        signals: All signal records.
        concept_signals: concept_id -> [signal_ids] mapping.
        fingerprints: Pre-loaded fingerprints for pattern matching.

    Returns:
        concept_id -> LIRScoreSet mapping.
    """
    if fingerprints is None:
        from core.lir.patterns import load_fingerprints
        fingerprints = load_fingerprints()

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
        pattern_match_score = _compute_pattern_match(concept_sigs, fingerprints)
        persistence = _compute_persistence(concept_sigs)
        cross_platform = _compute_cross_platform(concept_sigs)

        scores[cid] = LIRScoreSet(
            convergence=convergence,
            velocity=velocity,
            novelty=novelty,
            authority=authority,
            pattern_match=pattern_match_score,
            persistence=persistence,
            cross_platform=cross_platform,
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

    Uses sigmoid function over MAD baseline, with decay detection
    and global baseline fallback for cold-start concepts.
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
        # Cold-start: use global baseline by dominant tier
        tier_counts = Counter(s.tier for s in signals)
        dominant_tier = tier_counts.most_common(1)[0][0]
        global_baseline = GLOBAL_VELOCITY_BASELINE.get(dominant_tier, 2.0)
        if recent_avg <= 0:
            velocity = 0.0
        else:
            ratio = recent_avg / global_baseline
            mads_above = max(0.0, ratio - 1.0)
            velocity = 1.0 / (1.0 + math.exp(-VELOCITY_SIGMOID_K * (mads_above - VELOCITY_SIGMOID_X0)))
    else:
        # MADs above baseline
        ratio = recent_avg / baseline_avg
        mads_above = max(0.0, ratio - 1.0)
        velocity = 1.0 / (1.0 + math.exp(-VELOCITY_SIGMOID_K * (mads_above - VELOCITY_SIGMOID_X0)))

    velocity = min(1.0, velocity)

    # ── Decay detection ──
    # If peak in last 12 weeks was >3x the most recent period, apply penalty
    decay_window = VELOCITY_DECAY_WINDOW_WEEKS
    recent_decay_avg = sum(
        weekly_counts.get(w, 0) for w in range(decay_window)
    ) / max(1, decay_window)

    peak_count = max(
        (weekly_counts.get(w, 0) for w in range(VELOCITY_BASELINE_WEEKS)),
        default=0,
    )

    if peak_count > 0 and recent_decay_avg > 0:
        drop_ratio = recent_decay_avg / peak_count
        if drop_ratio < VELOCITY_DECAY_THRESHOLD:
            # Significant decay from peak — apply penalty
            velocity *= VELOCITY_DECAY_PENALTY

    return min(1.0, velocity)


def _compute_novelty(signals: List[LIRSignalRecord]) -> float:
    """Novelty score: blends EScore objective measurement with LLM stated_novelty.

    EScore component: ratio of active-period to base-period signal count.
    LLM component: weighted average + max of stated_novelty from extraction.
    """
    if not signals:
        return 0.5  # Default prior

    # ── EScore objective novelty ──
    # Split signals by date into base period (older half) and active period (recent half)
    dated_signals = []
    for s in signals:
        try:
            pub = datetime.fromisoformat(s.published_date.replace("Z", "+00:00"))
            dated_signals.append((pub, s))
        except (ValueError, TypeError):
            continue

    escore_novelty = 0.5  # Default if we can't compute
    if len(dated_signals) >= 2:
        dated_signals.sort(key=lambda x: x[0])
        midpoint = len(dated_signals) // 2
        base_count = midpoint
        active_count = len(dated_signals) - midpoint
        if base_count > 0:
            novelty_ratio = active_count / base_count
            # Normalize: ratio of 3.0+ = full novelty score
            escore_novelty = min(1.0, novelty_ratio / 3.0)

    # ── LLM stated novelty ──
    novelties = [s.stated_novelty for s in signals if s.stated_novelty > 0]
    if novelties:
        avg = sum(novelties) / len(novelties)
        max_val = max(novelties)
        llm_novelty = min(1.0, 0.6 * avg + 0.4 * max_val)
    else:
        llm_novelty = 0.5

    # Blend objective and subjective
    return min(1.0, ESCORE_NOVELTY_WEIGHT * escore_novelty + LLM_NOVELTY_WEIGHT * llm_novelty)


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


def _compute_pattern_match(
    signals: List[LIRSignalRecord],
    fingerprints: Dict[str, Fingerprint],
) -> float:
    """Pattern match score: DTW/cosine similarity against fingerprint library.

    Builds weekly signal counts and compares against known emergence patterns.
    """
    if not signals or not fingerprints:
        return 0.0

    # Build weekly counts (last 52 weeks, oldest first)
    now = datetime.now(timezone.utc)
    weekly_counts = [0.0] * 52

    for sig in signals:
        try:
            pub = datetime.fromisoformat(
                sig.published_date.replace("Z", "+00:00")
            )
            weeks_ago = (now - pub).days // 7
            if 0 <= weeks_ago < 52:
                weekly_counts[51 - weeks_ago] += 1.0
        except (ValueError, TypeError):
            continue

    if sum(weekly_counts) == 0:
        return 0.0

    return compute_pattern_match(weekly_counts, fingerprints)


def _compute_persistence(signals: List[LIRSignalRecord]) -> float:
    """Persistence score: EScore-inspired temporal persistence check.

    Requires signals to appear across multiple distinct months to
    filter out flash-in-the-pan hype. A concept must have at least
    PERSISTENCE_MIN_SIGNALS across PERSISTENCE_MIN_MONTHS to score >0.
    """
    if not signals:
        return 0.0

    count = len(signals)
    if count < PERSISTENCE_MIN_SIGNALS:
        return 0.0

    # Count distinct year-month buckets
    months = set()
    for sig in signals:
        try:
            pub = datetime.fromisoformat(
                sig.published_date.replace("Z", "+00:00")
            )
            months.add((pub.year, pub.month))
        except (ValueError, TypeError):
            continue

    distinct_months = len(months)
    if distinct_months < PERSISTENCE_MIN_MONTHS:
        return 0.0

    # Gradient score: 50% from signal count, 50% from month spread
    signal_component = min(1.0, count / PERSISTENCE_FULL_SIGNALS)
    month_component = min(1.0, distinct_months / PERSISTENCE_FULL_MONTHS)

    return min(1.0, 0.5 * signal_component + 0.5 * month_component)


def _compute_cross_platform(signals: List[LIRSignalRecord]) -> float:
    """Cross-platform score: multi-source confirmation.

    Requires confirmation from 2+ independent data sources to score >0.
    Dramatically reduces false positives from single-platform noise.
    """
    if not signals:
        return 0.0

    unique_sources = set(s.source_id for s in signals)
    unique_tiers = set(s.tier for s in signals)

    if len(unique_sources) < CROSS_PLATFORM_MIN_SOURCES:
        return 0.0

    # Base score from source diversity
    base = min(1.0, (len(unique_sources) - 1) / max(1, CROSS_PLATFORM_FULL_SOURCES - 1))

    # Tier bonus: confirmation across tiers is stronger than same-tier
    tier_bonus = min(0.30, (len(unique_tiers) - 1) * CROSS_PLATFORM_TIER_BONUS)

    return min(1.0, base + tier_bonus)
