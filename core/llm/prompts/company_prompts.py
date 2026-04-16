"""
LLM prompts for the Company Analysis feature.

Two prompts:
- company_profile_prompt: per-company synthesis across multiple technologies
- company_comparative_prompt: cross-company comparison once profiles exist
"""

import json

from core.llm.output_schemas.company_analysis import (
    CompanyAnalysisReport,
    CompanyProfile,
)


def company_profile_prompt(
    company: str,
    domain: str,
    technologies: list[str],
    articles_text: str,
    date_range: str = "",
) -> list[dict]:
    """Build a prompt to synthesize one company's positioning across techs."""
    schema_json = json.dumps(CompanyProfile.model_json_schema(), indent=2)
    tech_list = ", ".join(technologies)

    recency_block = ""
    if date_range:
        recency_block = (
            "RECENCY RULES:\n"
            f"- The primary date window is: {date_range}.\n"
            "- Articles older than 6 months from today should be used only as "
            "context, not as evidence of current activity.\n"
            "- If an article describes an old product launch as if it were new, "
            "ignore it or note it as legacy context.\n"
            "- Prioritize developments from the last 3 months in "
            "recent_developments.\n\n"
        )

    return [
        {
            "role": "system",
            "parts": (
                "You are a senior technology analyst profiling a company's "
                f"activity in the '{domain}' space.\n\n"
                f"TARGET COMPANY: {company}\n"
                f"DOMAIN: {domain}\n"
                f"TECHNOLOGIES TO ASSESS: {tech_list}\n\n"
                "Your task: produce a CompanyProfile that describes what "
                f"{company} is doing with each of the listed technologies, "
                "based ONLY on the provided articles. Include one "
                "technology_findings entry for EACH listed technology — if "
                "no evidence is found for a given technology, still include "
                "an entry with stance='no visible activity' and "
                "confidence=0.0.\n\n"
                "GROUNDING RULES:\n"
                f"- Every claim must be traceable to the articles provided.\n"
                "- Do NOT fabricate product names, partnership names, or "
                "investment figures.\n"
                f"- Only mention products, partners, or investments that are "
                f"explicitly attributed to {company} in the articles.\n"
                "- If an article talks about a DIFFERENT company, do not use "
                f"it as evidence for {company}.\n"
                "- Populate source_urls with URLs of articles that directly "
                "support each finding.\n\n"
                + recency_block
                + "CONFIDENCE SCORING:\n"
                "- 0.0 = no evidence found\n"
                "- 0.1-0.3 = single weak source or indirect mention\n"
                "- 0.4-0.6 = one strong source or multiple weak sources\n"
                "- 0.7-0.9 = multiple corroborating strong sources\n"
                "- 1.0 = reserved for official company announcements with "
                "multiple independent confirmations\n\n"
                "OUTPUT REQUIREMENT:\n"
                "Return ONLY a valid JSON object matching the schema below. "
                "No markdown fences, no commentary.\n\n"
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
                f"DOMAIN: {domain}\n"
                f"TECHNOLOGIES: {tech_list}\n\n"
                f"ARTICLES:\n\n{articles_text}\n\n"
                f"Produce the CompanyProfile for {company}. Return ONLY "
                "valid JSON."
            ),
        },
    ]


def company_comparative_prompt(
    report_tracking_id: str,
    domain: str,
    companies: list[str],
    technologies: list[str],
    profiles_json: str,
) -> list[dict]:
    """Build a prompt for cross-company comparison given existing profiles."""
    schema_json = json.dumps(
        CompanyAnalysisReport.model_json_schema(), indent=2
    )

    return [
        {
            "role": "system",
            "parts": (
                "You are a senior technology strategist synthesizing a "
                "comparative analysis across multiple companies in the "
                f"'{domain}' space.\n\n"
                "You will receive one CompanyProfile per analyzed company. "
                "Your task: produce a CompanyAnalysisReport containing:\n"
                "1. An executive summary (4-6 sentences) highlighting "
                "divergent strategies, notable leaders, and market patterns\n"
                "2. A comparative_matrix with one row per technology, "
                "picking the leader and giving a one-sentence rationale\n"
                "3. The original company_profiles list, unchanged\n\n"
                "RULES:\n"
                f"- Use report_tracking_id: {report_tracking_id}\n"
                f"- Use domain: {domain}\n"
                f"- companies_analyzed MUST be: {companies}\n"
                f"- technologies_analyzed MUST be: {technologies}\n"
                "- For each technology in comparative_matrix, leader MUST be "
                "one of the analyzed companies, or 'Unclear' if no company "
                "has clear leadership based on the profiles.\n"
                "- company_profiles in the output MUST be the EXACT profiles "
                "provided, not re-synthesized. Copy them verbatim.\n"
                "- Use markdown formatting in executive_summary (bold for "
                "company names, bullet points for key takeaways).\n\n"
                "OUTPUT REQUIREMENT:\n"
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
                f"COMPANY PROFILES:\n\n{profiles_json}\n\n"
                "Produce the comparative CompanyAnalysisReport. Return ONLY "
                "valid JSON."
            ),
        },
    ]
