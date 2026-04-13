from contextlib import contextmanager
import os
import re
import threading
from typing import Dict, List, Optional, Tuple

from langchain_core.language_models import LLM
from langchain_ollama import ChatOllama
from pydantic import PrivateAttr

from core.config import settings

# Concurrency limit per (model, port) — should match OLLAMA_NUM_PARALLEL
OLLAMA_CONCURRENCY = int(os.environ.get("OLLAMA_NUM_PARALLEL", 2))

# Global dictionary of semaphores per (model, port)
_locks: Dict[Tuple[str, int], threading.Semaphore] = {}
_locks_global_lock = threading.Lock()  # Protects access to the _locks dict

LOCAL_BASE_URL = settings.LOCAL_BASE_URL


@contextmanager
def model_port_lock(model: str, port: int):
    """
    Context manager that allows up to OLLAMA_CONCURRENCY concurrent requests
    per (model, port). Uses a semaphore instead of a lock to enable parallel
    requests when Ollama is configured with OLLAMA_NUM_PARALLEL > 1.
    """
    key = (model, port)

    # Ensure thread-safe creation of semaphores
    with _locks_global_lock:
        if key not in _locks:
            _locks[key] = threading.Semaphore(OLLAMA_CONCURRENCY)

    semaphore = _locks[key]
    semaphore.acquire()
    try:
        yield
    finally:
        semaphore.release()


class MyServerLLM(LLM):
    """
    Custom LLM wrapper using ChatOllama to call a locally running Ollama model.
    Uses semaphore to limit concurrent requests per (model, port) to OLLAMA_CONCURRENCY.
    """

    model: str
    port: int
    _client: ChatOllama = PrivateAttr()

    def __init__(self, model: str, port: int = 11434, **kwargs):
        print(f"Initializing MyOllamaLLM with model={model} at port={port}")
        super().__init__(model=model, port=port, **kwargs)

        from core.constants import MODEL_OUTPUT_TOKENS

        self._client = ChatOllama(
            model=model,
            base_url=f"{LOCAL_BASE_URL}:{port}",
            timeout=1000,
            num_predict=MODEL_OUTPUT_TOKENS,
            **kwargs,
        )

    @property
    def _llm_type(self) -> str:
        return "ollama_local_llm"

    def _call(self, prompt: str, stop: Optional[List[str]] = None) -> str:
        """
        Call the local Ollama model using ChatOllama.
        Limits concurrent requests per (model, port) via semaphore.
        """
        with model_port_lock(self.model, self.port):
            # Read thinking switch at call time so UI toggles take effect immediately
            from core.constants import SWITCHES

            self._client.reasoning = not SWITCHES.get("DISABLE_THINKING", True)
            print(f"Processing request for model={self.model}, port={self.port}")
            try:
                response = self._client.invoke(prompt, stop=stop)
                cleaned_text = re.sub(
                    r"<think>.*?</think>", "", response.content, flags=re.DOTALL
                )
                cleaned_text = re.sub(
                    r"<reasoning>.*?</reasoning>", "", cleaned_text, flags=re.DOTALL
                )
                return cleaned_text.strip()
            except Exception as e:
                raise RuntimeError(f"Failed to call Ollama locally: {e}") from e
