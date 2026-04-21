"""
Report verifier — filters off-topic content from the generated report.

Uses a lightweight LLM call to check each radar item, market signal, and trend
against the user's specific domain/topic. Removes items that are only tangentially
related (e.g., general AI news when the user asked about "World Models").
"""

import json
import logging
import time
from typing import List

from pydantic import BaseModel, Field

from core.constants import GPU_SENSING_CLASSIFY_LLM
from core.llm.client import invoke_llm
from core.llm.output_schemas.base import LLMOutputBase
from core.llm.output_schemas.sensing_outputs import TechSensingReport

logger = logging.getLogger("sensing.verifier")


class VerifiedItems(LLMOutputBase):
    """LLM output: lists of item names/titles that are on-topic + attribution warnings."""

    relevant_radar_items: List[str] = Field(
        description="Names of radar items that are directly relevant to the specific domain/topic."
    )
    relevant_market_signals: List[str] = Field(
        description="Company names of market signals that are directly relevant to the specific domain/topic."
    )
    relevant_trends: List[str] = Field(
        description="Names of trends that are directly relevant to the specific domain/topic."
    )
    attribution_warnings: List[str] = Field(
        default_factory=list,
        description=(
            "Warnings about potential misattributions. Format: "
            "'technology_name: entity_to_remove | reason'. "
            "E.g., 'TurboQuant: Google | only published research paper, did not release implementation'."
        ),
    )


