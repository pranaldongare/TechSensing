"""
EPO Open Patent Services (OPS) — fetches recent patents from the European Patent Office.

Free registration at https://developers.epo.org/user/register
Set EPO_CONSUMER_KEY and EPO_CONSUMER_SECRET in .env

Global coverage: 100M+ patent documents from EPO, WIPO, and national offices.
See: https://www.epo.org/searching-for-patents/data/web-services/ops.html
"""

import base64
import logging
import os
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import httpx

from core.sensing.ingest import RawArticle

logger = logging.getLogger("sensing.sources.epo_patents")

EPO_AUTH_URL = "https://ops.epo.org/3.2/auth/accesstoken"
EPO_SEARCH_URL = "https://ops.epo.org/3.2/rest-services/published-data/search/biblio"
EPO_MAX_RESULTS = 15

# Namespace used in EPO exchange-document XML
_EX_NS = "http://www.epo.org/exchange"

# Simple in-memory token cache
_token_cache: dict = {"token": None, "expires_at": 0.0}


def _get_credentials() -> tuple | None:
    """Get EPO OPS OAuth credentials from environment."""
    key = os.environ.get("EPO_CONSUMER_KEY", "").strip()
    secret = os.environ.get("EPO_CONSUMER_SECRET", "").strip()
    if key and secret:
        return (key, secret)
    return None


async def _get_access_token(client: httpx.AsyncClient, key: str, secret: str) -> str:
    """Obtain or reuse an OAuth2 access token (valid ~20 min)."""
    if _token_cache["token"] and time.time() < _token_cache["expires_at"] - 60:
        return _token_cache["token"]

    auth_str = base64.b64encode(f"{key}:{secret}".encode()).decode()
    resp = await client.post(
        EPO_AUTH_URL,
        headers={
            "Authorization": f"Basic {auth_str}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={"grant_type": "client_credentials"},
    )
    resp.raise_for_status()
    data = resp.json()

    _token_cache["token"] = data["access_token"]
    _token_cache["expires_at"] = time.time() + int(data.get("expires_in", 1200))

    return _token_cache["token"]


def _build_cql_query(
    domain: str,
    lookback_days: int,
    must_include: Optional[List[str]] = None,
) -> str:
    """Build a CQL query for EPO OPS bibliographic search.

    CQL syntax: ti="keyword" for title, ab="keyword" for abstract,
    pd>=YYYYMMDD for publication date filter.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    date_str = cutoff.strftime("%Y%m%d")

    # Collect keywords
    keywords = [domain]
    if must_include:
        keywords.extend(must_include[:5])

    # Each keyword → word-level search in title OR abstract
    # Use "all" operator for multi-word terms (AND of all words)
    # instead of exact-phrase matching which is too restrictive
    text_parts = []
    for kw in keywords:
        text_parts.append(f'(ti all "{kw}" OR ab all "{kw}")')

    # Any keyword match + date filter
    text_query = " OR ".join(text_parts)
    return f"({text_query}) AND pd>={date_str}"


def _parse_biblio_xml(xml_text: str) -> List[dict]:
    """Parse EPO OPS bibliographic XML into simple dicts."""
    results = []

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        logger.warning("Failed to parse EPO XML response")
        return []

    for doc in root.iter(f"{{{_EX_NS}}}exchange-document"):
        try:
            country = doc.get("country", "")
            doc_number = doc.get("doc-number", "")
            kind = doc.get("kind", "")

            # Get title (prefer English)
            title = ""
            for title_elem in doc.iter(f"{{{_EX_NS}}}invention-title"):
                lang = title_elem.get("lang", "")
                text = (title_elem.text or "").strip()
                if lang == "en" or not title:
                    title = text

            if not title:
                continue

            # Get abstract (prefer English)
            abstract = ""
            for abs_elem in doc.iter(f"{{{_EX_NS}}}abstract"):
                lang = abs_elem.get("lang", "")
                text_parts = []
                for child in abs_elem.iter():
                    if child.text:
                        text_parts.append(child.text.strip())
                text = " ".join(text_parts)
                if lang == "en" or not abstract:
                    abstract = text.strip()

            # Get publication date from publication-reference
            pub_date = ""
            for pub_ref in doc.iter(f"{{{_EX_NS}}}publication-reference"):
                for doc_id in pub_ref.iter(f"{{{_EX_NS}}}document-id"):
                    date_elem = doc_id.find(f"{{{_EX_NS}}}date")
                    if date_elem is not None and date_elem.text:
                        raw_date = date_elem.text.strip()
                        if len(raw_date) == 8:
                            pub_date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
                        break
                if pub_date:
                    break

            # Get applicant names
            applicants = []
            for applicant in doc.iter(f"{{{_EX_NS}}}applicant"):
                name_elem = applicant.find(f".//{{{_EX_NS}}}name")
                if name_elem is not None and name_elem.text:
                    applicants.append(name_elem.text.strip())

            patent_ref = f"{country}{doc_number}" if country and doc_number else ""

            results.append({
                "patent_ref": patent_ref,
                "title": title,
                "abstract": abstract,
                "pub_date": pub_date,
                "applicants": applicants[:3],
                "country": country,
                "kind": kind,
            })
        except Exception as e:
            logger.debug(f"Failed to parse EPO document element: {e}")
            continue

    return results


async def search_epo_patents(
    domain: str,
    lookback_days: int = 365,
    max_results: int = EPO_MAX_RESULTS,
    must_include: Optional[List[str]] = None,
) -> List[RawArticle]:
    """Fetch recent patents from EPO Open Patent Services.

    Args:
        domain: Target technology domain (e.g., "Generative AI").
        lookback_days: How far back to search (default 365 days).
        max_results: Maximum patents to return.
        must_include: Additional keywords to include in the search.

    Returns:
        List of RawArticle objects representing patent filings.
    """
    creds = _get_credentials()
    if not creds:
        logger.info(
            "EPO patent search skipped: EPO_CONSUMER_KEY/EPO_CONSUMER_SECRET not set in .env"
        )
        return []

    articles: List[RawArticle] = []

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            token = await _get_access_token(client, creds[0], creds[1])

            cql = _build_cql_query(domain, lookback_days, must_include)
            logger.debug(f"EPO CQL query: {cql}")

            resp = await client.get(
                EPO_SEARCH_URL,
                params={"q": cql, "Range": f"1-{max_results}"},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/xml",
                },
            )
            resp.raise_for_status()

            patents = _parse_biblio_xml(resp.text)

            for patent in patents[:max_results]:
                ref = patent["patent_ref"]
                title = patent["title"]
                abstract = patent["abstract"]
                pub_date = patent["pub_date"]
                applicants = patent["applicants"]

                applicant_str = ", ".join(applicants) if applicants else "Unknown applicant"

                # Espacenet URL for viewing the patent
                url = (
                    f"https://worldwide.espacenet.com/patent/search?q=pn%3D{ref}"
                    if ref else ""
                )

                articles.append(RawArticle(
                    title=title,
                    url=url,
                    source="EPO Patent",
                    published_date=pub_date,
                    snippet=f"Patent by {applicant_str} ({patent['country']})",
                    content=abstract,
                ))

        logger.info(f"EPO: fetched {len(articles)} patents for '{domain}'")

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 403:
            logger.warning("EPO API throttled (HTTP 403) — retry later")
        else:
            logger.warning(f"EPO API error ({e.response.status_code}): {e}")
    except Exception as e:
        logger.warning(f"EPO patent fetch failed: {e}")

    return articles
