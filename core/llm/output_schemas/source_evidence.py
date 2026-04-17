"""Shared schema fragments for per-claim source evidence (#25, #13).

Both Company Analysis findings and Key Companies updates can carry a
list of :class:`ClaimEvidence` records so the UI can render a per-claim
source panel. ``is_single_source`` is set by the sanitizer (not by the
LLM) and drives the single-source confidence downgrade.
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class ClaimEvidence(BaseModel):
    """A single verifiable claim with its supporting source URLs."""

    claim: str = Field(
        description=(
            "Self-contained factual claim (≤ 240 chars) extracted from "
            "the analysis, phrased so a reader can verify it against the "
            "linked sources."
        )
    )
    source_urls: List[str] = Field(
        default_factory=list,
        description=(
            "1-3 URLs of articles from the input set that substantiate "
            "the claim. Never fabricate URLs."
        ),
    )
    confidence: float = Field(
        default=0.0,
        description=(
            "Confidence in this specific claim 0.0-1.0 based on source "
            "quality and corroboration. Automatically downgraded to "
            "≤ 0.4 when only one source is cited."
        ),
    )
    is_single_source: bool = Field(
        default=False,
        description=(
            "Set by the sanitizer to True when only one source URL is "
            "listed. Drives the amber confidence dot in the UI."
        ),
    )


def downgrade_single_source(
    evidence: List[ClaimEvidence],
    ceiling: float = 0.4,
) -> List[ClaimEvidence]:
    """Mark claims backed by ≤ 1 source and cap their confidence.

    Returns the same list with mutations applied. Safe to call multiple
    times (idempotent).
    """
    for e in evidence or []:
        n = len([u for u in (e.source_urls or []) if u])
        e.is_single_source = n <= 1
        if e.is_single_source and e.confidence > ceiling:
            e.confidence = ceiling
    return evidence
