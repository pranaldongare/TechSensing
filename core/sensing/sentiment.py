"""Lightweight rule-based sentiment scorer for Key Companies updates.

We don't need model-quality sentiment here — only a coarse
positive/neutral/negative tag so the UI can colour badges and the
momentum score (#8) can factor it in. A small keyword lexicon paired
with category hints (#9) is accurate enough and adds zero latency or
LLM cost.
"""

from __future__ import annotations

from typing import Literal

Sentiment = Literal["positive", "neutral", "negative"]


_POSITIVE_CUES = (
    "launch", "launched", "launches", "release", "released", "unveil",
    "unveiled", "ship", "shipping", "shipped", "rollout", "expansion",
    "expands", "expanded", "partnership", "partnered", "partners with",
    "collaboration", "acquires", "acquired", "acquire", "investment",
    "funding", "series a", "series b", "series c", "series d", "series e",
    "raises", "raised", "wins", "won", "milestone", "breakthrough",
    "record", "beat expectations", "surpass", "outperform", "grew",
    "growth", "double-digit", "strong", "solid", "momentum",
    "positive", "approved", "approval", "cleared",
)

_NEGATIVE_CUES = (
    "layoff", "layoffs", "cuts", "cut jobs", "cut staff", "fire",
    "fired", "firing", "lawsuit", "sue", "sued", "investigation",
    "investigate", "probe", "fine", "fined", "penalty", "penalties",
    "sanction", "sanctioned", "banned", "ban", "outage", "breach",
    "hack", "hacked", "leaks", "leaked", "recall", "recalled",
    "decline", "declined", "drop", "dropped", "plunge", "slump",
    "falters", "faltering", "delayed", "delay", "postpone",
    "shutdown", "shuts down", "resigns", "resigned", "step down",
    "regulatory action", "charged", "indicted", "antitrust",
    "criticism", "backlash", "scandal", "controversy", "concern",
    "warns", "warned", "warning", "vulnerability", "exploit",
    "misses", "missed", "disappoint",
)


_CATEGORY_TILT: dict[str, Sentiment] = {
    "product launch": "positive",
    "funding": "positive",
    "partnership": "positive",
    "acquisition": "positive",
    "research": "neutral",
    "technical": "neutral",
    "regulatory": "negative",
    "people": "neutral",
    "other": "neutral",
}


def score_update(
    *,
    headline: str = "",
    summary: str = "",
    category: str = "",
) -> Sentiment:
    """Return a coarse sentiment label for a single update."""
    text = f"{headline or ''} {summary or ''}".lower()
    if not text.strip():
        return _CATEGORY_TILT.get((category or "").strip().lower(), "neutral")

    pos_hits = sum(1 for w in _POSITIVE_CUES if w in text)
    neg_hits = sum(1 for w in _NEGATIVE_CUES if w in text)

    # Any explicit negative cue wins; regulatory category also leans negative.
    if neg_hits > 0 and neg_hits >= pos_hits:
        return "negative"
    if pos_hits > neg_hits:
        return "positive"

    # Fall back to category tilt for updates with no strong cues.
    cat = (category or "").strip().lower()
    return _CATEGORY_TILT.get(cat, "neutral")
