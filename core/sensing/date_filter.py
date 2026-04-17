"""
Shared date-filtering helpers for all sensing pipelines.

Provides:
- parse_iso_date             — parse "2026-04-17" / ISO-8601 → datetime
- extract_date_from_text     — regex extraction from free text
- title_mentions_old_year    — detect old year references in titles/snippets
- filter_articles_by_date    — pre-LLM: drop RawArticles older than cutoff
- filter_findings_by_date    — post-LLM: drop items whose text mentions old dates
- reconcile_dates            — post-extraction: cross-validate source vs page dates
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

# Pattern for years that appear in article titles — used to detect
# re-syndicated old news.  Matches "2022", "2023", etc. in context
# that suggests the year is part of the article's subject, not a
# version number (e.g. "RFC 2024" or "Model v2024").
_TITLE_YEAR_PATTERN = re.compile(
    r"(?<![vV./\d])\b(20\d{2})\b(?![.\d])",
)

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


# ──────────────────────── stale-title detection ────────────────────────

def title_mentions_old_year(
    title: str,
    max_age_days: int = 180,
) -> bool:
    """Return True if *title* references a calendar year that ended more than
    *max_age_days* ago.

    This catches re-syndicated news like "IBM Unveils 433-Qubit Osprey
    Processor in 2022" that news aggregators serve with recent pub dates.
    Only fires on years that are unambiguously old — the current year and
    the immediately preceding year (within max_age_days) are allowed.
    """
    now = datetime.now(timezone.utc)
    for m in _TITLE_YEAR_PATTERN.finditer(title):
        year = int(m.group(1))
        # Treat the year's end (Dec 31) as the latest possible date for that year
        year_end = datetime(year, 12, 31, tzinfo=timezone.utc)
        if (now - year_end).days > max_age_days:
            return True
    return False


def _title_has_stale_year(
    title: str, snippet: str, cutoff: datetime,
) -> bool:
    """Check if the title or first sentence of the snippet contains a year
    that is clearly older than the cutoff.

    This is a stricter check than title_mentions_old_year: it uses the actual
    pipeline cutoff rather than a fixed 180-day window.
    """
    # Only check the title and the first 200 chars of snippet (to avoid
    # matching year references deep in article bodies)
    text = f"{title} {snippet[:200] if snippet else ''}"
    for m in _TITLE_YEAR_PATTERN.finditer(text):
        year = int(m.group(1))
        year_end = datetime(year, 12, 31, tzinfo=timezone.utc)
        if year_end < cutoff:
            return True
    return False


# ──────────────────────── date reconciliation ────────────────────────

def reconcile_dates(
    articles: list,
    lookback_days: int,
    *,
    label: str = "",
) -> tuple[list, int]:
    """Cross-validate source-provided dates against page metadata dates.

    After full-text extraction, ``trafilatura`` may have populated
    ``published_date`` with the *actual* page publication date (different
    from the aggregator/RSS syndication date).  This function:

    1. For each article whose ``published_date`` is recent but whose page
       content contains references to significantly older dates, flags
       the article as stale.
    2. Returns the filtered list and the count of articles removed.

    Works on objects with ``published_date``, ``title``, ``snippet``, and
    ``content`` attributes.
    """
    if lookback_days <= 0:
        return articles, 0

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=max(lookback_days * 2, 90))
    kept: list = []
    removed = 0

    for a in articles:
        title = getattr(a, "title", "") or ""
        snippet = getattr(a, "snippet", "") or ""
        content = getattr(a, "content", "") or ""

        # Check 1: Title/snippet explicitly references an old year
        if _title_has_stale_year(title, snippet, cutoff):
            logger.info(
                f"[{label}] Removed stale-titled article: {title[:80]}"
            )
            removed += 1
            continue

        # Check 2: Page content has a specific old date (YYYY-MM-DD) that
        # contradicts the source-provided date.
        source_dt = parse_iso_date(getattr(a, "published_date", "") or "")
        if source_dt and source_dt > cutoff:
            # Source says it's recent — cross-check against content
            content_dt = extract_date_from_text(content[:500])
            if content_dt and content_dt < cutoff:
                # Content's own date is old — this is re-syndicated content
                age_diff = (source_dt - content_dt).days
                if age_diff > 90:
                    logger.info(
                        f"[{label}] Removed re-syndicated article "
                        f"(source={source_dt.date()}, content={content_dt.date()}): "
                        f"{title[:80]}"
                    )
                    removed += 1
                    continue

        kept.append(a)

    if removed:
        logger.info(f"[{label}] Date reconciliation: removed {removed} stale articles")
    return kept, removed


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
    filtered_by_title_year = 0
    dropped_undated = 0

    for a in articles:
        title = getattr(a, "title", "") or ""
        snippet = getattr(a, "snippet", "") or ""

        # Fast check: title/snippet explicitly references an old year.
        # This catches re-syndicated old news that aggregators serve with
        # fresh pub dates (e.g. "IBM Osprey 2022" via Google News in 2026).
        if _title_has_stale_year(title, snippet, cutoff):
            filtered_by_title_year += 1
            filtered += 1
            continue

        pub_dt = parse_iso_date(getattr(a, "published_date", "") or "")

        extracted_from_content = False
        if pub_dt is None:
            text = f"{title} {snippet} {getattr(a, 'content', '')}"
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
                f" ({filtered_by_content} via content-date, "
                f"{filtered_by_title_year} via title-year detection)"
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
    filtered_by_title_year = 0
    dropped_undated = 0

    for item in findings:
        # Title-year check: catch stale content even if the date field is recent
        if text_getter:
            text = text_getter(item) or ""
            if _title_has_stale_year(text, "", cutoff):
                filtered += 1
                filtered_by_title_year += 1
                continue

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
                + (f" ({filtered_by_title_year} via title-year)" if filtered_by_title_year else "")
            )
        if dropped_undated:
            parts.append(f"dropped {dropped_undated} undated items")
        logger.info(f"{prefix}Post-LLM date filter: {'; '.join(parts)}")
    return kept
