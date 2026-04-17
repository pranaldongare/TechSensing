"""
LIR deduplication — content-hash + URL dedup for raw items.

Reuses URL normalization pattern from core/sensing/dedup.py.
"""

import hashlib
import logging
from typing import List, Set
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from core.lir.models import LIRRawItem

logger = logging.getLogger("lir.dedup")

# Tracking params to strip during URL normalization
_TRACKING_KEYS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
    "ref", "source", "fbclid", "gclid",
}


def _normalize_url(url: str) -> str:
    """Strip tracking params and normalize URL for comparison."""
    try:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        cleaned = {k: v for k, v in params.items() if k not in _TRACKING_KEYS}
        clean_query = urlencode(cleaned, doseq=True)
        return (
            urlunparse(parsed._replace(query=clean_query, fragment=""))
            .rstrip("/")
            .lower()
        )
    except Exception:
        return url.lower().strip()


def _content_hash(item: LIRRawItem) -> str:
    """Compute a content hash from title + URL."""
    text = f"{item.title.lower().strip()}|{_normalize_url(item.url)}"
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def deduplicate_lir_items(
    items: List[LIRRawItem],
    existing_ids: Set[str] | None = None,
) -> List[LIRRawItem]:
    """Remove duplicate LIR items by URL normalization and content hash.

    Args:
        items: Raw items to deduplicate.
        existing_ids: Optional set of already-known item_ids to skip.

    Returns:
        Deduplicated list preserving original order.
    """
    seen_urls: Set[str] = set()
    seen_hashes: Set[str] = set()
    known = existing_ids or set()
    unique: List[LIRRawItem] = []

    for item in items:
        # Skip if already in storage
        if item.item_id in known:
            continue

        norm_url = _normalize_url(item.url)
        if norm_url in seen_urls:
            continue

        ch = _content_hash(item)
        if ch in seen_hashes:
            continue

        seen_urls.add(norm_url)
        seen_hashes.add(ch)
        unique.append(item)

    removed = len(items) - len(unique)
    if removed > 0:
        logger.info(f"LIR dedup: {len(items)} -> {len(unique)} (removed {removed})")

    return unique
