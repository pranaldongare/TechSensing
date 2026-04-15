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
    for fname in report_files[:max_reports * 2]:  # load extra to filter
        fpath = os.path.join(sensing_dir, fname)
        try:
            async with aiofiles.open(fpath, "r") as f:
                data = json.loads(await f.read())

            if domain and data.get("domain", "").lower() != domain.lower():
                continue

            report_id = fname.replace("report_", "").replace(".json", "")

            # Extract relevant sections for context
            context = {
                "report_id": report_id,
                "domain": data.get("domain", ""),
                "date_range": data.get("date_range", ""),
                "executive_summary": data.get("executive_summary", ""),
                "radar_items": [
                    {"name": r.get("name"), "ring": r.get("ring"),
                     "quadrant": r.get("quadrant"),
                     "description": r.get("description", "")[:200],
                     "is_new": r.get("is_new", False),
                     "moved_in": r.get("moved_in")}
                    for r in data.get("radar_items", [])
                ],
                "key_trends": [
                    {"name": t.get("trend_name"), "impact": t.get("impact_level")}
                    for t in data.get("key_trends", [])
                ],
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
    context_json = json.dumps(report_contexts, indent=1)
    schema_json = json.dumps(QueryAnswer.model_json_schema(), indent=2)

    prompt = [
        {
            "role": "system",
            "parts": (
                "You are a technology intelligence analyst. Answer the user's question "
                "using ONLY the report data provided below. Be specific, cite report dates, "
                "and mention specific technologies by name.\n\n"
                f"REPORT DATA:\n{context_json}\n\n"
                f"Respond with valid JSON matching this schema:\n{schema_json}"
            ),
        },
        {"role": "user", "parts": question},
    ]

    result = await invoke_llm(
        gpu_model=GPU_SENSING_CLASSIFY_LLM.model,
        response_schema=QueryAnswer,
        contents=prompt,
        port=GPU_SENSING_CLASSIFY_LLM.port,
    )

    return QueryAnswer.model_validate(result)
