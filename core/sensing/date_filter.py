"""
Shared date-filtering helpers for all sensing pipelines.

Provides:
- parse_iso_date           — parse "2026-04-17" / ISO-8601 → datetime
- extract_date_from_text   — regex extraction from free text
- filter_articles_by_date  — pre-LLM: drop RawArticles older than cutoff
- filter_findings_by_date  — post-LLM: drop items whose text mentions old dates
"""

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, List, Optional, Protocol, Sequence

logger = logging.getLogger("sensing.date_filter")


# ──────────────────────── regex patterns ────────────────────────

_DATE_PATTERN_ISO = re.compile(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b")
_DATE_PATTERN_MONTH_YEAR = re.compile(
    r"\b(January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+(\d{1,2},?\s+)?(20\d{2})\b",
    re.IGNORECASE,
)
_DATE_PATTERN_YEAR = re.compile(r"\b(20\d{2})\b")

_MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


# ──────────────────────── date parsing ────────────────────────

def parse_iso_date(date_str: str) -> Optional[datetime]:
    """Parse ISO date string into UTC datetime."""
    if not date_str:
        return None
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def extract_date_from_text(text: str) -> Optional[datetime]:
    """Extract a date from free text.  Returns UTC datetime or None.

    Tries progressively less specific patterns:
    1. YYYY-MM-DD  (ISO)
    2. Month DD, YYYY  or  Month YYYY
    3. Just YYYY  (maps to Jun 15 of that year)
    """
    if not text:
        return None

    m = _DATE_PATTERN_ISO.search(text)
    if m:
        try:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            return datetime(y, mo, d, tzinfo=timezone.utc)
        except (ValueError, TypeError):
            pass

    m = _DATE_PATTERN_MONTH_YEAR.search(text)
    if m:
        try:
            month_num = _MONTH_MAP[m.group(1).lower()]
            year = int(m.group(3))
            return datetime(year, month_num, 15, tzinfo=timezone.utc)
        except (ValueError, KeyError):
            pass

    m = _DATE_PATTERN_YEAR.search(text)
    if m:
        try:
            return datetime(int(m.group(1)), 6, 15, tzinfo=timezone.utc)
        except (ValueError, TypeError):
            pass

    return None


# ──────────────────────── pre-LLM article filter ────────────────────────

def filter_articles_by_date(
    articles: list,
    lookback_days: int,
    *,
    buffer_multiplier: float = 1.5,
    drop_undated: bool = False,
    label: str = "",
) -> list:
    """Remove articles older than the allowed window.

    Works on any object with ``published_date``, ``title``, ``snippet`` and
    ``content`` attributes (e.g. ``RawArticle``).

    When ``drop_undated`` is *False* (default), articles with no extractable
    date are kept.  Set ``drop_undated=True`` for post-extraction calls where
    every reasonable attempt to determine the date has already been made (DDG
    news dates + trafilatura metadata).
    """
    if lookback_days <= 0:
        return articles

    cutoff = datetime.now(timezone.utc) - timedelta(
        days=int(lookback_days * buffer_multiplier)
    )
    kept: list = []
    filtered = 0
    filtered_by_content = 0
    dropped_undated = 0

    for a in articles:
        pub_dt = parse_iso_date(getattr(a, "published_date", "") or "")

        extracted_from_content = False
        if pub_dt is None:
            text = f"{getattr(a, 'title', '')} {getattr(a, 'snippet', '')} {getattr(a, 'content', '')}"
            pub_dt = extract_date_from_text(text)
            extracted_from_content = pub_dt is not None

        if pub_dt is None:
            if drop_undated:
                dropped_undated += 1
                continue
            kept.append(a)
            continue

        if pub_dt < cutoff:
            filtered += 1
            if extracted_from_content:
                filtered_by_content += 1
            continue

        kept.append(a)

    if filtered or dropped_undated:
        prefix = f"[{label}] " if label else ""
        parts = []
        if filtered:
            parts.append(
                f"removed {filtered} articles older than "
                f"{int(lookback_days * buffer_multiplier)} days"
                f" ({filtered_by_content} via content-based date extraction)"
            )
        if dropped_undated:
            parts.append(f"dropped {dropped_undated} undated articles")
        logger.info(f"{prefix}Date filter: {'; '.join(parts)}")
    return kept


# ──────────────────────── post-LLM finding filter ────────────────────────

def filter_findings_by_date(
    findings: list,
    lookback_days: int,
    *,
    buffer_multiplier: float = 1.5,
    drop_undated: bool = False,
    text_getter: Optional[Callable[[Any], str]] = None,
    date_getter: Optional[Callable[[Any], str]] = None,
    label: str = "",
) -> list:
    """Post-LLM date filter for structured findings.

    Iterates *findings* (any list of objects).  For each item:
    1. Try ``date_getter(item)`` → parse as ISO date.
    2. If no date, try ``text_getter(item)`` → extract date from text.
    3. If still no date: drop when ``drop_undated=True``, keep otherwise.

    Items whose extracted date is older than ``lookback_days * buffer``
    are removed.
    """
    if lookback_days <= 0 or not findings:
        return findings

    cutoff = datetime.now(timezone.utc) - timedelta(
        days=int(lookback_days * buffer_multiplier)
    )
    kept: list = []
    filtered = 0
    dropped_undated = 0

    for item in findings:
        # Primary: explicit date field
        date_str = date_getter(item) if date_getter else ""
        pub_dt = parse_iso_date(date_str or "")

        # Fallback: extract from text
        if pub_dt is None and text_getter:
            text = text_getter(item) or ""
            pub_dt = extract_date_from_text(text)

        if pub_dt is None:
            if drop_undated:
                dropped_undated += 1
                continue
            kept.append(item)
            continue

        if pub_dt < cutoff:
            filtered += 1
            continue

        kept.append(item)

    if filtered or dropped_undated:
        prefix = f"[{label}] " if label else ""
        parts = []
        if filtered:
            parts.append(
                f"removed {filtered} items older than "
                f"{int(lookback_days * buffer_multiplier)} days"
            )
        if dropped_undated:
            parts.append(f"dropped {dropped_undated} undated items")
        logger.info(f"{prefix}Post-LLM date filter: {'; '.join(parts)}")
    return kept
