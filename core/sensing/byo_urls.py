"""Per-user "bring-your-own URLs" registry.

Lets users paste authoritative URLs that should always be included in a
Company Analysis or Key Companies run for a given company, regardless of
what DDG / RSS / other providers surface.

Stored at ``data/{user_id}/sensing/byo_urls.json`` as::

    {"Apple": ["https://...", "https://..."], ...}
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Dict, List

import aiofiles

from core.sensing.ingest import RawArticle, extract_full_text

logger = logging.getLogger("sensing.byo_urls")


def _path(user_id: str) -> str:
    return os.path.join("data", user_id, "sensing", "byo_urls.json")


async def load_byo_urls(user_id: str) -> Dict[str, List[str]]:
    path = _path(user_id)
    if not os.path.exists(path):
        return {}
    try:
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            raw = await f.read()
        data = json.loads(raw)
        if not isinstance(data, dict):
            return {}
        return {
            str(k).strip(): [str(v).strip() for v in (vs or []) if str(v).strip()]
            for k, vs in data.items()
            if str(k).strip()
        }
    except Exception as e:
        logger.warning(f"[byo_urls] load failed for {user_id}: {e}")
        return {}


async def save_byo_urls(user_id: str, mapping: Dict[str, List[str]]) -> None:
    path = _path(user_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cleaned = {
        str(k).strip(): [str(v).strip() for v in (vs or []) if str(v).strip()]
        for k, vs in (mapping or {}).items()
        if str(k).strip()
    }
    async with aiofiles.open(path, "w", encoding="utf-8") as f:
        await f.write(json.dumps(cleaned, ensure_ascii=False, indent=2))


async def _fetch_as_article(url: str) -> RawArticle:
    """Wrap a URL as a RawArticle, then run ``extract_full_text`` on it."""
    article = RawArticle(
        title=url,
        url=url,
        source="BYO",
        snippet="",
    )
    try:
        article = await extract_full_text(article)
        # If trafilatura populated content and first line looks like a
        # title, promote it.
        if article.content:
            first = article.content.splitlines()[0].strip()
            if 10 <= len(first) <= 200:
                article.title = first
    except Exception as e:
        logger.debug(f"[byo_urls] extract failed for {url}: {e}")
    return article


async def fetch_byo_articles(
    user_id: str, company: str
) -> List[RawArticle]:
    """Return ``RawArticle``s for the user's BYO URLs for this company."""
    mapping = await load_byo_urls(user_id)
    urls = mapping.get(company.strip(), []) if company else []
    if not urls:
        return []
    logger.info(f"[byo_urls] {company}: {len(urls)} user-supplied URL(s)")
    return list(await asyncio.gather(*[_fetch_as_article(u) for u in urls]))
