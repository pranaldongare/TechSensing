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

    answer: str = ""                          # markdown answer
    sources: List[str] = []                   # report IDs used
    technologies_mentioned: List[str] = []    # radar item names referenced
    confidence: str = "low"                   # "high", "medium", "low"


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
        "using ONLY the report data provided below. Be specific, cite report dates, "
        "and mention specific technologies by name.\n\n"
        "Format the 'answer' field as Markdown:\n"
        "- Start with a 1-2 sentence direct response, citing the report date range.\n"
        "- For lists of 3+ items, use bullet points starting with '- '.\n"
        "- For each technology in a list, write the name in **bold** followed by "
        "' — ' and the key facts. Example: '- **FastDMS** — learned token eviction, "
        "6.4x compression'.\n"
        "- Use ## headings only if the answer has multiple distinct sections.\n"
        "- Keep prose tight and scannable.\n\n"
        f"REPORT DATA:\n{context_json}\n\n"
        f"USER QUESTION: {question}\n\n"
        "Output a single JSON object with these four keys:\n"
        '  "answer" (Markdown string), "sources" (array of report_id strings), '
        '"technologies_mentioned" (array of strings), "confidence" ("high"/"medium"/"low").\n'
        "Inside the JSON string for 'answer', escape every newline as the two-character "
        "sequence \\n. Do NOT include literal line breaks inside any string.\n"
        "Output ONLY the JSON — no markdown fences, no commentary.\n\n"
        "Example:\n"
        '{"answer": "Based on the April 2026 report...\\n\\n- **TechA** — fact 1\\n'
        '- **TechB** — fact 2", "sources": ["abc-123"], '
        '"technologies_mentioned": ["TechA", "TechB"], "confidence": "high"}\n\n'
        "YOUR JSON RESPONSE:"
    )

    model = GPU_SENSING_CLASSIFY_LLM.model
    port = GPU_SENSING_CLASSIFY_LLM.port
    max_attempts = 3

    last_error: Optional[str] = None
    last_raw: str = ""
    for attempt in range(1, max_attempts + 1):
        raw_output = ""
        try:
            raw_output = await _call_ollama_raw(prompt, model, port)
            last_raw = raw_output
            logger.info(f"Query LLM attempt {attempt}: got {len(raw_output)} chars")

            if not raw_output.strip():
                last_error = "LLM returned empty response"
                logger.error(f"Query attempt {attempt} failed: {last_error}")
                continue

            try:
                parsed = _parse_query_json(raw_output)
            except Exception as parse_err:
                last_error = f"JSON parse failed: {parse_err}"
                logger.error(
                    f"Query attempt {attempt} parse failed: {parse_err}\n"
                    f"  raw output (first 500 chars): {raw_output[:500]!r}"
                )
                continue

            # Detect and reject schema echo
            if _is_schema_echo(parsed):
                last_error = "LLM echoed schema instead of data"
                logger.error(
                    f"Query attempt {attempt}: schema echo detected\n"
                    f"  parsed keys: {list(parsed.keys())}"
                )
                continue

            try:
                return QueryAnswer.model_validate(parsed)
            except Exception as val_err:
                last_error = f"Schema validation failed: {val_err}"
                logger.error(
                    f"Query attempt {attempt} validation failed: {val_err}\n"
                    f"  parsed keys: {list(parsed.keys())}\n"
                    f"  raw output (first 500 chars): {raw_output[:500]!r}"
                )
                continue

        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"
            logger.error(
                f"Query attempt {attempt} failed: {last_error}\n"
                f"  raw output (first 500 chars): {raw_output[:500]!r}"
            )

    logger.error(
        f"All {max_attempts} query attempts failed. Last error: {last_error}\n"
        f"  Final raw output (first 1000 chars): {last_raw[:1000]!r}"
    )
    return QueryAnswer(
        answer=(
            "Sorry, I encountered an error processing your question. "
            f"Last error: {last_error or 'unknown'}"
        ),
        sources=[c["report_id"] for c in report_contexts],
        technologies_mentioned=[],
        confidence="low",
    )
