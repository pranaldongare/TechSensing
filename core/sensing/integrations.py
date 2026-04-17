"""Per-user integration credentials (Notion, Jira, Linear, ...).

Stored at ``data/{user_id}/sensing/integrations.json`` with shape::

    {
        "notion": {
            "token": "secret_...",
            "default_parent_page_id": "xxxxxxxxxxxx"
        },
        "jira": {
            "base_url": "https://acme.atlassian.net",
            "email": "me@acme.com",
            "api_token": "xxx",
            "project_key": "TECH"
        },
        "linear": {
            "api_key": "lin_api_...",
            "team_id": "..."
        }
    }

Tokens are **not** encrypted at rest — this is intentional, consistent
with how other per-user credentials are stored in this project. Access
is gated by the backend's existing user-id scoping.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict

import aiofiles

logger = logging.getLogger("sensing.integrations")


SUPPORTED_PROVIDERS = {"notion", "jira", "linear"}


def _path(user_id: str) -> str:
    return os.path.join("data", user_id, "sensing", "integrations.json")


async def load_integrations(user_id: str) -> Dict[str, Any]:
    path = _path(user_id)
    if not os.path.exists(path):
        return {}
    try:
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            raw = await f.read()
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning(f"[integrations] load failed for {user_id}: {e}")
        return {}


async def _persist(user_id: str, data: Dict[str, Any]) -> None:
    path = _path(user_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    async with aiofiles.open(path, "w", encoding="utf-8") as f:
        await f.write(json.dumps(data, ensure_ascii=False, indent=2))


async def get_integration(user_id: str, provider: str) -> Dict[str, Any]:
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(f"Unknown integration provider: {provider}")
    data = await load_integrations(user_id)
    return data.get(provider, {}) or {}


async def set_integration(
    user_id: str, provider: str, config: Dict[str, Any]
) -> Dict[str, Any]:
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(f"Unknown integration provider: {provider}")
    data = await load_integrations(user_id)
    data[provider] = config
    await _persist(user_id, data)
    return config


async def delete_integration(user_id: str, provider: str) -> bool:
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(f"Unknown integration provider: {provider}")
    data = await load_integrations(user_id)
    if provider not in data:
        return False
    del data[provider]
    await _persist(user_id, data)
    return True


def redact(config: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy with secret-like fields masked to last 4 chars."""
    out: Dict[str, Any] = {}
    secret_keys = {"token", "api_token", "api_key", "secret", "password"}
    for k, v in (config or {}).items():
        if k in secret_keys and isinstance(v, str) and v:
            out[k] = f"***{v[-4:]}" if len(v) > 4 else "***"
        else:
            out[k] = v
    return out
