"""
Smart Alerts — detects significant changes between consecutive sensing
reports and generates structured alert notifications.

Alert types
-----------
- ``ring_jump``:           Technology moved 2+ rings (e.g., Hold → Trial)
- ``direct_adopt``:        New technology enters Adopt or Trial ring directly
- ``weak_signal_breakout``: Weak signal crosses acceleration threshold
- ``stack_match``:         Technology from user's org context appeared on radar
- ``trend_surge``:         New trend with High impact appeared
"""

import json
import logging
import os
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import List, Optional

import aiofiles
from pydantic import BaseModel, Field

from core.llm.output_schemas.sensing_outputs import TechSensingReport, WeakSignal

logger = logging.getLogger("sensing.alerts")

RING_ORDER = ["Hold", "Assess", "Trial", "Adopt"]
NAME_MATCH_THRESHOLD = 0.85


# ── Models ───────────────────────────────────────────────────────────────


class SensingAlert(BaseModel):
    """A single alert notification from the sensing pipeline."""

    alert_type: str = Field(
        description=(
            "One of: ring_jump, direct_adopt, weak_signal_breakout, "
            "stack_match, trend_surge"
        )
    )
    severity: str = Field(description="Alert severity: critical, high, medium, low")
    title: str = Field(description="Short alert title.")
    description: str = Field(description="Detailed alert description.")
    technology_name: str = Field(
        default="", description="Related technology name."
    )
    metadata: dict = Field(
        default_factory=dict, description="Extra context data."
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class AlertPreferences(BaseModel):
    """User's alert preference configuration."""

    enabled: bool = Field(default=True)
    email_alerts: bool = Field(default=False)
    ring_jump_threshold: int = Field(
        default=2,
        description="Minimum ring jump distance to alert.",
    )
    weak_signal_acceleration_threshold: float = Field(
        default=2.0,
        description="Acceleration rate to trigger breakout alert.",
    )
    alert_on_direct_adopt: bool = Field(default=True)
    alert_on_stack_match: bool = Field(default=True)
    alert_on_trend_surge: bool = Field(default=True)


# ── Helpers ───��──────────────────────────────────────────────────────────


def _ring_distance(ring_a: str, ring_b: str) -> int:
    """Compute signed ring distance (positive = moved inward toward Adopt)."""
    try:
        idx_a = RING_ORDER.index(ring_a)
        idx_b = RING_ORDER.index(ring_b)
        return idx_b - idx_a
    except ValueError:
        return 0


def _fuzzy_match(name: str, candidates: dict[str, dict]) -> Optional[dict]:
    """Return the best fuzzy-matched candidate dict or None."""
    key = name.lower().strip()
    if key in candidates:
        return candidates[key]
    for cand_key, cand_val in candidates.items():
        if SequenceMatcher(None, key, cand_key).ratio() >= NAME_MATCH_THRESHOLD:
            return cand_val
    return None


# ── Persistence ──────────────────────────────────────────────────────────


async def load_alert_preferences(user_id: str) -> AlertPreferences:
    """Load user's alert preferences. Returns defaults if not configured."""
    fpath = f"data/{user_id}/sensing/alert_prefs.json"
    if not os.path.exists(fpath):
        return AlertPreferences()
    try:
        async with aiofiles.open(fpath, "r", encoding="utf-8") as f:
            data = json.loads(await f.read())
        return AlertPreferences(**data)
    except Exception:
        return AlertPreferences()


async def save_alert_preferences(
    user_id: str, prefs: AlertPreferences
) -> None:
    """Persist alert preferences to disk."""
    fpath = f"data/{user_id}/sensing/alert_prefs.json"
    os.makedirs(os.path.dirname(fpath), exist_ok=True)
    async with aiofiles.open(fpath, "w", encoding="utf-8") as f:
        await f.write(
            json.dumps(prefs.model_dump(), ensure_ascii=False, indent=2)
        )


# ── Core Detection ───────────────────────────────────────────────────────


async def detect_alerts(
    new_report: TechSensingReport,
    user_id: str,
    domain: str,
    previous_report_data: Optional[dict] = None,
    org_tech_stack: Optional[List[str]] = None,
    weak_signals: Optional[List[WeakSignal]] = None,
) -> List[SensingAlert]:
    """Detect alerts by comparing the new report against the previous one.

    Returns a list of :class:`SensingAlert` objects sorted by severity.
    """
    prefs = await load_alert_preferences(user_id)
    if not prefs.enabled:
        return []

    alerts: List[SensingAlert] = []

    # Build previous radar map: {name_lower: item_dict}
    prev_radar: dict[str, dict] = {}
    if previous_report_data:
        prev_items = previous_report_data.get("report", {}).get(
            "radar_items", []
        )
        for item in prev_items:
            name = (item.get("name") or "").lower().strip()
            if name:
                prev_radar[name] = item

    # ── ring_jump: 2+ ring movement ─────────────────────────────────────
    for item in new_report.radar_items:
        prev = _fuzzy_match(item.name, prev_radar)
        if prev:
            prev_ring = prev.get("ring", "")
            dist = _ring_distance(prev_ring, item.ring)
            if abs(dist) >= prefs.ring_jump_threshold:
                direction = "inward" if dist > 0 else "outward"
                severity = "critical" if abs(dist) >= 3 else "high"
                alerts.append(
                    SensingAlert(
                        alert_type="ring_jump",
                        severity=severity,
                        title=f"{item.name}: {prev_ring} \u2192 {item.ring}",
                        description=(
                            f"'{item.name}' moved {abs(dist)} rings {direction} "
                            f"from {prev_ring} to {item.ring}. {item.description}"
                        ),
                        technology_name=item.name,
                        metadata={
                            "previous_ring": prev_ring,
                            "current_ring": item.ring,
                            "distance": dist,
                        },
                    )
                )

    # ── direct_adopt: new tech enters Adopt/Trial ────────────────────────
    if prefs.alert_on_direct_adopt:
        for item in new_report.radar_items:
            if not _fuzzy_match(item.name, prev_radar) and item.ring in (
                "Adopt",
                "Trial",
            ):
                alerts.append(
                    SensingAlert(
                        alert_type="direct_adopt",
                        severity="high",
                        title=f"New: {item.name} enters {item.ring}",
                        description=(
                            f"'{item.name}' appeared for the first time "
                            f"directly in the {item.ring} ring. "
                            f"{item.description}"
                        ),
                        technology_name=item.name,
                        metadata={
                            "ring": item.ring,
                            "quadrant": item.quadrant,
                        },
                    )
                )

    # ── weak_signal_breakout ─────────────────────────────────────────────
    if weak_signals:
        for ws in weak_signals:
            if ws.acceleration_rate >= prefs.weak_signal_acceleration_threshold:
                alerts.append(
                    SensingAlert(
                        alert_type="weak_signal_breakout",
                        severity="medium",
                        title=(
                            f"Breakout: {ws.technology_name} "
                            f"({ws.acceleration_rate:.1f}x)"
                        ),
                        description=(
                            f"'{ws.technology_name}' has a "
                            f"{ws.acceleration_rate:.1f}x acceleration rate "
                            f"with current strength "
                            f"{ws.current_strength:.2f}. "
                            f"First seen: {ws.first_seen}. "
                            f"DVI score: {ws.dvi_score:.3f}."
                        ),
                        technology_name=ws.technology_name,
                        metadata={
                            "acceleration_rate": ws.acceleration_rate,
                            "current_strength": ws.current_strength,
                            "dvi_score": ws.dvi_score,
                        },
                    )
                )

    # ── stack_match: org tech appeared on radar ──────────────────────────
    if prefs.alert_on_stack_match and org_tech_stack:
        stack_lower = {t.lower().strip() for t in org_tech_stack}
        for item in new_report.radar_items:
            item_lower = item.name.lower().strip()
            for tech in stack_lower:
                if tech in item_lower or item_lower in tech:
                    alerts.append(
                        SensingAlert(
                            alert_type="stack_match",
                            severity="medium",
                            title=f"Stack match: {item.name} ({item.ring})",
                            description=(
                                f"'{item.name}' matches your org tech stack "
                                f"and is currently in the {item.ring} ring. "
                                f"{item.description}"
                            ),
                            technology_name=item.name,
                            metadata={
                                "ring": item.ring,
                                "matched_stack_item": tech,
                            },
                        )
                    )
                    break  # one alert per radar item

    # ── trend_surge: new High-impact trend ─────��─────────────────────────
    if prefs.alert_on_trend_surge:
        prev_trends: set[str] = set()
        if previous_report_data:
            for t in previous_report_data.get("report", {}).get(
                "key_trends", []
            ):
                prev_trends.add(t.get("trend_name", "").lower().strip())

        for trend in new_report.key_trends:
            if (
                trend.impact_level == "High"
                and trend.trend_name.lower().strip() not in prev_trends
            ):
                alerts.append(
                    SensingAlert(
                        alert_type="trend_surge",
                        severity="high",
                        title=f"New trend: {trend.trend_name}",
                        description=(
                            f"High-impact trend '{trend.trend_name}': "
                            f"{trend.description}"
                        ),
                        technology_name="",
                        metadata={
                            "impact": trend.impact_level,
                            "horizon": trend.time_horizon,
                        },
                    )
                )

    # Sort by severity
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    alerts.sort(key=lambda a: severity_order.get(a.severity, 4))

    logger.info(f"Alert detection: {len(alerts)} alerts generated")
    return alerts
