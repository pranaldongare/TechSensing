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

        try:
            response = requests.post(
                f"{self.base_url}/openapi/chat/v1/messages",
                headers=headers,
                json=request_body,
                timeout=600,
            )
            response.raise_for_status()

            data = response.json()

            if data.get("status") != "SUCCESS":
                error_code = data.get("responseCode", "UNKNOWN")
                error_msg = data.get("message", f"API error: {error_code}")
                raise RuntimeError(f"INTERNAL API failed: {error_code} - {error_msg}")

            content = data.get("content", "")

            # Strip reasoning tags (same pattern as remote_llm.py / local_llm.py)
            cleaned = re.sub(
                r"<thinking>.*?</thinking>", "", content, flags=re.DOTALL
            )
            cleaned = re.sub(
                r"<reasoning>.*?</reasoning>", "", cleaned, flags=re.DOTALL
            )

            return cleaned.strip()

        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Failed to call INTERNAL API: {e}") from e
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"Unexpected error calling INTERNAL API: {e}") from e
