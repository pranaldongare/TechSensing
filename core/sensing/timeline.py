"""
Multi-Report Timeline — builds per-technology ring evolution across reports.

Scans all report_*.json for a user+domain, extracts radar_items,
and builds a chronological timeline for each technology.
"""

import json
import logging
import os
from typing import List, Optional

import aiofiles
from pydantic import BaseModel, Field

logger = logging.getLogger("sensing.timeline")


class TechnologyTimelineEntry(BaseModel):
    report_date: str
    report_id: str
    ring: str
    quadrant: str


class TechnologyTimeline(BaseModel):
    technology_name: str
    quadrant: str = ""
    entries: List[TechnologyTimelineEntry]


class TimelineData(BaseModel):
    domain: str
    technologies: List[TechnologyTimeline]


async def build_timeline(
    user_id: str,
    domain: Optional[str] = None,
) -> TimelineData:
    """
    Build timeline data from all past reports for a user.

    If domain is specified, only includes reports matching that domain.
    Returns technologies with their ring values across report dates.
    """
    sensing_dir = f"data/{user_id}/sensing"

    if not os.path.exists(sensing_dir):
        return TimelineData(domain=domain or "", technologies=[])

    # Collect all reports
    reports: list[dict] = []
    for fname in os.listdir(sensing_dir):
        if not fname.startswith("report_") or not fname.endswith(".json"):
            continue
        try:
            fpath = os.path.join(sensing_dir, fname)
            async with aiofiles.open(fpath, "r", encoding="utf-8") as f:
                data = json.loads(await f.read())

            meta = data.get("meta", {})
            report = data.get("report", {})

            # Filter by domain if specified
            if domain and meta.get("domain", "").lower() != domain.lower():
                continue

            reports.append({
                "tracking_id": meta.get("tracking_id", ""),
                "domain": meta.get("domain", ""),
                "generated_at": meta.get("generated_at", ""),
                "radar_items": report.get("radar_items", []),
            })
        except Exception:
            continue

    # Sort by date
    reports.sort(key=lambda r: r.get("generated_at", ""))

    # Build per-technology timelines
    tech_entries: dict[str, list[TechnologyTimelineEntry]] = {}
    tech_quadrant: dict[str, str] = {}

    for report in reports:
        for item in report["radar_items"]:
            name = item.get("name", "").strip()
            if not name:
                continue

            key = name.lower()
            if key not in tech_entries:
                tech_entries[key] = []
                tech_quadrant[key] = item.get("quadrant", "")

            tech_entries[key].append(TechnologyTimelineEntry(
                report_date=report["generated_at"],
                report_id=report["tracking_id"],
                ring=item.get("ring", ""),
                quadrant=item.get("quadrant", ""),
            ))
            # Keep latest quadrant
            tech_quadrant[key] = item.get("quadrant", "")

    # Convert to output
    technologies = []
    for key, entries in tech_entries.items():
        if len(entries) < 1:
            continue
        # Use original casing from most recent entry
        display_name = entries[-1].ring  # fallback
        for report in reversed(reports):
            for item in report["radar_items"]:
                if item.get("name", "").lower().strip() == key:
                    display_name = item["name"]
                    break
            else:
                continue
            break

        technologies.append(TechnologyTimeline(
            technology_name=display_name,
            quadrant=tech_quadrant.get(key, ""),
            entries=entries,
        ))

    # Sort by number of appearances (most tracked first)
    technologies.sort(key=lambda t: len(t.entries), reverse=True)

    logger.info(
        f"Timeline built: {len(technologies)} technologies "
        f"across {len(reports)} reports"
    )

    return TimelineData(
        domain=domain or "",
        technologies=technologies,
    )
