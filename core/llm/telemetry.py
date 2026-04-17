"""LLM cost & latency telemetry wrapper.

``invoke_llm`` itself does not return usage statistics. Rather than
changing its signature (risking callers), this module provides a thin
async context manager / wrapper that records per-call timing and rough
token estimates, and persists them under
``data/{user_id}/sensing/telemetry_{tracking_id}.json`` so the UI can
show a cost/latency badge (#28).

Token estimation uses a cheap char/4 heuristic; good enough to give the
user a sense of scale without pulling in ``tiktoken`` as a hard dep.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

import aiofiles

from core.llm.client import invoke_llm as _invoke_llm

logger = logging.getLogger("llm.telemetry")


def _estimate_tokens(obj: Any) -> int:
    """Very rough token estimate (chars/4) on prompt-like structures."""
    if obj is None:
        return 0
    if isinstance(obj, str):
        return max(0, len(obj) // 4)
    if isinstance(obj, list):
        return sum(_estimate_tokens(x) for x in obj)
    if isinstance(obj, dict):
        total = 0
        for k, v in obj.items():
            total += _estimate_tokens(k) + _estimate_tokens(v)
        return total
    try:
        return max(0, len(str(obj)) // 4)
    except Exception:
        return 0


class TelemetryCollector:
    """Accumulates per-call telemetry for one run (tracking_id).

    Use as::

        tel = TelemetryCollector(user_id, tracking_id, kind="key_companies")
        result = await tel.invoke_llm(gpu_model=..., response_schema=..., contents=prompt, port=...)
        ...
        await tel.save()
    """

    def __init__(
        self,
        user_id: str,
        tracking_id: str,
        kind: str = "generic",
    ) -> None:
        self.user_id = user_id
        self.tracking_id = tracking_id
        self.kind = kind
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.calls: List[Dict[str, Any]] = []
        self._lock = asyncio.Lock()

    async def invoke_llm(
        self,
        *,
        gpu_model: str,
        response_schema: Any,
        contents: Any,
        port: int,
        label: str = "",
        **kwargs: Any,
    ):
        """Passthrough to ``invoke_llm`` with timing/size recording."""
        start = time.time()
        in_tokens = _estimate_tokens(contents)
        ok = True
        err = ""
        result: Any = None
        try:
            result = await _invoke_llm(
                gpu_model=gpu_model,
                response_schema=response_schema,
                contents=contents,
                port=port,
                **kwargs,
            )
            return result
        except Exception as e:
            ok = False
            err = str(e)
            raise
        finally:
            elapsed = time.time() - start
            # Try to estimate output size
            out_tokens = 0
            try:
                if result is not None and hasattr(result, "model_dump"):
                    out_tokens = _estimate_tokens(result.model_dump())
                elif result is not None:
                    out_tokens = _estimate_tokens(result)
            except Exception:
                out_tokens = 0
            async with self._lock:
                self.calls.append(
                    {
                        "label": label or getattr(response_schema, "__name__", "llm_call"),
                        "model": gpu_model,
                        "port": port,
                        "elapsed_s": round(elapsed, 3),
                        "input_tokens_est": in_tokens,
                        "output_tokens_est": out_tokens,
                        "ok": ok,
                        "error": err,
                        "at": datetime.now(timezone.utc).isoformat(),
                    }
                )

    def summary(self) -> Dict[str, Any]:
        total_calls = len(self.calls)
        ok_calls = sum(1 for c in self.calls if c.get("ok"))
        total_elapsed = round(sum(c.get("elapsed_s", 0.0) for c in self.calls), 3)
        total_in = sum(c.get("input_tokens_est", 0) for c in self.calls)
        total_out = sum(c.get("output_tokens_est", 0) for c in self.calls)
        return {
            "tracking_id": self.tracking_id,
            "kind": self.kind,
            "started_at": self.started_at,
            "total_calls": total_calls,
            "successful_calls": ok_calls,
            "total_elapsed_s": total_elapsed,
            "total_input_tokens_est": total_in,
            "total_output_tokens_est": total_out,
            "calls": self.calls,
        }

    def _path(self) -> str:
        return os.path.join(
            "data",
            self.user_id,
            "sensing",
            f"telemetry_{self.tracking_id}.json",
        )

    async def save(self) -> str:
        path = self._path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        payload = self.summary()
        try:
            async with aiofiles.open(path, "w", encoding="utf-8") as f:
                await f.write(json.dumps(payload, ensure_ascii=False, indent=2))
        except Exception as e:
            logger.warning(f"[telemetry] save failed {path}: {e}")
        return path


async def load_telemetry(user_id: str, tracking_id: str) -> Optional[Dict[str, Any]]:
    """Load saved telemetry for a given run, or ``None`` if missing."""
    path = os.path.join(
        "data", user_id, "sensing", f"telemetry_{tracking_id}.json"
    )
    if not os.path.exists(path):
        return None
    try:
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            raw = await f.read()
        return json.loads(raw)
    except Exception as e:
        logger.warning(f"[telemetry] load failed {path}: {e}")
        return None
