"""
Web-Powered Source Discovery — finds real, working RSS feeds and news sources
for any domain by searching the web, curating results via LLM, and validating feeds.

Runs on first pipeline execution for a domain and re-discovers every ~180 days.
Discovered sources are stored in the StoredDomainReference alongside LLM-generated feeds.

Storage: Integrated into data/domain_references/{domain_slug}.json
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Optional

import feedparser
from pydantic import BaseModel, Field

from core.llm.output_schemas.base import LLMOutputBase

logger = logging.getLogger("sensing.source_discovery")

SOURCE_DISCOVERY_TTL_DAYS = 180  # Re-discover sources every ~6 months
MAX_DISCOVERY_QUERIES = 8
MAX_SEARCH_RESULTS_PER_QUERY = 10
MAX_VALIDATED_SOURCES = 20
FEED_VALIDATION_TIMEOUT = 10  # seconds per feed probe


# ── Schemas ──────────────────────────────────────────────────────────


class DiscoveredSource(BaseModel):
    """A single source discovered via web search and validated."""

    name: str = Field(description="Human-readable name of the source.")
    site_url: str = Field(description="Main website URL.")
    feed_url: str = Field(
        default="",
        description="RSS/Atom feed URL if discovered. Empty if no feed found.",
    )
    source_type: str = Field(
        description=(
            "Type of source: 'blog', 'news_site', 'subreddit', 'newsletter', "
            "'academic', 'company_blog', 'aggregator', or 'other'."
        )
    )
    description: str = Field(
        description="1-2 sentence description of what this source covers."
    )
    relevance_reason: str = Field(
        description="Why this source is relevant to the target domain."
    )


class SourceDiscoveryQueries(LLMOutputBase):
    """LLM-generated search queries specifically for finding domain sources."""

    queries: List[str] = Field(
        description=(
            "8-12 web search queries designed to find news sites, blogs, RSS feeds, "
            "newsletters, and authoritative sources for the target domain. "
            "Mix general source-finding queries with domain-specific ones."
        )
    )


class SourceDiscoveryResult(LLMOutputBase):
    """LLM-curated list of domain-relevant sources extracted from web search results."""

    sources: List[DiscoveredSource] = Field(
        description=(
            "10-25 domain-relevant sources. Each should be a real website "
            "that publishes news, articles, or research about the target domain. "
            "Include a mix of news sites, blogs, subreddits, company blogs, "
            "and academic feeds."
        )
    )
    suggested_rss_feeds: List[str] = Field(
        description=(
            "5-15 RSS/Atom feed URLs extracted or inferred from the sources. "
            "Only include URLs you are highly confident are valid RSS feeds. "
            "Common patterns: /feed/, /rss, /atom.xml, /rss.xml, "
            "reddit.com/r/.../.rss, arxiv.org/rss/..."
        )
    )


# ── TTL check ────────────────────────────────────────────────────────


def should_rediscover_sources(sources_last_discovered: str) -> bool:
    """Check if source discovery should run based on TTL.

    Returns True if never discovered or if older than SOURCE_DISCOVERY_TTL_DAYS.
    """
    if not sources_last_discovered:
        return True
    try:
        last_dt = datetime.fromisoformat(sources_last_discovered)
        age_days = (datetime.now(timezone.utc) - last_dt).days
        return age_days >= SOURCE_DISCOVERY_TTL_DAYS
    except (ValueError, TypeError):
        return True


# ── Query generation ─────────────────────────────────────────────────


def _fallback_discovery_queries(domain: str) -> List[str]:
    """Template-based fallback queries when LLM is unavailable."""
    return [
        f"best {domain} news sites blogs RSS feeds",
        f"{domain} industry publications newsletters 2026",
        f"top {domain} technology blogs to follow",
        f"{domain} subreddit reddit community",
        f"{domain} research papers feeds arxiv",
        f"{domain} companies blogs engineering",
        f"best sources for {domain} news and developments",
        f"{domain} RSS feed directory list",
    ]


async def _generate_discovery_queries(
    domain: str,
    domain_summary: str = "",
    existing_feeds: Optional[List[str]] = None,
) -> List[str]:
    """Use LLM to generate smart search queries for source discovery.

    These queries are different from article-finding queries — they aim to find
    the sources themselves (blogs, news sites, RSS directories, lists of feeds).

    Falls back to template-based queries if LLM fails.
    """
    from core.constants import GPU_SENSING_CLASSIFY_LLM
    from core.llm.client import invoke_llm

    existing_text = ""
    if existing_feeds:
        existing_text = (
            "\n\nALREADY KNOWN FEEDS (do NOT search for these again):\n"
            + "\n".join(f"- {url}" for url in existing_feeds[:10])
        )

    prompt = [
        {
            "role": "system",
            "parts": (
                "You are a research librarian specializing in technology media. "
                f"Generate web search queries to find the best news sources, blogs, "
                f"RSS feeds, and newsletters for the '{domain}' domain.\n\n"
                "Your queries should help find:\n"
                "- Industry-specific news sites and blogs\n"
                "- Active subreddits (Reddit communities)\n"
                "- Company/project blogs from key players\n"
                "- Newsletter directories and curated lists\n"
                "- RSS feed directories and aggregator pages\n"
                "- Academic and research publication feeds\n\n"
                "QUERY DESIGN RULES:\n"
                "- Make queries natural language, suitable for DuckDuckGo\n"
                f"- Include queries like 'best {domain} blogs to follow'\n"
                f"- Include queries like '{domain} RSS feeds list'\n"
                f"- Include queries like '{domain} news sources'\n"
                f"- Include queries like 'top {domain} newsletters'\n"
                "- Include queries targeting specific sub-areas of the domain\n"
                "- Do NOT generate queries for finding articles — only for "
                "finding SOURCES\n"
                + existing_text
            ),
        },
        {
            "role": "user",
            "parts": (
                f"Domain: {domain}\n"
                + (f"Domain context: {domain_summary}\n" if domain_summary else "")
                + "\nGenerate 8-12 search queries for finding the best sources. "
                "Return ONLY valid JSON."
            ),
        },
    ]

    try:
        result = await invoke_llm(
            gpu_model=GPU_SENSING_CLASSIFY_LLM.model,
            response_schema=SourceDiscoveryQueries,
            contents=prompt,
            port=GPU_SENSING_CLASSIFY_LLM.port,
        )
        queries = SourceDiscoveryQueries.model_validate(result).queries
        if queries:
            return queries[:MAX_DISCOVERY_QUERIES]
    except Exception as e:
        logger.warning(f"LLM query generation failed, using templates: {e}")

    return _fallback_discovery_queries(domain)


# ── Web search ───────────────────────────────────────────────────────


async def _search_for_sources(
    queries: List[str],
    use_tavily: bool = True,
) -> List[dict]:
    """Run web searches to find source-related pages.

    Uses DuckDuckGo as primary (free, no API key) and Tavily as supplement
    for higher-quality results when available.

    Returns raw search result dicts: [{title, url, snippet}, ...]
    """
    from core.sensing.ingest import _ddgs_search

    all_results: List[dict] = []
    seen_urls: set = set()

    # DuckDuckGo searches (primary, always available)
    for query in queries:
        try:
            results = await asyncio.to_thread(
                _ddgs_search,
                query,
                MAX_SEARCH_RESULTS_PER_QUERY,
                None,  # No time limit for source discovery
            )
            for r in results:
                url = r.get("href", r.get("link", ""))
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_results.append({
                        "title": r.get("title", ""),
                        "url": url,
                        "snippet": r.get("body", ""),
                    })
        except Exception as e:
            logger.warning(f"DDG source search failed for '{query}': {e}")

    # Tavily supplement (if API key available)
    if use_tavily:
        try:
            from core.sensing.sources.google_patent_search import (
                _get_tavily_key,
                _tavily_search,
            )

            if _get_tavily_key():
                tavily_queries = queries[:3]
                for query in tavily_queries:
                    try:
                        results = await _tavily_search(query, max_results=5)
                        for r in results:
                            url = r.get("url", "")
                            if url and url not in seen_urls:
                                seen_urls.add(url)
                                all_results.append({
                                    "title": r.get("title", ""),
                                    "url": url,
                                    "snippet": r.get("content", ""),
                                })
                    except Exception as e:
                        logger.debug(
                            f"Tavily source search failed for '{query}': {e}"
                        )
        except ImportError:
            pass

    logger.info(
        f"Source discovery: {len(all_results)} raw results from "
        f"{len(queries)} queries"
    )
    return all_results


# ── LLM curation ─────────────────────────────────────────────────────


async def _curate_sources_via_llm(
    domain: str,
    search_results: List[dict],
    existing_feeds: Optional[List[str]] = None,
) -> SourceDiscoveryResult:
    """Pass raw web search results to LLM to extract and curate a list of
    domain-relevant sources with their feed URLs."""
    from core.constants import GPU_SENSING_CLASSIFY_LLM
    from core.llm.client import invoke_llm

    # Format search results for LLM
    results_text = ""
    for i, r in enumerate(search_results[:60], 1):
        results_text += (
            f"[{i}] {r['title']}\n"
            f"    URL: {r['url']}\n"
            f"    Snippet: {r['snippet'][:200]}\n\n"
        )

    existing_block = ""
    if existing_feeds:
        existing_block = (
            "\n\nALREADY KNOWN FEEDS (include these in your response if still "
            "valid, but focus on finding NEW sources not in this list):\n"
            + "\n".join(f"- {url}" for url in existing_feeds[:15])
        )

    prompt = [
        {
            "role": "system",
            "parts": (
                "You are a technology media analyst. Given web search results about "
                f"'{domain}' sources, extract a curated list of the best news sources, "
                "blogs, and RSS feeds for monitoring this domain.\n\n"
                "For each source you identify:\n"
                "1. Extract or infer its name and main URL\n"
                "2. Determine its type (blog, news_site, subreddit, newsletter, "
                "   academic, company_blog, aggregator, other)\n"
                "3. Write a brief description of what it covers\n"
                "4. Explain why it's relevant to the domain\n"
                "5. If you can identify or infer an RSS feed URL, include it\n\n"
                "RSS FEED URL PATTERNS (use these to infer feed URLs):\n"
                "- WordPress sites: {site_url}/feed/\n"
                "- Reddit: https://www.reddit.com/r/{subreddit}/.rss\n"
                "- arXiv: http://arxiv.org/rss/{category}\n"
                "- Medium: https://medium.com/feed/{publication}\n"
                "- Substack: https://{name}.substack.com/feed\n"
                "- GitHub: https://github.com/{org}/{repo}/releases.atom\n"
                "- General: {site_url}/rss, {site_url}/rss.xml, "
                "{site_url}/atom.xml, {site_url}/feed.xml\n\n"
                "Also provide a separate list of suggested_rss_feeds containing "
                "ONLY URLs you are highly confident are valid RSS/Atom feeds.\n\n"
                "QUALITY RULES:\n"
                "- Prefer sources that publish frequently (at least weekly)\n"
                "- Prefer sources with actual RSS/Atom feeds\n"
                "- Include a mix: news sites, blogs, subreddits, academic feeds\n"
                "- Exclude generic tech sites unless they have a domain-specific "
                "section\n"
                "- Do NOT include social media profiles (Twitter, LinkedIn, etc.)\n"
                "- Do NOT include paywalled sources without RSS feeds\n"
                + existing_block
            ),
        },
        {
            "role": "user",
            "parts": (
                f"Domain: {domain}\n\n"
                f"WEB SEARCH RESULTS:\n\n{results_text}\n\n"
                "Extract and curate the best sources from these results. "
                "Return ONLY valid JSON."
            ),
        },
    ]

    result = await invoke_llm(
        gpu_model=GPU_SENSING_CLASSIFY_LLM.model,
        response_schema=SourceDiscoveryResult,
        contents=prompt,
        port=GPU_SENSING_CLASSIFY_LLM.port,
    )

    return SourceDiscoveryResult.model_validate(result)


# ── RSS feed validation ──────────────────────────────────────────────


async def _validate_single_feed(url: str) -> Optional[str]:
    """Attempt to parse a single RSS/Atom feed URL.

    Returns the URL if valid (has entries or a feed title), None otherwise.
    """
    try:
        feed = await asyncio.wait_for(
            asyncio.to_thread(feedparser.parse, url),
            timeout=FEED_VALIDATION_TIMEOUT,
        )
        if feed.entries and len(feed.entries) > 0:
            logger.debug(f"Feed validated: {url} ({len(feed.entries)} entries)")
            return url
        if hasattr(feed, "feed") and feed.feed.get("title"):
            logger.debug(f"Feed validated (by title): {url}")
            return url
        logger.debug(f"Feed rejected (no entries or title): {url}")
        return None
    except asyncio.TimeoutError:
        logger.debug(f"Feed timeout: {url}")
        return None
    except Exception as e:
        logger.debug(f"Feed validation failed for {url}: {e}")
        return None


async def _validate_rss_feeds(feed_urls: List[str]) -> List[str]:
    """Validate a list of RSS feed URLs in parallel.

    Returns only URLs that successfully parse as RSS/Atom feeds.
    """
    if not feed_urls:
        return []

    unique_urls = list(dict.fromkeys(feed_urls))

    sem = asyncio.Semaphore(5)

    async def _validate_with_sem(url: str) -> Optional[str]:
        async with sem:
            return await _validate_single_feed(url)

    results = await asyncio.gather(
        *[_validate_with_sem(url) for url in unique_urls]
    )

    validated = [url for url in results if url is not None]
    logger.info(
        f"Feed validation: {len(validated)}/{len(unique_urls)} feeds validated"
    )
    return validated


# ── Top-level orchestrator ───────────────────────────────────────────


async def discover_domain_sources(
    domain: str,
    domain_summary: str = "",
    existing_feeds: Optional[List[str]] = None,
    progress_callback=None,
) -> tuple[List[DiscoveredSource], List[str]]:
    """Top-level source discovery orchestrator.

    1. Generate smart search queries via LLM
    2. Run web searches (DuckDuckGo + Tavily)
    3. Curate results via LLM into source list
    4. Validate RSS feeds
    5. Return (discovered_sources, validated_feed_urls)
    """
    async def _emit(msg: str):
        if progress_callback:
            await progress_callback("source_discovery", 3, msg)

    await _emit(f"Discovering sources for '{domain}'...")

    # Step 1: Generate discovery queries
    logger.info(f"[Source Discovery] Generating search queries for '{domain}'...")
    queries = await _generate_discovery_queries(
        domain=domain,
        domain_summary=domain_summary,
        existing_feeds=existing_feeds,
    )
    logger.info(f"[Source Discovery] Generated {len(queries)} discovery queries")

    # Step 2: Run web searches
    await _emit("Searching the web for domain sources...")
    logger.info("[Source Discovery] Running web searches...")
    search_results = await _search_for_sources(queries)
    logger.info(
        f"[Source Discovery] Got {len(search_results)} raw search results"
    )

    if not search_results:
        logger.warning(
            "[Source Discovery] No search results found, returning empty"
        )
        return [], []

    # Step 3: LLM curation
    await _emit("Curating discovered sources...")
    logger.info("[Source Discovery] Curating via LLM...")
    curated = await _curate_sources_via_llm(
        domain=domain,
        search_results=search_results,
        existing_feeds=existing_feeds,
    )
    logger.info(
        f"[Source Discovery] LLM curated {len(curated.sources)} sources, "
        f"{len(curated.suggested_rss_feeds)} suggested feeds"
    )

    # Step 4: Collect all candidate feed URLs
    candidate_feeds = list(curated.suggested_rss_feeds)
    for source in curated.sources:
        if source.feed_url and source.feed_url not in candidate_feeds:
            candidate_feeds.append(source.feed_url)

    # Step 5: Validate feeds
    await _emit("Validating RSS feeds...")
    logger.info(
        f"[Source Discovery] Validating {len(candidate_feeds)} candidate feeds..."
    )
    validated_feeds = await _validate_rss_feeds(candidate_feeds)
    logger.info(f"[Source Discovery] {len(validated_feeds)} feeds validated")

    # Clear invalid feed URLs from source objects
    validated_set = set(validated_feeds)
    for source in curated.sources:
        if source.feed_url and source.feed_url not in validated_set:
            source.feed_url = ""

    await _emit(
        f"Discovered {len(curated.sources)} sources, "
        f"{len(validated_feeds)} valid feeds"
    )

    return curated.sources, validated_feeds
