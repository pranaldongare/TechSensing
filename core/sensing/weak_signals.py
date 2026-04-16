"""
Weak Signal Detection — identifies emerging technologies with low absolute
visibility but high temporal acceleration (growth rate across runs).

Uses a DVI (Diffusion, Visibility, Impact) framework with time-weighting.
Stores per-technology article counts in signal_history.json for cross-run
comparison.  Each history entry is domain-tagged so signals from different
domains don't bleed into each other.
"""

import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Set

import aiofiles

from core.llm.output_schemas.sensing_outputs import (
    ClassifiedArticle,
    TechSensingReport,
    WeakSignal,
    WeakSignalTrajectoryPoint,
)

logger = logging.getLogger("sensing.weak_signals")

# Signals whose first_seen is older than this are no longer "emerging"
MAX_EMERGING_AGE_DAYS = 60

# Multiplier on lookback_days for per-article recency check.
RECENCY_BUFFER = 1.5

# Hard cap on article age when no lookback is supplied.
DEFAULT_ARTICLE_MAX_AGE_DAYS = 45

_ISO_DATE_RE = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")


def _parse_article_date(value: str) -> Optional[datetime]:
    """Parse an article's ``published_date`` into tz-aware UTC datetime."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        pass
    m = _ISO_DATE_RE.search(value)
    if m:
        try:
            return datetime(
                int(m.group(1)), int(m.group(2)), int(m.group(3)),
                tzinfo=timezone.utc,
            )
        except (ValueError, TypeError):
            return None
    return None


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


def _is_stale_or_generic(
    tech_name: str,
    generic_blocklist: Set[str],
    legacy_blocklist: Set[str],
) -> bool:
    """Return True if the technology name matches a generic or legacy term."""
    name_lower = tech_name.lower().strip()
    # Check exact matches and substring containment
    for term in generic_blocklist:
        t = term.lower().strip()
        if t and (t == name_lower or t in name_lower or name_lower in t):
            return True
    for term in legacy_blocklist:
        t = term.lower().strip()
        if t and (t == name_lower or t in name_lower or name_lower in t):
            return True
    return False


async def detect_weak_signals(
    report: TechSensingReport,
    classified_articles: List[ClassifiedArticle],
    user_id: Optional[str] = None,
    domain: str = "",
    generic_blocklist: Optional[Set[str]] = None,
    legacy_blocklist: Optional[Set[str]] = None,
    lookback_days: int = 0,
) -> List[WeakSignal]:
    """Detect weak signals by comparing current run metrics against history.

    Algorithm
    ---------
    1. For each radar item in the current report, count supporting articles
       and distinct sources.
    2. Load historical signal data for this user.
    3. Record the current run's metrics into history with domain tag
       (keep last 20 runs per technology).
    4. Filter history to current domain only when computing acceleration.
    5. Compute ``acceleration_rate = current_article_count /
       historical_avg_article_count``.
    6. Compute a DVI score:

       - Diffusion  = min(unique_sources / 5, 1.0)
       - Visibility  = min(article_count / 10, 1.0)
       - Impact      = avg_relevance_score

    7. Flag as weak signal if:

       - ``current_strength < 0.5`` (low absolute visibility), AND
       - ``acceleration_rate > 1.5`` (growing), AND
       - appeared in ``>= 2`` runs for this domain (not first-time noise).

    8. Exclude items that are generic, legacy, or have been emerging for
       more than ``MAX_EMERGING_AGE_DAYS`` days (they're established,
       not emerging).
    9. Before counting articles for the current run, drop any article
       whose ``published_date`` is older than
       ``lookback_days * RECENCY_BUFFER`` (default 45 days when no
       lookback is supplied). This prevents stale articles left over
       from permissive upstream filtering from inflating a signal's
       "current" visibility.
    """
    if not user_id:
        return []

    now_str = datetime.now(timezone.utc).isoformat()
    now_dt = datetime.now(timezone.utc)
    domain_lower = domain.lower().strip()
    blocklist_generic = generic_blocklist or set()
    blocklist_legacy = legacy_blocklist or set()

    # ── Per-article recency cutoff ───────────────────────────────────────
    # Keep articles whose published_date is within the report window (with
    # a small buffer). Articles with no parseable date are kept so we don't
    # discard legitimate signals that lack timestamps.
    if lookback_days and lookback_days > 0:
        max_article_age_days = int(lookback_days * RECENCY_BUFFER)
    else:
        max_article_age_days = DEFAULT_ARTICLE_MAX_AGE_DAYS
    article_cutoff = now_dt - timedelta(days=max_article_age_days)

    # ── Build tech → article stats from current run ──────────────────────
    tech_stats: dict[str, dict] = {}
    dropped_stale = 0
    for article in classified_articles:
        pub_dt = _parse_article_date(getattr(article, "published_date", ""))
        if pub_dt is not None and pub_dt < article_cutoff:
            dropped_stale += 1
            continue
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

    if dropped_stale:
        logger.info(
            f"Weak signals: dropped {dropped_stale} articles older than "
            f"{max_article_age_days}d from current-run stats"
        )

    # ── Build radar-item strength lookup ─────────────────────────────────
    strength_map = {
        item.name.lower().strip(): item.signal_strength
        for item in report.radar_items
    }

    # ── Load history and append current run ──────────────────────────────
    history = await load_signal_history(user_id)

    for tech_key, stats in tech_stats.items():
        entry = {
            "run_date": now_str,
            "domain": domain_lower,
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
    filtered_generic = 0
    filtered_stale = 0

    for tech_key, entries in history.items():
        # Filter to entries for the current domain only
        domain_entries = [
            e for e in entries
            if e.get("domain", "").lower().strip() == domain_lower
        ]

        if len(domain_entries) < 2:
            continue  # Need at least 2 data points in this domain

        current = domain_entries[-1]
        previous = domain_entries[:-1]

        # Historical averages (same domain only)
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
            # ── Stale/generic filtering ──────────────────────────────
            if _is_stale_or_generic(tech_key, blocklist_generic, blocklist_legacy):
                filtered_generic += 1
                logger.debug(f"Weak signal filtered (generic/legacy): {tech_key}")
                continue

            # ── Recency check: skip if first seen > 90 days ago ──────
            first_seen_str = domain_entries[0]["run_date"]
            try:
                first_seen_dt = datetime.fromisoformat(first_seen_str)
                age_days = (now_dt - first_seen_dt).days
                if age_days > MAX_EMERGING_AGE_DAYS:
                    filtered_stale += 1
                    logger.debug(
                        f"Weak signal filtered (stale, {age_days}d old): {tech_key}"
                    )
                    continue
            except (ValueError, TypeError):
                pass  # If date parsing fails, allow through

            # Find canonical name from radar items
            canonical_name = tech_key
            for item in report.radar_items:
                if item.name.lower().strip() == tech_key:
                    canonical_name = item.name
                    break

            trajectory = [
                WeakSignalTrajectoryPoint(
                    run_date=e["run_date"],
                    article_count=e["article_count"],
                    source_count=e["source_count"],
                    avg_relevance=e.get("avg_relevance", 0.5),
                    signal_strength=e.get("signal_strength", 0.2),
                )
                for e in domain_entries
            ]

            weak_signals.append(
                WeakSignal(
                    technology_name=canonical_name,
                    current_strength=round(current_strength, 3),
                    acceleration_rate=round(acceleration, 2),
                    first_seen=domain_entries[0]["run_date"],
                    run_count=len(domain_entries),
                    trajectory=trajectory,
                    dvi_score=dvi,
                )
            )

    # Sort by acceleration rate descending
    weak_signals.sort(key=lambda s: s.acceleration_rate, reverse=True)

    logger.info(
        f"Weak signal detection: {len(weak_signals)} signals detected "
        f"from {len(history)} tracked technologies "
        f"(filtered: {filtered_generic} generic/legacy, {filtered_stale} stale)"
    )

    return weak_signals
