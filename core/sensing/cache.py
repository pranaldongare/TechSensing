"""
Article classification cache — avoids re-classifying articles
already processed in previous pipeline runs.

Storage: data/sensing_cache/{url_hash}.json
TTL: 30 days
"""

import hashlib
import json
import logging
import os
import time
from typing import Optional

from core.llm.output_schemas.sensing_outputs import ClassifiedArticle

logger = logging.getLogger("sensing.cache")

CACHE_DIR = "data/sensing_cache"
CACHE_TTL_SECONDS = 30 * 24 * 3600  # 30 days


def _url_hash(url: str) -> str:
    """SHA256 hash of URL, truncated to 16 chars."""
    return hashlib.sha256(url.strip().lower().encode()).hexdigest()[:16]


def _ensure_cache_dir() -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)


def get_cached_classification(url: str) -> Optional[ClassifiedArticle]:
    """Look up a cached classification by article URL."""
    h = _url_hash(url)
    fpath = os.path.join(CACHE_DIR, f"{h}.json")

    if not os.path.exists(fpath):
        return None

    try:
        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None

    cached_at = data.get("cached_at", 0)
    if time.time() - cached_at > CACHE_TTL_SECONDS:
        # Expired
        try:
            os.remove(fpath)
        except OSError:
            pass
        return None

    try:
        return ClassifiedArticle.model_validate(data["article"])
    except Exception:
        return None


def cache_classification(article: ClassifiedArticle) -> None:
    """Cache a classified article by its URL."""
    _ensure_cache_dir()
    h = _url_hash(article.url)
    fpath = os.path.join(CACHE_DIR, f"{h}.json")

    try:
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(
                {"cached_at": time.time(), "article": article.model_dump()},
                f,
                ensure_ascii=False,
            )
    except Exception as e:
        logger.warning(f"Failed to cache classification for {article.url}: {e}")


def clear_expired_cache() -> int:
    """Remove expired cache entries. Returns count of removed files."""
    if not os.path.exists(CACHE_DIR):
        return 0

    removed = 0
    now = time.time()
    for fname in os.listdir(CACHE_DIR):
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(CACHE_DIR, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            if now - data.get("cached_at", 0) > CACHE_TTL_SECONDS:
                os.remove(fpath)
                removed += 1
        except Exception:
            try:
                os.remove(fpath)
                removed += 1
            except OSError:
                pass

    if removed:
        logger.info(f"Cache cleanup: removed {removed} expired entries")
    return removed
