"""
Natural Language Query — answers questions using stored report data.

Searches report JSONs for relevant context, then uses LLM to generate
a grounded answer.
"""

import json
import logging
import os
from typing import List, Optional

import aiofiles

from core.constants import GPU_SENSING_CLASSIFY_LLM
from core.llm.client import invoke_llm
from core.llm.output_schemas.base import LLMOutputBase

logger = logging.getLogger("sensing.query")


class QueryAnswer(LLMOutputBase):
    """LLM-generated answer to a natural language query."""

    answer: str  # markdown answer
    sources: List[str]  # report IDs used
    technologies_mentioned: List[str]  # radar item names referenced
    confidence: str  # "high", "medium", "low"


async def query_reports(
    user_id: str,
    question: str,
    domain: Optional[str] = None,
    max_reports: int = 5,
) -> QueryAnswer:
    """Answer a natural language question using stored report data."""
    sensing_dir = f"data/{user_id}/sensing"
    if not os.path.exists(sensing_dir):
        return QueryAnswer(
            answer="No reports found. Generate a sensing report first.",
            sources=[],
            technologies_mentioned=[],
            confidence="low",
        )

    # Load recent reports (filtered by domain if specified)
    report_files = sorted(
        [f for f in os.listdir(sensing_dir)
         if f.startswith("report_") and f.endswith(".json")],
        reverse=True,
    )

    report_contexts = []
    for fname in report_files:  # scan all reports to find domain matches
        fpath = os.path.join(sensing_dir, fname)
        try:
            async with aiofiles.open(fpath, "r") as f:
                raw = json.loads(await f.read())

            # Reports are stored as {"report": {...}, "meta": {...}}
            report = raw.get("report", raw)
            meta = raw.get("meta", {})

            # Domain lives in meta or report
            report_domain = (
                meta.get("domain", "")
                or report.get("domain", "")
            )
            if domain and report_domain.lower() != domain.lower():
                continue

            report_id = meta.get("tracking_id") or fname.replace("report_", "").replace(".json", "")
            generated_at = meta.get("generated_at", "")

            # Extract relevant sections for context
            context = {
                "report_id": report_id,
                "domain": report_domain,
                "generated_at": generated_at,
                "report_title": report.get("report_title", ""),
                "date_range": report.get("date_range", ""),
                "executive_summary": report.get("executive_summary", ""),
                "recommendations": report.get("recommendations", []),
                "radar_items": [
                    {"name": r.get("name"), "ring": r.get("ring"),
                     "quadrant": r.get("quadrant"),
                     "description": r.get("description", "")[:300],
                     "is_new": r.get("is_new", False),
                     "moved_in": r.get("moved_in"),
                     "key_players": r.get("key_players", []),
                     "practical_applications": r.get("practical_applications", [])[:3]}
                    for r in report.get("radar_items", [])
                ],
                "key_trends": [
                    {"name": t.get("trend_name"), "impact": t.get("impact_level"),
                     "description": t.get("description", "")[:200]}
                    for t in report.get("key_trends", [])
                ],
                "top_events": [
                    {"headline": e.get("headline"), "actor": e.get("actor"),
                     "event_type": e.get("event_type"),
                     "impact_summary": e.get("impact_summary", "")[:200]}
                    for e in report.get("top_events", [])
                ] if report.get("top_events") else [],
                "market_signals": [
                    {"company": s.get("company_or_player"), "signal": s.get("signal"),
                     "description": s.get("industry_impact", "")[:150]}
                    for s in report.get("market_signals", [])[:10]
                ],
                "blind_spots": [
                    {"area": b.get("area"), "why_it_matters": b.get("why_it_matters", "")[:150]}
                    for b in report.get("blind_spots", [])
                ] if report.get("blind_spots") else [],
            }
            report_contexts.append(context)

            if len(report_contexts) >= max_reports:
                break

        except Exception as e:
            logger.warning(f"Failed to load {fname}: {e}")

    if not report_contexts:
        return QueryAnswer(
            answer=f"No reports found for domain '{domain}'." if domain
                   else "No reports found.",
            sources=[],
            technologies_mentioned=[],
            confidence="low",
        )

    # Build LLM prompt
    logger.info(
        f"Query: '{question}' | domain={domain} | "
        f"{len(report_contexts)} reports loaded | "
        f"radar_items={sum(len(c['radar_items']) for c in report_contexts)} | "
        f"trends={sum(len(c['key_trends']) for c in report_contexts)}"
    )
    context_json = json.dumps(report_contexts, indent=1)
    schema_json = json.dumps(QueryAnswer.model_json_schema(), indent=2)

    prompt = [
        {
            "role": "system",
            "parts": (
                "You are a technology intelligence analyst. Answer the user's question "
                "using ONLY the report data provided below. Be specific, cite report dates "
                "and generation timestamps, and mention specific technologies by name. "
                "Include details from radar items, key trends, market signals, and "
                "recommendations where relevant. If the data contains relevant information, "
                "provide a thorough answer.\n\n"
                f"REPORT DATA:\n{context_json}\n\n"
                f"Respond with valid JSON matching this schema:\n{schema_json}"
            ),
        },
        {"role": "user", "parts": question},
    ]

    try:
        result = await invoke_llm(
            gpu_model=GPU_SENSING_CLASSIFY_LLM.model,
            response_schema=QueryAnswer,
            contents=prompt,
            port=GPU_SENSING_CLASSIFY_LLM.port,
        )
        return QueryAnswer.model_validate(result)
    except Exception as e:
        logger.error(f"Query LLM call failed: {e}")
        return QueryAnswer(
            answer="Sorry, I encountered an error processing your question. Please try again.",
            sources=[c["report_id"] for c in report_contexts],
            technologies_mentioned=[],
            confidence="low",
        )
