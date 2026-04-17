"""Competitive-overlap matrix (#10).

Given a :class:`CompanyAnalysisReport` with per-company
``technology_findings``, compute, for each ordered pair
``(tech_a, tech_b)`` (``tech_a != tech_b``), how many analyzed
companies have "evidenced activity" in *both* technologies.

Pure function — no LLM cost. A company is considered "active" in a
technology when the matching :class:`CompanyTechFinding` either has
``confidence >= 0.4`` *or* has at least one ``source_url``. This
avoids counting the "no visible activity" stub findings the LLM
emits for empty cells.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Set

from core.llm.output_schemas.analysis_extensions import OverlapCell

if TYPE_CHECKING:  # pragma: no cover
    from core.llm.output_schemas.company_analysis import (
        CompanyAnalysisReport,
        CompanyTechFinding,
    )


_EMPTY_STANCE_TOKENS = {
    "no visible activity",
    "no activity",
    "not applicable",
    "n/a",
    "none",
    "",
}


def _finding_is_active(f: "CompanyTechFinding") -> bool:
    """Return True when the finding represents real evidenced activity."""
    stance_norm = (getattr(f, "stance", "") or "").strip().lower()
    if stance_norm in _EMPTY_STANCE_TOKENS:
        # A "no visible activity" stub is still counted if it somehow
        # carries source URLs — guard below handles that too.
        pass
    has_confidence = (getattr(f, "confidence", 0.0) or 0.0) >= 0.4
    has_sources = bool(getattr(f, "source_urls", None))
    has_products = bool(getattr(f, "specific_products", None))
    if stance_norm in _EMPTY_STANCE_TOKENS and not (
        has_confidence or has_sources or has_products
    ):
        return False
    return has_confidence or has_sources or has_products


def _company_tech_map(
    report: "CompanyAnalysisReport",
) -> Dict[str, Set[str]]:
    """Build {company: set(active technologies)}."""
    out: Dict[str, Set[str]] = {}
    for profile in report.company_profiles or []:
        company = (profile.company or "").strip()
        if not company:
            continue
        active: Set[str] = set()
        for finding in profile.technology_findings or []:
            tech = (finding.technology or "").strip()
            if not tech:
                continue
            if _finding_is_active(finding):
                active.add(tech)
        out[company] = active
    return out


def compute_overlap_matrix(
    report: "CompanyAnalysisReport",
) -> List[OverlapCell]:
    """Produce overlap cells for every ordered (tech_a, tech_b) pair.

    Symmetric pairs (A,B) and (B,A) are emitted separately so the UI
    can render either a triangular or full heatmap without post-
    processing.
    """
    technologies: List[str] = [
        (t or "").strip()
        for t in (report.technologies_analyzed or [])
        if (t or "").strip()
    ]
    if len(technologies) < 2:
        return []

    active_by_company = _company_tech_map(report)
    cells: List[OverlapCell] = []
    for a in technologies:
        for b in technologies:
            if a == b:
                continue
            overlap_companies = sorted(
                c
                for c, techs in active_by_company.items()
                if a in techs and b in techs
            )
            cells.append(
                OverlapCell(
                    technology_a=a,
                    technology_b=b,
                    overlap_count=len(overlap_companies),
                    overlap_companies=overlap_companies,
                )
            )
    return cells


__all__ = ["compute_overlap_matrix"]
