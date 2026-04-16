"""
Pydantic schemas for the Company Analysis feature.

Structure:
- CompanyTechFinding: what one company is doing with one technology
- CompanyProfile: aggregate view of one company across all selected
  technologies, plus strengths and gaps
- ComparativeRow: per-technology leader pick across all companies
- CompanyAnalysisReport: the full report output
"""

from typing import List

from pydantic import BaseModel, Field

from core.llm.output_schemas.base import LLMOutputBase


class CompanyTechFinding(BaseModel):
    """What one company is doing with one specific technology."""

    technology: str = Field(
        description="Technology name — must match one of the radar item names."
    )
    summary: str = Field(
        description=(
            "2-3 sentence summary of what the company is doing with this "
            "technology, grounded in the provided articles."
        )
    )
    specific_products: List[str] = Field(
        default_factory=list,
        description=(
            "Named products or services the company has released that use "
            "this technology. Empty list if none are evidenced."
        ),
    )
    recent_developments: List[str] = Field(
        default_factory=list,
        description=(
            "Recent moves (launches, demos, research, acquisitions) within "
            "the last 6 months. Each item is a short phrase."
        ),
    )
    partnerships: List[str] = Field(
        default_factory=list,
        description="Relevant partners, collaborators, or integrations.",
    )
    investment_signal: str = Field(
        default="",
        description=(
            "Funding, acquisitions, or hiring signals related to this "
            "technology. Empty string if none evidenced."
        ),
    )
    stance: str = Field(
        default="",
        description=(
            "Short verdict on the company's position, e.g. 'heavily "
            "invested', 'exploring', 'defensive', 'no visible activity'."
        ),
    )
    confidence: float = Field(
        default=0.0,
        description=(
            "Confidence in this finding 0.0-1.0 based on source quality "
            "and number of corroborating sources. Use 0.0 when no evidence "
            "was found."
        ),
    )
    source_urls: List[str] = Field(
        default_factory=list,
        description="URLs of articles that informed this finding.",
    )


class CompanyProfile(LLMOutputBase):
    """Aggregate profile of one company across all analyzed technologies."""

    company: str = Field(description="Company name.")
    overall_summary: str = Field(
        description=(
            "3-4 sentences summarizing the company's overall positioning "
            "in the target domain."
        )
    )
    technology_findings: List[CompanyTechFinding] = Field(
        description=(
            "One finding per analyzed technology. Include 'no visible "
            "activity' entries for technologies where no evidence was found."
        )
    )
    strengths: List[str] = Field(
        default_factory=list,
        description="Areas where the company appears to lead or excel.",
    )
    gaps: List[str] = Field(
        default_factory=list,
        description="Areas where the company appears behind or absent.",
    )
    sources_used: int = Field(
        default=0,
        description="Total distinct sources used to build this profile.",
    )


class ComparativeRow(BaseModel):
    """Cross-company comparison for one technology."""

    technology: str = Field(description="Technology name.")
    leader: str = Field(
        description=(
            "Name of the company judged to be leading in this technology "
            "among the analyzed companies. Use 'Unclear' if no clear "
            "leader can be identified."
        )
    )
    rationale: str = Field(
        description="One-sentence rationale for the leader pick."
    )


class CompanyAnalysisReport(LLMOutputBase):
    """Full company analysis output."""

    report_tracking_id: str = Field(
        description="Parent Tech Sensing report tracking ID."
    )
    domain: str = Field(description="Domain inherited from parent report.")
    companies_analyzed: List[str] = Field(
        description="Company names analyzed, in input order."
    )
    technologies_analyzed: List[str] = Field(
        description="Technology names analyzed, in the order selected."
    )
    executive_summary: str = Field(
        description=(
            "4-6 sentence cross-company summary highlighting divergent "
            "strategies and notable patterns."
        )
    )
    company_profiles: List[CompanyProfile] = Field(
        description="One profile per analyzed company."
    )
    comparative_matrix: List[ComparativeRow] = Field(
        description="One row per analyzed technology."
    )
