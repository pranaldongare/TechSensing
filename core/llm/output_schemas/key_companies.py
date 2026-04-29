"""
Pydantic schemas for the Key Companies feature — weekly cross-domain
updates for a user-selected set of companies.

Unlike Company Analysis (which is tied to a report's radar items and uses a
multi-month lookback), Key Companies is a recurring, domain-agnostic,
last-week briefing: "What did these companies do this week?"
"""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from core.llm.output_schemas.analysis_extensions import (
    DiffTag,
    DomainRollupEntry,
    HiringSnapshot,
    MomentumSnapshot,
)
from core.llm.output_schemas.base import LLMOutputBase
from core.llm.output_schemas.source_evidence import ClaimEvidence


# Allowed update categories.  Kept as a tuple for reuse in prompts and
# post-validation normalization.
UPDATE_CATEGORIES = (
    "Product Launch",
    "Funding",
    "Partnership",
    "Acquisition",
    "Research",
    "Technical",
    "Regulatory",
    "People",
    "Other",
)


class CompanyUpdate(BaseModel):
    """A single newsworthy update about a company."""

    category: str = Field(
        default="Other",
        description=(
            "One of: 'Product Launch', 'Funding', 'Partnership', "
            "'Acquisition', 'Research', 'Technical', 'Regulatory', "
            "'People', 'Other'."
        ),
    )
    headline: str = Field(
        description="Short headline for the update (≤ 120 chars)."
    )
    summary: str = Field(
        description=(
            "1-2 sentence summary of the update, grounded in the provided "
            "articles."
        )
    )
    date: str = Field(
        default="",
        description=(
            "Best-effort date of the event in YYYY-MM-DD. Leave empty if "
            "no date is derivable from the article."
        ),
    )
    domain: str = Field(
        default="",
        description=(
            "Primary technology domain this update touches (e.g., "
            "'Generative AI', 'Quantum Computing', 'Robotics', "
            "'Cybersecurity', 'Semiconductors', 'Biotech'). Leave empty "
            "if not applicable."
        ),
    )
    quantitative_highlights: List[str] = Field(
        default_factory=list,
        description=(
            "1-3 specific quantitative facts from the article — revenue figures, "
            "funding amounts, benchmark scores, user/customer counts, performance "
            "metrics, market share numbers, growth percentages. Each item must cite "
            "the number and its context. Only include numbers explicitly stated in "
            "the articles — do NOT fabricate."
        ),
    )
    source_url: str = Field(
        default="",
        description="URL of the article supporting this update.",
    )
    sentiment: Literal["positive", "neutral", "negative"] = Field(
        default="neutral",
        description=(
            "Emotional tone of the update relative to the company "
            "(#9). Set by the sentiment scorer, not the LLM."
        ),
    )
    evidence: List[ClaimEvidence] = Field(
        default_factory=list,
        description=(
            "Per-claim source citations for substantive claims in the "
            "summary. Optional (#25)."
        ),
    )
    diff: DiffTag = Field(
        default_factory=DiffTag,
        description=(
            "Relationship to the previous briefing for the same "
            "watchlist (#12). 'NEW' on first run or when no previous "
            "briefing exists."
        ),
    )


class CompanyBriefing(LLMOutputBase):
    """Weekly briefing for one company."""

    company: str = Field(description="Company name.")
    overall_summary: str = Field(
        description=(
            "2-3 sentence overview of the company's notable activity during "
            "the briefing period. Use markdown (bold for key terms)."
        )
    )
    domains_active: List[str] = Field(
        default_factory=list,
        description=(
            "Technology domains where the company was active during the "
            "period (e.g., 'Generative AI', 'Quantum Computing')."
        ),
    )
    updates: List[CompanyUpdate] = Field(
        default_factory=list,
        description=(
            "Chronological list of notable updates during the period. "
            "Empty list if no notable activity was found."
        ),
    )
    key_themes: List[str] = Field(
        default_factory=list,
        description=(
            "Short phrases capturing the strategic themes of the week "
            "for this company (e.g., 'doubling down on agents', 'hardware "
            "supply chain push')."
        ),
    )
    sources_used: int = Field(
        default=0,
        description="Number of distinct articles used to build this briefing.",
    )
    momentum: MomentumSnapshot = Field(
        default_factory=MomentumSnapshot,
        description="Momentum score (#8). Computed post-LLM.",
    )
    hiring_signals: HiringSnapshot = Field(
        default_factory=HiringSnapshot,
        description="Hiring-signal snapshot (#31). Computed post-LLM.",
    )


class KeyCompaniesReport(LLMOutputBase):
    """Full weekly briefing across all requested companies."""

    companies_analyzed: List[str] = Field(
        description="Company names analyzed, in input order."
    )
    highlight_domain: str = Field(
        default="",
        description=(
            "Optional user-specified domain to emphasize. Empty string "
            "means cross-domain (no single focus)."
        ),
    )
    period_days: int = Field(
        default=7,
        description="Length of the briefing window in days.",
    )
    period_start: str = Field(
        default="",
        description="Start of the briefing window (ISO date).",
    )
    period_end: str = Field(
        default="",
        description="End of the briefing window (ISO date).",
    )
    cross_company_summary: str = Field(
        default="",
        description=(
            "Markdown summary (4-6 sentences) highlighting the week's most "
            "important moves across all analyzed companies, divergent "
            "strategies, and any notable cross-company themes."
        ),
    )
    briefings: List[CompanyBriefing] = Field(
        default_factory=list,
        description="One briefing per analyzed company.",
    )
    domain_rollup: List[DomainRollupEntry] = Field(
        default_factory=list,
        description=(
            "Cross-domain rollup counts across all briefings (#29). "
            "Populated by the cross-domain aggregator."
        ),
    )
    watchlist_id: str = Field(
        default="",
        description=(
            "Optional watchlist this run was derived from (#15). Empty "
            "when the run was ad-hoc."
        ),
    )
    diff_summary: Optional[dict] = Field(
        default=None,
        description=(
            "Summary of the diff vs the previous run for the same "
            "company set (#12). Keys: previous_tracking_id, "
            "resolved_topics[], new_count, ongoing_count. Null when "
            "this is the first run or no prior run exists."
        ),
    )
