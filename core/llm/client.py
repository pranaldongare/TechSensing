import asyncio
import contextvars
import itertools
import json
import logging
import os
import time
from collections import OrderedDict
from datetime import datetime, timezone

from google import genai
from langchain_core.output_parsers import PydanticOutputParser
from openai import AsyncOpenAI

from core.config import settings
from core.constants import FALLBACK_GEMINI_MODEL, FALLBACK_OPENAI_MODEL, SWITCHES
from core.utils.llm_output_sanitizer import (
    _wrap_bare_array,
    parse_llm_json,
    sanitize_llm_json,
)

# ── Logging with tracking_id correlation ──────────────────────────
tracking_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "tracking_id", default=""
)


class _TrackingFilter(logging.Filter):
    """Inject tracking_id into every log record for correlation."""
    def filter(self, record):
        record.tracking_id = tracking_id_var.get("")
        return True


logger = logging.getLogger("llm.client")
logger.addFilter(_TrackingFilter())

# Directory for logging parse failures
_PARSE_ERRORS_DIR = "DEBUG/parse_errors"
os.makedirs(_PARSE_ERRORS_DIR, exist_ok=True)

# Per-call structured log of every LLM exchange (request + response + error).
# Useful for debugging INTERNAL API failures where the underlying HTTP error
# would otherwise be lost. Disable with LLM_CALL_LOG=false if disk usage is
# a concern (default: enabled). One line per call, JSONL.
_LLM_CALL_LOG_ENABLED = os.getenv("LLM_CALL_LOG", "true").lower() != "false"
_LLM_CALL_LOG_DIR = "DEBUG/llm_calls"
if _LLM_CALL_LOG_ENABLED:
    os.makedirs(_LLM_CALL_LOG_DIR, exist_ok=True)

# ── LLM concurrency semaphore ────────────────────────────────────
# Limits concurrent LLM calls to avoid GPU thrashing.
# Configurable via LLM_MAX_CONCURRENCY env var (default: 2).
_LLM_SEMAPHORE = asyncio.Semaphore(int(os.getenv("LLM_MAX_CONCURRENCY", "2")))

# ── Timeouts (seconds) ───────────────────────────────────────────
GPU_TIMEOUT = int(os.getenv("LLM_GPU_TIMEOUT", "1200"))       # 20 minutes
GEMINI_TIMEOUT = int(os.getenv("LLM_GEMINI_TIMEOUT", "180"))  # 3 minutes
OPENAI_TIMEOUT = int(os.getenv("LLM_OPENAI_TIMEOUT", "180"))  # 3 minutes

# ── Max output tokens for fallback providers ─────────────────────
GEMINI_MAX_OUTPUT_TOKENS = int(os.getenv("LLM_GEMINI_MAX_TOKENS", "16384"))


