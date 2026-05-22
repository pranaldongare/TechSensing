"""
End-to-end diagnostic for INTERNAL LLM article classification.

Runs the SAME prompt the production classifier builds, but with extensive
logging at every step so we can pinpoint exactly where INTERNAL is failing.

Two modes:
  1. ``raw`` (default) — calls INTERNALLLM._call directly. Logs the full
     HTTP request and full HTTP response. This isolates "does INTERNAL
     actually work?" from "does the parse logic work?".
  2. ``full`` — calls the real ``invoke_llm`` with INTERNAL_NO_FALLBACK
     forced True. Logs every parse attempt and validation step. This
     exposes failures in the parse + Pydantic validation chain.

Both modes write a full log to DEBUG/diagnose_internal_classifier.log
that the user can share for offline debugging.

Usage on the server (where INTERNAL is configured):
    python scripts/diagnose_internal_classifier.py            # raw mode
    python scripts/diagnose_internal_classifier.py --mode full
    python scripts/diagnose_internal_classifier.py --mode both
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

# Add the project root (parent of scripts/) to sys.path so `from core.*` works
# when the script is invoked as `python scripts/diagnose_internal_classifier.py`.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=_PROJECT_ROOT / ".env")
except ImportError:
    pass

# ── Logging: console (verbose) + file (everything) ─────────────────────
LOG_DIR = Path("DEBUG")
LOG_DIR.mkdir(exist_ok=True)
LOG_PATH = LOG_DIR / "diagnose_internal_classifier.log"

_root = logging.getLogger()
_root.setLevel(logging.DEBUG)
_root.handlers.clear()

_fmt = logging.Formatter(
    "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)

_console = logging.StreamHandler(sys.stdout)
_console.setLevel(logging.DEBUG)
_console.setFormatter(_fmt)
_root.addHandler(_console)

_file = logging.FileHandler(LOG_PATH, mode="w", encoding="utf-8")
_file.setLevel(logging.DEBUG)
_file.setFormatter(_fmt)
_root.addHandler(_file)

log = logging.getLogger("diagnose")


# ── Helpers ───────────────────────────────────────────────────────────

def _redact(token: str) -> str:
    if not token:
        return "(empty)"
    if len(token) <= 12:
        return "***"
    return f"{token[:6]}...{token[-4:]} (len={len(token)})"


def _banner(text: str) -> None:
    bar = "=" * max(60, len(text) + 4)
    log.info("")
    log.info(bar)
    log.info(f"  {text}")
    log.info(bar)


def _dump_settings() -> bool:
    """Log the INTERNAL config (with token redacted). Returns True if usable."""
    from core.config import settings
    log.info("Current INTERNAL configuration:")
    log.info(f"  USE_INTERNAL          = {settings.USE_INTERNAL}")
    log.info(f"  INTERNAL_NO_FALLBACK  = {settings.INTERNAL_NO_FALLBACK}")
    log.info(f"  INTERNAL_BASE_URL     = {settings.INTERNAL_BASE_URL!r}")
    log.info(f"  INTERNAL_MODEL_ID     = {settings.INTERNAL_MODEL_ID!r}")
    log.info(f"  INTERNAL_CLIENT_KEY   = {_redact(settings.INTERNAL_CLIENT_KEY)}")
    log.info(f"  INTERNAL_API_TOKEN    = {_redact(settings.INTERNAL_API_TOKEN)}")
    log.info(f"  INTERNAL_USER_EMAIL   = {settings.INTERNAL_USER_EMAIL!r}")
    log.info(f"  INTERNAL_MAX_NEW_TOKENS = {settings.INTERNAL_MAX_NEW_TOKENS}")
    log.info(f"  LLM_CALL_LOG          = {os.getenv('LLM_CALL_LOG', '(unset)')}")

    missing = []
    if not settings.INTERNAL_BASE_URL:
        missing.append("INTERNAL_BASE_URL")
    if not settings.INTERNAL_API_TOKEN:
        missing.append("INTERNAL_API_TOKEN")
    if not settings.INTERNAL_MODEL_ID:
        missing.append("INTERNAL_MODEL_ID")
    if missing:
        log.error(f"MISSING required env vars: {missing}")
        return False
    return True


# ── Fixture: a small batch of 2 fake articles ─────────────────────────

FIXTURE_ARTICLES_TEXT = """\
--- Article 1 ---
Title: Anthropic releases Claude 4.7 with improved tool use
Source: anthropic.com
URL: https://www.anthropic.com/news/claude-4-7
Date: 2026-05-19
Content:
Anthropic today announced Claude 4.7, the latest version of its frontier model,
with substantially improved tool-use reliability and a 500K-token context
window. Internal benchmarks show a 32% reduction in tool-call errors on the
agent-bench suite versus Claude 4.6. The model is available immediately via
the Claude API and AWS Bedrock.

