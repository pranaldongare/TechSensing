"""Key Companies diff-view (#12).

Compares the current briefing's updates against the most recent prior
run for the same company set (or watchlist) and tags each update with
``NEW``, ``ONGOING`` or surfaces ``RESOLVED`` topics from the previous
run that no longer appear.

Pure-local heuristic — no LLM cost. A resolved-topic annotation is
attached to the cross-company summary as a short bullet list so the
user sees "closed threads" without polluting the per-update rows.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from core.llm.output_schemas.analysis_extensions import DiffTag
from core.llm.output_schemas.key_companies import CompanyUpdate
from core.sensing.run_history import (
    find_previous_key_companies_run,
    load_run,
)

logger = logging.getLogger("sensing.diff")

_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> set[str]:
    return {t for t in _WORD_RE.findall((text or "").lower()) if len(t) > 2}


def _url_key(url: str) -> str:
    if not url:
        return ""
    u = url.strip().lower()
    # Strip fragment + trailing slash.
    u = u.split("#", 1)[0].rstrip("/")
    return u


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _previous_update_fingerprints(
    prev_report: Dict[str, Any],
) -> List[Tuple[str, str, set[str], str]]:
    """Return [(company_lower, url_key, headline_tokens, headline_raw)]."""
    out: List[Tuple[str, str, set[str], str]] = []
    for briefing in prev_report.get("briefings") or []:
        company = (briefing.get("company") or "").strip().lower()
        for u in briefing.get("updates") or []:
            headline = (u.get("headline") or "").strip()
            url = _url_key(u.get("source_url") or "")
            if not headline and not url:
                continue
            out.append((company, url, _tokenize(headline), headline))
    return out


def _resolved_topics(
    prev_fps: Sequence[Tuple[str, str, set[str], str]],
    current_fps: Sequence[Tuple[str, str, set[str], str]],
    *,
    max_topics: int = 8,
) -> List[Tuple[str, str]]:
    """Previous items that don't appear in current run — (company, headline)."""
    current_urls = {url for (_, url, _, _) in current_fps if url}
    current_by_company: Dict[str, List[set[str]]] = {}
    for (company, _, tokens, _) in current_fps:
        current_by_company.setdefault(company, []).append(tokens)

    resolved: List[Tuple[str, str]] = []
    for (company, url, tokens, headline) in prev_fps:
        if url and url in current_urls:
            continue
        # If any current headline in same company is near-duplicate, skip.
        peers = current_by_company.get(company, [])
        if any(_jaccard(tokens, p) >= 0.6 for p in peers):
            continue
        resolved.append((company, headline))
        if len(resolved) >= max_topics:
            break
    return resolved


async def annotate_key_companies_diff(
    user_id: str,
    report: Any,
    *,
    current_tracking_id: str,
) -> Optional[Dict[str, Any]]:
    """Mutate ``report.briefings[*].updates[*].diff`` in place.

    Returns ``None`` when no prior run exists; otherwise returns
    ``{"previous_tracking_id", "resolved_topics", "new_count",
    "ongoing_count"}``.
    """
    if not getattr(report, "briefings", None):
        return None

    companies = [b.company for b in report.briefings]
    prev_entry = await find_previous_key_companies_run(
        user_id,
        companies,
        before_tracking_id=current_tracking_id,
    )
    if not prev_entry:
        return None

    prev_data = await load_run(prev_entry["path"])
    if not prev_data:
        return None
    prev_report = prev_data.get("report") or {}

    prev_fps = _previous_update_fingerprints(prev_report)
    prev_urls = {url for (_, url, _, _) in prev_fps if url}
    prev_by_company: Dict[str, List[Tuple[str, set[str], str]]] = {}
    for (company, url, tokens, headline) in prev_fps:
        prev_by_company.setdefault(company, []).append((url, tokens, headline))

    new_count = 0
    ongoing_count = 0
    current_fps: List[Tuple[str, str, set[str], str]] = []

    for briefing in report.briefings:
        company_lc = (briefing.company or "").strip().lower()
        peers = prev_by_company.get(company_lc, [])
        for u in briefing.updates:
            url_k = _url_key(u.source_url or "")
            headline_toks = _tokenize(u.headline)
            status = "NEW"
            matched: str = ""
            if url_k and url_k in prev_urls:
                status = "ONGOING"
            else:
                # Token overlap match within same company.
                for (_, p_tokens, p_headline) in peers:
                    if _jaccard(headline_toks, p_tokens) >= 0.55:
                        status = "ONGOING"
                        matched = p_headline
                        break
            u.diff = DiffTag(
                status=status,  # type: ignore[arg-type]
                previous_headline=matched,
            )
            if status == "NEW":
                new_count += 1
            else:
                ongoing_count += 1
            current_fps.append(
                (company_lc, url_k, headline_toks, u.headline or "")
            )

    resolved = _resolved_topics(prev_fps, current_fps)

    logger.info(
        f"[kc_diff] prev={prev_entry.get('tracking_id','?')} "
        f"NEW={new_count} ONGOING={ongoing_count} RESOLVED={len(resolved)}"
    )
    return {
        "previous_tracking_id": prev_entry.get("tracking_id", ""),
        "resolved_topics": [
            {"company": c, "headline": h} for (c, h) in resolved
        ],
        "new_count": new_count,
        "ongoing_count": ongoing_count,
    }


__all__ = ["annotate_key_companies_diff"]