async def verify_report(
    report: TechSensingReport,
    domain: str,
    must_include: list[str] | None = None,
    dont_include: list[str] | None = None,
    custom_requirements: str = "",
) -> TechSensingReport:
    """
    Verify report content against the user's domain and filter off-topic items.
    Returns a new report with only relevant items kept.
    """
    verify_start = time.time()

    # Build a compact summary of all items for the verifier
    radar_names = [item.name for item in report.radar_items]
    signal_companies = [s.company_or_player for s in report.market_signals]
    trend_names = [t.trend_name for t in report.key_trends]

    # Build key_players lookup from radar_item_details
    detail_key_players = {
        d.technology_name: d.key_players
        for d in report.radar_item_details
    }

    items_summary = {
        "radar_items": [
            {
                "name": item.name,
                "description": item.description,
                "key_players": detail_key_players.get(item.name, []),
            }
            for item in report.radar_items
        ],
        "market_signals": [
            {"company": s.company_or_player, "signal": s.signal}
            for s in report.market_signals
        ],
        "trends": [
            {"name": t.trend_name, "description": t.description}
            for t in report.key_trends
        ],
    }

    must_str = f"\nMust-include keywords: {', '.join(must_include)}" if must_include else ""
    dont_str = f"\nDon't-include keywords: {', '.join(dont_include)}" if dont_include else ""
    custom_req_str = ""
    if custom_requirements:
        custom_req_str = (
            f"\nUSER FOCUS REQUIREMENTS (MANDATORY):\n"
            f"The user specified: {custom_requirements}\n"
            "Items aligning with these requirements should be RETAINED even if "
            "their broad domain relevance is moderate. Items that contradict "
            "these requirements should be EXCLUDED.\n"
        )

    prompt = [
        {
            "role": "system",
            "parts": (
                f"You are a relevance checker for a tech sensing report about '{domain}'.\n\n"
                "Your task is to review each item and determine if it is DIRECTLY relevant "
                f"to the specific topic of '{domain}'.\n\n"
                "STRICT RELEVANCE CRITERIA:\n"
                f"- Items must be specifically about or closely related to '{domain}'\n"
                "- General industry news that only tangentially mentions the domain should be EXCLUDED\n"
                "- Company announcements that are about other topics (not the domain) should be EXCLUDED\n"
                "- Broad AI/tech news that doesn't specifically relate to the domain should be EXCLUDED\n"
                "- Technologies from OTHER domains (e.g., general-purpose LLMs like GPT-4/Gemini/Claude, "
                "cryptocurrency, cloud platforms) should be EXCLUDED unless they are specifically "
                f"designed for or applied to '{domain}'\n"
                f"- If '{domain}' is a specific sub-topic (e.g., 'World Models', 'Graph Neural Networks'), "
                "do NOT include general parent-topic items unless they directly discuss the sub-topic\n\n"
                "SPECIFICITY FILTER (radar items only):\n"
                "- EXCLUDE radar items that are company/organization names\n"
                "- EXCLUDE radar items that are generic product families without version specifics\n"
                "- EXCLUDE radar items that are overly broad categories or the domain name itself\n"
                f"- ONLY keep radar items that name a SPECIFIC technology, model, technique, tool, or framework within {domain}\n\n"
                "RECENCY FILTER (radar items only):\n"
                "- EXCLUDE radar items for technologies that are older than 6 months and have "
                "NOT been significantly updated recently\n"
                "- Legacy technologies mentioned only as historical context or comparison should be EXCLUDED\n"
                + must_str + dont_str + custom_req_str + "\n\n"
                "ATTRIBUTION CHECK:\n"
                "- For each radar item, review key_players against its description.\n"
                "- Flag cases where a company is listed as a key_player but the description "
                "only mentions them publishing a research paper, NOT building or releasing the technology.\n"
                "- Flag cases where community/open-source implementations are attributed to "
                "the research paper's author instead of the actual implementer.\n"
                "- Format each warning as: 'technology_name: entity_to_remove | reason'\n"
                "- E.g., 'TurboQuant: Google | only published research paper, did not release implementation'\n\n"
                "OUTPUT RULES:\n"
                "- Return ONLY a valid JSON object with keys: relevant_radar_items, "
                "relevant_signals, relevant_trends, attribution_warnings.\n"
                "- Do NOT include schema definitions, $defs, $ref, properties, or type metadata.\n"
                "- Output must be valid JSON only.\n"
                "- List ONLY the names/companies of items that pass the relevance check.\n"
                "- Be strict — when in doubt, exclude the item.\n"
            ),
        },
        {
            "role": "user",
            "parts": (
                f"DOMAIN: {domain}\n\n"
                f"ITEMS TO VERIFY:\n{json.dumps(items_summary, indent=2, ensure_ascii=False)}\n\n"
                "Return ONLY the names of items that are directly relevant. Be strict."
            ),
        },
    ]

    try:
        logger.info(
            f"Verifying report relevance: {len(radar_names)} radar items, "
            f"{len(signal_companies)} signals, {len(trend_names)} trends"
        )

        result = await invoke_llm(
            gpu_model=GPU_SENSING_CLASSIFY_LLM.model,
            response_schema=VerifiedItems,
            contents=prompt,
            port=GPU_SENSING_CLASSIFY_LLM.port,
        )

        verified = VerifiedItems.model_validate(result)

        # Filter report items
        relevant_radar = set(verified.relevant_radar_items)
        relevant_signals = set(verified.relevant_market_signals)
        relevant_trends = set(verified.relevant_trends)

        orig_radar = len(report.radar_items)
        orig_signals = len(report.market_signals)
        orig_trends = len(report.key_trends)

        # Filter radar items and their details
        report.radar_items = [
            item for item in report.radar_items if item.name in relevant_radar
        ]
        report.radar_item_details = [
            item for item in report.radar_item_details
            if item.technology_name in relevant_radar
        ]

        # Filter market signals
        report.market_signals = [
            s for s in report.market_signals
            if s.company_or_player in relevant_signals
        ]

        # Filter trends
        report.key_trends = [
            t for t in report.key_trends if t.trend_name in relevant_trends
        ]

        # Filter notable articles: keep only those whose technology matches
        if report.notable_articles:
            report.notable_articles = [
                a for a in report.notable_articles
                if a.technology_name in relevant_radar
            ]

        # Apply attribution warnings — remove misattributed key_players
        if verified.attribution_warnings:
            for warning in verified.attribution_warnings:
                logger.warning(f"Attribution warning: {warning}")
                # Parse "technology_name: entity_to_remove | reason"
                if ":" in warning and "|" in warning:
                    tech_part, rest = warning.split(":", 1)
                    entity_part = rest.split("|", 1)[0].strip()
                    tech_name = tech_part.strip()
                    for detail in report.radar_item_details:
                        if detail.technology_name == tech_name:
                            original = list(detail.key_players)
                            detail.key_players = [
                                p for p in detail.key_players
                                if p.lower() != entity_part.lower()
                            ]
                            if len(detail.key_players) < len(original):
                                logger.info(
                                    f"Removed '{entity_part}' from {tech_name} key_players"
                                )

        elapsed = time.time() - verify_start
        logger.info(
            f"Verification complete in {elapsed:.1f}s — "
            f"radar: {orig_radar}->{len(report.radar_items)}, "
            f"signals: {orig_signals}->{len(report.market_signals)}, "
            f"trends: {orig_trends}->{len(report.key_trends)}, "
            f"attribution_warnings: {len(verified.attribution_warnings)}"
        )

    except Exception as e:
        logger.warning(f"Verification failed (keeping original report): {e}")
        # On failure, return unmodified report

    return report