--- Article 2 ---
Title: vLLM 0.9.0 ships continuous batching v2
Source: github.com
URL: https://github.com/vllm-project/vllm/releases/tag/v0.9.0
Date: 2026-05-20
Content:
The vLLM team released v0.9.0 today. The headline feature is "continuous
batching v2" which the team claims doubles throughput on H100 GPUs for
long-context workloads. The release also adds first-class support for
speculative decoding with draft models, and an experimental disaggregated
prefill/decode mode.
"""


def _build_classifier_prompt():
    """Build the exact prompt the production classifier uses."""
    from core.llm.prompts.sensing_prompts import sensing_classify_prompt
    from core.sensing.config import get_preset_for_domain

    preset = get_preset_for_domain("Generative AI")
    return sensing_classify_prompt(
        articles_text=FIXTURE_ARTICLES_TEXT,
        domain="Generative AI",
        custom_requirements="",
        key_people=None,
        topic_categories_text=preset.topic_categories,
        industry_segments_text=preset.industry_segments,
        custom_quadrant_names=None,
        date_range="May 14, 2026 - May 21, 2026",
    )


def _serialize_prompt(contents) -> str:
    """Mirror invoke_llm's _serialize_prompt_messages."""
    if isinstance(contents, list) and contents and isinstance(contents[0], dict):
        parts = []
        for msg in contents:
            role = msg.get("role", "system").upper()
            body = msg.get("parts", "")
            parts.append(f"[{role}]\n{body}")
        return "\n\n".join(parts)
    return str(contents)


# ── Mode 1: RAW HTTP exchange via INTERNALLLM._call ───────────────────

async def run_raw_mode() -> bool:
    _banner("MODE 1: RAW — INTERNALLLM._call directly")
    from core.config import settings
    from core.llm.configurations.internal_llm import INTERNALLLM
    from core.llm.output_schemas.sensing_outputs import ArticleBatchClassification
    from langchain_core.output_parsers import PydanticOutputParser

    log.info("Building the exact classifier prompt the pipeline uses...")
    raw_contents = _build_classifier_prompt()
    serialized = _serialize_prompt(raw_contents)
    log.info(f"  Serialized prompt: {len(serialized)} chars")
    log.debug(f"  Prompt preview (first 800 chars):\n{serialized[:800]}")

    # The full prompt the invoke_llm wrapper adds includes schema instructions.
    # Replicate that here so the raw call is apples-to-apples.
    parser = PydanticOutputParser(pydantic_object=ArticleBatchClassification)
    full_prompt = (
        f"Extract structured data according to this model:\n"
        f"{parser.get_format_instructions()}\n\n"
        f"Input:\n{serialized}\n\n"
        f"CRITICAL OUTPUT RULES:\n"
        f"1. Output must be valid JSON.\n"
        f"2. Escape newlines as \\n and tabs as \\t within JSON strings.\n"
        f"3. If you generate internal reasoning (e.g. inside <think> tags), "
        f"you MUST produce the final JSON object AFTER the closing </think> tag.\n"
        f"4. Do not output any text before or after the JSON object.\n"
        f"5. Do NOT echo the schema definition. Never include \"$defs\", "
        f"\"$ref\", \"properties\", \"required\", \"title\", \"type\":\"object\" "
        f"or \"description\" as top-level keys. Only output the DATA that "
        f"conforms to the schema.\n"
        f"6. Every list/array field must contain actual items.\n"
    )
    log.info(f"  Full prompt (schema injected): {len(full_prompt)} chars")

    log.info("Instantiating INTERNALLLM client...")
    llm = INTERNALLLM(
        model=settings.INTERNAL_MODEL_ID,
        base_url=settings.INTERNAL_BASE_URL,
        client_key=settings.INTERNAL_CLIENT_KEY,
        api_token=settings.INTERNAL_API_TOKEN,
        user_email=settings.INTERNAL_USER_EMAIL,
    )
    log.info(f"  Target URL: {llm.base_url}/openapi/chat/v1/messages")
    log.info(f"  Model ID:   {llm.model}")
    log.info(f"  Max tokens: {settings.INTERNAL_MAX_NEW_TOKENS}")

    log.info("Sending request to INTERNAL API...")
    t0 = time.time()
    try:
        raw_output = await asyncio.to_thread(
            llm._call,
            full_prompt,
            max_new_tokens=settings.INTERNAL_MAX_NEW_TOKENS,
        )
    except Exception as e:
        elapsed = time.time() - t0
        log.error(
            f"INTERNAL call FAILED after {elapsed:.2f}s with "
            f"{type(e).__name__}: {e}"
        )
        log.error("Full traceback:\n%s", traceback.format_exc())
        _dump_last_raw_exchange()
        return False
    elapsed = time.time() - t0
    log.info(f"INTERNAL call returned in {elapsed:.2f}s")
    log.info(f"  Returned text length: {len(raw_output)} chars")

    # Always dump the raw HTTP exchange to terminal so the user sees the full
    # status, headers, and response body without having to open a file.
    _dump_last_raw_exchange()

    if not raw_output or not raw_output.strip():
        log.error("INTERNAL returned an EMPTY response.")
        log.error(
            "If the raw_jsonl shows HTTP 200 with status=SUCCESS but content "
            "is empty, the model is producing no text. Check "
            "INTERNAL_MAX_NEW_TOKENS and any safety filters on the INTERNAL "
            "side."
        )
        return False

    _dump_long_text("FULL LLM OUTPUT", raw_output)

    log.info("Attempting to parse output as ArticleBatchClassification JSON...")
    return _attempt_parse(raw_output, ArticleBatchClassification, parser)


