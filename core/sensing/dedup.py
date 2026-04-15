"""
Deduplication of collected articles.
Uses three-tier dedup:
  1. URL normalization (exact match)
  2. Fuzzy title matching (SequenceMatcher, 85% threshold)
  3. TF-IDF cosine similarity on title+snippet (0.65 threshold)
"""

from difflib import SequenceMatcher
from typing import List
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from core.sensing.config import DEDUP_SIMILARITY_THRESHOLD
from core.sensing.ingest import RawArticle

import logging

logger = logging.getLogger("sensing.dedup")

SEMANTIC_SIMILARITY_THRESHOLD = 0.65


def deduplicate_articles(articles: List[RawArticle]) -> List[RawArticle]:
    """Remove duplicate articles using three-tier dedup."""
    # Tier 1 + 2: URL + fuzzy title (existing logic)
    tier1_unique = _url_and_title_dedup(articles)

    # Tier 3: TF-IDF semantic dedup on title+snippet
    final_unique = _tfidf_dedup(tier1_unique)

    removed = len(articles) - len(final_unique)
    if removed > 0:
        logger.info(
            f"Dedup: {len(articles)} -> {len(final_unique)} "
            f"(removed {removed}: URL/title={len(articles)-len(tier1_unique)}, "
            f"semantic={len(tier1_unique)-len(final_unique)})"
        )

    return final_unique


def _url_and_title_dedup(articles: List[RawArticle]) -> List[RawArticle]:
    """Tier 1+2: URL normalization + fuzzy title matching."""
    seen_urls: set[str] = set()
    seen_titles: list[str] = []
    unique: List[RawArticle] = []

    for article in articles:
        norm_url = _normalize_url(article.url)
        if norm_url in seen_urls:
            continue
        if _is_title_duplicate(article.title, seen_titles):
            continue

        seen_urls.add(norm_url)
        seen_titles.append(article.title.lower().strip())
        unique.append(article)

    return unique


def _tfidf_dedup(articles: List[RawArticle]) -> List[RawArticle]:
    """Tier 3: TF-IDF cosine similarity on title+snippet."""
    if len(articles) < 2:
        return articles

    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
    except ImportError:
        logger.warning("scikit-learn not installed, skipping semantic dedup")
        return articles

    # Build text corpus from title + snippet
    corpus = []
    for a in articles:
        text = f"{a.title} {a.snippet or ''}"
        corpus.append(text.lower().strip())

    try:
        vectorizer = TfidfVectorizer(
            max_features=5000,
            stop_words="english",
            ngram_range=(1, 2),
        )
        tfidf_matrix = vectorizer.fit_transform(corpus)
        sim_matrix = cosine_similarity(tfidf_matrix)
    except Exception as e:
        logger.warning(f"TF-IDF dedup failed: {e}")
        return articles

    # Mark duplicates (keep the first occurrence)
    is_duplicate = [False] * len(articles)
    for i in range(len(articles)):
        if is_duplicate[i]:
            continue
        for j in range(i + 1, len(articles)):
            if is_duplicate[j]:
                continue
            if sim_matrix[i, j] >= SEMANTIC_SIMILARITY_THRESHOLD:
                is_duplicate[j] = True
                logger.debug(
                    f"Semantic dedup: '{articles[j].title[:60]}' "
                    f"duplicate of '{articles[i].title[:60]}' "
                    f"(sim={sim_matrix[i, j]:.2f})"
                )

    return [a for a, dup in zip(articles, is_duplicate) if not dup]


def _normalize_url(url: str) -> str:
    """Strip tracking params and normalize URL for comparison."""
    try:
        parsed = urlparse(url)
        # Remove common tracking parameters
        params = parse_qs(parsed.query)
        tracking_keys = {
            "utm_source",
            "utm_medium",
            "utm_campaign",
            "utm_content",
            "utm_term",
            "ref",
            "source",
            "fbclid",
            "gclid",
        }
        cleaned = {k: v for k, v in params.items() if k not in tracking_keys}
        clean_query = urlencode(cleaned, doseq=True)
        return (
            urlunparse(parsed._replace(query=clean_query, fragment=""))
            .rstrip("/")
            .lower()
        )
    except Exception:
        return url.lower().strip()


def _is_title_duplicate(title: str, seen_titles: list[str]) -> bool:
    """Check if a title is too similar to any previously seen title."""
    normalized = title.lower().strip()
    for seen in seen_titles:
        ratio = SequenceMatcher(None, normalized, seen).ratio()
        if ratio >= DEDUP_SIMILARITY_THRESHOLD:
            return True
    return False
