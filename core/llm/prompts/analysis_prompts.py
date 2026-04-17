"""Prompts for Phase 3 & 6 secondary analytical passes.

These prompts are NOT the main report-writers — they run as small
structured-output passes over an already-generated
:class:`CompanyAnalysisReport` to extract cross-cutting signals
(themes, contradictions, hallucinations, opportunity/threat).

Each helper returns the list-of-messages shape expected by
``invoke_llm``.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, List, Sequence

from pydantic import BaseModel, Field

from core.llm.output_schemas.analysis_extensions import (
    ContradictionFlag,
    OpportunityThreatFraming,
    ThemeCluster,
    UnsupportedClaim,
)

if TYPE_CHECKING:  # pragma: no cover
    from core.llm.output_schemas.company_analysis import (
        CompanyAnalysisReport,
        CompanyProfile,
    )


# ──────────────────────────────────────────────────────────────
# Output envelopes — Gemini-style structured output requires the
# top-level schema to be an object, not a list.
# ──────────────────────────────────────────────────────────────


class ThemeClusterList(BaseModel):
    themes: List[ThemeCluster] = Field(default_factory=list)


class ContradictionList(BaseModel):
    contradictions: List[ContradictionFlag] = Field(default_factory=list)


class UnsupportedClaimList(BaseModel):
    unsupported: List[UnsupportedClaim] = Field(default_factory=list)


class SimilarCompanies(BaseModel):
    companies: List[str] = Field(default_factory=list)
    rationale: str = ""


# ──────────────────────────────────────────────────────────────
# #11 — Strategic themes across all analyzed companies
# ──────────────────────────────────────────────────────────────


def strategic_themes_prompt(
    report: "CompanyAnalysisReport", max_themes: int = 6
) -> list[dict]:
    """Extract 3–6 cross-company strategic themes.

    Input: the comparative matrix + condensed per-company tech findings.
    Output: :class:`ThemeClusterList`.
    """
    condensed = []
    for prof in report.company_profiles or []:
        findings = []
        for f in (prof.technology_findings or [])[:10]:
            findings.append(
                {
                    "technology": f.technology,
                    "stance": f.stance,
                    "summary": f.summary[:300],
                    "products": f.specific_products[:3],
                    "developments": (f.recent_developments or [])[:3],
                }
            )
        condensed.append(
            {
                "company": prof.company,
                "overall_summary": (prof.overall_summary or "")[:400],
                "findings": findings,
            }
        )
    payload = json.dumps(
        {
            "domain": report.domain,
            "companies": report.companies_analyzed,
            "technologies": report.technologies_analyzed,
            "profiles": condensed,
        },
        indent=2,
    )
    schema_json = json.dumps(ThemeClusterList.model_json_schema(), indent=2)

    return [
        {
            "role": "system",
            "parts": (
                "You extract cross-company STRATEGIC THEMES from a set of "
                "company analysis profiles.\n\n"
                f"Return at most {max_themes} distinct themes. A theme must:\n"
                "- Span 2 or more companies (never single-company).\n"
                "- Be actionable / interpretable (NOT just a restatement of "
                "a technology name).\n"
                "- Cite 2+ companies in ``companies`` and name the underlying "
                "technologies in ``technologies``.\n"
                "- Have a ``rationale`` that explicitly mentions the "
                "company names it spans.\n\n"
                "Output schema:\n"
                f"```json\n{schema_json}\n```"
            ),
        },
        {
            "role": "user",
            "parts": (
                "Input profiles (condensed):\n\n"
                f"{payload}\n\n"
                "Identify the cross-company strategic themes."
            ),
        },
    ]


# ──────────────────────────────────────────────────────────────
# #26 — Contradiction detection
# ──────────────────────────────────────────────────────────────


def contradiction_prompt(
    company: str,
    tech: str,
    article_bundle: str,
) -> list[dict]:
    """Find conflicting claims across a cluster of articles."""
    schema_json = json.dumps(ContradictionList.model_json_schema(), indent=2)
    return [
        {
            "role": "system",
            "parts": (
                "You detect CONTRADICTIONS between news articles about "
                "the SAME event.\n\n"
                "Examples of contradictions: different release dates, "
                "different funding amounts, different model parameter "
                "counts, conflicting executive quotes.\n"
                "Ignore stylistic rewording. Only flag factual conflicts.\n\n"
                "If there are no contradictions, return an empty list.\n\n"
                "Output schema:\n"
                f"```json\n{schema_json}\n```"
            ),
        },
        {
            "role": "user",
            "parts": (
                f"COMPANY: {company}\nTECHNOLOGY: {tech}\n\n"
                f"Articles:\n\n{article_bundle}"
            ),
        },
    ]


# ──────────────────────────────────────────────────────────────
# #27 — Hallucination probe
# ──────────────────────────────────────────────────────────────


def hallucination_probe_prompt(
    profile_json: str,
    articles_digest: str,
) -> list[dict]:
    """Find claims in a generated profile that are NOT supported by articles."""
    schema_json = json.dumps(
        UnsupportedClaimList.model_json_schema(), indent=2
    )
    return [
        {
            "role": "system",
            "parts": (
                "You verify claims in a COMPANY PROFILE against the "
                "ARTICLES that were used to produce it.\n\n"
                "For each claim, check whether the articles support it. "
                "List only claims that are NOT supported (i.e. they would "
                "qualify as hallucinations). For each, suggest whether to "
                "drop, flag, or rewrite.\n\n"
                "If every claim is supported, return an empty list.\n\n"
                "Output schema:\n"
                f"```json\n{schema_json}\n```"
            ),
        },
        {
            "role": "user",
            "parts": (
                "PROFILE TO CHECK:\n"
                f"{profile_json}\n\n"
                "SUPPORTING ARTICLES:\n"
                f"{articles_digest}"
            ),
        },
    ]


# ──────────────────────────────────────────────────────────────
# #33 — Opportunity / threat framing
# ──────────────────────────────────────────────────────────────


def opportunity_threat_prompt(
    report: "CompanyAnalysisReport", org_context: str
) -> list[dict]:
    """Produce opportunity/threat framing relative to the user's org."""
    schema_json = json.dumps(
        OpportunityThreatFraming.model_json_schema(), indent=2
    )
    summary = {
        "executive_summary": report.executive_summary,
        "companies": report.companies_analyzed,
        "technologies": report.technologies_analyzed,
        "comparative": [
            {
                "technology": r.technology,
                "leader": r.leader,
                "rationale": r.rationale,
            }
            for r in (report.comparative_matrix or [])
        ],
        "themes": [t.theme for t in (report.strategic_themes or [])],
    }
    return [
        {
            "role": "system",
            "parts": (
                "You frame a competitive landscape as OPPORTUNITIES and "
                "THREATS from the point of view of the USER'S ORGANIZATION.\n\n"
                "Distinct outputs:\n"
                "- opportunities: where the user's org can win or capitalize.\n"
                "- threats: where competitors are pulling ahead or changing "
                "the market in ways that risk the user's org.\n"
                "- recommended_actions: 3-5 concrete next steps.\n\n"
                "Always populate ``org_context_used`` with a short label "
                "describing the org.\n\n"
                "Output schema:\n"
                f"```json\n{schema_json}\n```"
            ),
        },
        {
            "role": "user",
            "parts": (
                f"USER ORG CONTEXT:\n{org_context}\n\n"
                "LANDSCAPE SUMMARY:\n"
                + json.dumps(summary, indent=2)
            ),
        },
    ]


