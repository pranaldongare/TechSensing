"""Per-company event timeline (#14).

Aggregates Key Companies updates and Company Analysis
``recent_developments`` across ALL historical runs for one user,
grouped by company and month, color-coded by category.

Pure-read feature — no new storage, no LLM cost. Timeline is built
on demand from already-persisted run files.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from core.sensing.run_history import (
    list_company_analysis_runs,
    list_key_companies_runs,
    load_run,
)

logger = logging.getLogger("sensing.company_timeline")


class TimelineEvent(BaseModel):
    """A single dated event for one company."""

    company: str
    date: str = Field(description="ISO date (YYYY-MM-DD or full ISO).")
    month_bucket: str = Field(
        default="",
        description="YYYY-MM derived from ``date`` for grouping.",
    )
    category: str = Field(default="Other")
    headline: str
    summary: str = Field(default="")
    source: str = Field(
        default="key_companies",
        description=(
            "Which pipeline produced the event: 'key_companies' or "
            "'company_analysis'."
        ),
    )
    source_url: str = Field(default="")
    tracking_id: str = Field(default="")


class CompanyTimeline(BaseModel):
    """Full timeline for one company across every run found."""

    company: str
    events: List[TimelineEvent] = Field(default_factory=list)
    first_seen: str = Field(default="")
    last_seen: str = Field(default="")


@dataclass
class _RawEvent:
    company: str
    date: str
    category: str
    headline: str
    summary: str = ""
    source: str = "key_companies"
    source_url: str = ""
    tracking_id: str = ""


def _month_bucket(iso_date: str) -> str:
    if not iso_date:
        return ""
    s = iso_date.strip()
    if len(s) >= 7 and s[4] == "-":
        return s[:7]
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m")
    except Exception:
        return ""


def _normalize_date(raw: str, fallback: str = "") -> str:
    if raw:
        return raw
    return fallback or datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _kc_updates_from(report: Dict[str, Any], tracking_id: str) -> List[_RawEvent]:
    events: List[_RawEvent] = []
    for briefing in report.get("briefings") or []:
        company = briefing.get("company") or ""
        if not company:
            continue
        for u in briefing.get("updates") or []:
            events.append(
                _RawEvent(
                    company=company,
                    date=_normalize_date(
                        u.get("date") or "", fallback=u.get("published") or ""
                    ),
                    category=u.get("category") or "Other",
                    headline=u.get("headline") or "",
                    summary=u.get("summary") or "",
                    source="key_companies",
                    source_url=(u.get("source_url") or ""),
                    tracking_id=tracking_id,
                )
            )
    return events


def _ca_events_from(
    report: Dict[str, Any], tracking_id: str, generated_at: str
) -> List[_RawEvent]:
    events: List[_RawEvent] = []
    fallback = generated_at[:10] if generated_at else ""
    for profile in report.get("company_profiles") or []:
        company = profile.get("company") or ""
        if not company:
            continue
        for f in profile.get("technology_findings") or []:
            tech = f.get("technology") or ""
            source_url = (f.get("source_urls") or [""])[0] if f.get("source_urls") else ""
            for dev in f.get("recent_developments") or []:
                if not dev:
                    continue
                events.append(
                    _RawEvent(
                        company=company,
                        date=fallback,
                        category=tech or "Analysis",
                        headline=dev[:160],
                        summary=f.get("summary", "")[:300],
                        source="company_analysis",
                        source_url=source_url,
                        tracking_id=tracking_id,
                    )
                )
    return events


async def build_company_timeline(
    user_id: str,
    *,
    companies: Optional[List[str]] = None,
    max_events_per_company: int = 200,
) -> List[CompanyTimeline]:
    """Build per-company timelines across all saved runs for ``user_id``.

    Filters to ``companies`` when supplied (case-insensitive).
    """
    raw_events: List[_RawEvent] = []

    # Key Companies runs
    for entry in await list_key_companies_runs(user_id):
        data = await load_run(entry["path"])
        if not data:
            continue
        report = data.get("report") or {}
        raw_events.extend(_kc_updates_from(report, entry["tracking_id"]))

    # Company Analysis runs
    for entry in await list_company_analysis_runs(user_id):
        data = await load_run(entry["path"])
        if not data:
            continue
        report = data.get("report") or {}
        raw_events.extend(
            _ca_events_from(
                report,
                entry["tracking_id"],
                entry.get("generated_at", "") or "",
            )
        )

    # Optional company filter
    if companies:
        wanted = {c.strip().lower() for c in companies if c.strip()}
        raw_events = [
            e for e in raw_events if e.company.strip().lower() in wanted
        ]

    # Group by company
    by_company: Dict[str, List[_RawEvent]] = {}
    for e in raw_events:
        by_company.setdefault(e.company, []).append(e)

    timelines: List[CompanyTimeline] = []
    for company, events in by_company.items():
        events.sort(key=lambda e: e.date or "", reverse=True)
        events = events[:max_events_per_company]
        tl_events = [
            TimelineEvent(
                company=e.company,
                date=e.date or "",
                month_bucket=_month_bucket(e.date),
                category=e.category or "Other",
                headline=e.headline,
                summary=e.summary,
                source=e.source,
                source_url=e.source_url,
                tracking_id=e.tracking_id,
            )
            for e in events
        ]
        if not tl_events:
            continue
        first = min((e.date for e in tl_events if e.date), default="")
        last = max((e.date for e in tl_events if e.date), default="")
        timelines.append(
            CompanyTimeline(
                company=company,
                events=tl_events,
                first_seen=first,
                last_seen=last,
            )
        )

    # Sort companies by recent activity
    timelines.sort(key=lambda t: t.last_seen or "", reverse=True)
    logger.info(
        f"[company_timeline] built timelines for {len(timelines)} "
        f"company/companies from {len(raw_events)} event(s)"
    )
    return timelines


__all__ = [
    "TimelineEvent",
    "CompanyTimeline",
    "build_company_timeline",
]
