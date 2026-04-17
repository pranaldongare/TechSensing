"""YouTube provider — videos/podcasts mentioning the company.

Prefers the YouTube Data API v3 when ``YOUTUBE_API_KEY`` is set (much
better recency and metadata); falls back to a DuckDuckGo
site-restricted search against ``youtube.com`` so we always get
*something* when the API key is missing or rate-limited.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import List

import httpx

from core.config import settings
from core.sensing.ingest import RawArticle, search_duckduckgo

logger = logging.getLogger("sensing.providers.youtube")

YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"


def _get_api_key() -> str:
    key = getattr(settings, "YOUTUBE_API_KEY", "") or ""
    return key.strip()


async def _api_search(
    company: str, *, lookback_days: int, max_results: int
) -> List[RawArticle]:
    api_key = _get_api_key()
    if not api_key:
        return []

    params: dict = {
        "part": "snippet",
        "q": company,
        "type": "video",
        "order": "date",
        "maxResults": min(max(max_results, 1), 25),
        "key": api_key,
    }
    if lookback_days > 0:
        published_after = (
            datetime.now(timezone.utc) - timedelta(days=lookback_days)
        )
        # RFC 3339 UTC "Zulu" format required by the YouTube API.
        params["publishedAfter"] = (
            published_after.strftime("%Y-%m-%dT%H:%M:%SZ")
        )

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(YOUTUBE_SEARCH_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        logger.warning(
            f"[youtube] API error for {company!r}: "
            f"{e.response.status_code} {e.response.text[:200]}"
        )
        return []
    except Exception as e:
        logger.warning(f"[youtube] API call failed for {company!r}: {e}")
        return []

    articles: List[RawArticle] = []
    for item in data.get("items", []):
        if not isinstance(item, dict):
            continue
        video_id = (item.get("id") or {}).get("videoId") or ""
        snippet = item.get("snippet") or {}
        if not video_id:
            continue
        url = f"https://www.youtube.com/watch?v={video_id}"
        articles.append(
            RawArticle(
                title=snippet.get("title", "") or "YouTube video",
                url=url,
                source="YouTube",
                published_date=snippet.get("publishedAt", ""),
                snippet=(snippet.get("channelTitle") or "") + " | "
                + (snippet.get("description", "") or "")[:300],
                content=snippet.get("description", "") or "",
            )
        )
    return articles[:max_results]


async def _ddg_fallback(
    company: str, *, lookback_days: int, max_results: int
) -> List[RawArticle]:
    queries = [
        f'site:youtube.com "{company}"',
        f'"{company}" interview site:youtube.com',
    ]
    try:
        results = await search_duckduckgo(
            queries=queries,
            domain="Technology",
            lookback_days=lookback_days,
        )
    except Exception as e:
        logger.warning(f"[youtube] DDG fallback failed for {company!r}: {e}")
        return []

    filtered: List[RawArticle] = []
    seen: set = set()
    for art in results:
        if not art.url or "youtube.com" not in art.url:
            continue
        if art.url in seen:
            continue
        seen.add(art.url)
        filtered.append(
            RawArticle(
                title=art.title,
                url=art.url,
                source="YouTube",
                published_date=art.published_date or "",
                snippet=art.snippet or "YouTube (DDG fallback)",
                content=art.content,
            )
        )
    return filtered[:max_results]


class YouTubeProvider:
    """YouTube provider (API or DDG fallback)."""

    name = "youtube"

    async def search(
        self,
        company: str,
        *,
        queries: List[str],  # noqa: ARG002 — company drives the query
        domain: str = "",  # noqa: ARG002
        lookback_days: int = 30,
        max_results: int = 10,
    ) -> List[RawArticle]:
        if not company:
            return []

        if _get_api_key():
            articles = await _api_search(
                company,
                lookback_days=lookback_days,
                max_results=max_results,
            )
            if articles:
                logger.info(
                    f"[youtube] {company!r}: {len(articles)} video(s) via API"
                )
                return articles
            logger.info(
                f"[youtube] API returned 0 for {company!r}; falling back to DDG"
            )

        articles = await _ddg_fallback(
            company, lookback_days=lookback_days, max_results=max_results
        )
        logger.info(
            f"[youtube] {company!r}: {len(articles)} video(s) via DDG fallback"
        )
        return articles