def _dump_long_text(label: str, text: str, line_prefix: str = "  ") -> None:
    """Print a long text block to terminal/log with clear delimiters."""
    sep = "─" * 60
    log.info(f"┌{sep} {label} ({len(text)} chars) {sep}")
    for line in text.splitlines() or [""]:
        log.info(f"{line_prefix}{line}")
    log.info(f"└{sep} END {label} {sep}")


def _dump_last_raw_exchange() -> None:
    """Read the last line from DEBUG/llm_calls/internal_raw.jsonl and print
    its key fields to terminal. This is the full HTTP request/response that
    internal_llm.py wrote during the call we just made."""
    raw_path = Path("DEBUG") / "llm_calls" / "internal_raw.jsonl"
    if not raw_path.exists():
        log.warning(
            f"Raw HTTP log not found at {raw_path.resolve()} — "
            "is LLM_CALL_LOG disabled?"
        )
        return
    try:
        last_line = ""
        with raw_path.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    last_line = line
        if not last_line:
            log.warning("Raw HTTP log is empty.")
            return
        entry = json.loads(last_line)
    except Exception as e:
        log.warning(f"Could not read raw HTTP log: {e}")
        return

    log.info("─── Raw HTTP exchange (most recent entry) ───")
    log.info(f"  timestamp:    {entry.get('timestamp')}")
    log.info(f"  url:          {entry.get('url')}")
    log.info(f"  method:       {entry.get('method')}")
    log.info(f"  status:       {entry.get('status')}")
    log.info(f"  elapsed_s:    {entry.get('elapsed_s')}")
    log.info(f"  response_status_code: {entry.get('response_status_code')}")
    log.info(f"  error:        {entry.get('error') or '(none)'}")
    log.info("  request_headers (sanitized):")
    for k, v in (entry.get("request_headers") or {}).items():
        log.info(f"    {k}: {v}")
    log.info("  response_headers:")
    for k, v in (entry.get("response_headers") or {}).items():
        log.info(f"    {k}: {v}")
    req_body = entry.get("request_body") or {}
    log.info(f"  request_body.modelIds: {req_body.get('modelIds')}")
    log.info(f"  request_body.llmConfig: {req_body.get('llmConfig')}")
    log.info(f"  request_body.isStream: {req_body.get('isStream')}")
    contents = req_body.get("contents") or []
    if contents:
        log.info(f"  request_body.contents[0] length: {len(str(contents[0]))} chars")
    resp_body = entry.get("response_body") or ""
    _dump_long_text("RESPONSE BODY (raw HTTP)", str(resp_body))