def _log_parse_failure(
    source: str,
    attempt: int,
    raw_output: str,
    error: str,
    schema_name: str,
    prompt_snippet: str = "",
):
    """Log a parse failure to a JSONL file for later analysis."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tracking_id": tracking_id_var.get(""),
        "source": source,
        "attempt": attempt,
        "schema": schema_name,
        "error": error,
        "raw_output": raw_output[:5000],
        "prompt_tail": prompt_snippet[-500:] if prompt_snippet else "",
    }
    try:
        log_path = os.path.join(_PARSE_ERRORS_DIR, "failures.jsonl")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _log_llm_call(
    source: str,
    attempt: int,
    model: str,
    prompt: str,
    output: str = "",
    error: str = "",
    elapsed_s: float = 0.0,
    schema: str = "",
    status: str = "ok",
):
    """Append one structured line per LLM exchange to DEBUG/llm_calls/calls.jsonl.

    Captures the prompt tail, output preview, and any error so failures
    (especially INTERNAL HTTP errors) are recoverable from disk after the
    fact. Also emits an INFO log so the same data is visible in stdout.

    `status` is one of: "ok", "blank", "transport_error", "parse_error",
    "timeout", "http_error".
    """
    prompt_chars = len(prompt or "")
    output_chars = len(output or "")
    summary = (
        f"[LLMCall] source={source} attempt={attempt} status={status} "
        f"model={model} schema={schema} elapsed={elapsed_s:.2f}s "
        f"prompt_chars={prompt_chars} output_chars={output_chars}"
    )
    if error:
        summary += f" error={error[:200]!r}"
    elif output:
        summary += f" output_preview={output[:200]!r}"
    if status == "ok":
        logger.info(summary)
    else:
        logger.warning(summary)

    if not _LLM_CALL_LOG_ENABLED:
        return

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tracking_id": tracking_id_var.get(""),
        "source": source,
        "attempt": attempt,
        "status": status,
        "model": model,
        "schema": schema,
        "elapsed_s": round(elapsed_s, 3),
        "prompt_chars": prompt_chars,
        "output_chars": output_chars,
        "prompt_tail": (prompt or "")[-1500:],
        "output_preview": (output or "")[:5000],
        "error": (error or "")[:5000],
    }
    try:
        log_path = os.path.join(_LLM_CALL_LOG_DIR, "calls.jsonl")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


# Always use local Ollama LLM
from core.llm.configurations.local_llm import MyServerLLM

# Optional: INTERNAL API LLM wrapper. The USE_INTERNAL switch is read at call
# time, so leaving this import None is fine when the feature is disabled.
try:
    from core.llm.configurations.internal_llm import INTERNALLLM
except Exception as _exc:
    logger.warning("INTERNALLLM unavailable — INTERNAL API disabled: %s", _exc)
    INTERNALLLM = None

# ── LRU cache for LLM client instances ───────────────────────────
_LLM_CACHE_MAX = int(os.getenv("LLM_CACHE_MAX", "8"))
_llm_cache: OrderedDict = OrderedDict()


def _get_cached_llm(model: str, port: int) -> MyServerLLM:
    """Return a cached MyServerLLM instance with LRU eviction."""
    key = (model, port)
    if key in _llm_cache:
        _llm_cache.move_to_end(key)
        return _llm_cache[key]
    llm = MyServerLLM(model=model, port=port)
    _llm_cache[key] = llm
    while len(_llm_cache) > _LLM_CACHE_MAX:
        _llm_cache.popitem(last=False)
    return llm


API_KEYS = [
    settings.API_KEY_1,
    settings.API_KEY_2,
    settings.API_KEY_3,
    settings.API_KEY_4,
    settings.API_KEY_5,
    settings.API_KEY_6,
]

openai_client = AsyncOpenAI(api_key=settings.OPENAI_API)
MAX_RETRIES = 4

# Thread-safe API key cycling
_api_key_cycle = itertools.cycle(API_KEYS)
_api_key_lock = asyncio.Lock()


async def _next_api_key():
    """Get the next API key in round-robin fashion, safely under concurrency."""
    async with _api_key_lock:
        return next(_api_key_cycle)


# ── INTERNAL API: sticky-skip context var + rate limiter ──────────
# After a transport-level INTERNAL failure, skip INTERNAL for the rest of
# this async context (request). Parse failures do NOT trip the skip — those
# get self-corrected within the existing retry loop.
_skip_internal: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "skip_internal", default=False
)


class _RateLimiter:
    """Async sliding-window rate limiter — 3 calls per 60 s by default."""

    def __init__(self, max_calls: int, window_seconds: float):
        self.max_calls = max_calls
        self.window = window_seconds
        self._timestamps: list[float] = []
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.time()
            self._timestamps = [t for t in self._timestamps if now - t < self.window]
            if len(self._timestamps) >= self.max_calls:
                wait = self.window - (now - self._timestamps[0])
                if wait > 0:
                    logger.info("INTERNAL rate-limited; sleeping %.1fs", wait)
                    await asyncio.sleep(wait)
                    now = time.time()
                    self._timestamps = [
                        t for t in self._timestamps if now - t < self.window
                    ]
            self._timestamps.append(now)


_internal_rate_limiter = _RateLimiter(max_calls=3, window_seconds=60.0)


def _check_empty_lists(result, response_schema) -> None:
    """
    Reject outputs where ALL required list fields are empty.
    """
    from pydantic.fields import PydanticUndefined

    model_fields = getattr(response_schema, "model_fields", {})
    required_list_fields = []
    for name, info in model_fields.items():
        annotation = info.annotation
        origin = getattr(annotation, "__origin__", None)
        if origin is not list:
            continue
        if info.default is not PydanticUndefined or info.default_factory is not None:
            continue
        required_list_fields.append(name)

    if not required_list_fields:
        return

    all_empty = all(
        len(getattr(result, f, None) or []) == 0 for f in required_list_fields
    )
    if all_empty:
        raise ValueError(
            f"All required list fields are empty ({', '.join(required_list_fields)}). "
            "Expected actual data items, not empty arrays."
        )


def _try_parse(raw_output: str, parser, response_schema):
    """
    Attempt to parse LLM output with sanitization and repair fallbacks.
    """
    cleaned = sanitize_llm_json(raw_output)

    # Strategy 1: Sanitized output through LangChain's parser
    try:
        result = parser.parse(cleaned)
        _check_empty_lists(result, response_schema)
        return result
    except Exception:
        pass

    # Strategy 2: Direct parse with schema metadata stripping + bare array wrapping
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, list):
            parsed = _wrap_bare_array(parsed, response_schema)
        if isinstance(parsed, dict):
            from core.utils.llm_output_sanitizer import _strip_schema_metadata
            parsed = _strip_schema_metadata(parsed, response_schema)
        result = response_schema.model_validate(parsed)
        _check_empty_lists(result, response_schema)
        return result
    except Exception:
        pass

    # Strategy 3: json_repair + Pydantic model_validate
    result = parse_llm_json(raw_output, response_schema)
    _check_empty_lists(result, response_schema)
    return result


def _serialize_prompt_messages(messages: list) -> str:
    """Convert a list of role/parts message dicts into a readable prompt string."""
    parts = []
    for msg in messages:
        role = msg.get("role", "system").upper()
        content = msg.get("parts", "")
        parts.append(f"[{role}]\n{content}")
    return "\n\n".join(parts)


async def invoke_llm(
    gpu_model,
    response_schema,
    contents,
    port=11434,
    remove_thinking=False,
):
    """
    Unified structured LLM invocation with retries and fallbacks:
    - GPU server (local Ollama)
    - Gemini API
    - OpenAI API

    Guarded by a concurrency semaphore to prevent GPU thrashing.
    """
    async with _LLM_SEMAPHORE:
        return await _invoke_llm_inner(
            gpu_model, response_schema, contents, port, remove_thinking
        )


async def _invoke_llm_inner(
    gpu_model,
    response_schema,
    contents,
    port,
    remove_thinking,
):
    parser = PydanticOutputParser(pydantic_object=response_schema)
    schema_name = getattr(response_schema, "__name__", "unknown")

    if isinstance(contents, list) and contents and isinstance(contents[0], dict) and "role" in contents[0]:
        serialized = _serialize_prompt_messages(contents)
    else:
        serialized = str(contents)

    is_answer_schema = hasattr(response_schema, "model_fields") and "answer" in response_schema.model_fields

    if is_answer_schema:
        prompt = f"""{serialized}

