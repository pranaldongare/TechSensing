"""Per-user company watchlists for Key Companies.

Stored at ``data/{user_id}/sensing/watchlists.json`` as a list of::

    {
        "id": "wl_abc123",
        "name": "AI Frontier Labs",
        "companies": ["OpenAI", "Anthropic", "Google DeepMind"],
        "highlight_domain": "Generative AI",
        "period_days": 7,
        "created_at": "2026-04-16T...",
        "updated_at": "2026-04-16T..."
    }
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import aiofiles

logger = logging.getLogger("sensing.watchlists")


def _path(user_id: str) -> str:
    return os.path.join("data", user_id, "sensing", "watchlists.json")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def list_watchlists(user_id: str) -> List[Dict[str, Any]]:
    path = _path(user_id)
    if not os.path.exists(path):
        return []
    try:
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            raw = await f.read()
        data = json.loads(raw)
        if not isinstance(data, list):
            return []
        return data
    except Exception as e:
        logger.warning(f"[watchlists] load failed for {user_id}: {e}")
        return []


async def _persist(user_id: str, items: List[Dict[str, Any]]) -> None:
    path = _path(user_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    async with aiofiles.open(path, "w", encoding="utf-8") as f:
        await f.write(json.dumps(items, ensure_ascii=False, indent=2))


def _sanitize(body: Dict[str, Any]) -> Dict[str, Any]:
    companies = [
        str(c).strip()
        for c in (body.get("companies") or [])
        if str(c).strip()
    ]
    return {
        "name": str(body.get("name") or "Untitled watchlist").strip(),
        "companies": companies[:30],
        "highlight_domain": str(body.get("highlight_domain") or "").strip(),
        "period_days": max(1, min(int(body.get("period_days") or 7), 30)),
    }


async def create_watchlist(
    user_id: str,
    body: Dict[str, Any],
) -> Dict[str, Any]:
    items = await list_watchlists(user_id)
    clean = _sanitize(body)
    record = {
        "id": f"wl_{uuid.uuid4().hex[:10]}",
        **clean,
        "created_at": _now(),
        "updated_at": _now(),
    }
    items.append(record)
    await _persist(user_id, items)
    return record


async def get_watchlist(
    user_id: str, watchlist_id: str
) -> Optional[Dict[str, Any]]:
    items = await list_watchlists(user_id)
    for it in items:
        if it.get("id") == watchlist_id:
            return it
    return None


async def update_watchlist(
    user_id: str, watchlist_id: str, body: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    items = await list_watchlists(user_id)
    for i, it in enumerate(items):
        if it.get("id") == watchlist_id:
            updated = {**it, **_sanitize(body), "updated_at": _now()}
            items[i] = updated
            await _persist(user_id, items)
            return updated
    return None


async def delete_watchlist(user_id: str, watchlist_id: str) -> bool:
    items = await list_watchlists(user_id)
    new_items = [it for it in items if it.get("id") != watchlist_id]
    if len(new_items) == len(items):
        return False
    await _persist(user_id, new_items)
    return True
