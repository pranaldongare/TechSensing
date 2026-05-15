"""
INTERNAL LLM API wrapper.

Implements the LangChain ``LLM`` interface so it plugs into the same
``invoke_llm()`` flow as the local Ollama (MyServerLLM) backend. Used as an
optional primary inference path before the local-GPU + Gemini + OpenAI
fallback chain. Activated via ``USE_INTERNAL=true`` in ``.env``.

Mirror of PRISM's ``INTERNAL_llm.py`` — kept byte-equivalent so the corporate
INTERNAL API contract is identical across projects.

Every HTTP exchange (success OR failure) is appended to
``DEBUG/llm_calls/internal_raw.jsonl`` with the full request body, request
headers (auth token redacted), response status, response headers, and
response body — no truncation. Disable via ``LLM_CALL_LOG=false`` if disk
usage is a concern.
"""

import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests
from langchain_core.language_models import LLM

logger = logging.getLogger("llm.internal")

# ── Raw exchange log (full request + response per call) ──────────
_RAW_LOG_ENABLED = os.getenv("LLM_CALL_LOG", "true").lower() != "false"
_RAW_LOG_PATH = os.path.join("DEBUG", "llm_calls", "internal_raw.jsonl")
if _RAW_LOG_ENABLED:
    os.makedirs(os.path.dirname(_RAW_LOG_PATH), exist_ok=True)


def _redact_token(value: str) -> str:
    """Redact a Bearer token while preserving enough for correlation.

    Returns the literal "Bearer " prefix (if present) followed by the first
    6 and last 4 chars of the actual token, separated by ``...``. Tokens
    shorter than 12 chars are fully masked.
    """
    if not value:
        return ""
    parts = value.split(" ", 1)
    prefix = ""
    actual = value
    if len(parts) == 2 and parts[0].lower() == "bearer":
        prefix = parts[0] + " "
        actual = parts[1]
    if len(actual) <= 12:
        return f"{prefix}***"
    return f"{prefix}{actual[:6]}...{actual[-4:]} (len={len(actual)})"


def _redact_headers(headers: Dict[str, str]) -> Dict[str, str]:
    """Return a copy of headers with sensitive values masked."""
    redacted = {}
    for key, value in headers.items():
        kl = key.lower()
        if "token" in kl or "auth" in kl or "key" in kl:
            redacted[key] = _redact_token(value)
        else:
            redacted[key] = value
    return redacted


def _try_get_tracking_id() -> str:
    """Best-effort lookup of the per-request tracking_id ContextVar."""
    try:
        from core.llm.client import tracking_id_var
        return tracking_id_var.get("")
    except Exception:
        return ""