RESPONSE FORMAT — CRITICAL:
You MUST respond with a single valid JSON object matching this schema:
{parser.get_format_instructions()}

JSON RULES:
1. Output ONLY the JSON object — no markdown fences, no commentary, no text before or after.
2. Escape newlines as \\n and tabs as \\t within JSON string values.
3. If you use internal reasoning (e.g. <think> tags), produce the JSON AFTER the closing tag.
4. The "answer" field should contain your FULL, DETAILED response following the guidelines above. Do NOT truncate or shorten it.
5. For tables inside the answer field, use HTML <table> tags, NOT Markdown pipe tables.
6. Do NOT echo the schema definition. Never include "$defs", "$ref", "properties", "required", "title", "type":"object" or "description" as top-level keys. Only output the DATA that conforms to the schema.
"""
    else:
        prompt = f"""Extract structured data according to this model:
{parser.get_format_instructions()}

Input:
{serialized}

CRITICAL OUTPUT RULES:
1. Output must be valid JSON.
2. Escape newlines as \\n and tabs as \\t within JSON strings.
3. If you generate internal reasoning (e.g. inside <think> tags), you MUST produce the final JSON object AFTER the closing </think> tag.
4. Do not output any text before or after the JSON object.
5. Do NOT echo the schema definition. Never include "$defs", "$ref", "properties", "required", "title", "type":"object" or "description" as top-level keys. Only output the DATA that conforms to the schema.
6. Every list/array field must contain actual items. Do not return empty arrays unless the input data genuinely contains zero relevant items.
"""

    def _build_prompt(base, failed_output, parse_error):
        if failed_output and parse_error:
            logger.info("Self-correction: injecting previous output + error into prompt")
            return (
                f"{base}\n\n"
                "--- PREVIOUS ATTEMPT FAILED ---\n"
                "Your previous output could not be parsed. Fix the errors and output valid JSON only.\n\n"
                f"Previous output (rejected):\n{failed_output[:2000]}\n\n"
                f"Parse error:\n{parse_error}\n\n"
                "Fix the above errors and return ONLY valid JSON matching the schema."
            )
        return base

    # ── GPU SERVER (full retry cycle) ────────────────────
    last_failed_output = None
    last_parse_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        logger.info("Attempt %d/%d for schema=%s", attempt, MAX_RETRIES, schema_name)
        effective_prompt = _build_prompt(prompt, last_failed_output, last_parse_error)

        # ── Phase 0: INTERNAL API (opt-in, before GPU) ──────────
        use_internal = (
            SWITCHES.get("USE_INTERNAL", False)
            and INTERNALLLM is not None
            and not _skip_internal.get()
            and settings.INTERNAL_BASE_URL
            and settings.INTERNAL_API_TOKEN
        )
        if use_internal:
            internal_output = None
            internal_parse_error = False
            for blank_retry in range(2):
                s = time.time()
                try:
                    if SWITCHES.get("RATE_LIMIT_INTERNAL", True):
                        await _internal_rate_limiter.acquire()
                    logger.info("Trying INTERNAL API (attempt=%d)...", attempt)
                    internal_llm = INTERNALLLM(
                        model=settings.INTERNAL_MODEL_ID,
                        base_url=settings.INTERNAL_BASE_URL,
                        client_key=settings.INTERNAL_CLIENT_KEY,
                        api_token=settings.INTERNAL_API_TOKEN,
                        user_email=settings.INTERNAL_USER_EMAIL,
                    )
                    s = time.time()
                    internal_output = await asyncio.to_thread(
                        internal_llm._call, effective_prompt
                    )
                    elapsed = time.time() - s

                    if not internal_output or not internal_output.strip():
                        _log_llm_call(
                            source="internal", attempt=attempt,
                            model=settings.INTERNAL_MODEL_ID,
                            prompt=effective_prompt, output="",
                            error="empty response", elapsed_s=elapsed,
                            schema=schema_name, status="blank",
                        )
                        internal_output = None
                        continue

                    try:
                        structured = _try_parse(internal_output, parser, response_schema)
                    except Exception as parse_exc:
                        _log_llm_call(
                            source="internal", attempt=attempt,
                            model=settings.INTERNAL_MODEL_ID,
                            prompt=effective_prompt, output=internal_output,
                            error=str(parse_exc), elapsed_s=elapsed,
                            schema=schema_name, status="parse_error",
                        )
                        raise
                    _log_llm_call(
                        source="internal", attempt=attempt,
                        model=settings.INTERNAL_MODEL_ID,
                        prompt=effective_prompt, output=internal_output,
                        elapsed_s=elapsed, schema=schema_name, status="ok",
                    )
                    return structured
                except Exception as exc:
                    elapsed = time.time() - s
                    err = str(exc)
                    if internal_output:
                        # Parse error — feed back into the next attempt's prompt
                        # so INTERNAL gets a self-correction shot before GPU.
                        last_failed_output = internal_output
                        last_parse_error = err
                        internal_parse_error = True
                        _log_parse_failure(
                            source="internal",
                            attempt=attempt,
                            raw_output=internal_output,
                            error=err,
                            schema_name=schema_name,
                            prompt_snippet=effective_prompt if isinstance(effective_prompt, str) else str(effective_prompt),
                        )
                    else:
                        # Transport-level failure — set sticky skip so we
                        # don't keep hammering INTERNAL, and fall through to
                        # GPU on this same attempt.
                        _log_llm_call(
                            source="internal", attempt=attempt,
                            model=settings.INTERNAL_MODEL_ID,
                            prompt=effective_prompt, output="",
                            error=err, elapsed_s=elapsed,
                            schema=schema_name, status="transport_error",
                        )
                        _skip_internal.set(True)
                        logger.info(
                            "INTERNAL marked skipped for remainder of this request"
                        )
                    break
            # On a parse error, give INTERNAL the next attempt to self-correct
            # before falling through to GPU. Transport errors fall through now.
            if internal_parse_error:
                continue

        if gpu_model:
            llm_output = None
            for blank_retry in range(2):
                s = time.time()
                try:
                    logger.info("Trying GPU server (port=%d)...", port)
                    gpu_llm = _get_cached_llm(gpu_model, port)
                    s = time.time()
                    llm_output = await asyncio.wait_for(
                        asyncio.to_thread(gpu_llm._call, effective_prompt),
                        timeout=GPU_TIMEOUT,
                    )
                    elapsed = time.time() - s

                    if not llm_output or not llm_output.strip():
                        _log_llm_call(
                            source="gpu", attempt=attempt, model=gpu_model,
                            prompt=effective_prompt, output="",
                            error="empty response", elapsed_s=elapsed,
                            schema=schema_name, status="blank",
                        )
                        llm_output = None
                        continue

                    try:
                        structured = _try_parse(llm_output, parser, response_schema)
                    except Exception as parse_exc:
                        _log_llm_call(
                            source="gpu", attempt=attempt, model=gpu_model,
                            prompt=effective_prompt, output=llm_output,
                            error=str(parse_exc), elapsed_s=elapsed,
                            schema=schema_name, status="parse_error",
                        )
                        raise
                    _log_llm_call(
                        source="gpu", attempt=attempt, model=gpu_model,
                        prompt=effective_prompt, output=llm_output,
                        elapsed_s=elapsed, schema=schema_name, status="ok",
                    )
                    return structured
                except asyncio.TimeoutError:
                    elapsed = time.time() - s
                    _log_llm_call(
                        source="gpu", attempt=attempt, model=gpu_model,
                        prompt=effective_prompt, output="",
                        error=f"timeout after {GPU_TIMEOUT}s (port={port})",
                        elapsed_s=elapsed, schema=schema_name, status="timeout",
                    )
                    break
                except Exception as e:
                    elapsed = time.time() - s
                    error_str = str(e)
                    if llm_output:
                        last_failed_output = llm_output
                        last_parse_error = error_str
                        _log_parse_failure(
                            source="gpu",
                            attempt=attempt,
                            raw_output=llm_output,
                            error=error_str,
                            schema_name=schema_name,
                            prompt_snippet=effective_prompt if isinstance(effective_prompt, str) else str(effective_prompt),
                        )
                        logger.info(
                            "Self-correction: captured failed GPU output (%d chars)",
                            len(llm_output),
                        )
                    else:
                        _log_llm_call(
                            source="gpu", attempt=attempt, model=gpu_model,
                            prompt=effective_prompt, output="",
                            error=error_str, elapsed_s=elapsed,
                            schema=schema_name, status="transport_error",
                        )
                    break
            else:
                logger.warning("GPU returned empty output twice, moving to next attempt")
            if last_failed_output:
                continue

        # === GEMINI FALLBACK ===
        if SWITCHES["FALLBACK_TO_GEMINI"]:
            logger.info("Falling back to Gemini...")

            for _ in range(len(API_KEYS)):
                api_key = await _next_api_key()
                client = genai.Client(api_key=api_key)
                s = time.time()
                raw_output = None
                try:
                    config = genai.types.GenerateContentConfig(
                        temperature=0.2,
                        max_output_tokens=GEMINI_MAX_OUTPUT_TOKENS,
                        response_mime_type="text/plain",
                        safety_settings=[],
                    )

                    if remove_thinking:
                        config.thinking_config = genai.types.ThinkingConfig(
                            thinking_budget=0
                        )

                    response = await asyncio.wait_for(
                        asyncio.to_thread(
                            client.models.generate_content,
                            model=FALLBACK_GEMINI_MODEL,
                            contents=effective_prompt,
                            config=config,
                        ),
                        timeout=GEMINI_TIMEOUT,
                    )

                    try:
                        raw_output = response.text or str(response)
                    except Exception:
                        raw_output = str(response)

                    elapsed = time.time() - s
                    try:
                        structured = _try_parse(raw_output, parser, response_schema)
                    except Exception as parse_exc:
                        _log_llm_call(
                            source="gemini", attempt=attempt,
                            model=FALLBACK_GEMINI_MODEL,
                            prompt=effective_prompt, output=raw_output or "",
                            error=str(parse_exc), elapsed_s=elapsed,
                            schema=schema_name, status="parse_error",
                        )
                        raise
                    _log_llm_call(
                        source="gemini", attempt=attempt,
                        model=FALLBACK_GEMINI_MODEL,
                        prompt=effective_prompt, output=raw_output or "",
                        elapsed_s=elapsed, schema=schema_name, status="ok",
                    )
                    return structured

                except asyncio.TimeoutError:
                    elapsed = time.time() - s
                    _log_llm_call(
                        source="gemini", attempt=attempt,
                        model=FALLBACK_GEMINI_MODEL,
                        prompt=effective_prompt, output="",
                        error=f"timeout after {GEMINI_TIMEOUT}s",
                        elapsed_s=elapsed, schema=schema_name, status="timeout",
                    )
                except Exception as e:
                    elapsed = time.time() - s
                    if raw_output:
                        _log_parse_failure(
                            source="gemini",
                            attempt=attempt,
                            raw_output=raw_output,
                            error=str(e),
                            schema_name=schema_name,
                        )
                    else:
                        _log_llm_call(
                            source="gemini", attempt=attempt,
                            model=FALLBACK_GEMINI_MODEL,
                            prompt=effective_prompt, output="",
                            error=str(e), elapsed_s=elapsed,
                            schema=schema_name, status="transport_error",
                        )
                    await asyncio.sleep(0.2)

        # === OPENAI FALLBACK ===
        if SWITCHES["FALLBACK_TO_OPENAI"]:
            openai_raw = None
            s = time.time()
            try:
                logger.info("Falling back to OpenAI...")
                s = time.time()
                response = await asyncio.wait_for(
                    openai_client.chat.completions.create(
                        model=FALLBACK_OPENAI_MODEL,
                        messages=[{"role": "user", "content": effective_prompt}],
                        temperature=0.2,
                    ),
                    timeout=OPENAI_TIMEOUT,
                )

                openai_raw = response.choices[0].message.content
                elapsed = time.time() - s
                try:
                    structured = _try_parse(openai_raw, parser, response_schema)
                except Exception as parse_exc:
                    _log_llm_call(
                        source="openai", attempt=attempt,
                        model=FALLBACK_OPENAI_MODEL,
                        prompt=effective_prompt, output=openai_raw or "",
                        error=str(parse_exc), elapsed_s=elapsed,
                        schema=schema_name, status="parse_error",
                    )
                    raise
                _log_llm_call(
                    source="openai", attempt=attempt,
                    model=FALLBACK_OPENAI_MODEL,
                    prompt=effective_prompt, output=openai_raw or "",
                    elapsed_s=elapsed, schema=schema_name, status="ok",
                )
                return structured

            except asyncio.TimeoutError:
                elapsed = time.time() - s
                _log_llm_call(
                    source="openai", attempt=attempt,
                    model=FALLBACK_OPENAI_MODEL,
                    prompt=effective_prompt, output="",
                    error=f"timeout after {OPENAI_TIMEOUT}s",
                    elapsed_s=elapsed, schema=schema_name, status="timeout",
                )
            except Exception as e:
                elapsed = time.time() - s
                if openai_raw:
                    _log_parse_failure(
                        source="openai",
                        attempt=attempt,
                        raw_output=openai_raw,
                        error=str(e),
                        schema_name=schema_name,
                    )
                else:
                    _log_llm_call(
                        source="openai", attempt=attempt,
                        model=FALLBACK_OPENAI_MODEL,
                        prompt=effective_prompt, output="",
                        error=str(e), elapsed_s=elapsed,
                        schema=schema_name, status="transport_error",
                    )

        await asyncio.sleep(2)

    raise RuntimeError(
        "All fallback attempts failed (INTERNAL + GPU + Gemini + OpenAI)."
    )
