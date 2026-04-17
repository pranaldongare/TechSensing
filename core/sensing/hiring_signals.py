"""Hiring-signal heuristics (#31).

LinkedIn public pages are closed, so we use:
  - DDG ``site:linkedin.com/jobs "{company}"`` queries
  - Company careers pages (/{company_slug}/careers, /careers)

We count job postings by inferred seniority and domain, then compare
against a previous run to determine the trend.

Gated behind ``SENSING_FEATURES["hiring_signals"]``.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from core.constants import SENSING_FEATURES
from core.sensing.ingest import search_duckduckgo

logger = logging.getLogger("sensing.hiring_signals")


async def fetch_hiring_signals(
    company: str,
    *,
    lookback_days: int = 30,
    previous_total: int = 0,
) -> Dict[str, Any]:
    """Return a HiringSnapshot-compatible dict for *company*.

    Returned keys: ``total_postings``, ``seniority_breakdown``,
    ``domains``, ``trend_vs_previous``.
    """
    if not SENSING_FEATURES.get("hiring_signals", True):
        return _empty()

    queries = [
        f'site:linkedin.com/jobs "{company}"',
        f'"{company}" hiring careers',
    ]
    articles = []
    for q in queries:
        try:
            results = await search_duckduckgo(
                queries=[q],
                domain="jobs",
                lookback_days=lookback_days,
            )
            articles.extend(results)
        except Exception as e:
            logger.debug(f"Hiring search failed for '{q}': {e}")

    if not articles:
        return _empty()

    # ── Parse postings heuristically ──
    total = len(articles)
    seniority_counts: Dict[str, int] = {}
    domain_set: set[str] = set()

    for a in articles:
        text = f"{a.title or ''} {a.snippet or ''}".lower()
        seniority, domains = _classify(text)
        if seniority:
            seniority_counts[seniority] = seniority_counts.get(seniority, 0) + 1
        domain_set.update(domains)

    seniority_breakdown = [
        f"{k}: {v}" for k, v in sorted(seniority_counts.items(), key=lambda x: -x[1])
    ]

    trend = "unknown"
    if previous_total > 0:
        if total > previous_total * 1.2:
            trend = "up"
        elif total < previous_total * 0.8:
            trend = "down"
        else:
            trend = "flat"

    return {
        "total_postings": total,
        "seniority_breakdown": seniority_breakdown,
        "domains": sorted(domain_set),
        "trend_vs_previous": trend,
    }


# ──────────────────────────── helpers ───────────────────────────


_SENIORITY_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("Director+", re.compile(r"\b(director|vp|vice president|cto|head of)\b", re.I)),
    ("Staff/Principal", re.compile(r"\b(staff|principal|distinguished)\b", re.I)),
    ("Senior", re.compile(r"\bsenior\b", re.I)),
    ("Mid-level", re.compile(r"\b(mid|software engineer|data scientist)\b", re.I)),
    ("Junior/Intern", re.compile(r"\b(junior|intern|entry.level|associate)\b", re.I)),
]

_DOMAIN_KEYWORDS: Dict[str, re.Pattern] = {
    "ML/AI": re.compile(r"\b(machine learning|ml|artificial intelligence|ai|deep learning|nlp|llm)\b", re.I),
    "Cloud": re.compile(r"\b(cloud|aws|azure|gcp|devops|sre|infrastructure)\b", re.I),
    "Security": re.compile(r"\b(security|infosec|cybersec|devsecops)\b", re.I),
    "Data": re.compile(r"\b(data engineer|data analyst|analytics|etl|warehouse)\b", re.I),
    "Frontend": re.compile(r"\b(frontend|react|vue|angular|ui|ux)\b", re.I),
    "Backend": re.compile(r"\b(backend|java|golang|python|rust|scala)\b", re.I),
    "Mobile": re.compile(r"\b(mobile|ios|android|flutter|react native)\b", re.I),
}


def _classify(text: str) -> Tuple[Optional[str], List[str]]:
    seniority: Optional[str] = None
    for label, pat in _SENIORITY_PATTERNS:
        if pat.search(text):
            seniority = label
            break

    domains: List[str] = []
    for label, pat in _DOMAIN_KEYWORDS.items():
        if pat.search(text):
            domains.append(label)

    return seniority, domains


def _empty() -> Dict[str, Any]:
    return {
        "total_postings": 0,
        "seniority_breakdown": [],
        "domains": [],
        "trend_vs_previous": "unknown",
    }