def _log_raw_exchange(entry: Dict[str, Any]) -> None:
    """Append one full HTTP exchange to the raw log."""
    if not _RAW_LOG_ENABLED:
        return
    try:
        with open(_RAW_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except Exception as exc:
        # Never let logging failures break the actual call.
        logger.warning("Failed to write internal_raw.jsonl: %s", exc)


class INTERNALLLM(LLM):
    """
    Custom LLM wrapper for INTERNAL API.

    Implements the same LangChain interface as MyServerLLM, ensuring
    compatibility with the existing invoke_llm() function.
    """

    model: str = ""
    base_url: str = ""
    client_key: str = ""
    api_token: str = ""
    user_email: str = ""
    use_stream: bool = False

    def __init__(
        self,
        model: str,
        base_url: str,
        client_key: str,
        api_token: str,
        user_email: str = "",
        use_stream: bool = False,
        **kwargs,
    ):
        super().__init__(model=model, **kwargs)
        self.base_url = base_url
        self.client_key = client_key
        self.api_token = api_token
        self.user_email = user_email
        self.use_stream = use_stream

    @property
    def _llm_type(self) -> str:
        return "INTERNAL_llm"

    def _call(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        max_new_tokens: int = 8000,
        temperature: float = 0.4,
        top_k: int = 14,
        top_p: float = 0.94,
        repetition_penalty: float = 1.04,
        system_prompt: Optional[str] = None,
    ) -> str:
        """Call INTERNAL API synchronously.

        Returns:
            Generated text response (with ``<thinking>`` / ``<reasoning>``
            tags stripped).

        Raises:
            RuntimeError: If API call fails or returns a non-SUCCESS status.
        """
        # Ensure API token has "Bearer " prefix
        api_token = self.api_token
        if not api_token.startswith("Bearer "):
            api_token = f"Bearer {api_token}"

        headers = {
            "x-generative-ai-client": self.client_key,
            "x-openapi-token": api_token,
            "x-generative-ai-user-email": self.user_email,
            "Content-Type": "application/json",
        }

        request_body = {
            "modelIds": [self.model],
            "contents": [prompt],
            "isStream": self.use_stream,
            "llmConfig": {
                "max_new_tokens": max_new_tokens,
                "seed": None,
                "top_k": top_k,
                "top_p": top_p,
                "temperature": temperature,
                "repetition_penalty": repetition_penalty,
            },
        }

        if system_prompt:
            request_body["systemPrompt"] = system_prompt

        url = f"{self.base_url}/openapi/chat/v1/messages"
        tracking_id = _try_get_tracking_id()
        started_at = time.time()

        # Pre-build the part of the log entry that's known before the call.
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tracking_id": tracking_id,
            "method": "POST",
            "url": url,
            "request_headers": _redact_headers(headers),
            "request_body": request_body,
        }

        try:
            response = requests.post(
                url,
                headers=headers,
                json=request_body,
                timeout=600,
            )
        except requests.exceptions.RequestException as e:
            elapsed = time.time() - started_at
            log_entry["elapsed_s"] = round(elapsed, 3)
            log_entry["status"] = "transport_error"
            log_entry["error"] = f"{type(e).__name__}: {e}"
            _log_raw_exchange(log_entry)
            raise RuntimeError(
                f"Failed to call INTERNAL API ({url}): {type(e).__name__}: {e}"
            ) from e

        elapsed = time.time() - started_at
        log_entry["elapsed_s"] = round(elapsed, 3)

        # Capture status + body BEFORE raise_for_status so HTTP errors carry
        # the server's actual error payload instead of a generic HTTPError.
        status_code = response.status_code
        try:
            body_text = response.text or ""
        except Exception:
            body_text = "<could not read response body>"

        log_entry["response_status_code"] = status_code
        log_entry["response_headers"] = dict(response.headers)
        log_entry["response_body"] = body_text

        if status_code >= 400:
            log_entry["status"] = "http_error"
            log_entry["error"] = f"HTTP {status_code}"
            _log_raw_exchange(log_entry)
            preview = body_text[:2000] + ("..." if len(body_text) > 2000 else "")
            raise RuntimeError(
                f"INTERNAL API HTTP {status_code} from {url}\n"
                f"  response body: {preview}"
            )

        try:
            data = response.json()
        except Exception as e:
            log_entry["status"] = "non_json_response"
            log_entry["error"] = f"{type(e).__name__}: {e}"
            _log_raw_exchange(log_entry)
            preview = body_text[:1000] + ("..." if len(body_text) > 1000 else "")
            raise RuntimeError(
                f"INTERNAL API returned non-JSON response (HTTP {status_code}): "
                f"{type(e).__name__}: {e}\n"
                f"  body preview: {preview}"
            ) from e

        if data.get("status") != "SUCCESS":
            error_code = data.get("responseCode", "UNKNOWN")
            error_msg = data.get("message", f"API error: {error_code}")
            log_entry["status"] = "api_error"
            log_entry["error"] = f"code={error_code}, message={error_msg}"
            _log_raw_exchange(log_entry)
            raise RuntimeError(
                f"INTERNAL API status != SUCCESS (HTTP {status_code}): "
                f"code={error_code}, message={error_msg}"
            )

        content = data.get("content", "")

        # Strip reasoning tags (same pattern as remote_llm.py / local_llm.py)
        cleaned = re.sub(
            r"<thinking>.*?</thinking>", "", content, flags=re.DOTALL
        )
        cleaned = re.sub(
            r"<reasoning>.*?</reasoning>", "", cleaned, flags=re.DOTALL
        )

        log_entry["status"] = "ok"
        log_entry["error"] = ""
        _log_raw_exchange(log_entry)
        return cleaned.strip()
