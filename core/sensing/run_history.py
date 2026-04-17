"""Read-only index over past sensing runs.

Enables diffs (#12), timelines (#14), and scheduled-digest comparisons
(#16) by letting callers find the most recent prior run for a given
``(kind, scope_key)`` tuple, where ``scope_key`` is the sorted list of
companies for Key Companies or the parent report_tracking_id for
Company Analysis.
"""

from __future__ import annotations

import glob
import json
import logging
import os
from typing import Any, Dict, List, Optional

import aiofiles

logger = logging.getLogger("sensing.run_history")


def _sensing_dir(user_id: str) -> str:
    return os.path.join("data", user_id, "sensing")


async def _read_json(path: str) -> Optional[Dict[str, Any]]:
    try:
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            raw = await f.read()
        return json.loads(raw)
    except Exception as e:
        logger.debug(f"[run_history] read failed {path}: {e}")
        return None


async def list_key_companies_runs(user_id: str) -> List[Dict[str, Any]]:
    """Enumerate saved Key Companies runs (newest first).

    Each entry:
      {path, tracking_id, companies, highlight_domain, period_start,
       period_end, generated_at}
    """
    directory = _sensing_dir(user_id)
    if not os.path.isdir(directory):
        return []
    pattern = os.path.join(directory, "key_companies_*.json")
    paths = [
        p for p in glob.glob(pattern)
        if "_status_" not in os.path.basename(p)
    ]
    entries: List[Dict[str, Any]] = []
    for path in paths:
        data = await _read_json(path)
        if not data:
            continue
        meta = data.get("meta", {}) or {}
        report = data.get("report", {}) or {}
        entries.append(
            {
                "path": path,
                "tracking_id": meta.get("tracking_id")
                or os.path.splitext(os.path.basename(path))[0]
                .replace("key_companies_", ""),
                "companies": meta.get("companies")
                or report.get("companies_analyzed")
                or [],
                "highlight_domain": meta.get("highlight_domain")
                or report.get("highlight_domain", ""),
                "period_start": meta.get("period_start")
                or report.get("period_start", ""),
                "period_end": meta.get("period_end")
                or report.get("period_end", ""),
                "generated_at": meta.get("generated_at", ""),
            }
        )
    entries.sort(key=lambda r: r.get("generated_at", ""), reverse=True)
    return entries


async def list_company_analysis_runs(user_id: str) -> List[Dict[str, Any]]:
    directory = _sensing_dir(user_id)
    if not os.path.isdir(directory):
        return []
    pattern = os.path.join(directory, "company_analysis_*.json")
    paths = [
        p for p in glob.glob(pattern)
        if "_status_" not in os.path.basename(p)
    ]
    entries: List[Dict[str, Any]] = []
    for path in paths:
        data = await _read_json(path)
        if not data:
            continue
        meta = data.get("meta", {}) or {}
        report = data.get("report", {}) or {}
        entries.append(
            {
                "path": path,
                "tracking_id": meta.get("tracking_id")
                or os.path.splitext(os.path.basename(path))[0]
                .replace("company_analysis_", ""),
                "report_tracking_id": meta.get("report_tracking_id")
                or report.get("report_tracking_id", ""),
                "domain": meta.get("domain") or report.get("domain", ""),
                "companies": meta.get("companies")
                or report.get("companies_analyzed")
                or [],
                "technologies": meta.get("technologies")
                or report.get("technologies_analyzed")
                or [],
                "generated_at": meta.get("generated_at", ""),
            }
        )
    entries.sort(key=lambda r: r.get("generated_at", ""), reverse=True)
    return entries


def _company_key(companies: List[str]) -> str:
    return "|".join(sorted(c.strip().lower() for c in (companies or []) if c))


async def find_previous_key_companies_run(
    user_id: str,
    companies: List[str],
    before_tracking_id: str = "",
) -> Optional[Dict[str, Any]]:
    """Return the most recent prior KC run for the same company set.

    ``before_tracking_id`` excludes the current in-progress run so we
    don't compare a run against itself.
    """
    target = _company_key(companies)
    entries = await list_key_companies_runs(user_id)
    for e in entries:
        if e.get("tracking_id") == before_tracking_id:
            continue
        if _company_key(e.get("companies") or []) == target:
            return e
    return None


async def load_run(path: str) -> Optional[Dict[str, Any]]:
    """Load a full run payload by its saved path."""
    return await _read_json(path)
