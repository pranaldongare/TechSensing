"""
GitHub Trending — fetches recently-created popular repos for a domain.

Uses the GitHub Search API (no auth required for 60 req/hr;
set GITHUB_TOKEN env var for 5000 req/hr).
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import List

import httpx

from core.sensing.ingest import RawArticle

logger = logging.getLogger("sensing.sources.github")

GITHUB_MAX_RESULTS = 15


async def fetch_github_trending(
    domain: str,
    lookback_days: int = 7,
    max_results: int = GITHUB_MAX_RESULTS,
) -> List[RawArticle]:
    """Fetch trending GitHub repos for a domain (0 lookback_days = no date filter)."""
    if lookback_days > 0:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        query = f"{domain} created:>{cutoff}"
    else:
        query = f"{domain} stars:>10"

    headers: dict[str, str] = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    articles: List[RawArticle] = []

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                "https://api.github.com/search/repositories",
                params={"q": query, "sort": "stars", "order": "desc", "per_page": max_results},
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

            items = data.get("items") or []
            for repo in items[:max_results]:
                if not isinstance(repo, dict):
                    continue
                full_name = repo.get("full_name") or ""
                html_url = repo.get("html_url") or ""
                if not full_name or not html_url:
                    continue
                description = repo.get("description") or ""
                language = repo.get("language") or "Unknown"
                stars = repo.get("stargazers_count") or 0
                articles.append(RawArticle(
                    title=full_name,
                    url=html_url,
                    source="GitHub",
                    published_date=repo.get("created_at") or "",
                    snippet=f"{stars} stars | {language} | {description[:200]}",
                    content=description,
                ))

        logger.info(f"GitHub: fetched {len(articles)} repos for '{domain}'")

    except Exception as e:
        logger.warning(f"GitHub fetch failed: {e}")

    return articles
