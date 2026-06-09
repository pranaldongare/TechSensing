"""
China-specific sources and queries for the China Focus report mode.

When China Focus is enabled the whole report is China-scoped, so ingestion is
driven by these China feeds/queries instead of the general ones. A small set of
US-oriented queries is also provided to ground the China-vs-US comparison.

Queries are deliberately region/category-driven (never pinned to specific
vendor or model names) to avoid biasing toward whatever was prominent at the
model's training cutoff.
"""

from typing import List

# Curated China-tech RSS feeds (English-language coverage of Chinese tech/AI).
CHINA_RSS_FEEDS: List[str] = [
    "https://syncedreview.com/feed/",        # Synced — Chinese AI research/industry
    "https://technode.com/feed/",            # TechNode — China tech
    "https://pandaily.com/feed/",            # Pandaily — China tech
    "https://kr-asia.com/feed",              # KrASIA — China/Asia startups
    "https://www.scmp.com/rss/36/feed",      # SCMP — Tech
]

# Region terms used to bias source fetchers (arXiv/DDG/Semantic Scholar/Reddit)
# toward China-affiliated work.
CHINA_REGION_TERMS: List[str] = ["China", "Chinese"]


def get_china_feeds(domain: str) -> List[str]:
    """RSS feeds for China mode. Domain-agnostic China-tech feeds; the
    classifier + China report prompts scope them to the target domain."""
    return list(CHINA_RSS_FEEDS)


def get_china_search_queries(domain: str) -> List[str]:
    """China-scoped, stream-organized search queries for the domain.

    Streams: Business, Technology, Implementation, Research — plus a general
    catch-all. Region/category-driven only (no vendor/model names).
    """
    return [
        f"China {domain} latest developments",
        f"Chinese {domain} model OR system release",      # technology
        f"China {domain} research paper OR benchmark",    # research
        f"China {domain} open source project",            # research / OSS
        f"China {domain} startup funding OR investment",   # business
        f"China {domain} commercialization OR partnership",  # business
        f"China {domain} deployment OR application OR product",  # implementation
        f"China {domain} agentic OR enterprise adoption",  # implementation
        f"China {domain} policy OR regulation OR standards",  # business/policy
        f"Chinese AI lab OR university {domain}",          # research/tech
    ]


def get_us_comparison_queries(domain: str) -> List[str]:
    """US-scoped queries used only to ground the China-vs-US comparison.

    Region/category-driven (no vendor/model names) to stay evergreen.
    """
    return [
        f"United States {domain} latest developments",
        f"US {domain} frontier model OR system release",
        f"US {domain} ecosystem funding OR investment",
        f"American AI lab OR university {domain} research",
        f"US {domain} open source OR deployment",
    ]
