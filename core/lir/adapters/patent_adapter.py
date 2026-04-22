"""
Patent LIR adapter — uses Lens.org API for structured patent data.

Tier 1: Patent filings, 12-36 month lead time.
Falls back to EPO Open Patent Services if Lens.org key not available,
and to Tavily search as last resort.
"""

import hashlib
import logging
import os
from datetime import datetime
from typing import List

import httpx

from core.lir.models import LIRRawItem

logger = logging.getLogger("lir.adapters.patent")

LENS_API_URL = "https://api.lens.org/patent/search"
EPO_OPS_URL = "https://ops.epo.org/3.2/rest-services/published-data/search"

# Broad patent classifications (not AI-only)
PATENT_CPC_CODES = [
    "G06N",   # Computing arrangements based on specific computational models (ML/AI)
    "H04L",   # Transmission of digital information (networking)
    "G06F",   # Electric digital data processing (general computing)
    "G16H",   # Healthcare informatics
    "H01L",   # Semiconductor devices
    "G06Q",   # Business methods / fintech
]

# Broad keyword queries for patent search (diverse domains)
PATENT_QUERIES = [
    "artificial intelligence",
    "machine learning",
    "quantum computing",
    "blockchain",
    "autonomous vehicle",
    "edge computing",
    "natural language processing",
    "robotics",
    "cybersecurity",
    "renewable energy storage",
]


