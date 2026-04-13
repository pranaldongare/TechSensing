"""
Radar Movement Detection — compares current radar items against the most
recent previous report for the same domain to detect ring changes.
"""

import json
import logging
import os
from difflib import SequenceMatcher
from typing import Optional

import aiofiles

from core.llm.output_schemas.sensing_outputs import TechSensingReport

logger = logging.getLogger("sensing.movement")

# Fuzzy name match threshold (same as dedup)
NAME_MATCH_THRESHOLD = 0.85


async def detect_radar_movements(
    new_report: TechSensingReport,
    user_id: str,
    domain: str,
) -> TechSensingReport:
    """
    Compare current radar items against the previous report for this domain.
    Sets `moved_in` on items whose ring changed since last report.
    Returns the (possibly modified) report.
    """
    previous = await load_previous_report(user_id, domain)
    if previous is None:
        logger.info("No previous report found for movement detection")
        return new_report

    prev_radar = previous.get("report", {}).get("radar_items", [])
    if not prev_radar:
        logger.info("Previous report has no radar items")
        return new_report

    # Build name→ring lookup from previous report
    prev_ring_map: dict[str, str] = {}
    for item in prev_radar:
        name = (item.get("name") or "").strip()
        ring = (item.get("ring") or "").strip()
        if name and ring:
            prev_ring_map[name.lower()] = ring

    if not prev_ring_map:
        return new_report

    moved_count = 0
    for radar_item in new_report.radar_items:
        current_name = radar_item.name.strip().lower()
        prev_ring = _find_previous_ring(current_name, prev_ring_map)
        if prev_ring and prev_ring != radar_item.ring:
            radar_item.moved_in = prev_ring
            moved_count += 1
            logger.info(
                f"Movement detected: '{radar_item.name}' "
                f"{prev_ring} -> {radar_item.ring}"
            )

    logger.info(
        f"Movement detection complete: {moved_count} items moved "
        f"out of {len(new_report.radar_items)} total"
    )
    return new_report


def _find_previous_ring(
    name: str, prev_map: dict[str, str]
) -> Optional[str]:
    """Find the previous ring for a technology, using exact then fuzzy match."""
    # Exact match
    if name in prev_map:
        return prev_map[name]

    # Fuzzy match
    for prev_name, ring in prev_map.items():
        ratio = SequenceMatcher(None, name, prev_name).ratio()
        if ratio >= NAME_MATCH_THRESHOLD:
            return ring

    return None


async def load_previous_report(
    user_id: str, domain: str
) -> Optional[dict]:
    """Load the most recent report file for user+domain."""
    sensing_dir = f"data/{user_id}/sensing"
    if not os.path.exists(sensing_dir):
        return None

    candidates: list[tuple[str, str]] = []
    for fname in os.listdir(sensing_dir):
        if fname.startswith("report_") and fname.endswith(".json"):
            fpath = os.path.join(sensing_dir, fname)
            candidates.append((fpath, fname))

    if not candidates:
        return None

    # Sort by modification time, most recent first
    candidates.sort(key=lambda x: os.path.getmtime(x[0]), reverse=True)

    for fpath, fname in candidates:
        try:
            async with aiofiles.open(fpath, "r", encoding="utf-8") as f:
                data = json.loads(await f.read())
            report_domain = data.get("meta", {}).get("domain", "")
            if report_domain.lower().strip() == domain.lower().strip():
                logger.info(f"Found previous report: {fname}")
                return data
        except Exception:
            continue

    return None
