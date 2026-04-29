"""
LLM prompts for the Key Companies feature.

Two prompts:
- company_weekly_brief_prompt: per-company last-week synthesis
- key_companies_cross_prompt: cross-company summary once briefings exist
"""

import json
from datetime import datetime

from core.llm.output_schemas.key_companies import (
    CompanyBriefing,
    KeyCompaniesReport,
    UPDATE_CATEGORIES,
)
from core.llm.prompts.shared import tense_rules_block


def company_weekly_brief_prompt(
    company: str,
    articles_text: str,
    period_start: str,
    period_end: str,
    highlight_domain: str = "",
) -> list[dict]:
    """Build a prompt to synthesize one company's weekly briefing."""
    schema_json = json.dumps(CompanyBriefing.model_json_schema(), indent=2)
    categories = ", ".join(f"'{c}'" for c in UPDATE_CATEGORIES)

    domain_block = (
        f"HIGHLIGHT DOMAIN: {highlight_domain}. Prioritize updates in this "
        "domain, but do NOT suppress genuinely important updates in other "
        "domains — the user still wants cross-domain coverage.\n\n"
        if highlight_domain
        else "SCOPE: This is a CROSS-DOMAIN briefing. Cover all technology "
        "areas where the company was active (e.g., AI, quantum, chips, "
        "biotech, robotics, security, climate tech).\n\n"
    )

    return [
        {
            "role": "system",
            "parts": (
                "You are a senior technology analyst producing a WEEKLY "
                f"briefing for {company}.\n\n"
                f"TARGET COMPANY: {company}\n"
                f"BRIEFING WINDOW: {period_start} → {period_end}\n\n"
                + domain_block
                + "Your task: extract notable technical and business "
                f"updates about {company} during the briefing window. "
                "Each update should be a concrete, evidenced event — "
                "product launches, funding rounds, partnerships, "
                "acquisitions, research papers, technical announcements, "
                "regulatory actions, or key personnel moves.\n\n"
                "GROUNDING RULES:\n"
                f"- Every update must be traceable to one of the provided "
                f"articles about {company}.\n"
                "- Do NOT fabricate product names, partners, funding "
                "amounts, or personnel.\n"
                "- If an article is clearly about a DIFFERENT company "
                f"(not {company}), ignore it.\n"
                "- If no notable activity was found, return an empty "
                "updates list and state that plainly in overall_summary.\n\n"
                "RECENCY RULES (CRITICAL — enforce strictly):\n"
                f"- Today's date: {datetime.now().strftime('%B %d, %Y')}.\n"
                f"- Only include events dated within the window "
                f"({period_start} to {period_end}).\n"
                "- If an article is older but announces something new this "
                "week, include the new event (not the old context).\n"
                "- If you cannot confidently date an event to within the "
                "window, DROP it.\n"
                "- Do NOT include product launches, funding rounds, or "
                "announcements from before the window period — even if the "
                "article mentions them as background.\n"
                "- Each update's 'date' field MUST be a YYYY-MM-DD date "
                f"between {period_start} and {period_end}.\n\n"
                + tense_rules_block()
                + "CATEGORIZATION:\n"
                f"- Each update's category MUST be exactly one of: "
                f"{categories}.\n"
                "- 'Technical' is for architectural/capability announcements "
                "that are not full product launches (e.g., a new model "
                "checkpoint, infra upgrade, benchmark).\n"
                "- 'Other' is a last resort.\n\n"
                "QUANTITATIVE DATA:\n"
                "- For each update, extract 1-3 quantitative facts into "
                "quantitative_highlights — revenue figures, funding amounts, "
                "benchmark scores, user counts, performance metrics, growth "
                "percentages, market share numbers.\n"
                "- Each item must cite the concrete number and context, e.g. "
                "'$6.5B revenue in Q1 2026, up 35% YoY' or "
                "'Achieves 94.2% on MMLU, surpassing GPT-4o'.\n"
                "- Only include numbers explicitly stated in the articles.\n"
                "- Return an empty list if no quantitative data is available.\n\n"
                "STRATEGIC INTENT & IMPACT:\n"
                "- For each update, assess the company's strategic_intent — "
                "the likely strategic motivation behind the move:\n"
                "  * 'defensive' — responding to competitor pressure or "
                "protecting market position\n"
                "  * 'offensive' — proactively attacking new markets or "
                "undermining competitors\n"
                "  * 'expansion' — entering new domains, geographies, or "
                "customer segments\n"
                "  * 'cost_optimization' — reducing costs, improving "
                "efficiency, or restructuring\n"
                "  * 'ecosystem_building' — growing platform/partner/developer "
                "ecosystem\n"
                "  * 'talent' — acquiring talent, key hires, or team building\n"
                "  * Leave empty if intent is unclear or not applicable.\n"
                "- For each update, assess impact: 'high', 'medium', or 'low':\n"
                "  * 'high' — market-shifting move, >$1B scale, or major "
                "competitive disruption\n"
                "  * 'medium' — meaningful competitive move with clear "
                "industry relevance\n"
                "  * 'low' — incremental, niche, or limited immediate impact\n\n"
                "DOMAIN TAGGING:\n"
                "- Populate each update's `domain` field with the primary "
                "technology domain it touches (e.g., 'Generative AI', "
                "'Quantum Computing', 'Robotics', 'Semiconductors', "
                "'Cybersecurity', 'Biotech', 'Cloud', 'Autonomous "
                "Vehicles'). Use empty string if not applicable.\n"
                "- domains_active at the briefing level is the set of "
                "unique non-empty domains across the updates.\n\n"
                "OUTPUT REQUIREMENT:\n"
                "Return ONLY a valid JSON object matching the schema "
                "below. No markdown fences, no commentary outside JSON.\n\n"
                f"OUTPUT SCHEMA:\n```json\n{schema_json}\n```\n\n"
                "OUTPUT RULES:\n"
                "- Valid JSON only, no markdown fencing.\n"
                "- Newlines inside string values MUST be written as \\n.\n"
                '- Double quotes inside string values MUST be escaped as \\".\n'
            ),
        },
        {
            "role": "user",
            "parts": (
                f"COMPANY: {company}\n"
                f"WINDOW: {period_start} → {period_end}\n\n"
                f"ARTICLES:\n\n{articles_text}\n\n"
                f"Produce the weekly CompanyBriefing for {company}. "
                "Return ONLY valid JSON."
            ),
        },
    ]


