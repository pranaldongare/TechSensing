"""
Semantic Scholar — fetches recent academic papers across all disciplines.

Uses the free Semantic Scholar Academic Graph API (no key required).
Covers 200M+ papers from all fields — fills the gap where arXiv only
covers CS/Physics/Math.

API docs: https://api.semanticscholar.org/
Rate limit: 100 requests/sec (unauthenticated)
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import httpx

from core.sensing.ingest import RawArticle

logger = logging.getLogger("sensing.sources.semantic_scholar")

S2_MAX_RESULTS = 20
S2_API_URL = "https://api.semanticscholar.org/graph/v1/paper/search"


async def fetch_semantic_scholar(
    domain: str,
    lookback_days: int = 30,
    max_results: int = S2_MAX_RESULTS,
    must_include: Optional[list[str]] = None,
) -> List[RawArticle]:
    """Fetch recent papers from Semantic Scholar for a domain.

    Searches across all academic fields — particularly valuable for domains
    not well covered by arXiv (biotech, materials science, medicine, etc.).

    Args:
        domain: Target domain name (used as search query).
        lookback_days: Only return papers published within this window.
        max_results: Maximum number of papers to return.
        must_include: Optional keywords to combine with domain for search.
    """
    articles: List[RawArticle] = []

    # Build query: domain + optional keywords
    query = domain
    if must_include:
        query += " " + " ".join(must_include[:3])

    # Compute date range for filtering
    cutoff = None
    if lookback_days > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)

    # S2 supports year-based filtering
    year_filter = ""
    if cutoff:
        year_filter = f"{cutoff.year}-"

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            params = {
                "query": query,
                "limit": min(max_results, 100),
                "fields": (
                    "title,abstract,url,year,publicationDate,"
                    "authors,venue,citationCount,openAccessPdf"
                ),
            }
            if year_filter:
                params["year"] = year_filter

            # Retry with backoff on 429 rate-limit responses
            data = None
            for attempt in range(3):
                resp = await client.get(S2_API_URL, params=params)
                if resp.status_code == 429:
                    wait = 2 ** attempt  # 1s, 2s, 4s
                    logger.info(f"Semantic Scholar 429 — retrying in {wait}s (attempt {attempt + 1}/3)")
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                data = resp.json()
                break

            if data is None:
                logger.warning("Semantic Scholar: exhausted retries after 429s")
                return articles

            for paper in data.get("data", [])[:max_results]:
                title = paper.get("title", "")
                if not title:
                    continue

                # Use publicationDate for filtering (YYYY-MM-DD format)
                pub_date = paper.get("publicationDate", "")
                if cutoff and pub_date:
                    try:
                        pub_dt = datetime.strptime(
                            pub_date, "%Y-%m-%d"
                        ).replace(tzinfo=timezone.utc)
                        if pub_dt < cutoff:
                            continue
                    except (ValueError, TypeError):
                        pass

                # Build metadata snippet
                authors = ", ".join(
                    a.get("name", "")
                    for a in paper.get("authors", [])[:3]
                )
                venue = paper.get("venue", "")
                citations = paper.get("citationCount", 0)
                snippet_parts = [authors]
                if venue:
                    snippet_parts.append(venue)
                if citations:
                    snippet_parts.append(f"{citations} citations")
                snippet = " | ".join(p for p in snippet_parts if p)

                # Prefer open access PDF URL, fall back to S2 page
                url = paper.get("url", "")
                oa_pdf = paper.get("openAccessPdf")
                if oa_pdf and isinstance(oa_pdf, dict):
                    url = oa_pdf.get("url", url)

                articles.append(RawArticle(
                    title=title,
                    url=url,
                    source="Semantic Scholar",
                    published_date=pub_date or str(paper.get("year", "")),
                    snippet=snippet,
                    content=paper.get("abstract", "") or "",
                ))

        logger.info(
            f"Semantic Scholar: fetched {len(articles)} papers for '{domain}'"
        )

    except Exception as e:
        logger.warning(f"Semantic Scholar fetch failed: {e}")

    return articles