# ──────────────────────────────────────────────────────────────
# #32 — Similar companies
# ──────────────────────────────────────────────────────────────


def similar_companies_prompt(
    seed_company: str,
    domain: str,
    existing_companies: Sequence[str] = (),
    max_suggestions: int = 5,
) -> list[dict]:
    """Suggest peer companies similar to ``seed_company`` in ``domain``."""
    schema_json = json.dumps(SimilarCompanies.model_json_schema(), indent=2)
    already = ", ".join(existing_companies) or "(none)"
    return [
        {
            "role": "system",
            "parts": (
                "Suggest peer / competitor companies similar to the seed "
                "company in the specified domain.\n\n"
                f"Return up to {max_suggestions} DISTINCT companies. Do NOT "
                "include any companies already in EXISTING LIST.\n"
                "Prefer well-known, public-facing companies that have "
                "demonstrated activity in the domain.\n\n"
                "Output schema:\n"
                f"```json\n{schema_json}\n```"
            ),
        },
        {
            "role": "user",
            "parts": (
                f"SEED COMPANY: {seed_company}\n"
                f"DOMAIN: {domain}\n"
                f"EXISTING LIST: {already}\n"
            ),
        },
    ]


__all__ = [
    "ThemeClusterList",
    "ContradictionList",
    "UnsupportedClaimList",
    "SimilarCompanies",
    "strategic_themes_prompt",
    "contradiction_prompt",
    "hallucination_probe_prompt",
    "opportunity_threat_prompt",
    "similar_companies_prompt",
]
