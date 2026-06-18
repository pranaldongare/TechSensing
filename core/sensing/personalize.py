"""
Personalization pass — curate a report into two profile-driven sections:

  - "For You": report items matching the active profile (interests / stack /
    priorities / competitors), with the matched terms surfaced as "why".
  - "This might interest you": high-impact items OUTSIDE the profile (engineered
    serendipity) — a minimum quota always kept so personalization never hides
    important developments (anti-filter-bubble floor).

Deterministic (no LLM). Runs after the report is generated. The personalization
slider (0-100) scales how many "For You" items are shown.
"""

import logging
from typing import Optional

from core.llm.output_schemas.sensing_outputs import PersonalizedItem, PersonalizedSections

logger = logging.getLogger("sensing.personalize")

_IMPACT_RANK = {"high": 3.0, "medium": 2.0, "low": 1.0, "": 1.0}
_MIGHT_INTEREST_FLOOR = 2   # always keep at least this many serendipity items
_MIGHT_INTEREST_CAP = 4
_FOR_YOU_MAX = 8


def _candidates(report) -> list[dict]:
    """Flatten radar items, top events, and key trends into scored candidates."""
    out: list[dict] = []
    for it in getattr(report, "radar_items", []) or []:
        title = getattr(it, "name", "") or ""
        if not title:
            continue
        text = f"{title} {getattr(it, 'quadrant', '')} {getattr(it, 'ring', '')}"
        out.append({
            "title": title, "kind": "radar",
            "summary": getattr(it, "description", "") or "",
            "source_url": "",
            "impact_score": float(getattr(it, "signal_strength", 0.0) or 0.0) + 1.0,
            "impact": getattr(it, "ring", "") or "",
            "text": text,
        })
    for ev in getattr(report, "top_events", []) or []:
        title = getattr(ev, "headline", "") or ""
        if not title:
            continue
        rel = " ".join(getattr(ev, "related_technologies", []) or [])
        urls = getattr(ev, "source_urls", []) or []
        out.append({
            "title": title, "kind": "event",
            "summary": getattr(ev, "impact_summary", "") or "",
            "source_url": urls[0] if urls else "",
            "impact_score": _IMPACT_RANK.get((getattr(ev, "impact", "") or "").lower(), 1.0) + 1.0,
            "impact": getattr(ev, "impact", "") or "",
            "text": f"{title} {getattr(ev, 'actor', '')} {rel} {getattr(ev, 'segment', '')}",
        })
    for tr in getattr(report, "key_trends", []) or []:
        title = getattr(tr, "trend_name", "") or ""
        if not title:
            continue
        out.append({
            "title": title, "kind": "trend",
            "summary": getattr(tr, "description", "") or "",
            "source_url": "",
            "impact_score": 1.5,
            "impact": "",
            "text": f"{title} {getattr(tr, 'description', '')}",
        })
    return out


def build_personalized_sections(
    report,
    profile,
    domain: str,
    personalization: int,
) -> Optional[PersonalizedSections]:
    """Return the For-You / might-interest curation, or None when the profile
    carries no usable interest signal (nothing to personalize on)."""
    from core.sensing.profile import resolve_profile_prefs

    prefs = resolve_profile_prefs(profile, domain) if profile else {"interests": [], "avoid": []}
    match_terms = list(dict.fromkeys([
        *(getattr(profile, "interests", []) or []),
        *(getattr(profile, "tech_stack", []) or []),
        *(getattr(profile, "priorities", []) or []),
        *(getattr(profile, "competitors", []) or []),
        *(prefs.get("interests") or []),
    ]))
    match_set = [t.strip() for t in match_terms if t and len(t.strip()) >= 3]
    avoid_set = [t.strip().lower() for t in (prefs.get("avoid") or []) if t and len(t.strip()) >= 3]

    p = max(0, min(100, int(personalization or 0)))
    if not match_set or p == 0:
        return None

    cands = _candidates(report)
    for c in cands:
        low = c["text"].lower()
        c["why"] = [t for t in match_set if t.lower() in low]
        c["avoided"] = any(a in low for a in avoid_set)

    matched = [c for c in cands if c["why"] and not c["avoided"]]
    matched.sort(key=lambda c: (len(c["why"]), c["impact_score"]), reverse=True)
    for_you_size = max(1, round(p / 100 * _FOR_YOU_MAX))
    for_you = matched[:for_you_size]

    unmatched = [c for c in cands if not c["why"] and not c["avoided"]]
    unmatched.sort(key=lambda c: c["impact_score"], reverse=True)
    might = unmatched[:max(_MIGHT_INTEREST_FLOOR, _MIGHT_INTEREST_CAP)][:_MIGHT_INTEREST_CAP]

    def _mk(c: dict) -> PersonalizedItem:
        return PersonalizedItem(
            title=c["title"][:120],
            kind=c["kind"],
            summary=(c["summary"] or "")[:240],
            why=c["why"][:5],
            source_url=c["source_url"],
            impact=c["impact"],
        )

    sections = PersonalizedSections(
        for_you=[_mk(c) for c in for_you],
        might_interest=[_mk(c) for c in might],
        profile_name=getattr(profile, "name", "") or "",
        personalization=p,
    )
    logger.info(
        f"[Personalize] for_you={len(sections.for_you)}, "
        f"might_interest={len(sections.might_interest)} (p={p})"
    )
    return sections
