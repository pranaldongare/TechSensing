"""RSS / company-blog auto-discovery provider.

For each company we attempt a handful of conventional feed paths on
the company's main domain (``/feed``, ``/rss``, ``/blog/feed``,
``/news/feed``). Every discovered-valid feed URL is cached per user at
``data/{user_id}/sensing/discovered_feeds.json`` so subsequent runs
skip the discovery probe and go straight to parsing.

No-auth, no API keys. Fully additive — if nothing is discovered the
provider returns an empty list and the pipeline degrades gracefully to
its other sources.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import aiofiles
import feedparser
import httpx

from core.sensing.ingest import RawArticle

logger = logging.getLogger("sensing.providers.rss")


# Common feed paths probed per domain. Ordered by "most likely to exist".
FEED_PATHS = (
    "/feed",
    "/rss",
    "/feed.xml",
    "/rss.xml",
    "/blog/feed",
    "/blog/rss",
    "/news/feed",
    "/news/rss",
    "/feed/",
    "/atom.xml",
    "/index.xml",
)

# Companies whose public sites differ from their canonical name.
_DOMAIN_HINTS: Dict[str, List[str]] = {
    "openai": ["openai.com"],
    "anthropic": ["anthropic.com"],
    "google deepmind": ["deepmind.google", "deepmind.com"],
    "deepmind": ["deepmind.google", "deepmind.com"],
    "meta": ["meta.com", "about.fb.com"],
    "meta ai": ["ai.meta.com"],
    "facebook": ["about.fb.com", "meta.com"],
    "microsoft": ["microsoft.com", "blogs.microsoft.com"],
    "apple": ["apple.com"],
    "amazon": ["aboutamazon.com"],
    "amazon web services": ["aws.amazon.com"],
    "aws": ["aws.amazon.com"],
    "nvidia": ["blogs.nvidia.com", "nvidia.com"],
    "hugging face": ["huggingface.co"],
    "mistral": ["mistral.ai"],
    "mistral ai": ["mistral.ai"],
    "stability ai": ["stability.ai"],
    "cohere": ["cohere.com"],
    "databricks": ["databricks.com"],
    "pinecone": ["pinecone.io"],
    "perplexity": ["perplexity.ai"],
    "xai": ["x.ai"],
    "together ai": ["together.ai"],
    "ibm": ["research.ibm.com", "ibm.com"],
    "intel": ["intel.com"],
    "red hat": ["redhat.com"],
    "langchain": ["blog.langchain.dev", "langchain.com"],
    "llamaindex": ["llamaindex.ai"],
}


def _slug(company: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "", (company or "").lower())
    return s


def _candidate_domains(company: str) -> List[str]:
    """Return ordered list of domains to probe."""
    key = (company or "").strip().lower()
    hints = _DOMAIN_HINTS.get(key, [])
    slug = _slug(company)
    if slug:
        hints = hints + [f"{slug}.com", f"{slug}.ai", f"{slug}.io"]
    # Dedup preserving order
    seen: set = set()
    out: List[str] = []
    for d in hints:
        if d and d not in seen:
            seen.add(d)
            out.append(d)
    return out


def _cache_path(user_id: str) -> str:
    return os.path.join(
        "data", user_id, "sensing", "discovered_feeds.json"
    )


async def _load_cache(user_id: str) -> Dict[str, List[str]]:
    path = _cache_path(user_id)
    if not os.path.exists(path):
        return {}
    try:
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            raw = await f.read()
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning(f"[rss] cache read failed: {e}")
        return {}


async def _save_cache(
    user_id: str, cache: Dict[str, List[str]]
) -> None:
    path = _cache_path(user_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(cache, ensure_ascii=False, indent=2))
    except Exception as e:
        logger.warning(f"[rss] cache write failed: {e}")


async def _validate_feed(client: httpx.AsyncClient, url: str) -> bool:
    """HEAD + tiny GET + feedparser sanity check."""
    try:
        resp = await client.get(url, timeout=10, follow_redirects=True)
        if resp.status_code >= 400:
            return False
        body = resp.text[:4000]
        if not body:
            return False
        ct = resp.headers.get("content-type", "").lower()
        if any(
            m in ct
            for m in ("xml", "rss", "atom", "application/rdf")
        ):
            return True
        # Some servers return text/html — still ok if content parses.
        parsed = feedparser.parse(body)
        return bool(parsed.entries)
    except Exception:
        return False


async def _discover_feeds(
    company: str, *, max_per_domain: int = 2
) -> List[str]:
    domains = _candidate_domains(company)
    if not domains:
        return []

    found: List[str] = []
    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
        for d in domains[:3]:  # cap probes
            hits = 0
            for p in FEED_PATHS:
                url = f"https://{d}{p}"
                if await _validate_feed(client, url):
                    found.append(url)
                    hits += 1
                    if hits >= max_per_domain:
                        break
            if hits:
                # If one domain yielded a feed, don't spam the next.
                break
    return found


def _parse_feed_date(entry: dict) -> Optional[datetime]:
    for key in ("published_parsed", "updated_parsed"):
        val = entry.get(key)
        if val:
            try:
                return datetime(*val[:6], tzinfo=timezone.utc)
            except Exception:
                continue
    return None


async def _parse_feed(
    feed_url: str, *, lookback_days: int, company: str, max_results: int
) -> List[RawArticle]:
    try:
        feed = await asyncio.to_thread(feedparser.parse, feed_url)
    except Exception as e:
        logger.warning(f"[rss] parse failed for {feed_url}: {e}")
        return []

    source_name = (feed.feed.get("title") or feed_url)[:80]
    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=lookback_days)
        if lookback_days > 0
        else None
    )
    out: List[RawArticle] = []
    for entry in feed.entries[: max_results * 2]:
        pub = _parse_feed_date(entry)
        if cutoff and pub and pub < cutoff:
            continue
        title = (entry.get("title") or "Untitled").strip()
        link = entry.get("link") or ""
        if not link:
            continue
        # Light company-relevance filter — accept by default but
        # prefer items that mention the company name.
        summary = entry.get("summary", "")[:500]
        out.append(
            RawArticle(
                title=title,
                url=link,
                source=source_name,
                published_date=pub.isoformat() if pub else None,
                snippet=summary,
            )
        )
        if len(out) >= max_results:
            break

    # Favour entries mentioning the company name in title/summary.
    if company:
        needle = company.lower()
        matched = [
            a
            for a in out
            if needle in (a.title or "").lower()
            or needle in (a.snippet or "").lower()
        ]
        if matched:
            return matched[:max_results]
    return out[:max_results]


class RSSProvider:
    """Auto-discovered company blog / news feed provider."""

    name = "rss"

    def __init__(self, user_id: str = ""):
        # ``user_id`` is supplied by the aggregator when known; otherwise
        # the cache read/write is skipped and every run re-discovers.
        self.user_id = user_id

    async def search(
        self,
        company: str,
        *,
        queries: List[str],  # noqa: ARG002 — feed-driven
        domain: str = "",  # noqa: ARG002
        lookback_days: int = 30,
        max_results: int = 15,
    ) -> List[RawArticle]:
        if not company:
            return []

        cache: Dict[str, List[str]] = {}
        if self.user_id:
            cache = await _load_cache(self.user_id)

        cache_key = company.strip().lower()
        feeds = cache.get(cache_key) or []
        if not feeds:
            feeds = await _discover_feeds(company)
            if feeds and self.user_id:
                cache[cache_key] = feeds
                await _save_cache(self.user_id, cache)

        if not feeds:
            logger.info(f"[rss] {company!r}: no feed discovered")
            return []

        per_feed = max(3, max_results // max(1, len(feeds)))
        batches = await asyncio.gather(
            *[
                _parse_feed(
                    url,
                    lookback_days=lookback_days,
                    company=company,
                    max_results=per_feed,
                )
                for url in feeds
            ],
            return_exceptions=True,
        )
        merged: List[RawArticle] = []
        seen: set = set()
        for batch in batches:
            if isinstance(batch, BaseException):
                continue
            for art in batch:
                if art.url and art.url not in seen:
                    seen.add(art.url)
                    merged.append(art)

        logger.info(
            f"[rss] {company!r}: {len(merged)} article(s) from "
            f"{len(feeds)} feed(s)"
        )
        return merged[:max_results]
