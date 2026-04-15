"""
DEV.to — fetches recent developer articles and tutorials.

Uses the free DEV.to API (no key required).
Covers 500K+ developer articles — practitioner perspectives, tutorials,
tool reviews, and opinion pieces across all technology domains.

API docs: https://developers.forem.com/api/v1
Rate limit: 30 requests/30 seconds
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import httpx

from core.sensing.ingest import RawArticle

logger = logging.getLogger("sensing.sources.devto")

DEVTO_MAX_RESULTS = 15
DEVTO_API_URL = "https://dev.to/api/articles"


async def fetch_devto_articles(
    domain: str,
    lookback_days: int = 7,
    max_results: int = DEVTO_MAX_RESULTS,
    must_include: Optional[list[str]] = None,
) -> List[RawArticle]:
    """Fetch recent articles from DEV.to for a domain.

    Searches developer community articles — valuable for practical content,
    tutorials, and tool reviews that traditional news sources miss.

    Args:
        domain: Target domain name (used as search tag/query).
        lookback_days: Only return articles published within this window.
        max_results: Maximum number of articles to return.
        must_include: Optional keywords to search for additionally.
    """
    articles: List[RawArticle] = []
    seen_urls: set = set()

    cutoff = None
    if lookback_days > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)

    # Build search terms: main domain + optional keywords
    search_terms = [domain]
    if must_include:
        for kw in must_include[:2]:
            search_terms.append(f"{domain} {kw}")

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            for term in search_terms:
                try:
                    # DEV.to search endpoint
                    resp = await client.get(
                        f"{DEVTO_API_URL}",
                        params={
                            "per_page": min(max_results, 30),
                            "tag": _to_tag(domain),
                        },
                        headers={"Accept": "application/json"},
                    )

                    # If tag-based search returns too few, try text search
                    if resp.status_code != 200 or not resp.json():
                        resp = await client.get(
                            "https://dev.to/search/feed_content",
                            params={
                                "per_page": min(max_results, 30),
                                "search_fields": term,
                                "sort_by": "published_at",
                                "sort_direction": "desc",
                                "class_name": "Article",
                            },
                            headers={"Accept": "application/json"},
                        )

                    if resp.status_code != 200:
                        continue

                    data = resp.json()
                    # Handle both list response and dict with "result" key
                    items = data if isinstance(data, list) else data.get("result", [])

                    for article in items:
                        title = article.get("title", "")
                        if not title:
                            continue

                        url = article.get("url") or article.get("path", "")
                        if url and not url.startswith("http"):
                            url = f"https://dev.to{url}"
                        if not url or url in seen_urls:
                            continue
                        seen_urls.add(url)

                        # Date filtering
                        pub_str = (
                            article.get("published_at", "")
                            or article.get("published_timestamp", "")
                        )
                        pub_date = pub_str[:10] if pub_str else ""
                        if cutoff and pub_date:
                            try:
                                pub_dt = datetime.strptime(
                                    pub_date, "%Y-%m-%d"
                                ).replace(tzinfo=timezone.utc)
                                if pub_dt < cutoff:
                                    continue
                            except (ValueError, TypeError):
                                pass

                        # Build metadata
                        user = article.get("user", {})
                        author = user.get("name", "") if isinstance(user, dict) else ""
                        reactions = article.get("public_reactions_count", 0) or article.get("positive_reactions_count", 0)
                        comments = article.get("comments_count", 0)
                        tags = article.get("tag_list", [])
                        if isinstance(tags, list):
                            tags_str = ", ".join(tags[:5])
                        else:
                            tags_str = str(tags)

                        snippet_parts = []
                        if author:
                            snippet_parts.append(author)
                        if tags_str:
                            snippet_parts.append(tags_str)
                        if reactions:
                            snippet_parts.append(f"{reactions} reactions")
                        if comments:
                            snippet_parts.append(f"{comments} comments")
                        snippet = " | ".join(snippet_parts)

                        content = article.get("description", "") or ""

                        articles.append(RawArticle(
                            title=title,
                            url=url,
                            source="DEV.to",
                            published_date=pub_date,
                            snippet=snippet,
                            content=content,
                        ))

                        if len(articles) >= max_results:
                            break

                except Exception as e:
                    logger.warning(f"DEV.to search failed for '{term}': {e}")

                if len(articles) >= max_results:
                    break

        logger.info(
            f"DEV.to: fetched {len(articles)} articles for '{domain}'"
        )

    except Exception as e:
        logger.warning(f"DEV.to fetch failed: {e}")

    return articles[:max_results]


def _to_tag(domain: str) -> str:
    """Convert a domain name to a DEV.to tag (lowercase, no spaces)."""
    return domain.lower().replace(" ", "").replace("-", "")
