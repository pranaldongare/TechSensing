"""
Report comparison — diffs two sensing reports to identify
added/removed/moved radar items and trend changes.
"""

from difflib import SequenceMatcher
from typing import List, Optional

from pydantic import BaseModel


class RadarDiffItem(BaseModel):
    name: str
    status: str  # "added" | "removed" | "moved" | "unchanged"
    quadrant: str
    current_ring: Optional[str] = None
    previous_ring: Optional[str] = None
    description: str = ""


class TrendDiff(BaseModel):
    name: str
    status: str  # "new" | "removed" | "continuing"


class ReportComparison(BaseModel):
    report_a_id: str
    report_b_id: str
    report_a_title: str
    report_b_title: str
    report_a_date: str
    report_b_date: str
    radar_diff: List[RadarDiffItem]
    trend_diff: List[TrendDiff]
    new_signals: List[str]
    removed_signals: List[str]
    summary: str


NAME_MATCH_THRESHOLD = 0.85


def _fuzzy_match(name: str, candidates: dict[str, dict]) -> Optional[str]:
    """Find best fuzzy match for a name in candidates dict."""
    name_lower = name.lower().strip()
    if name_lower in candidates:
        return name_lower
    for cand in candidates:
        if SequenceMatcher(None, name_lower, cand).ratio() >= NAME_MATCH_THRESHOLD:
            return cand
    return None


def compare_reports(report_a: dict, report_b: dict) -> ReportComparison:
    """
    Compare two reports. report_a = older, report_b = newer.
    Both are full report_data dicts with 'report' and 'meta' keys.
    """
    meta_a = report_a.get("meta", {})
    meta_b = report_b.get("meta", {})
    rep_a = report_a.get("report", {})
    rep_b = report_b.get("report", {})

    # --- Radar diff ---
    radar_a = {item["name"].lower().strip(): item for item in rep_a.get("radar_items", [])}
    radar_b = {item["name"].lower().strip(): item for item in rep_b.get("radar_items", [])}

    radar_diff: List[RadarDiffItem] = []
    matched_b: set[str] = set()

    for name_a, item_a in radar_a.items():
        match_key = _fuzzy_match(item_a["name"], radar_b)
        if match_key:
            matched_b.add(match_key)
            item_b = radar_b[match_key]
            if item_a.get("ring") != item_b.get("ring"):
                radar_diff.append(RadarDiffItem(
                    name=item_b["name"],
                    status="moved",
                    quadrant=item_b.get("quadrant", ""),
                    current_ring=item_b.get("ring"),
                    previous_ring=item_a.get("ring"),
                    description=item_b.get("description", ""),
                ))
            else:
                radar_diff.append(RadarDiffItem(
                    name=item_b["name"],
                    status="unchanged",
                    quadrant=item_b.get("quadrant", ""),
                    current_ring=item_b.get("ring"),
                    previous_ring=item_a.get("ring"),
                    description=item_b.get("description", ""),
                ))
        else:
            radar_diff.append(RadarDiffItem(
                name=item_a["name"],
                status="removed",
                quadrant=item_a.get("quadrant", ""),
                previous_ring=item_a.get("ring"),
                description=item_a.get("description", ""),
            ))

    for name_b, item_b in radar_b.items():
        if name_b not in matched_b:
            radar_diff.append(RadarDiffItem(
                name=item_b["name"],
                status="added",
                quadrant=item_b.get("quadrant", ""),
                current_ring=item_b.get("ring"),
                description=item_b.get("description", ""),
            ))

    # Sort: moved first, then added, removed, unchanged
    status_order = {"moved": 0, "added": 1, "removed": 2, "unchanged": 3}
    radar_diff.sort(key=lambda x: status_order.get(x.status, 4))

    # --- Trend diff ---
    trends_a = {t["trend_name"].lower().strip() for t in rep_a.get("key_trends", [])}
    trends_b = {t["trend_name"].lower().strip() for t in rep_b.get("key_trends", [])}
    trend_names_b = {t["trend_name"] for t in rep_b.get("key_trends", [])}
    trend_names_a = {t["trend_name"] for t in rep_a.get("key_trends", [])}

    trend_diff: List[TrendDiff] = []
    matched_trends: set[str] = set()

    for t in rep_b.get("key_trends", []):
        t_lower = t["trend_name"].lower().strip()
        if t_lower in trends_a:
            trend_diff.append(TrendDiff(name=t["trend_name"], status="continuing"))
            matched_trends.add(t_lower)
        else:
            trend_diff.append(TrendDiff(name=t["trend_name"], status="new"))

    for t in rep_a.get("key_trends", []):
        t_lower = t["trend_name"].lower().strip()
        if t_lower not in matched_trends and t_lower not in trends_b:
            trend_diff.append(TrendDiff(name=t["trend_name"], status="removed"))

    # --- Signal diff ---
    signals_a = {s.get("company_or_player", "").lower().strip() for s in rep_a.get("market_signals", [])}
    signals_b = {s.get("company_or_player", "").lower().strip() for s in rep_b.get("market_signals", [])}
    signal_names_b = {s.get("company_or_player", "") for s in rep_b.get("market_signals", [])}
    signal_names_a = {s.get("company_or_player", "") for s in rep_a.get("market_signals", [])}

    new_signals = [s for s in signal_names_b if s.lower().strip() not in signals_a]
    removed_signals = [s for s in signal_names_a if s.lower().strip() not in signals_b]

    # --- Summary ---
    added_count = sum(1 for r in radar_diff if r.status == "added")
    removed_count = sum(1 for r in radar_diff if r.status == "removed")
    moved_count = sum(1 for r in radar_diff if r.status == "moved")
    summary = f"{added_count} added, {removed_count} removed, {moved_count} moved"

    return ReportComparison(
        report_a_id=meta_a.get("tracking_id", ""),
        report_b_id=meta_b.get("tracking_id", ""),
        report_a_title=rep_a.get("report_title", "Untitled"),
        report_b_title=rep_b.get("report_title", "Untitled"),
        report_a_date=meta_a.get("generated_at", ""),
        report_b_date=meta_b.get("generated_at", ""),
        radar_diff=radar_diff,
        trend_diff=trend_diff,
        new_signals=new_signals,
        removed_signals=removed_signals,
        summary=summary,
    )