class PatentLIRAdapter:
    """Tier-1 adapter: Patent filings via Lens.org, EPO, or Tavily fallback."""

    source_id: str = "patents"
    tier: str = "T1"
    lead_time_prior_days: int = 730  # ~24 months
    authority_prior: float = 0.80

    async def poll(
        self,
        since: datetime,
        max_results: int = 50,
    ) -> List[LIRRawItem]:
        """Fetch recent patents using best available source."""
        lens_key = os.environ.get("LENS_API_KEY", "").strip()
        if lens_key:
            return await self._poll_lens(lens_key, since, max_results)

        # Fallback to EPO OPS (free, no key needed)
        try:
            items = await self._poll_epo(since, max_results)
            if items:
                return items
        except Exception as e:
            logger.warning(f"EPO fallback failed: {e}")

        # Last resort: Tavily search
        return await self._poll_tavily(since, max_results)

    async def _poll_lens(
        self,
        api_key: str,
        since: datetime,
        max_results: int,
    ) -> List[LIRRawItem]:
        """Fetch patents from Lens.org API with structured data."""
        since_str = since.strftime("%Y-%m-%d")
        all_items: List[LIRRawItem] = []
        seen_ids: set = set()

        query_body = {
            "query": {
                "bool": {
                    "must": [
                        {"range": {"date_published": {"gte": since_str}}},
                        {
                            "bool": {
                                "should": [
                                    {"match": {"title": kw}}
                                    for kw in PATENT_QUERIES[:5]
                                ],
                                "minimum_should_match": 1,
                            }
                        },
                    ]
                }
            },
            "size": min(max_results, 50),
            "sort": [{"date_published": "desc"}],
            "include": [
                "lens_id", "title", "abstract", "date_published",
                "biblio.parties.applicants", "biblio.classifications_cpc",
                "scholarly_citations_count",
            ],
        }

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    LENS_API_URL,
                    json=query_body,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            for result in data.get("data", []):
                lens_id = result.get("lens_id", "")
                if not lens_id or lens_id in seen_ids:
                    continue
                seen_ids.add(lens_id)

                title = result.get("title", "")
                abstract = result.get("abstract", "")
                pub_date = result.get("date_published", "")
                citations = result.get("scholarly_citations_count", 0)

                # Extract applicant names
                applicants = []
                biblio = result.get("biblio", {})
                for party in biblio.get("parties", {}).get("applicants", []):
                    name = party.get("extracted_name", {}).get("value", "")
                    if name:
                        applicants.append(name)

                # Extract CPC codes
                cpc_codes = []
                for cls in biblio.get("classifications_cpc", []):
                    code = cls.get("symbol", "")
                    if code:
                        cpc_codes.append(code[:4])  # First 4 chars = section

                url = f"https://www.lens.org/lens/patent/{lens_id}"
                item_id = f"patent:{hashlib.sha256(lens_id.encode()).hexdigest()[:12]}"

                all_items.append(
                    LIRRawItem(
                        item_id=item_id,
                        source_id="patents",
                        tier="T1",
                        title=title,
                        url=url,
                        published_date=pub_date,
                        snippet=abstract[:500] if abstract else "",
                        content=abstract,
                        authors=", ".join(applicants[:3]),
                        categories=" | ".join(sorted(set(cpc_codes))),
                        metadata={
                            "citation_count": citations,
                            "applicants": applicants,
                        },
                    )
                )

            logger.info(f"Lens.org patent adapter: {len(all_items)} patents")
        except Exception as e:
            logger.warning(f"Lens.org patent search failed: {e}")

        return all_items[:max_results]

    async def _poll_epo(
        self,
        since: datetime,
        max_results: int,
    ) -> List[LIRRawItem]:
        """Fetch patents from EPO Open Patent Services (free, no key)."""
        all_items: List[LIRRawItem] = []
        seen_urls: set = set()

        # EPO uses a simple query syntax
        queries = PATENT_QUERIES[:5]  # Use top 5 queries
        per_query = max(3, max_results // len(queries))

        for query in queries:
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.get(
                        EPO_OPS_URL,
                        params={
                            "q": f'ta="{query}"',  # Title/Abstract search
                            "Range": f"1-{per_query}",
                        },
                        headers={"Accept": "application/json"},
                    )

                    if resp.status_code == 200:
                        data = resp.json()
                        results = (
                            data.get("ops:world-patent-data", {})
                            .get("ops:biblio-search", {})
                            .get("ops:search-result", {})
                            .get("ops:publication-reference", [])
                        )

                        if isinstance(results, dict):
                            results = [results]

                        for pub_ref in results[:per_query]:
                            doc_id = pub_ref.get("document-id", {})
                            country = doc_id.get("country", {}).get("$", "")
                            doc_number = doc_id.get("doc-number", {}).get("$", "")
                            kind = doc_id.get("kind", {}).get("$", "")

                            if not doc_number:
                                continue

                            patent_number = f"{country}{doc_number}{kind}"
                            url = f"https://worldwide.espacenet.com/patent/search?q={patent_number}"

                            if url in seen_urls:
                                continue
                            seen_urls.add(url)

                            item_id = f"patent:{hashlib.sha256(patent_number.encode()).hexdigest()[:12]}"
                            all_items.append(
                                LIRRawItem(
                                    item_id=item_id,
                                    source_id="patents",
                                    tier="T1",
                                    title=f"Patent {patent_number}",
                                    url=url,
                                    published_date="",
                                    snippet=query,
                                    content=f"Patent {patent_number} related to {query}",
                                    categories=query,
                                )
                            )
            except Exception as e:
                logger.warning(f"EPO search for '{query}' failed: {e}")

        logger.info(f"EPO patent adapter: {len(all_items)} patents")
        return all_items[:max_results]

    async def _poll_tavily(
        self,
        since: datetime,
        max_results: int,
    ) -> List[LIRRawItem]:
        """Legacy fallback: fetch patents via Tavily search."""
        api_key = os.environ.get("TAVILY_API_KEY", "").strip()
        if not api_key:
            logger.info("Patent adapter skipped: no LENS_API_KEY or TAVILY_API_KEY")
            return []

        from core.sensing.sources.google_patent_search import _tavily_search

        all_items: List[LIRRawItem] = []
        seen_urls: set = set()

        per_keyword = max(2, max_results // max(len(PATENT_QUERIES), 1))

        for keyword in PATENT_QUERIES[:5]:
            try:
                query = f"site:patents.google.com {keyword}"
                results = await _tavily_search(query, max_results=per_keyword)

                for r in results:
                    url = r.get("url", "").strip()
                    title = r.get("title", "").strip()
                    content = r.get("content", "").strip()

                    if not url or not title:
                        continue
                    if "patents.google.com" not in url:
                        continue
                    if url in seen_urls:
                        continue

                    seen_urls.add(url)
                    item_id = f"patent:{hashlib.sha256(url.encode()).hexdigest()[:12]}"

                    all_items.append(
                        LIRRawItem(
                            item_id=item_id,
                            source_id="patents",
                            tier="T1",
                            title=title,
                            url=url,
                            published_date="",
                            snippet=content[:500] if content else "",
                            content=content,
                            categories=keyword,
                        )
                    )
            except Exception as e:
                logger.warning(f"Tavily patent search for '{keyword}' failed: {e}")

        logger.info(f"Tavily patent adapter (fallback): {len(all_items)} patents")
        return all_items[:max_results]

    async def backfill(
        self,
        start_date: str,
        end_date: str,
    ) -> List[LIRRawItem]:
        """Backfill patents for a date range."""
        since = datetime.fromisoformat(start_date)
        return await self.poll(since, max_results=100)
