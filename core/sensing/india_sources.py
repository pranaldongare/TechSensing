"""
India-specific sources and queries for the India Focus report mode.

When India Focus is enabled the whole report is India-scoped, so ingestion is
driven by these India feeds/queries instead of the general ones. A small set of
global-frontier queries is also provided to ground the India-vs-Global comparison.

Queries are deliberately region/category-driven (never pinned to specific
vendor or model names) to avoid biasing toward whatever was prominent at the
model's training cutoff.
"""

from typing import List

# Curated India-tech RSS feeds (English-language coverage of Indian tech/AI).
INDIA_RSS_FEEDS: List[str] = [
    "https://analyticsindiamag.com/feed/",   # AIM — India AI/analytics
    "https://inc42.com/feed/",               # Inc42 — India startups/tech
    "https://yourstory.com/feed",            # YourStory — India startups
    "https://www.medianama.com/feed/",       # MediaNama — India tech policy
    "https://economictimes.indiatimes.com/tech/rssfeeds/13357270.cms",  # ET Tech
]

# Region terms used to bias source fetchers (arXiv/DDG/Semantic Scholar/Reddit)
# toward India-affiliated work.
INDIA_REGION_TERMS: List[str] = ["India", "Indian"]


def get_india_feeds(domain: str) -> List[str]:
    """RSS feeds for India mode. Domain-agnostic India-tech feeds; the
    classifier + India report prompts scope them to the target domain."""
    return list(INDIA_RSS_FEEDS)


def get_india_search_queries(domain: str) -> List[str]:
    """India-scoped, stream-organized search queries for the domain.

    Streams: Business, Technology, Implementation, Research — plus a general
    catch-all. Region/category-driven only (no vendor/model names).
    """
    return [
        f"India {domain} latest developments",
        f"Indian {domain} model OR system release",         # technology
        f"India {domain} research paper OR benchmark",      # research
        f"India {domain} open source project",              # research / OSS
        f"India {domain} startup funding OR investment",     # business
        f"India {domain} commercialization OR partnership",  # business
        f"India {domain} deployment OR application OR product",  # implementation
        f"India {domain} agentic OR enterprise adoption",   # implementation
        f"India {domain} policy OR regulation OR IndiaAI Mission",  # business/policy
        f"Indian AI lab OR IIT OR IISc {domain}",           # research/tech
    ]


def get_global_comparison_queries(domain: str) -> List[str]:
    """Global-frontier queries used only to ground the India-vs-Global comparison.

    Region/category-driven (no vendor/model names) to stay evergreen.
    """
    return [
        f"global {domain} frontier model OR system release",
        f"US {domain} latest developments",
        f"China {domain} latest developments",
        f"{domain} state of the art global benchmark",
        f"global {domain} ecosystem funding OR investment",
    ]
