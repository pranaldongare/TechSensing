"""Per-user exclusion keywords.

Stored at ``data/{user_id}/sensing/exclusions.json`` as::

    {
        "global": ["clickbait", "rumor"],
        "per_company": {
            "Apple": ["fruit", "record label"]
        }
    }

Exclusion matching is substring + case-insensitive on article title and
snippet. If any exclusion keyword appears, the article is dropped before
LLM synthesis.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Dict, Iterable, List

import aiofiles

from core.sensing.ingest import RawArticle

logger = logging.getLogger("sensing.exclusions")


def _path(user_id: str) -> str:
    return os.path.join("data", user_id, "sensing", "exclusions.json")


def _empty() -> Dict[str, object]:
    return {"global": [], "per_company": {}}


async def load_exclusions(user_id: str) -> Dict[str, object]:
    """Load exclusion config. Returns ``{"global": [], "per_company": {}}``."""
    path = _path(user_id)
    if not os.path.exists(path):
        return _empty()
    try:
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            raw = await f.read()
        data = json.loads(raw) or {}
        return {
            "global": [
                str(x).strip() for x in (data.get("global") or []) if str(x).strip()
            ],
            "per_company": {
                str(k).strip(): [
                    str(x).strip() for x in (vs or []) if str(x).strip()
                ]
                for k, vs in (data.get("per_company") or {}).items()
                if str(k).strip()
            },
        }
    except Exception as e:
        logger.warning(f"[exclusions] load failed for {user_id}: {e}")
        return _empty()


async def save_exclusions(user_id: str, exclusions: Dict[str, object]) -> None:
    """Persist exclusion config. Overwrites entirely."""
    path = _path(user_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cleaned = {
        "global": [
            str(x).strip() for x in (exclusions.get("global") or []) if str(x).strip()
        ],
        "per_company": {
            str(k).strip(): [
                str(x).strip() for x in (vs or []) if str(x).strip()
            ]
            for k, vs in (exclusions.get("per_company") or {}).items()
            if str(k).strip()
        },
    }
    async with aiofiles.open(path, "w", encoding="utf-8") as f:
        await f.write(json.dumps(cleaned, ensure_ascii=False, indent=2))


def _match(text: str, needles: Iterable[str]) -> bool:
    if not text:
        return False
    low = text.lower()
    return any(n.lower() in low for n in needles if n)


def apply_exclusions(
    articles: List[RawArticle],
    exclusions: Dict[str, object],
    company: str = "",
) -> List[RawArticle]:
    """Drop articles matching global or company-specific exclusion keywords."""
    global_kw: List[str] = list(exclusions.get("global") or [])
    per_company = exclusions.get("per_company") or {}
    co_kw: List[str] = list(per_company.get(company, []))
    all_kw = [k for k in (global_kw + co_kw) if k]
    if not all_kw:
        return articles

    kept: List[RawArticle] = []
    dropped = 0
    for a in articles:
        text = f"{a.title or ''} {a.snippet or ''}"
        if _match(text, all_kw):
            dropped += 1
            continue
        kept.append(a)
    if dropped:
        logger.info(
            f"[exclusions] dropped {dropped} article(s) for {company or 'global'}"
        )
    return kept
