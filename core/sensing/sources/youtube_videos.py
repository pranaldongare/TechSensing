"""
YouTube Trending Videos — searches for trending videos related to radar technologies.

Uses the YouTube Data API v3 search endpoint via httpx.
Requires YOUTUBE_API_KEY in .env (free tier: 10,000 units/day).
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import List, Optional

import httpx

from core.config import settings

logger = logging.getLogger("sensing.sources.youtube")

YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"

# Defaults
MAX_VIDEOS_PER_TECH = 3
MAX_TECHNOLOGIES = 10
CONCURRENCY_LIMIT = 3


@dataclass
class TrendingVideo:
    """A single trending video result for a radar technology."""

    technology_name: str
    title: str
    url: str
    description: str
    uploader: str  # channel name
    duration: str  # e.g., "PT12M34S" -> "12:34"
    published: str  # ISO date string
    view_count: int
    thumbnail_url: str


def _parse_iso_duration(iso_duration: str) -> str:
    """Convert ISO 8601 duration (PT12M34S) to human-readable (12:34)."""
    if not iso_duration or not iso_duration.startswith("PT"):
        return ""
    rest = iso_duration[2:]  # strip "PT"
    hours, minutes, seconds = 0, 0, 0
    if "H" in rest:
        h_part, rest = rest.split("H", 1)
        hours = int(h_part)
    if "M" in rest:
        m_part, rest = rest.split("M", 1)
        minutes = int(m_part)
    if "S" in rest:
        s_part = rest.replace("S", "")
        seconds = int(s_part)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


async def fetch_youtube_videos(
    technology_names: List[str],
    max_videos_per_tech: int = MAX_VIDEOS_PER_TECH,
    max_technologies: int = MAX_TECHNOLOGIES,
) -> List[TrendingVideo]:
    """
    Search for trending YouTube videos for each technology name.

    Args:
        technology_names: Radar item names to search for.
        max_videos_per_tech: Max videos per technology (default 3).
        max_technologies: Max technologies to search (default 10).

    Returns:
        List of TrendingVideo results across all technologies.
    """
    api_key = getattr(settings, "YOUTUBE_API_KEY", "")
    if not api_key:
        logger.warning("YOUTUBE_API_KEY not set — skipping YouTube video enrichment")
        return []

    techs_to_search = technology_names[:max_technologies]
    all_videos: List[TrendingVideo] = []
    sem = asyncio.Semaphore(CONCURRENCY_LIMIT)

    async def _search_one(
        client: httpx.AsyncClient, tech_name: str
    ) -> List[TrendingVideo]:
        async with sem:
            try:
                # Step 1: Search for videos
                search_resp = await client.get(
                    YOUTUBE_SEARCH_URL,
                    params={
                        "part": "snippet",
                        "q": tech_name,
                        "type": "video",
                        "order": "relevance",
                        "maxResults": max_videos_per_tech,
                        "key": api_key,
                    },
                )
                search_resp.raise_for_status()
                search_data = search_resp.json()

                items = search_data.get("items", [])
                if not items:
                    logger.info(f"YouTube: no results for '{tech_name}'")
                    return []

                # Collect video IDs for statistics lookup
                video_ids = [
                    item["id"]["videoId"]
                    for item in items
                    if item.get("id", {}).get("videoId")
                ]

                # Step 2: Get video details (duration, view count)
                stats_map: dict = {}
                if video_ids:
                    details_resp = await client.get(
                        YOUTUBE_VIDEOS_URL,
                        params={
                            "part": "contentDetails,statistics",
                            "id": ",".join(video_ids),
                            "key": api_key,
                        },
                    )
                    details_resp.raise_for_status()
                    for detail in details_resp.json().get("items", []):
                        vid = detail["id"]
                        duration = (
                            detail.get("contentDetails", {}).get("duration", "")
                        )
                        view_count = (
                            detail.get("statistics", {}).get("viewCount", "0")
                        )
                        stats_map[vid] = {
                            "duration": _parse_iso_duration(duration),
                            "view_count": _safe_int(view_count),
                        }

                # Step 3: Build TrendingVideo list
                videos = []
                for item in items:
                    video_id = item.get("id", {}).get("videoId", "")
                    if not video_id:
                        continue
                    snippet = item.get("snippet", {})
                    stats = stats_map.get(video_id, {})
                    thumbnails = snippet.get("thumbnails", {})
                    thumb = (
                        thumbnails.get("medium", {}).get("url")
                        or thumbnails.get("default", {}).get("url", "")
                    )

                    videos.append(
                        TrendingVideo(
                            technology_name=tech_name,
                            title=snippet.get("title", ""),
                            url=f"https://www.youtube.com/watch?v={video_id}",
                            description=snippet.get("description", "")[:300],
                            uploader=snippet.get("channelTitle", ""),
                            duration=stats.get("duration", ""),
                            published=snippet.get("publishedAt", ""),
                            view_count=stats.get("view_count", 0),
                            thumbnail_url=thumb,
                        )
                    )

                logger.info(f"YouTube: found {len(videos)} videos for '{tech_name}'")
                return videos
            except httpx.HTTPStatusError as e:
                logger.warning(
                    f"YouTube API error for '{tech_name}': "
                    f"{e.response.status_code} {e.response.text[:200]}"
                )
                return []
            except Exception as e:
                logger.warning(f"YouTube search failed for '{tech_name}': {e}")
                return []

    async with httpx.AsyncClient(timeout=30) as client:
        results = await asyncio.gather(
            *[_search_one(client, t) for t in techs_to_search]
        )

    for video_list in results:
        all_videos.extend(video_list)

    logger.info(
        f"YouTube: total {len(all_videos)} videos for "
        f"{len(techs_to_search)} technologies"
    )
    return all_videos


def _safe_int(value: Optional[str]) -> int:
    """Safely parse a string to int, returning 0 on failure."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return 0
