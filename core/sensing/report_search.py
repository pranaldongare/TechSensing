"""
Report library search — full-text search across stored sensing reports.

Searches report titles, executive summaries, bottom lines, radar item names,
trend names, and event headlines using case-insensitive substring matching.
"""

import json
import logging
import os
from datetime import datetime
from typing import List, Optional

import aiofiles

logger = logging.getLogger("sensing.search")


async def search_reports(
    user_id: str,
    query: str,
    domain: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    max_results: int = 20,
) -> List[dict]:
    """Search stored reports for a query string.

    Returns a list of matching report summaries sorted by relevance (match count).
    """
    sensing_dir = f"data/{user_id}/sensing"
    if not os.path.exists(sensing_dir):
        return []

    query_lower = query.lower()
    results = []

    for fname in os.listdir(sensing_dir):
        if not (fname.startswith("report_") and fname.endswith(".json")):
            continue

        fpath = os.path.join(sensing_dir, fname)
        try:
            async with aiofiles.open(fpath, "r", encoding="utf-8") as f:
                data = json.loads(await f.read())

            meta = data.get("meta", {})
            report = data.get("report", {})

            # Domain filter
            if domain:
                meta_domain = (meta.get("domain") or "").lower()
                report_domain = (report.get("domain") or "").lower()
                if domain.lower() not in (meta_domain, report_domain):
                    continue

            # Date filter
            generated_at = meta.get("generated_at", "")
            if date_from and generated_at < date_from:
                continue
            if date_to and generated_at > date_to:
                continue

            # Build searchable text fields
            title = report.get("report_title", "")
            summary = report.get("executive_summary", "")
            bottom_line = report.get("bottom_line", "")
            radar_names = [r.get("name", "") for r in report.get("radar_items", [])]
            trend_names = [t.get("trend_name", "") for t in report.get("key_trends", [])]
            event_headlines = [e.get("headline", "") for e in report.get("top_events", [])]

            # Count matches across all fields
            all_text = " ".join([
                title, summary, bottom_line,
                *radar_names, *trend_names, *event_headlines,
            ]).lower()

            match_count = all_text.count(query_lower)
            if match_count == 0:
                continue

            tracking_id = meta.get("tracking_id") or fname.replace("report_", "").replace(".json", "")
            bl_snippet = (bottom_line[:150] + "...") if len(bottom_line) > 150 else bottom_line

            results.append({
                "tracking_id": tracking_id,
                "report_title": title or "Untitled",
                "domain": meta.get("domain") or report.get("domain", ""),
                "generated_at": generated_at,
                "bottom_line_snippet": bl_snippet,
                "match_count": match_count,
            })

        except Exception as e:
            logger.warning(f"Failed to search {fname}: {e}")
            continue

    # Sort by match count descending, then by date descending
    results.sort(key=lambda r: (-r["match_count"], r.get("generated_at", "")), reverse=False)
    results.sort(key=lambda r: -r["match_count"])

    return results[:max_results]
