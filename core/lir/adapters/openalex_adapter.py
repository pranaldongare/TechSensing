"""
OpenAlex LIR adapter — academic discovery with citation velocity data.

Tier 1: Academic papers from OpenAlex (250M+ works, free CC0 license).
Captures citation counts and concept tags for authority/novelty scoring.
No API key required (polite pool with email in User-Agent).
"""

import hashlib
import logging
from datetime import datetime, timezone
from typing import List

import httpx

from core.lir.models import LIRRawItem

logger = logging.getLogger("lir.adapters.openalex")

OPENALEX_API = "https://api.openalex.org"
# Polite pool email — gets higher rate limits
OPENALEX_EMAIL = "techsensing@example.com"


class OpenAlexLIRAdapter:
    """Tier-1 adapter: OpenAlex academic papers with citation velocity."""

    source_id: str = "openalex"
    tier: str = "T1"
    lead_time_prior_days: int = 730  # ~24 months
    authority_prior: float = 0.85

    async def poll(
        self,
        since: datetime,
        max_results: int = 50,
    ) -> List[LIRRawItem]:
        """Fetch recently published highly-cited works from OpenAlex."""
        all_items: List[LIRRawItem] = []
        seen_ids: set = set()

        since_str = since.strftime("%Y-%m-%d")

        # Strategy 1: Recently published works with high citation velocity
        # (sorted by cited_by_count to find fast-rising papers)
        try:
            items = await self._fetch_works(
                filter_str=f"from_publication_date:{since_str},type:article",
                sort="cited_by_count:desc",
                max_results=max_results // 2,
            )
            for item in items:
                if item.item_id not in seen_ids:
                    seen_ids.add(item.item_id)
                    all_items.append(item)
        except Exception as e:
            logger.warning(f"OpenAlex high-citation fetch failed: {e}")

        # Strategy 2: Trending concepts — recently published across broad topics
        try:
            items = await self._fetch_works(
                filter_str=f"from_publication_date:{since_str},type:article",
                sort="publication_date:desc",
                max_results=max_results // 2,
            )
            for item in items:
                if item.item_id not in seen_ids:
                    seen_ids.add(item.item_id)
                    all_items.append(item)
        except Exception as e:
            logger.warning(f"OpenAlex recent fetch failed: {e}")

        logger.info(f"OpenAlex LIR adapter: {len(all_items)} works")
        return all_items[:max_results]

    async def _fetch_works(
        self,
        filter_str: str,
        sort: str,
        max_results: int = 25,
    ) -> List[LIRRawItem]:
        """Fetch works from OpenAlex API."""
        items: List[LIRRawItem] = []

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{OPENALEX_API}/works",
                params={
                    "filter": filter_str,
                    "sort": sort,
                    "per_page": min(max_results, 50),
                    "select": (
                        "id,title,publication_date,doi,cited_by_count,"
                        "authorships,concepts,primary_location,abstract_inverted_index"
                    ),
                    "mailto": OPENALEX_EMAIL,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        for work in data.get("results", []):
            openalex_id = work.get("id", "")
            title = work.get("title", "")
            if not title:
                continue

            pub_date = work.get("publication_date", "")
            doi = work.get("doi", "")
            cited_by = work.get("cited_by_count", 0)

            # Build URL
            url = doi if doi else openalex_id
            if not url:
                continue

            # Extract author names (top 5)
            authors = []
            for authorship in work.get("authorships", [])[:5]:
                author_name = authorship.get("author", {}).get("display_name", "")
                if author_name:
                    authors.append(author_name)

            # Extract concept tags
            concepts = []
            for concept in work.get("concepts", [])[:5]:
                concept_name = concept.get("display_name", "")
                if concept_name:
                    concepts.append(concept_name)

            # Reconstruct abstract from inverted index
            abstract = self._reconstruct_abstract(
                work.get("abstract_inverted_index", {})
            )

            # Source journal/venue
            venue = ""
            primary_loc = work.get("primary_location", {})
            if primary_loc:
                source = primary_loc.get("source", {})
                if source:
                    venue = source.get("display_name", "")

            item_id = f"oalex:{hashlib.sha256(openalex_id.encode()).hexdigest()[:12]}"

            snippet_parts = []
            if authors:
                snippet_parts.append(", ".join(authors[:3]))
            if venue:
                snippet_parts.append(venue)
            if cited_by:
                snippet_parts.append(f"{cited_by} citations")

            items.append(
                LIRRawItem(
                    item_id=item_id,
                    source_id="openalex",
                    tier="T1",
                    title=title,
                    url=url,
                    published_date=pub_date,
                    snippet=" | ".join(snippet_parts),
                    content=abstract[:2000] if abstract else title,
                    authors=", ".join(authors[:5]),
                    categories=" | ".join(concepts[:5]),
                    metadata={
                        "citation_count": cited_by,
                        "concepts": concepts,
                        "venue": venue,
                    },
                )
            )

        return items

    @staticmethod
    def _reconstruct_abstract(inverted_index: dict) -> str:
        """Reconstruct abstract text from OpenAlex inverted index format."""
        if not inverted_index:
            return ""

        try:
            # Build (position, word) pairs and sort by position
            word_positions = []
            for word, positions in inverted_index.items():
                for pos in positions:
                    word_positions.append((pos, word))
            word_positions.sort()
            return " ".join(word for _, word in word_positions[:300])
        except Exception:
            return ""

    async def backfill(self, start_date: str, end_date: str) -> List[LIRRawItem]:
        """Backfill OpenAlex works for a date range."""
        since = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)
        return await self.poll(since, max_results=200)
