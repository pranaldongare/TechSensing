"""GitHub provider — company org activity + trending-repo matches.

Two complementary passes:

1. **Org-level pass** — if the company has a known GitHub org (see
   ``github_org_map.json``), list the org's most recently-pushed
   public repos via the Search API. This catches release activity
   even for companies whose public presence is smaller than their
   product footprint.
2. **Keyword pass** — reuses :func:`fetch_github_trending` with the
   company name as the search term to pick up community repos that
   mention the company.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List

import httpx

from core.sensing.ingest import RawArticle
from core.sensing.sources.github_trending import fetch_github_trending

logger = logging.getLogger("sensing.providers.github")

_ORG_MAP_PATH = os.path.join(
    os.path.dirname(__file__), "github_org_map.json"
)

_org_map_cache: Dict[str, str] | None = None


def _load_org_map() -> Dict[str, str]:
    global _org_map_cache
    if _org_map_cache is not None:
        return _org_map_cache
    try:
        with open(_ORG_MAP_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        _org_map_cache = {
            str(k).strip().lower(): str(v).strip() for k, v in raw.items()
        }
    except Exception as e:
        logger.warning(f"[github] org map unavailable: {e}")
        _org_map_cache = {}
    return _org_map_cache


def _guess_org(company: str) -> str | None:
    if not company:
        return None
    key = company.strip().lower()
    return _load_org_map().get(key)


async def _fetch_org_repos(
    org: str, *, lookback_days: int, max_results: int
) -> List[RawArticle]:
    """List recently-pushed repos for a known GitHub org."""
    headers: Dict[str, str] = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    if lookback_days > 0:
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=lookback_days)
        ).strftime("%Y-%m-%d")
        q = f"org:{org} pushed:>{cutoff}"
    else:
        q = f"org:{org}"

    articles: List[RawArticle] = []
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                "https://api.github.com/search/repositories",
                params={
                    "q": q,
                    "sort": "updated",
                    "order": "desc",
                    "per_page": max_results,
                },
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            for repo in (data.get("items") or [])[:max_results]:
                if not isinstance(repo, dict):
                    continue
                full_name = repo.get("full_name") or ""
                html_url = repo.get("html_url") or ""
                if not full_name or not html_url:
                    continue
                desc = repo.get("description") or ""
                lang = repo.get("language") or "Unknown"
                stars = repo.get("stargazers_count") or 0
                articles.append(
                    RawArticle(
                        title=f"{full_name} (org update)",
                        url=html_url,
                        source="GitHub",
                        published_date=repo.get("pushed_at")
                        or repo.get("updated_at")
                        or "",
                        snippet=f"{stars} stars | {lang} | {desc[:200]}",
                        content=desc,
                    )
                )
    except Exception as e:
        logger.warning(f"[github] org scan failed for {org!r}: {e}")
    return articles


class GitHubProvider:
    """GitHub org + keyword search provider."""

    name = "github"

    async def search(
        self,
        company: str,
        *,
        queries: List[str],  # noqa: ARG002 — company/org drives query
        domain: str = "",  # noqa: ARG002
        lookback_days: int = 30,
        max_results: int = 15,
    ) -> List[RawArticle]:
        if not company:
            return []

        tasks = []
        org = _guess_org(company)
        if org:
            tasks.append(
                _fetch_org_repos(
                    org, lookback_days=lookback_days, max_results=max_results
                )
            )

        # Keyword pass — wrap the existing trending helper.
        tasks.append(
            fetch_github_trending(
                domain=company,
                lookback_days=lookback_days,
                max_results=max_results,
            )
        )

        try:
            batches = await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            logger.warning(f"[github] gather failed for {company!r}: {e}")
            return []

        merged: List[RawArticle] = []
        seen: set = set()
        for batch in batches:
            if isinstance(batch, BaseException):
                logger.warning(f"[github] sub-query failed: {batch}")
                continue
            for art in batch:
                if art.url and art.url not in seen:
                    seen.add(art.url)
                    merged.append(art)

        logger.info(
            f"[github] {company!r}: {len(merged)} repo(s) "
            f"(org={org or 'none'})"
        )
        return merged[:max_results]
