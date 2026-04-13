"""
USPTO Patent Search — fetches recent patents matching a domain query.

Uses the USPTO PatentsView API (v1) with httpx.
Requires an API key (set PATENTSVIEW_API_KEY in .env).
See: https://patentsview.org/apis/api-endpoints/patents
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import httpx

from core.sensing.ingest import RawArticle

logger = logging.getLogger("sensing.sources.patents")

PATENTSVIEW_API_URL = "https://search.patentsview.org/api/v1/patent/"
PATENT_MAX_RESULTS = 15


def _get_api_key() -> str | None:
    """Get PatentsView API key from environment."""
    return os.environ.get("PATENTSVIEW_API_KEY", "").strip() or None


def _build_patent_query(
    keywords: List[str],
    lookback_days: int = 365,
) -> dict:
    """Build a PatentsView API v1 query body."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    date_str = cutoff.strftime("%Y-%m-%d")

    # Build text match rules for title or abstract
    text_rules = []
    for kw in keywords[:5]:  # Cap at 5 keywords
        text_rules.append(
            {"_or": [
                {"_text_any": {"patent_title": kw}},
                {"_text_any": {"patent_abstract": kw}},
            ]}
        )

    query = {
        "_and": [
            {"_gte": {"patent_date": date_str}},
            {"_or": text_rules} if len(text_rules) > 1 else text_rules[0],
        ]
    }

    return query


async def search_patents(
    domain: str,
    lookback_days: int = 365,
    max_results: int = PATENT_MAX_RESULTS,
    must_include: Optional[List[str]] = None,
) -> List[RawArticle]:
    """Fetch recent USPTO patents for a domain.

    Args:
        domain: Target technology domain (e.g., "Generative AI").
        lookback_days: How far back to search (default 365 days for patents).
        max_results: Maximum patents to return.
        must_include: Additional keywords to include in the search.

    Returns:
        List of RawArticle objects representing patent filings.
    """
    api_key = _get_api_key()
    if not api_key:
        logger.info("USPTO patent search skipped: PATENTSVIEW_API_KEY not set in .env")
        return []

    # Build keyword list from domain + must_include
    keywords = [domain]
    if must_include:
        keywords.extend(must_include[:3])

    articles: List[RawArticle] = []

    try:
        query = _build_patent_query(keywords, lookback_days)

        body = {
            "q": query,
            "f": [
                "patent_id",
                "patent_title",
                "patent_abstract",
                "patent_date",
                "assignees.assignee_organization",
            ],
            "o": {
                "per_page": max_results,
                "matched_subentities_only": True,
            },
            "s": [{"patent_date": "desc"}],
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                PATENTSVIEW_API_URL,
                json=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Api-Key": api_key,
                },
            )
            resp.raise_for_status()

        data = resp.json()
        patents = data.get("patents") or []

        for patent in patents:
            if not isinstance(patent, dict):
                continue
            patent_id = patent.get("patent_id", "")
            title = patent.get("patent_title", "").strip()
            abstract = patent.get("patent_abstract", "").strip()
            date = patent.get("patent_date", "")

            if not title:
                continue

            # Extract assignee organizations
            assignees = patent.get("assignees") or []
            orgs = [
                a.get("assignee_organization", "")
                for a in assignees
                if isinstance(a, dict) and a.get("assignee_organization")
            ]
            assignee_str = ", ".join(orgs[:3]) if orgs else "Unknown assignee"

            # Google Patents URL for the patent
            url = f"https://patents.google.com/patent/US{patent_id}" if patent_id else ""

            articles.append(RawArticle(
                title=title,
                url=url,
                source="USPTO Patent",
                published_date=date,
                snippet=f"Patent by {assignee_str}",
                content=abstract,
            ))

        logger.info(f"USPTO: fetched {len(articles)} patents for '{domain}'")

    except httpx.HTTPStatusError as e:
        logger.warning(f"USPTO API error ({e.response.status_code}): {e}")
    except Exception as e:
        logger.warning(f"USPTO patent fetch failed: {e}")

    return articles
