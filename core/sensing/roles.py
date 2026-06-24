"""
Role specifications — the single source of truth for how a report is tailored to
the reader's stakeholder role.

Each role maps to a structured spec (emphasis, horizon, reading level, metrics,
recommendation style). That spec is rendered into:

  - ``build_role_directive(role)`` — a structured directive injected into report
    synthesis (core / radar / insights / details) via custom_requirements.
  - ``role_audience(role)`` — the Bottom Line audience label.
  - ``role_boost_terms(role)`` / ``role_boost_sources(role)`` — signals used to
    re-rank candidate articles toward what this role cares about.

This replaces the older flat ROLE_PROMPTS / ROLE_AUDIENCE dictionaries.
"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class RoleSpec:
    title: str                       # e.g. "Engineering Lead / Architect"
    label: str                       # Bottom Line audience label, e.g. "an engineering lead / architect"
    emphasis: str = ""
    horizon: str = ""
    depth: str = ""                  # reading level / jargon
    metrics: str = ""                # which metrics/lens to foreground
    recommendation_style: str = ""   # briefing type for recommendations
    boost_terms: List[str] = field(default_factory=list)    # ranking keywords
    boost_sources: List[str] = field(default_factory=list)  # ranking source names


_GENERAL = RoleSpec(title="General reader", label="the reader")

ROLE_SPECS = {
    "cto": RoleSpec(
        title="Chief Technology Officer",
        label="a CTO / technology strategy leader",
        emphasis="strategic implications, competitive positioning, build-vs-buy decisions, "
                 "technology bets, and organizational readiness",
        horizon="12-24 months",
        depth="concise and business-oriented; explain technical terms in terms of business impact",
        metrics="business impact, competitive risk, cost/ROI, and adoption signals",
        recommendation_style="frame recommendations as strategic decisions/bets with clear "
                             "trade-offs (build vs buy vs wait) and resourcing implications",
        boost_terms=["strategy", "competitive", "acquisition", "funding", "partnership",
                     "enterprise", "roadmap", "investment", "platform"],
    ),
    "engineering_lead": RoleSpec(
        title="Engineering Lead / Architect",
        label="an engineering lead / architect",
        emphasis="technical architecture, integration complexity, migration paths, "
                 "team skill requirements, and scalability/reliability",
        horizon="3-12 months",
        depth="technically precise; assume an engineering audience",
        metrics="integration effort, maturity/stability, performance characteristics, "
                "and operational cost",
        recommendation_style="frame recommendations as adoption/architecture decisions with "
                             "effort, migration risk, and prerequisites",
        boost_terms=["architecture", "integration", "scalability", "migration", "infrastructure",
                     "framework", "platform", "reliability", "latency", "throughput", "kubernetes"],
    ),
    "developer": RoleSpec(
        title="Software Developer",
        label="a software developer / builder",
        emphasis="APIs, SDKs, libraries, documentation maturity, code examples, ecosystem, "
                 "and hands-on evaluation",
        horizon="now to 3 months",
        depth="highly technical and practical; concrete and example-driven",
        metrics="API quality, documentation maturity, benchmarks, integration effort, "
                "and community traction",
        recommendation_style="frame recommendations as concrete hands-on next steps "
                             "(what to try, prototype, or read this week)",
        boost_terms=["release", "open source", "open-source", "sdk", "api", "library",
                     "github", "framework", "toolkit", "tutorial", "benchmark"],
        boost_sources=["GitHub", "Hacker News"],
    ),
    "product_manager": RoleSpec(
        title="Product Manager",
        label="a product manager",
        emphasis="user impact, market differentiation, competitor adoption, time-to-value, "
                 "and feature parity",
        horizon="3-9 months",
        depth="balanced; product/market framing over deep technical detail",
        metrics="user/market impact, competitor moves, time-to-value, and differentiation",
        recommendation_style="frame recommendations as product opportunities/risks with user "
                             "and market rationale",
        boost_terms=["launch", "feature", "user", "customer", "adoption", "pricing",
                     "market", "competitor", "ux", "partnership"],
    ),
    "analyst": RoleSpec(
        title="Technology Analyst",
        label="a technology analyst",
        emphasis="evidence and data points, trend trajectories, source quality, comparative "
                 "analysis, and market sizing",
        horizon="6-18 months",
        depth="analytical and evidence-led; cite specifics and quantify where possible",
        metrics="quantitative data, growth/adoption rates, and confidence/source quality",
        recommendation_style="frame conclusions as evidence-backed assessments with confidence "
                             "levels and supporting data",
        boost_terms=["benchmark", "study", "paper", "research", "data", "survey",
                     "report", "growth", "adoption", "trend", "analysis"],
        boost_sources=["arXiv", "Semantic Scholar"],
    ),
    "exec": RoleSpec(
        title="Business Executive",
        label="a business executive",
        emphasis="business impact, market shifts, funding/M&A, competitive dynamics, and risk",
        horizon="12-24 months",
        depth="plain-language and non-technical; lead with the 'so what' for the business",
        metrics="revenue/cost impact, market movement, and competitive risk",
        recommendation_style="frame recommendations as business decisions/options with clear "
                             "pros, cons, and a recommended course",
        boost_terms=["funding", "acquisition", "raises", "ipo", "revenue", "market",
                     "partnership", "merger", "valuation", "enterprise"],
    ),
    "general": _GENERAL,
}


def _spec(role: str) -> RoleSpec:
    return ROLE_SPECS.get((role or "").strip().lower(), _GENERAL)


def role_audience(role: str) -> str:
    """Bottom Line audience label for the role."""
    return _spec(role).label


def build_role_directive(role: str) -> str:
    """Structured role directive injected into report synthesis. Returns '' for
    the general role (no role steering)."""
    s = _spec(role)
    if not s.emphasis:
        return ""
    return (
        f"AUDIENCE: {s.title}. Emphasize {s.emphasis}. "
        f"Time horizon: {s.horizon}. "
        f"Reading level: {s.depth}. "
        f"Foreground metrics related to {s.metrics}. "
        f"Recommendations: {s.recommendation_style}. "
        "Structure for this reader using BLUF — lead with the conclusion, then support "
        "it; foreground the 3-4 most material points and keep the rest concise."
    )


def role_boost_terms(role: str) -> List[str]:
    return _spec(role).boost_terms


def role_boost_sources(role: str) -> List[str]:
    return _spec(role).boost_sources


def is_role_tailored(role: str) -> bool:
    """True when the role has an actual tailoring spec (i.e. not general/unknown)."""
    return bool(_spec(role).emphasis)
