"""
Cross-domain Dashboard — aggregates intelligence across all tracked domains.

Scans all report files for a user, extracts highlights, and returns
a unified view of recent activity across domains.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import List

import aiofiles
from pydantic import BaseModel, Field

logger = logging.getLogger("sensing.dashboard")


class DomainSummaryItem(BaseModel):
    """Summary of one domain's most recent report."""

    domain: str
    report_id: str
    report_date: str
    report_title: str
    total_radar_items: int
    new_items_count: int  # items with is_new=True
    moved_items_count: int  # items with moved_in not null
    adopt_ring_items: List[str]  # names of items in Adopt ring
    top_trends: List[str]  # top 3 trend names
    alert_count: int
    weak_signal_count: int


class CrossDomainDashboard(BaseModel):
    """Aggregated dashboard across all domains for a user."""

    user_id: str
    generated_at: str
    domains: List[DomainSummaryItem]
    total_domains: int
    total_radar_items: int
    total_new_items: int
    total_alerts: int
    recent_adopt_items: List[dict]  # [{name, domain, date}]
    recent_movements: List[dict]  # [{name, domain, from_ring, to_ring, date}]


async def build_dashboard(user_id: str) -> CrossDomainDashboard:
    """Build cross-domain dashboard by scanning all report files."""
    sensing_dir = f"data/{user_id}/sensing"
    domains: List[DomainSummaryItem] = []
    all_adopt_items = []
    all_movements = []
    total_alerts = 0

    if not os.path.exists(sensing_dir):
        return CrossDomainDashboard(
            user_id=user_id,
            generated_at=datetime.now(timezone.utc).isoformat(),
            domains=[],
            total_domains=0,
            total_radar_items=0,
            total_new_items=0,
            total_alerts=0,
            recent_adopt_items=[],
            recent_movements=[],
        )

    # Find all report files grouped by domain
    report_files = sorted(
        [f for f in os.listdir(sensing_dir) if f.startswith("report_") and f.endswith(".json")],
        reverse=True,
    )

    seen_domains: dict[str, dict] = {}  # domain -> latest report data

    for fname in report_files:
        fpath = os.path.join(sensing_dir, fname)
        try:
            async with aiofiles.open(fpath, "r") as f:
                data = json.loads(await f.read())

            report_domain = data.get("domain", "Unknown")
            if report_domain in seen_domains:
                continue  # Already have latest for this domain

            seen_domains[report_domain] = data

            radar_items = data.get("radar_items", [])
            new_items = [r for r in radar_items if r.get("is_new")]
            moved_items = [r for r in radar_items if r.get("moved_in")]
            adopt_items = [r["name"] for r in radar_items if r.get("ring") == "Adopt"]
            trends = data.get("key_trends", [])
            report_id = fname.replace("report_", "").replace(".json", "")

            # Extract alerts from associated alert file
            alert_count = 0
            alert_file = os.path.join(sensing_dir, f"alerts_{report_id}.json")
            if os.path.exists(alert_file):
                try:
                    async with aiofiles.open(alert_file, "r") as af:
                        alerts = json.loads(await af.read())
                        alert_count = len(alerts) if isinstance(alerts, list) else 0
                except Exception:
                    pass

            total_alerts += alert_count

            weak_signals = data.get("weak_signals", [])

            summary = DomainSummaryItem(
                domain=report_domain,
                report_id=report_id,
                report_date=data.get("date_range", ""),
                report_title=data.get("report_title", ""),
                total_radar_items=len(radar_items),
                new_items_count=len(new_items),
                moved_items_count=len(moved_items),
                adopt_ring_items=adopt_items,
                top_trends=[t.get("trend_name", "") for t in trends[:3]],
                alert_count=alert_count,
                weak_signal_count=len(weak_signals),
            )
            domains.append(summary)

            # Collect cross-domain highlights
            for item in adopt_items:
                all_adopt_items.append({
                    "name": item,
                    "domain": report_domain,
                    "date": data.get("date_range", ""),
                })

            for item in moved_items:
                all_movements.append({
                    "name": item.get("name", ""),
                    "domain": report_domain,
                    "from_ring": item.get("moved_in", ""),
                    "to_ring": item.get("ring", ""),
                    "date": data.get("date_range", ""),
                })

        except Exception as e:
            logger.warning(f"Failed to parse {fname}: {e}")
            continue

    return CrossDomainDashboard(
        user_id=user_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        domains=domains,
        total_domains=len(domains),
        total_radar_items=sum(d.total_radar_items for d in domains),
        total_new_items=sum(d.new_items_count for d in domains),
        total_alerts=total_alerts,
        recent_adopt_items=all_adopt_items[:20],
        recent_movements=all_movements[:20],
    )