def key_companies_cross_prompt(
    briefings_json: str,
    companies: list[str],
    period_start: str,
    period_end: str,
    highlight_domain: str = "",
) -> list[dict]:
    """Build a prompt for the cross-company weekly summary."""
    schema_json = json.dumps(KeyCompaniesReport.model_json_schema(), indent=2)

    return [
        {
            "role": "system",
            "parts": (
                "You are a senior technology strategist producing a "
                "cross-company WEEKLY digest.\n\n"
                f"BRIEFING WINDOW: {period_start} → {period_end}\n"
                f"COMPANIES: {', '.join(companies)}\n"
                + (
                    f"HIGHLIGHT DOMAIN: {highlight_domain}\n\n"
                    if highlight_domain
                    else "SCOPE: Cross-domain — cover all technology areas.\n\n"
                )
                + "You will receive one CompanyBriefing per analyzed "
                "company. Your task: produce a KeyCompaniesReport "
                "containing:\n"
                "1. cross_company_summary — a 4-6 sentence markdown digest "
                "of the week's most important moves across all companies. "
                "Use bold for company names, call out divergent strategies, "
                "and flag any cross-company themes (e.g., 'three of five "
                "companies announced agent platforms this week').\n"
                "2. topic_highlights — 4-8 at-a-glance topic highlights "
                "summarizing the most important themes across all companies. "
                "Each has a short topic label (2-4 words like 'Agentic AI', "
                "'Chip Wars', 'Enterprise Cloud') and a 1-2 sentence update. "
                "Pick topics that span multiple companies or represent the "
                "highest-impact developments. Keep domain-agnostic.\n"
                "3. competitive_matrix — competitive intelligence with:\n"
                "   a) domain_grid: For each technology domain that had "
                "activity this week, list which companies are active, who "
                "leads, and a 1-sentence competitive summary.\n"
                "   b) head_to_head: 2-5 direct comparisons between pairs "
                "of companies competing in the same domain. Include the "
                "overlapping domain, a 2-3 sentence comparison, and which "
                "company has the edge (if discernible). Focus on the most "
                "interesting rivalries.\n"
                "4. The original briefings list, preserved verbatim.\n\n"
                "RULES:\n"
                f"- companies_analyzed MUST be exactly: {companies}\n"
                f"- period_start='{period_start}', "
                f"period_end='{period_end}'\n"
                f"- highlight_domain='{highlight_domain}'\n"
                "- briefings MUST be the EXACT briefings provided, copied "
                "verbatim — do not re-synthesize them.\n"
                "- Use markdown in cross_company_summary (bullets OK).\n"
                "- topic_highlights and competitive_matrix are NEW analysis "
                "you produce — they are NOT copied from briefings.\n\n"
                + tense_rules_block()
                + "OUTPUT REQUIREMENT:\n"
                "Return ONLY a valid JSON object matching the schema below.\n\n"
                f"OUTPUT SCHEMA:\n```json\n{schema_json}\n```\n\n"
                "OUTPUT RULES:\n"
                "- Valid JSON only, no markdown fencing.\n"
                "- Newlines inside string values MUST be written as \\n.\n"
                '- Double quotes inside string values MUST be escaped as \\".\n'
            ),
        },
        {
            "role": "user",
            "parts": (
                f"COMPANY BRIEFINGS:\n\n{briefings_json}\n\n"
                "Produce the cross-company KeyCompaniesReport. Return "
                "ONLY valid JSON."
            ),
        },
    ]
