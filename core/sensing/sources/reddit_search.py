"""
Reddit Search — fetches recent discussions from any subreddit via the public JSON API.

No API key required. Uses the /.json endpoint on Reddit's search pages.
Rate limit: ~1 request per 2 seconds (we respect this with a brief delay).

This complements the RSS-based subreddit feeds by dynamically finding relevant
discussions across ALL subreddits for any domain, not just hardcoded ones.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import httpx

from core.sensing.ingest import RawArticle

logger = logging.getLogger("sensing.sources.reddit")

REDDIT_MAX_RESULTS = 20
REDDIT_SEARCH_URL = "https://www.reddit.com/search.json"
REDDIT_USER_AGENT = "TechSensing/1.0 (Research Pipeline)"


async def search_reddit(
    domain: str,
    lookback_days: int = 7,
    max_results: int = REDDIT_MAX_RESULTS,
    must_include: Optional[list[str]] = None,
) -> List[RawArticle]:
    """Search Reddit for recent discussions about a domain.

    Searches across all subreddits — finds domain-relevant discussions
    that hardcoded RSS feeds would miss.

    Args:
        domain: Target domain name (used as search query).
        lookback_days: Time filter (day/week/month/year).
        max_results: Maximum number of posts to return.
        must_include: Optional keywords to add to the search.
    """
    articles: List[RawArticle] = []

    # Map lookback_days to Reddit time filter
    if lookback_days <= 1:
        time_filter = "day"
    elif lookback_days <= 7:
        time_filter = "week"
    elif lookback_days <= 30:
        time_filter = "month"
    else:
        time_filter = "year"

    # Build queries: main domain + optional keyword variants
    queries = [domain]
    if must_include:
        for kw in must_include[:2]:
            queries.append(f"{domain} {kw}")

    seen_urls: set = set()

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            for query in queries:
                try:
                    resp = await client.get(
                        REDDIT_SEARCH_URL,
                        params={
                            "q": query,
                            "sort": "relevance",
                            "t": time_filter,
                            "limit": min(max_results, 25),
                            "type": "link",
                        },
                        headers={"User-Agent": REDDIT_USER_AGENT},
                    )
                    resp.raise_for_status()
                    data = resp.json()

                    for child in data.get("data", {}).get("children", []):
                        post = child.get("data", {})
                        title = post.get("title", "")
                        if not title:
                            continue

                        permalink = post.get("permalink", "")
                        url = f"https://www.reddit.com{permalink}" if permalink else ""
                        if url in seen_urls:
                            continue
                        seen_urls.add(url)

                        # Parse timestamp
                        created_utc = post.get("created_utc", 0)
                        pub_date = ""
                        if created_utc:
                            pub_date = datetime.fromtimestamp(
                                created_utc, tz=timezone.utc
                            ).strftime("%Y-%m-%d")

                        subreddit = post.get("subreddit", "")
                        score = post.get("score", 0)
                        num_comments = post.get("num_comments", 0)

                        snippet = (
                            f"r/{subreddit} | {score} upvotes, "
                            f"{num_comments} comments"
                        )

                        # Content: selftext for text posts, title for link posts
                        content = post.get("selftext", "") or title

                        articles.append(RawArticle(
                            title=title,
                            url=url,
                            source="Reddit",
                            published_date=pub_date,
                            snippet=snippet,
                            content=content[:2000],
                        ))

                        if len(articles) >= max_results:
                            break

                except Exception as e:
                    logger.warning(f"Reddit search failed for '{query}': {e}")

                # Respect rate limit between queries
                if len(queries) > 1:
                    await asyncio.sleep(2)

                if len(articles) >= max_results:
                    break

        logger.info(
            f"Reddit: fetched {len(articles)} posts for '{domain}'"
        )

    except Exception as e:
        logger.warning(f"Reddit search failed: {e}")

    return articles[:max_results]
