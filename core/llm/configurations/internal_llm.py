"""
INTERNAL LLM API wrapper.

Implements the LangChain ``LLM`` interface so it plugs into the same
``invoke_llm()`` flow as the local Ollama (MyServerLLM) backend. Used as an
optional primary inference path before the local-GPU + Gemini + OpenAI
fallback chain. Activated via ``USE_INTERNAL=true`` in ``.env``.

Mirror of PRISM's ``INTERNAL_llm.py`` — kept byte-equivalent so the corporate
INTERNAL API contract is identical across projects.
"""

import re
from typing import List, Optional

import requests
from langchain_core.language_models import LLM


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
        try:
            response = requests.post(
                url,
                headers=headers,
                json=request_body,
                timeout=600,
            )
        except requests.exceptions.RequestException as e:
            # Pure transport failure — no response body to inspect.
            raise RuntimeError(
                f"Failed to call INTERNAL API ({url}): {type(e).__name__}: {e}"
            ) from e

        # Capture status + body BEFORE raise_for_status so HTTP errors carry
        # the server's actual error payload instead of a generic HTTPError.
        status_code = response.status_code
        try:
            body_text = response.text or ""
        except Exception:
            body_text = "<could not read response body>"

        if status_code >= 400:
            # Truncate massive bodies to keep error messages readable.
            preview = body_text[:2000] + ("..." if len(body_text) > 2000 else "")
            raise RuntimeError(
                f"INTERNAL API HTTP {status_code} from {url}\n"
                f"  response body: {preview}"
            )

        try:
            data = response.json()
        except Exception as e:
            preview = body_text[:1000] + ("..." if len(body_text) > 1000 else "")
            raise RuntimeError(
                f"INTERNAL API returned non-JSON response (HTTP {status_code}): "
                f"{type(e).__name__}: {e}\n"
                f"  body preview: {preview}"
            ) from e

        if data.get("status") != "SUCCESS":
            error_code = data.get("responseCode", "UNKNOWN")
            error_msg = data.get("message", f"API error: {error_code}")
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

        return cleaned.strip()
