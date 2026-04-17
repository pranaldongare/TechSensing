"""Cross-cutting schema extensions for Company Analysis and Key Companies.

All models here are optional add-ons: old reports written before these
fields existed should still deserialize cleanly because every field has
a default.
"""

from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, Field

# ──────────────────────────────────────────────────────────────
# Phase 3.1 — Momentum (#8)
# ──────────────────────────────────────────────────────────────


class MomentumSnapshot(BaseModel):
    """Numeric momentum score for one company during a briefing window."""

    score: float = Field(
        default=0.0,
        description="0-100 momentum score, higher = more active / notable.",
    )
    update_count: int = Field(default=0)
    weighted_score: float = Field(default=0.0)
    top_drivers: List[str] = Field(
        default_factory=list,
        description=(
            "Short labels of the categories or events that drove the "
            "score (e.g., 'Product Launch', 'Funding $2B')."
        ),
    )


# ──────────────────────────────────────────────────────────────
# Phase 3.2 — Competitive overlap matrix (#10)
# ──────────────────────────────────────────────────────────────


class OverlapCell(BaseModel):
    """One cell in the (technology × technology) overlap heatmap."""

    technology_a: str
    technology_b: str
    overlap_count: int = Field(
        default=0,
        description=(
            "Number of analyzed companies with evidenced activity in "
            "BOTH technologies."
        ),
    )
    overlap_companies: List[str] = Field(default_factory=list)


# ──────────────────────────────────────────────────────────────
# Phase 3.3 — Strategic themes (#11)
# ──────────────────────────────────────────────────────────────


class ThemeCluster(BaseModel):
    """A cross-company strategic theme surfaced by the LLM."""

    theme: str = Field(description="Short label for the theme.")
    rationale: str = Field(
        description="2-3 sentence explanation citing evidence across companies."
    )
    companies: List[str] = Field(default_factory=list)
    technologies: List[str] = Field(default_factory=list)


# ──────────────────────────────────────────────────────────────
# Phase 3.5 — Cross-domain rollup (#29)
# ──────────────────────────────────────────────────────────────


class DomainRollupEntry(BaseModel):
    domain: str
    update_count: int = Field(default=0)
    company_count: int = Field(
        default=0,
        description="Distinct companies with at least one update in this domain.",
    )


# ──────────────────────────────────────────────────────────────
# Phase 3.6 — Investment signals (#30)
# ──────────────────────────────────────────────────────────────


class InvestmentEvent(BaseModel):
    """A discrete financial / investment signal."""

    company: str
    event_type: Literal[
        "Funding",
        "Acquisition",
        "IPO",
        "Divestiture",
        "Partnership",
        "Hiring",
        "Other",
    ] = "Other"
    amount_usd: float = Field(
        default=0.0,
        description="Amount in USD (best-effort; 0 when unknown).",
    )
    amount_text: str = Field(
        default="",
        description="Raw amount as it appeared ('$2B', '$500M series C').",
    )
    date: str = Field(default="", description="YYYY-MM-DD if known.")
    description: str = Field(default="")
    source_url: str = Field(default="")


# ──────────────────────────────────────────────────────────────
# Phase 4.3 — Diff status (#12)
# ──────────────────────────────────────────────────────────────


DiffStatus = Literal["NEW", "ONGOING", "RESOLVED"]


class DiffTag(BaseModel):
    """Diff label attached to a single update after comparison with previous run."""

    status: DiffStatus = "NEW"
    previous_headline: str = Field(
        default="",
        description="Matched prior headline when status is 'ONGOING' or 'RESOLVED'.",
    )


# ──────────────────────────────────────────────────────────────
# Phase 6.2 — Contradictions (#26)
# ──────────────────────────────────────────────────────────────


class ContradictionFlag(BaseModel):
    topic: str
    claim_a: str
    claim_b: str
    sources_a: List[str] = Field(default_factory=list)
    sources_b: List[str] = Field(default_factory=list)
    resolution: Literal["unclear", "A", "B"] = "unclear"
    note: str = Field(default="")


# ──────────────────────────────────────────────────────────────
# Phase 6.3 — Hallucination probe (#27)
# ──────────────────────────────────────────────────────────────


class UnsupportedClaim(BaseModel):
    claim: str
    reason: str = Field(
        default="",
        description=(
            "Why the claim is not supported by the input articles — "
            "'no source mentions X', 'fabricated partnership', etc."
        ),
    )
    suggested_action: Literal["drop", "flag", "rewrite"] = "flag"


# ──────────────────────────────────────────────────────────────
# Phase 6.4 — Hiring signals (#31)
# ──────────────────────────────────────────────────────────────


class HiringSnapshot(BaseModel):
    total_postings: int = Field(default=0)
    seniority_breakdown: List[str] = Field(
        default_factory=list,
        description="Strings like 'Senior: 12', 'Staff: 3', 'Director: 1'.",
    )
    domains: List[str] = Field(
        default_factory=list,
        description="Domains inferred from job titles (e.g., 'ML', 'Cloud', 'Security').",
    )
    trend_vs_previous: Literal["up", "flat", "down", "unknown"] = "unknown"


# ──────────────────────────────────────────────────────────────
# Phase 6.5 — Opportunity / threat framing (#33)
# ──────────────────────────────────────────────────────────────


class OpportunityThreatFraming(BaseModel):
    org_context_used: str = Field(
        default="",
        description="Short label for the user org-context profile used."
    )
    opportunities: List[str] = Field(default_factory=list)
    threats: List[str] = Field(default_factory=list)
    recommended_actions: List[str] = Field(default_factory=list)
