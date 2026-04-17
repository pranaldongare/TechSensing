"""Per-user company alias registry.

Stored at ``data/{user_id}/sensing/aliases.json`` as::

    {"Meta": ["Facebook", "FB", "Meta Platforms"], ...}

Used to expand search queries so that "Meta" also picks up hits for
"Facebook" / "FB" etc.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Dict, List

import aiofiles

logger = logging.getLogger("sensing.aliases")


def _path(user_id: str) -> str:
    return os.path.join("data", user_id, "sensing", "aliases.json")


async def load_aliases(user_id: str) -> Dict[str, List[str]]:
    """Load alias map for user. Returns empty dict if not set."""
    path = _path(user_id)
    if not os.path.exists(path):
        return {}
    try:
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            raw = await f.read()
        data = json.loads(raw)
        if not isinstance(data, dict):
            return {}
        # Coerce values to list[str] and strip empties
        return {
            str(k).strip(): [str(v).strip() for v in (vs or []) if str(v).strip()]
            for k, vs in data.items()
            if str(k).strip()
        }
    except Exception as e:
        logger.warning(f"[aliases] load failed for {user_id}: {e}")
        return {}


async def save_aliases(user_id: str, aliases: Dict[str, List[str]]) -> None:
    """Persist alias map. Overwrites entirely."""
    path = _path(user_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cleaned = {
        str(k).strip(): [str(v).strip() for v in (vs or []) if str(v).strip()]
        for k, vs in (aliases or {}).items()
        if str(k).strip()
    }
    async with aiofiles.open(path, "w", encoding="utf-8") as f:
        await f.write(json.dumps(cleaned, ensure_ascii=False, indent=2))


def expand_company(
    company: str,
    aliases: Dict[str, List[str]],
) -> List[str]:
    """Return [company, *aliases] if a mapping exists (case-insensitive).

    Always includes the canonical name as the first element. Deduplicates
    case-insensitively while preserving casing order.
    """
    if not company:
        return []
    canonical = company.strip()
    low = canonical.lower()

    extras: List[str] = []
    for key, vals in aliases.items():
        if key.strip().lower() == low:
            extras = [v for v in vals if v]
            break

    seen: set = {low}
    out: List[str] = [canonical]
    for v in extras:
        vl = v.strip().lower()
        if vl and vl not in seen:
            seen.add(vl)
            out.append(v.strip())
    return out
