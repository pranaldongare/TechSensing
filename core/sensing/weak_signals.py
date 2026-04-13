"""
Weak Signal Detection — identifies emerging technologies with low absolute
visibility but high temporal acceleration (growth rate across runs).

Uses a DVI (Diffusion, Visibility, Impact) framework with time-weighting.
Stores per-technology article counts in signal_history.json for cross-run
comparison.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import List, Optional

import aiofiles

from core.llm.output_schemas.sensing_outputs import (
    ClassifiedArticle,
    TechSensingReport,
    WeakSignal,
    WeakSignalTrajectoryPoint,
)

logger = logging.getLogger("sensing.weak_signals")


def _history_path(user_id: str) -> str:
    return f"data/{user_id}/sensing/signal_history.json"


async def load_signal_history(user_id: str) -> dict:
    """Load signal history from disk.

    Returns ``{tech_name_lower: [entry_dict, ...]}``.
    """
    fpath = _history_path(user_id)
    if not os.path.exists(fpath):
        return {}
    try:
        async with aiofiles.open(fpath, "r", encoding="utf-8") as f:
            return json.loads(await f.read())
    except Exception as e:
        logger.warning(f"Failed to load signal history: {e}")
        return {}


async def save_signal_history(user_id: str, history: dict) -> None:
    """Persist signal history to disk."""
    fpath = _history_path(user_id)
    os.makedirs(os.path.dirname(fpath), exist_ok=True)
    async with aiofiles.open(fpath, "w", encoding="utf-8") as f:
        await f.write(json.dumps(history, ensure_ascii=False, indent=2))


async def detect_weak_signals(
    report: TechSensingReport,
    classified_articles: List[ClassifiedArticle],
    user_id: Optional[str] = None,
) -> List[WeakSignal]:
    """Detect weak signals by comparing current run metrics against history.

    Algorithm
    ---------
    1. For each radar item in the current report, count supporting articles
       and distinct sources.
    2. Load historical signal data for this user.
    3. Record the current run's metrics into history (keep last 20 runs per
       technology).
    4. Compute ``acceleration_rate = current_article_count /
       historical_avg_article_count``.
    5. Compute a DVI score:

       - Diffusion  = min(unique_sources / 5, 1.0)
       - Visibility  = min(article_count / 10, 1.0)
       - Impact      = avg_relevance_score

    6. Flag as weak signal if:

       - ``current_strength < 0.5`` (low absolute visibility), AND
       - ``acceleration_rate > 1.5`` (growing), AND
       - appeared in ``>= 2`` runs (not first-time noise).
    """
    if not user_id:
        return []

    now = datetime.now(timezone.utc).isoformat()

    # ── Build tech → article stats from current run ──────────────────────
    tech_stats: dict[str, dict] = {}
    for article in classified_articles:
        key = article.technology_name.lower().strip()
        if key not in tech_stats:
            tech_stats[key] = {
                "article_count": 0,
                "sources": set(),
                "relevance_sum": 0.0,
            }
        tech_stats[key]["article_count"] += 1
        tech_stats[key]["sources"].add(article.source)
        tech_stats[key]["relevance_sum"] += article.relevance_score

    # ── Build radar-item strength lookup ─────────────────────────────────
    strength_map = {
        item.name.lower().strip(): item.signal_strength
        for item in report.radar_items
    }

    # ── Load history and append current run ──────────────────────────────
    history = await load_signal_history(user_id)

    for tech_key, stats in tech_stats.items():
        entry = {
            "run_date": now,
            "article_count": stats["article_count"],
            "source_count": len(stats["sources"]),
            "avg_relevance": round(
                stats["relevance_sum"] / stats["article_count"], 3
            )
            if stats["article_count"] > 0
            else 0.0,
            "signal_strength": strength_map.get(tech_key, 0.2),
        }
        if tech_key not in history:
            history[tech_key] = []
        history[tech_key].append(entry)
        # Keep last 20 runs max per technology
        history[tech_key] = history[tech_key][-20:]

    await save_signal_history(user_id, history)

    # ── Detect weak signals ──────────────────────────────────────────────
    weak_signals: List[WeakSignal] = []

    for tech_key, entries in history.items():
        if len(entries) < 2:
            continue  # Need at least 2 data points

        current = entries[-1]
        previous = entries[:-1]

        # Historical averages
        avg_articles = sum(e["article_count"] for e in previous) / len(previous)
        current_articles = current["article_count"]

        # Acceleration rate
        acceleration = (
            current_articles / avg_articles
            if avg_articles > 0
            else float(current_articles)
        )

        # Current strength
        current_strength = current.get("signal_strength", 0.2)

        # DVI score
        diffusion = min(current.get("source_count", 0) / 5.0, 1.0)
        visibility = min(current_articles / 10.0, 1.0)
        impact = current.get("avg_relevance", 0.5)
        dvi = round(diffusion * visibility * impact, 3)

        # Weak signal criteria
        if current_strength < 0.5 and acceleration > 1.5:
            # Find canonical name from radar items
            canonical_name = tech_key
            for item in report.radar_items:
                if item.name.lower().strip() == tech_key:
                    canonical_name = item.name
                    break

            trajectory = [
                WeakSignalTrajectoryPoint(**e) for e in entries
            ]

            weak_signals.append(
                WeakSignal(
                    technology_name=canonical_name,
                    current_strength=round(current_strength, 3),
                    acceleration_rate=round(acceleration, 2),
                    first_seen=entries[0]["run_date"],
                    run_count=len(entries),
                    trajectory=trajectory,
                    dvi_score=dvi,
                )
            )

    # Sort by acceleration rate descending
    weak_signals.sort(key=lambda s: s.acceleration_rate, reverse=True)

    logger.info(
        f"Weak signal detection: {len(weak_signals)} signals detected "
        f"from {len(history)} tracked technologies"
    )

    return weak_signals
