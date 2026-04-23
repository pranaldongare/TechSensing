"""
LIR backtest engine — replay mode with clock-freezing and weight learning.

Replays historical data through the 7-component scoring engine at past
timestamps to evaluate how early concepts reach ring thresholds.
"""

import itertools
import logging
import math
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional

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
    RING_THRESHOLDS,
    SCORE_WEIGHTS,
    SOURCE_TIER_AUTHORITY,
    VELOCITY_BASELINE_WEEKS,
    VELOCITY_DECAY_PENALTY,
    VELOCITY_DECAY_THRESHOLD,
    VELOCITY_DECAY_WINDOW_WEEKS,
    VELOCITY_SIGMOID_K,
    VELOCITY_SIGMOID_X0,
    score_to_ring,
)
from core.lir.models import LIRConcept, LIRScoreSet, LIRSignalRecord
from core.lir.patterns import compute_pattern_match, load_fingerprints
from core.lir.storage import load_concept_signals, load_concepts, load_signals

logger = logging.getLogger("lir.backtest")


@dataclass
class BacktestSnapshot:
    """A single point-in-time snapshot of a concept's scores during backtest."""

    week_offset: int  # Weeks from start of backtest window
    date: str  # ISO date of the snapshot
    signal_count: int
    scores: Dict[str, float]  # All 7 score components
    composite: float
    ring: str


@dataclass
class BacktestConceptResult:
    """Backtest results for a single concept."""

    concept_id: str
    canonical_name: str
    snapshots: List[BacktestSnapshot] = field(default_factory=list)
    first_assess_week: Optional[int] = None
    first_trial_week: Optional[int] = None
    first_adopt_week: Optional[int] = None
    consensus_week: Optional[int] = None  # When it was known mainstream


@dataclass
class BacktestRunResult:
    """Result of a full backtest run."""

    run_id: str
    start_date: str
    end_date: str
    weights_used: Dict[str, float]
    concept_results: List[BacktestConceptResult]
    total_concepts: int
    execution_time_seconds: float
    errors: List[str] = field(default_factory=list)


# ──────────────────────── Scoring (frozen-clock variant) ────────────────────────