def _attempt_parse(raw_output, response_schema, parser) -> bool:
    """Replicate client.py::_try_parse with verbose logging at every step."""
    from core.utils.llm_output_sanitizer import (
        _wrap_bare_array,
        parse_llm_json,
        sanitize_llm_json,
    )

    log.info("Parse Strategy 1: sanitize_llm_json + parser.parse")
    cleaned = sanitize_llm_json(raw_output)
    log.info(f"  After sanitize: {len(cleaned)} chars (preview: {cleaned[:200]!r})")
    try:
        result = parser.parse(cleaned)
        log.info(f"  Strategy 1 SUCCESS: {type(result).__name__} with "
                 f"{len(result.articles) if hasattr(result, 'articles') else '?'} articles")
        _log_classified_summary(result)
        return True
    except Exception as e:
        log.warning(f"  Strategy 1 FAILED: {type(e).__name__}: {e}")

    log.info("Parse Strategy 2: json.loads + model_validate")
    try:
        parsed = json.loads(cleaned)
        log.info(f"  json.loads OK — type={type(parsed).__name__}")
        if isinstance(parsed, list):
            log.info(f"  Got a bare array of {len(parsed)} items — wrapping")
            parsed = _wrap_bare_array(parsed, response_schema)
        if isinstance(parsed, dict):
            log.info(f"  Dict keys: {sorted(parsed.keys())}")
            from core.utils.llm_output_sanitizer import _strip_schema_metadata
            parsed = _strip_schema_metadata(parsed, response_schema)
            log.info(f"  After strip_schema_metadata: keys={sorted(parsed.keys())}")
        result = response_schema.model_validate(parsed)
        log.info(f"  Strategy 2 SUCCESS: {type(result).__name__} with "
                 f"{len(result.articles) if hasattr(result, 'articles') else '?'} articles")
        _log_classified_summary(result)
        return True
    except Exception as e:
        log.warning(f"  Strategy 2 FAILED: {type(e).__name__}: {e}")

    log.info("Parse Strategy 3: json_repair + model_validate")
    try:
        result = parse_llm_json(raw_output, response_schema)
        log.info(f"  Strategy 3 SUCCESS: {type(result).__name__} with "
                 f"{len(result.articles) if hasattr(result, 'articles') else '?'} articles")
        _log_classified_summary(result)
        return True
    except Exception as e:
        log.error(f"  Strategy 3 FAILED: {type(e).__name__}: {e}")
        log.error("Full traceback:\n%s", traceback.format_exc())
        log.error("All three parse strategies FAILED. Dumping full raw output:")
        _dump_long_text("UNPARSEABLE LLM OUTPUT", raw_output)
        out_path = LOG_DIR / "diagnose_internal_classifier_unparseable.txt"
        out_path.write_text(raw_output, encoding="utf-8")
        log.error(f"Also saved to: {out_path.resolve()}")
        return False


def _log_classified_summary(result) -> None:
    if not hasattr(result, "articles"):
        return
    for i, a in enumerate(result.articles, 1):
        log.info(
            f"    Article {i}: name={getattr(a, 'technology_name', '?')!r}, "
            f"quadrant={getattr(a, 'quadrant', '?')}, "
            f"ring={getattr(a, 'ring', '?')}, "
            f"relevance={getattr(a, 'relevance_score', '?')}"
        )


# ── Mode 2: FULL invoke_llm path ──────────────────────────────────────

