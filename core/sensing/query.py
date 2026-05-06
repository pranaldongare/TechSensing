"""
Natural Language Query — answers questions using stored report data.

Searches report JSONs for relevant context, then uses LLM to generate
a grounded answer.

Uses a direct Ollama call (no PydanticOutputParser schema injection)
to prevent the local model from echoing the JSON schema instead of
producing actual data.
"""

import json
import logging
import os
import re
from typing import List, Optional

import aiofiles
import httpx

from core.constants import GPU_SENSING_CLASSIFY_LLM
from core.llm.output_schemas.base import LLMOutputBase

logger = logging.getLogger("sensing.query")

# Ollama generate endpoint
_OLLAMA_BASE = "http://localhost:{port}"
_OLLAMA_TIMEOUT = 120.0  # seconds


class QueryAnswer(LLMOutputBase):
    """LLM-generated answer to a natural language query."""

    answer: str  # markdown answer
    sources: List[str]  # report IDs used
    technologies_mentioned: List[str]  # radar item names referenced
    confidence: str  # "high", "medium", "low"


async def _call_ollama_raw(prompt: str, model: str, port: int) -> str:
    """Call Ollama /api/generate directly (no schema injection)."""
    url = f"{_OLLAMA_BASE.format(port=port)}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": 4096},
    }
    async with httpx.AsyncClient(timeout=_OLLAMA_TIMEOUT) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data.get("response", "")


def _parse_query_json(raw: str) -> dict:
    """Extract a JSON object from the LLM's raw text output."""
    # Strip thinking tags
    text = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
    text = re.sub(r"<reasoning>.*?</reasoning>", "", text, flags=re.DOTALL)
    text = text.strip()

    # Strip markdown code fences
    text = re.sub(r"^```(?:json)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    text = text.strip()

    # Try direct parse
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # Try extracting the first JSON object
    match = re.search(r"\{", text)
    if match:
        start = match.start()
        # Find the matching closing brace
        depth = 0
        in_str = False
        escape = False
        for i in range(start, len(text)):
            c = text[i]
            if escape:
                escape = False
                continue
            if c == "\\":
                escape = True
                continue
            if c == '"' and not escape:
                in_str = not in_str
                continue
            if in_str:
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break

    # Try json_repair as last resort
    try:
        import json_repair

        repaired = json_repair.loads(text)
        if isinstance(repaired, dict):
            return repaired
    except Exception:
        pass

    raise ValueError(f"Could not extract JSON from LLM output: {text[:500]}")


def _is_schema_echo(parsed: dict) -> bool:
    """Detect if the parsed dict is a JSON schema definition rather than data."""
    schema_keys = {"properties", "required", "type", "description", "$defs", "$ref", "title"}
    top_keys = set(parsed.keys())
    # If most top-level keys are schema keywords, it's an echo
    return len(top_keys & schema_keys) >= 2 and "answer" not in parsed


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

            # Domain lives in meta and/or report (LLM may rephrase the domain)
            meta_domain = meta.get("domain", "")
            report_domain = report.get("domain", "")
            if domain:
                domain_lower = domain.lower()
                if (meta_domain.lower() != domain_lower
                        and report_domain.lower() != domain_lower):
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
        logger.warning(
            f"No reports matched domain='{domain}' — "
            f"{len(report_files)} files scanned in {sensing_dir}"
        )
        return QueryAnswer(
            answer=f"No reports found for domain '{domain}'." if domain
                   else "No reports found.",
            sources=[],
            technologies_mentioned=[],
            confidence="low",
        )

    # Build LLM prompt — no JSON schema injection to avoid echo issues
    logger.info(
        f"Query: '{question}' | domain={domain} | "
        f"{len(report_contexts)} reports loaded | "
        f"radar_items={sum(len(c['radar_items']) for c in report_contexts)} | "
        f"trends={sum(len(c['key_trends']) for c in report_contexts)}"
    )
    context_json = json.dumps(report_contexts, indent=1)

    prompt = (
        "You are a technology intelligence analyst. Answer the user's question "
        "using ONLY the report data provided below. Be specific, cite report dates "
        "and generation timestamps, and mention specific technologies by name. "
        "Include details from radar items, key trends, market signals, and "
        "recommendations where relevant. If the data contains relevant information, "
        "provide a thorough answer.\n\n"
        "ANSWER FORMATTING — the 'answer' field MUST be Markdown:\n"
        "- Open with a 1-2 sentence direct response (no heading), citing the "
        "report date range and generation timestamp.\n"
        "- Then use short ## section headings to organize the body when there "
        "are multiple distinct points (e.g., ## Key Alternatives, ## Trade-offs, "
        "## Recommendations). Skip headings if the answer is short.\n"
        "- Use bullet lists ('- ') when listing 3+ items (technologies, "
        "alternatives, recommendations).\n"
        "- For each technology mentioned in a list item, lead with the name in "
        "**bold** followed by an em-dash and the key facts/metrics. Example: "
        "'- **FastDMS** — learned token eviction, 6.4x compression, "
        "outperforms BF16/FP8 baselines'.\n"
        "- Use Markdown newlines (\\n\\n between paragraphs/lists, \\n inside "
        "lists). Inside the JSON string, write them as the escaped sequences "
        "\\n and \\n\\n — do not embed raw newlines.\n"
        "- Keep prose tight. Prefer scannable structure over long paragraphs.\n\n"
        f"REPORT DATA:\n{context_json}\n\n"
        f"USER QUESTION: {question}\n\n"
        "Respond with ONLY a JSON object (no commentary, no markdown fences) "
        "with exactly these four keys:\n"
        '- "answer": your detailed Markdown answer as a string\n'
        '- "sources": array of report_id strings you referenced\n'
        '- "technologies_mentioned": array of technology name strings\n'
        '- "confidence": one of "high", "medium", or "low"\n\n'
        "OUTPUT ONLY THE JSON OBJECT. Example:\n"
        '{"answer": "Based on the April 2026 report...\\n\\n## Key Alternatives\\n'
        '- **TechA** — fact 1, metric 2\\n- **TechB** — fact 1, metric 2", '
        '"sources": ["abc-123"], '
        '"technologies_mentioned": ["TechA", "TechB"], '
        '"confidence": "high"}\n\n'
        "YOUR JSON RESPONSE:"
    )

    model = GPU_SENSING_CLASSIFY_LLM.model
    port = GPU_SENSING_CLASSIFY_LLM.port
    max_attempts = 3

    for attempt in range(1, max_attempts + 1):
        try:
            raw_output = await _call_ollama_raw(prompt, model, port)
            logger.info(f"Query LLM attempt {attempt}: got {len(raw_output)} chars")

            parsed = _parse_query_json(raw_output)

            # Detect and reject schema echo
            if _is_schema_echo(parsed):
                logger.warning(
                    f"Query attempt {attempt}: LLM echoed schema instead of data, retrying"
                )
                continue

            return QueryAnswer.model_validate(parsed)

        except Exception as e:
            logger.warning(f"Query attempt {attempt} failed: {e}")

    logger.error(f"All {max_attempts} query attempts failed")
    return QueryAnswer(
        answer="Sorry, I encountered an error processing your question. Please try again.",
        sources=[c["report_id"] for c in report_contexts],
        technologies_mentioned=[],
        confidence="low",
    )