def _score_at_time(
    concept_signals: List[LIRSignalRecord],
    cutoff: datetime,
    weights: Dict[str, float],
    fingerprints=None,
) -> LIRScoreSet:
    """Score a concept using only signals available before the cutoff date.

    This is the clock-frozen variant of compute_scores — it filters
    signals by published_date and computes all 7 components.
    """
    # Filter signals to those published before cutoff
    visible = []
    for s in concept_signals:
        try:
            pub = datetime.fromisoformat(s.published_date.replace("Z", "+00:00"))
            if pub <= cutoff:
                visible.append(s)
        except (ValueError, TypeError):
            continue

    if not visible:
        return LIRScoreSet()

    # ── Convergence ──
    count = len(visible)
    base = min(1.0, math.log(count + 1) / math.log(35))
    unique_tiers = set(s.tier for s in visible)
    tier_bonus = min(MAX_CONVERGENCE_BONUS, (len(unique_tiers) - 1) * CONVERGENCE_TIER_BONUS)
    unique_sources = set(s.source_id for s in visible)
    source_bonus = min(0.1, (len(unique_sources) - 1) * 0.05)
    convergence = min(1.0, base + tier_bonus + source_bonus)

    # ── Velocity ──
    weekly_counts: Dict[int, int] = defaultdict(int)
    for sig in visible:
        try:
            pub = datetime.fromisoformat(sig.published_date.replace("Z", "+00:00"))
            weeks_ago = max(0, (cutoff - pub).days // 7)
            weekly_counts[weeks_ago] += 1
        except (ValueError, TypeError):
            continue

    velocity = 0.0
    if weekly_counts and len(visible) >= 2:
        recent_weeks = 4
        baseline_weeks = min(VELOCITY_BASELINE_WEEKS, max(weekly_counts.keys()) + 1)
        recent_total = sum(weekly_counts.get(w, 0) for w in range(recent_weeks))
        baseline_total = sum(weekly_counts.get(w, 0) for w in range(recent_weeks, baseline_weeks))
        baseline_avg = baseline_total / max(1, baseline_weeks - recent_weeks)
        recent_avg = recent_total / max(1, recent_weeks)

        if baseline_avg == 0:
            # Cold-start: use global baseline by dominant tier
            tier_counts = Counter(s.tier for s in visible)
            dominant_tier = tier_counts.most_common(1)[0][0]
            global_baseline = GLOBAL_VELOCITY_BASELINE.get(dominant_tier, 2.0)
            if recent_avg > 0:
                ratio = recent_avg / global_baseline
                mads_above = max(0.0, ratio - 1.0)
                velocity = 1.0 / (1.0 + math.exp(-VELOCITY_SIGMOID_K * (mads_above - VELOCITY_SIGMOID_X0)))
        else:
            ratio = recent_avg / baseline_avg
            mads_above = max(0.0, ratio - 1.0)
            velocity = 1.0 / (1.0 + math.exp(-VELOCITY_SIGMOID_K * (mads_above - VELOCITY_SIGMOID_X0)))
            velocity = min(1.0, velocity)

        # Decay detection
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
                velocity *= VELOCITY_DECAY_PENALTY

    velocity = min(1.0, velocity)

    # ── Novelty (EScore blend) ──
    dated_signals = []
    for s in visible:
        try:
            pub = datetime.fromisoformat(s.published_date.replace("Z", "+00:00"))
            dated_signals.append((pub, s))
        except (ValueError, TypeError):
            continue

    escore_novelty = 0.5
    if len(dated_signals) >= 2:
        dated_signals.sort(key=lambda x: x[0])
        midpoint = len(dated_signals) // 2
        base_count = midpoint
        active_count = len(dated_signals) - midpoint
        if base_count > 0:
            novelty_ratio = active_count / base_count
            escore_novelty = min(1.0, novelty_ratio / 3.0)

    novelties = [s.stated_novelty for s in visible if s.stated_novelty > 0]
    if novelties:
        avg_n = sum(novelties) / len(novelties)
        max_n = max(novelties)
        llm_novelty = min(1.0, 0.6 * avg_n + 0.4 * max_n)
    else:
        llm_novelty = 0.5

    novelty = min(1.0, ESCORE_NOVELTY_WEIGHT * escore_novelty + LLM_NOVELTY_WEIGHT * llm_novelty)

    # ── Authority ──
    total_w = 0.0
    weighted_auth = 0.0
    for sig in visible:
        tier_auth = SOURCE_TIER_AUTHORITY.get(sig.tier, 0.5)
        rel = max(0.1, sig.relevance_score)
        weighted_auth += tier_auth * rel
        total_w += rel
    authority = min(1.0, weighted_auth / total_w) if total_w > 0 else 0.5

    # ── Pattern match ──
    weekly_for_pattern = []
    for w in range(51, -1, -1):
        weekly_for_pattern.append(float(weekly_counts.get(w, 0)))
    pattern_match = compute_pattern_match(weekly_for_pattern, fingerprints)

    # ── Persistence ──
    months = set()
    for pub_dt, _ in dated_signals:
        months.add((pub_dt.year, pub_dt.month))
    distinct_months = len(months)

    persistence = 0.0
    if count >= PERSISTENCE_MIN_SIGNALS and distinct_months >= PERSISTENCE_MIN_MONTHS:
        signal_component = min(1.0, count / PERSISTENCE_FULL_SIGNALS)
        month_component = min(1.0, distinct_months / PERSISTENCE_FULL_MONTHS)
        persistence = min(1.0, 0.5 * signal_component + 0.5 * month_component)

    # ── Cross-platform ──
    cross_platform = 0.0
    if len(unique_sources) >= CROSS_PLATFORM_MIN_SOURCES:
        cp_base = min(1.0, (len(unique_sources) - 1) / max(1, CROSS_PLATFORM_FULL_SOURCES - 1))
        cp_tier_bonus = min(0.30, (len(unique_tiers) - 1) * CROSS_PLATFORM_TIER_BONUS)
        cross_platform = min(1.0, cp_base + cp_tier_bonus)

    return LIRScoreSet(
        convergence=convergence,
        velocity=velocity,
        novelty=novelty,
        authority=authority,
        pattern_match=pattern_match,
        persistence=persistence,
        cross_platform=cross_platform,
    )


# ──────────────────────── Backtest run ────────────────────────


async def run_backtest(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    step_weeks: int = 4,
    weights: Optional[Dict[str, float]] = None,
    concept_filter: Optional[List[str]] = None,
    progress_callback: Optional[Callable] = None,
) -> BacktestRunResult:
    """Run a backtest over historical LIR data.

    Steps through time in week-sized increments, scoring all concepts
    at each point using only data visible at that time.

    Args:
        start_date: ISO date to start backtesting from (default: earliest signal).
        end_date: ISO date to end backtesting at (default: today).
        step_weeks: Number of weeks between scoring snapshots.
        weights: Custom SCORE_WEIGHTS to use (default: current weights).
        concept_filter: Optional list of concept_ids to backtest (default: all).
        progress_callback: Optional async callable(pct, detail).

    Returns:
        BacktestRunResult with per-concept timelines.
    """
    start_time = time.time()
    run_id = f"bt_{int(start_time)}"
    errors: List[str] = []

    if weights is None:
        weights = SCORE_WEIGHTS.copy()

    # Load all data
    concepts = await load_concepts()
    signals = await load_signals()
    concept_signals_map = await load_concept_signals()
    fingerprints = load_fingerprints()

    if concept_filter:
        concepts = {cid: c for cid, c in concepts.items() if cid in concept_filter}

    # Determine time range
    all_dates = []
    for sig in signals.values():
        try:
            dt = datetime.fromisoformat(sig.published_date.replace("Z", "+00:00"))
            all_dates.append(dt)
        except (ValueError, TypeError):
            continue

    if not all_dates:
        return BacktestRunResult(
            run_id=run_id,
            start_date=start_date or "",
            end_date=end_date or "",
            weights_used=weights,
            concept_results=[],
            total_concepts=0,
            execution_time_seconds=time.time() - start_time,
            errors=["No signals with valid dates found"],
        )

    bt_start = (
        datetime.fromisoformat(start_date) if start_date
        else min(all_dates)
    )
    bt_end = (
        datetime.fromisoformat(end_date) if end_date
        else datetime.now(timezone.utc)
    )

    if bt_start.tzinfo is None:
        bt_start = bt_start.replace(tzinfo=timezone.utc)
    if bt_end.tzinfo is None:
        bt_end = bt_end.replace(tzinfo=timezone.utc)

    # Build concept -> signals lookup
    concept_sigs: Dict[str, List[LIRSignalRecord]] = {}
    for cid in concepts:
        sig_ids = concept_signals_map.get(cid, [])
        concept_sigs[cid] = [signals[sid] for sid in sig_ids if sid in signals]

    # Generate time steps
    step_delta = timedelta(weeks=step_weeks)
    time_points = []
    t = bt_start
    while t <= bt_end:
        time_points.append(t)
        t += step_delta
    if not time_points or time_points[-1] < bt_end:
        time_points.append(bt_end)

    total_steps = len(time_points) * len(concepts)
    completed = 0

    # Run backtest
    results: Dict[str, BacktestConceptResult] = {}

    for cid, concept in concepts.items():
        result = BacktestConceptResult(
            concept_id=cid,
            canonical_name=concept.canonical_name,
        )

        for i, cutoff in enumerate(time_points):
            try:
                score_set = _score_at_time(
                    concept_sigs.get(cid, []),
                    cutoff,
                    weights,
                    fingerprints,
                )

                # Compute composite using all 7 weights
                composite = sum(
                    getattr(score_set, k, 0.0) * weights.get(k, 0.0)
                    for k in weights
                )
                ring = score_to_ring(composite)

                # Count visible signals
                visible_count = sum(
                    1 for s in concept_sigs.get(cid, [])
                    if _is_visible(s, cutoff)
                )

                snapshot = BacktestSnapshot(
                    week_offset=i * step_weeks,
                    date=cutoff.isoformat(),
                    signal_count=visible_count,
                    scores=asdict(score_set),
                    composite=round(composite, 4),
                    ring=ring,
                )
                result.snapshots.append(snapshot)

                # Track ring milestones
                if ring == "assess" and result.first_assess_week is None:
                    result.first_assess_week = i * step_weeks
                if ring == "trial" and result.first_trial_week is None:
                    result.first_trial_week = i * step_weeks
                if ring == "adopt" and result.first_adopt_week is None:
                    result.first_adopt_week = i * step_weeks

            except Exception as e:
                errors.append(f"Concept {cid} at {cutoff.isoformat()}: {e}")

            completed += 1

        if progress_callback and total_steps > 0:
            pct = int(100 * completed / total_steps)
            try:
                await progress_callback(pct, f"Backtesting {cid}")
            except Exception:
                pass

        results[cid] = result

    elapsed = time.time() - start_time
    logger.info(
        f"Backtest complete: {len(results)} concepts, "
        f"{len(time_points)} time steps, {elapsed:.1f}s"
    )

    return BacktestRunResult(
        run_id=run_id,
        start_date=bt_start.isoformat(),
        end_date=bt_end.isoformat(),
        weights_used=weights,
        concept_results=list(results.values()),
        total_concepts=len(results),
        execution_time_seconds=elapsed,
        errors=errors,
    )


def _is_visible(sig: LIRSignalRecord, cutoff: datetime) -> bool:
    """Check if a signal was published before the cutoff."""
    try:
        pub = datetime.fromisoformat(sig.published_date.replace("Z", "+00:00"))
        return pub <= cutoff
    except (ValueError, TypeError):
        return False


# ──────────────────────── Weight grid search ────────────────────────


async def weight_grid_search(
    target_concept_id: str,
    target_ring: str = "assess",
    target_lead_weeks: int = 52,
    consensus_date: Optional[str] = None,
) -> List[Dict]:
    """Search for optimal SCORE_WEIGHTS that maximize early detection.

    Tries a grid of weight combinations (all 7 components) and evaluates
    how early the target concept reaches the target ring.

    Args:
        target_concept_id: Concept to optimize for.
        target_ring: Ring that should be reached early.
        target_lead_weeks: How many weeks before consensus to aim for.
        consensus_date: ISO date when the concept became mainstream.

    Returns:
        List of {weights, first_ring_week, target_ring} dicts,
        sorted by earliest ring achievement.
    """
    # Define weight grid for all 7 components (must sum to ~1.0)
    weight_options = {
        "convergence": [0.15, 0.20, 0.25],
        "velocity": [0.15, 0.20, 0.25],
        "novelty": [0.10, 0.15, 0.20],
        "authority": [0.10, 0.15, 0.20],
        "pattern_match": [0.05, 0.10, 0.15],
        "persistence": [0.05, 0.10, 0.15],
        "cross_platform": [0.05, 0.10, 0.15],
    }

    keys = list(weight_options.keys())
    combos = list(itertools.product(*[weight_options[k] for k in keys]))

    # Filter to combos that sum to roughly 1.0 (±0.05)
    valid_combos = []
    for combo in combos:
        total = sum(combo)
        if 0.95 <= total <= 1.05:
            valid_combos.append(dict(zip(keys, combo)))

    logger.info(f"Weight grid search: {len(valid_combos)} valid weight combinations")

    results = []
    for weights in valid_combos[:50]:  # Cap at 50 to avoid excessive compute
        try:
            bt = await run_backtest(
                weights=weights,
                concept_filter=[target_concept_id],
                step_weeks=4,
            )

            for cr in bt.concept_results:
                if cr.concept_id == target_concept_id:
                    ring_week = None
                    if target_ring == "assess":
                        ring_week = cr.first_assess_week
                    elif target_ring == "trial":
                        ring_week = cr.first_trial_week
                    elif target_ring == "adopt":
                        ring_week = cr.first_adopt_week

                    results.append({
                        "weights": weights,
                        "first_ring_week": ring_week,
                        "target_ring": target_ring,
                    })

        except Exception as e:
            logger.warning(f"Grid search failed for weights {weights}: {e}")

    # Sort by earliest ring achievement
    results.sort(key=lambda r: r.get("first_ring_week") or 9999)
    return results