async def run_full_mode() -> bool:
    _banner("MODE 2: FULL — invoke_llm() with INTERNAL_NO_FALLBACK forced True")
    from core.config import settings
    from core.constants import SWITCHES
    from core.llm.client import invoke_llm
    from core.llm.output_schemas.sensing_outputs import ArticleBatchClassification

    # Force NO_FALLBACK so this test never accidentally returns a GPU result.
    SWITCHES["INTERNAL_NO_FALLBACK"] = True
    settings.INTERNAL_NO_FALLBACK = True
    log.info("Forced SWITCHES['INTERNAL_NO_FALLBACK'] = True for this run.")

    contents = _build_classifier_prompt()
    log.info(f"  Built classifier prompt: {len(_serialize_prompt(contents))} chars")

    log.info("Calling invoke_llm() — this exercises the full Phase 0 pipeline...")
    t0 = time.time()
    try:
        result = await invoke_llm(
            gpu_model="qwen3:14b",
            response_schema=ArticleBatchClassification,
            contents=contents,
            port=11434,
        )
    except Exception as e:
        elapsed = time.time() - t0
        log.error(f"invoke_llm FAILED after {elapsed:.2f}s with "
                  f"{type(e).__name__}: {e}")
        log.error("Full traceback:\n%s", traceback.format_exc())
        # Dump the per-call structured log AND the raw HTTP exchange so the
        # user sees everything in the terminal without opening files.
        _dump_last_call_log()
        _dump_last_raw_exchange()
        return False
    elapsed = time.time() - t0
    log.info(f"invoke_llm SUCCEEDED in {elapsed:.2f}s")
    log.info(f"  Got {len(result.articles)} classified articles")
    _log_classified_summary(result)
    # Even on success, show the user the raw exchange so they can confirm
    # everything is wired up correctly.
    _dump_last_raw_exchange()
    return True


def _dump_last_call_log() -> None:
    """Read the last line from DEBUG/llm_calls/calls.jsonl and print key
    fields. This is the higher-level invoke_llm summary."""
    call_path = Path("DEBUG") / "llm_calls" / "calls.jsonl"
    if not call_path.exists():
        log.warning(f"Call log not found at {call_path.resolve()}")
        return
    try:
        last_line = ""
        with call_path.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    last_line = line
        if not last_line:
            return
        entry = json.loads(last_line)
    except Exception as e:
        log.warning(f"Could not read call log: {e}")
        return
    log.info("─── Per-call log (most recent entry) ───")
    log.info(f"  source:    {entry.get('source')}")
    log.info(f"  status:    {entry.get('status')}")
    log.info(f"  attempt:   {entry.get('attempt')}")
    log.info(f"  model:     {entry.get('model')}")
    log.info(f"  schema:    {entry.get('schema')}")
    log.info(f"  elapsed_s: {entry.get('elapsed_s')}")
    log.info(f"  error:     {entry.get('error') or '(none)'}")
    out_prev = entry.get("output_preview") or ""
    if out_prev:
        _dump_long_text("CALL LOG OUTPUT PREVIEW", out_prev)


# ── Main ──────────────────────────────────────────────────────────────

async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("raw", "full", "both"),
        default="raw",
        help="raw = INTERNALLLM._call only (default). full = invoke_llm. both = run both.",
    )
    args = parser.parse_args()

    _banner("INTERNAL Classifier Diagnostic")
    log.info(f"Started: {datetime.now(timezone.utc).isoformat()}")
    log.info(f"CWD:     {os.getcwd()}")
    log.info(f"Logfile: {LOG_PATH.resolve()}")
    log.info(f"Mode:    {args.mode}")

    if not _dump_settings():
        log.error("Fix the missing env vars before continuing.")
        return 1

    results = {}
    if args.mode in ("raw", "both"):
        try:
            results["raw"] = await run_raw_mode()
        except Exception as e:
            log.error(f"Mode 'raw' crashed unexpectedly: {e}")
            log.error(traceback.format_exc())
            results["raw"] = False

    if args.mode in ("full", "both"):
        try:
            results["full"] = await run_full_mode()
        except Exception as e:
            log.error(f"Mode 'full' crashed unexpectedly: {e}")
            log.error(traceback.format_exc())
            results["full"] = False

    _banner("VERDICT")
    for mode_name, ok in results.items():
        log.info(f"  {mode_name}: {'PASS' if ok else 'FAIL'}")
    log.info("")
    log.info(f"Full log saved to:               {LOG_PATH.resolve()}")
    log.info(f"Per-call structured log:         DEBUG/llm_calls/calls.jsonl")
    log.info(f"Raw INTERNAL HTTP exchanges:     DEBUG/llm_calls/internal_raw.jsonl")
    if any(not v for v in results.values()):
        log.info("")
        log.info("Share all three log files for offline debugging.")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
