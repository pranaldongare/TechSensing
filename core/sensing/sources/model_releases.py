"""
Model Releases — 3-tier structured sourcing for recent AI model releases.

Tier 1 (Primary): HuggingFace Hub API — open-weight models with real metadata
Tier 2 (Curated): Major AI lab blog RSS — proprietary models (OpenAI, Anthropic, etc.)
Tier 3 (Fallback): DDG search — only used when Tiers 1+2 yield very few results
"""

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import feedparser
import httpx

from core.sensing.config import (
    HF_KNOWN_ORGS,
    HF_MIN_DOWNLOADS,
    HF_MIN_LIKES,
    MAJOR_LAB_BLOG_FEEDS,
    MODEL_ANNOUNCEMENT_KEYWORDS,
)
from core.sensing.date_filter import filter_articles_by_date
from core.sensing.ingest import RawArticle, search_duckduckgo

logger = logging.getLogger("sensing.sources.model_releases")

HF_API_URL = "https://huggingface.co/api/models"

# ── HuggingFace pipeline_tag → modality mapping ──
_HF_PIPELINE_TO_MODALITY = {
    "text-generation": "Text",
    "text2text-generation": "Text",
    "fill-mask": "Text",
    "conversational": "Text",
    "text-classification": "Text",
    "question-answering": "Text",
    "summarization": "Text",
    "translation": "Text",
    "image-classification": "Multimodal",
    "visual-question-answering": "Multimodal",
    "image-to-text": "Multimodal",
    "image-text-to-text": "Multimodal",
    "document-question-answering": "Multimodal",
    "zero-shot-image-classification": "Multimodal",
    "zero-shot-object-detection": "Multimodal",
    "video-text-to-text": "Multimodal",
    "text-to-image": "Image",
    "image-to-image": "Image",
    "unconditional-image-generation": "Image",
    "image-segmentation": "Image",
    "text-to-video": "Video",
    "video-classification": "Video",
    "text-to-audio": "Audio",
    "audio-classification": "Audio",
    "automatic-speech-recognition": "Speech",
    "text-to-speech": "Speech",
    "feature-extraction": "Embedding",
    "sentence-similarity": "Embedding",
    "object-detection": "Multimodal",
    "depth-estimation": "3D",
    "reinforcement-learning": "Action",
    "robotics": "Action",
}

# ── Parameter size patterns in tags ──
_PARAM_PATTERN = re.compile(r"(\d+\.?\d*)\s*[bB](?:illion)?", re.IGNORECASE)
_PARAM_TAG_PATTERN = re.compile(r"^(\d+\.?\d*)[bB]$", re.IGNORECASE)


_PARAM_NAME_PATTERN = re.compile(r"[-_](\d+\.?\d*)[bB](?:[-_]|$)")


def _extract_params_from_tags(tags: List[str], model_id: str = "") -> str:
    """Extract parameter count from HuggingFace model tags or model name."""
    for tag in tags:
        m = _PARAM_TAG_PATTERN.match(tag.strip())
        if m:
            return f"{m.group(1)}B"
    # Fallback: extract from model name (e.g., "Qwen3.6-35B-A3B")
    if model_id:
        name_part = model_id.split("/")[-1] if "/" in model_id else model_id
        m = _PARAM_NAME_PATTERN.search(name_part)
        if m:
            return f"{m.group(1)}B"
    return ""


def _extract_model_type_from_tags(tags: List[str]) -> str:
    """Infer model architecture type from tags."""
    tag_set = {t.lower() for t in tags}
    if "moe" in tag_set or "mixture-of-experts" in tag_set:
        return "MoE"
    if "mamba" in tag_set or "state-space" in tag_set:
        return "Mamba"
    if "diffusion" in tag_set:
        return "Diffusion"
    if "transformer" in tag_set or "transformers" in tag_set:
        return "Transformer"
    if "flow-matching" in tag_set:
        return "Flow-matching"
    return "Transformer"  # default assumption


def _extract_license_from_tags(tags: List[str]) -> str:
    """Extract license information from HuggingFace tags."""
    license_prefixes = ("license:", "license-")
    for tag in tags:
        tl = tag.lower()
        for prefix in license_prefixes:
            if tl.startswith(prefix):
                return tag[len(prefix):].strip()
    return ""


def _is_quantization(model: dict) -> bool:
    """Check if a model is a quantization/repackaging (not an original release)."""
    model_id = model.get("modelId") or model.get("id", "")
    name_lower = model_id.lower()
    tags = {t.lower() for t in model.get("tags", [])}

    # GGUF/GPTQ/AWQ quantizations are repackagings
    quant_indicators = ("gguf", "gptq", "awq", "exl2", "bnb", "fp8")
    if any(q in name_lower for q in quant_indicators):
        return True
    if tags & {"gguf", "gptq", "awq", "exl2"}:
        return True

    # Known quantization uploaders
    quant_uploaders = {"mradermacher", "thebloke", "unsloth", "bartowski"}
    author = model_id.split("/")[0].lower() if "/" in model_id else ""
    if author in quant_uploaders:
        return True

    return False


def _is_significant_model(model: dict) -> bool:
    """Check if a HuggingFace model passes the significance threshold."""
    # Exclude quantizations/repackagings
    if _is_quantization(model):
        return False

    downloads = model.get("downloads", 0) or 0
    likes = model.get("likes", 0) or 0
    model_id = model.get("modelId") or model.get("id", "")
    author = model_id.split("/")[0] if "/" in model_id else ""

    if author.lower() in {org.lower() for org in HF_KNOWN_ORGS}:
        return True
    if downloads >= HF_MIN_DOWNLOADS:
        return True
    if likes >= HF_MIN_LIKES:
        return True
    return False


# ═══════════════════════════════════════════════════════════════════
# Tier 1: HuggingFace Hub API
# ═══════════════════════════════════════════════════════════════════

async def fetch_huggingface_releases(
    lookback_days: int = 30,
    max_results: int = 20,
) -> List[dict]:
    """Tier 1: Fetch recent significant models from HuggingFace Hub API.

    Uses a two-pronged strategy:
    1. Query each known org for recently created models (catches new releases)
    2. Fetch recently created models sorted by downloads (catches breakout models)

    Returns raw HF model dicts (not yet converted to ModelRelease)
    so that the extractor module handles the conversion.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    seen_ids: set = set()
    significant_models: List[dict] = []

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            # Strategy 1: Query each known org for their newest models
            for org in HF_KNOWN_ORGS:
                try:
                    resp = await client.get(
                        HF_API_URL,
                        params={
                            "author": org,
                            "sort": "createdAt",
                            "direction": "-1",
                            "limit": 5,
                        },
                    )
                    if resp.status_code != 200:
                        continue
                    models = resp.json()

                    for model in models:
                        model_id = model.get("modelId") or model.get("id", "")
                        if not model_id or model_id in seen_ids:
                            continue

                        created = model.get("createdAt", "")
                        if not created:
                            continue
                        try:
                            created_dt = datetime.fromisoformat(
                                created.replace("Z", "+00:00")
                            )
                            if created_dt < cutoff:
                                break  # sorted newest-first
                        except (ValueError, TypeError):
                            continue

                        # Skip quantizations even from known orgs
                        if _is_quantization(model):
                            continue

                        # For known orgs, still filter minor variants
                        # (checkpoints, test uploads) by requiring some traction
                        downloads = model.get("downloads", 0) or 0
                        likes = model.get("likes", 0) or 0
                        if downloads >= 100 or likes >= 5:
                            seen_ids.add(model_id)
                            significant_models.append(model)

                except Exception:
                    continue

            # Strategy 2: Fetch recent models sorted by downloads
            # to catch breakout models from lesser-known orgs
            try:
                resp = await client.get(
                    HF_API_URL,
                    params={
                        "sort": "downloads",
                        "direction": "-1",
                        "limit": 200,
                        "full": "false",
                    },
                )
                if resp.status_code == 200:
                    models = resp.json()
                    for model in models:
                        model_id = model.get("modelId") or model.get("id", "")
                        if not model_id or model_id in seen_ids:
                            continue

                        created = model.get("createdAt", "")
                        if not created:
                            continue
                        try:
                            created_dt = datetime.fromisoformat(
                                created.replace("Z", "+00:00")
                            )
                            if created_dt < cutoff:
                                continue
                        except (ValueError, TypeError):
                            continue

                        if _is_significant_model(model):
                            seen_ids.add(model_id)
                            significant_models.append(model)
            except Exception:
                pass

        logger.info(
            f"HuggingFace releases: {len(significant_models)} significant "
            f"models in last {lookback_days} days"
        )

    except Exception as e:
        logger.warning(f"HuggingFace API fetch failed: {e}")

    return significant_models[:max_results]


# ═══════════════════════════════════════════════════════════════════
# Tier 2: Major Lab Blog RSS
# ═══════════════════════════════════════════════════════════════════

def _is_model_announcement(title: str) -> bool:
    """Check if a blog post title looks like a model announcement."""
    title_lower = title.lower()
    return any(kw in title_lower for kw in MODEL_ANNOUNCEMENT_KEYWORDS)


async def fetch_major_lab_blogs(
    lookback_days: int = 30,
) -> List[RawArticle]:
    """Tier 2: Fetch model announcements from major AI lab blog RSS feeds.

    Only returns entries whose titles match model announcement keywords.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    articles: List[RawArticle] = []

    for lab_name, feed_url in MAJOR_LAB_BLOG_FEEDS.items():
        try:
            feed = await asyncio.to_thread(feedparser.parse, feed_url)

            for entry in feed.entries[:20]:
                title = entry.get("title", "")
                if not title or not _is_model_announcement(title):
                    continue

                # Parse date
                pub_date = _parse_feed_date(entry)
                if pub_date and pub_date < cutoff:
                    continue

                articles.append(
                    RawArticle(
                        title=title,
                        url=entry.get("link", ""),
                        source=lab_name,
                        published_date=pub_date.isoformat() if pub_date else None,
                        snippet=entry.get("summary", "")[:500],
                    )
                )
        except Exception as e:
            logger.debug(f"Blog RSS failed for {lab_name}: {e}")

    logger.info(f"Major lab blogs: {len(articles)} announcement articles")
    return articles


# ═══════════════════════════════════════════════════════════════════
# Tier 3: DDG Fallback (existing approach, demoted)
# ═══════════════════════════════════════════════════════════════════

def _model_release_queries() -> List[str]:
    """Generate model release search queries with the current year."""
    year = datetime.now(timezone.utc).year
    return [
        f"new AI model release {year}",
        f"LLM launch open source model {year}",
        f"foundation model release benchmark {year}",
        f"diffusion model release {year}",
        f"AI model announcement parameters open weight {year}",
    ]


async def search_model_releases_ddg(
    lookback_days: int = 30,
    max_results: int = 15,
) -> List[RawArticle]:
    """Tier 3 (fallback): DDG search for model releases.

    Only used when Tiers 1+2 yield very few results.
    Applies strict date filtering.
    """
    try:
        articles = await search_duckduckgo(
            queries=_model_release_queries(),
            domain="Generative AI",
            lookback_days=lookback_days,
        )
        logger.info(f"DDG model releases fallback: {len(articles)} raw articles")

        # Strict date filtering (buffer_multiplier=1.0 — no benefit of doubt)
        articles = filter_articles_by_date(
            articles, lookback_days,
            buffer_multiplier=1.0,
            drop_undated=True,
            label="model-releases-ddg",
        )

        return articles[:max_results]
    except Exception as e:
        logger.warning(f"DDG model releases fallback failed: {e}")
        return []


# ═══════════════════════════════════════════════════════════════════
# Unified orchestrator
# ═══════════════════════════════════════════════════════════════════

async def get_model_releases(lookback_days: int = 30) -> "List":
    """Unified model release sourcing: HF API + major lab blogs + DDG fallback.

    Returns List[ModelRelease] — import is deferred to avoid circular imports.
    """
    from core.sensing.model_release_extractor import (
        build_releases_from_hf,
        extract_model_releases,
        extract_releases_from_blogs,
    )

    all_releases = []

    # Tier 1: HuggingFace (structured, reliable)
    hf_models = await fetch_huggingface_releases(lookback_days)
    if hf_models:
        hf_releases = build_releases_from_hf(hf_models)
        all_releases.extend(hf_releases)
        logger.info(f"Tier 1 (HuggingFace): {len(hf_releases)} releases")

    # Tier 2: Major lab blogs (for proprietary models)
    blog_articles = await fetch_major_lab_blogs(lookback_days)
    if blog_articles:
        blog_releases = await extract_releases_from_blogs(
            blog_articles, lookback_days
        )
        all_releases.extend(blog_releases)
        logger.info(f"Tier 2 (Blogs): {len(blog_releases)} releases")

    # Tier 3: DDG fallback (only if tiers 1+2 yield very few)
    if len(all_releases) < 3:
        logger.info("Tiers 1+2 yielded <3 results, activating DDG fallback...")
        ddg_articles = await search_model_releases_ddg(lookback_days, max_results=15)
        if ddg_articles:
            ddg_releases = await extract_model_releases(
                ddg_articles, lookback_days
            )
            all_releases.extend(ddg_releases)
            logger.info(f"Tier 3 (DDG fallback): {len(ddg_releases)} releases")

    # Deduplicate by normalized model name
    all_releases = _deduplicate_releases(all_releases)

    logger.info(
        f"Model releases total: {len(all_releases)} "
        f"(after dedup across all tiers)"
    )
    return all_releases


def _deduplicate_releases(releases: list) -> list:
    """Deduplicate releases by normalized model name."""
    seen: set = set()
    unique = []
    for r in releases:
        key = r.model_name.lower().strip().replace("-", " ").replace("_", " ")
        # Also normalize org prefix (e.g., "meta-llama/Llama-4" → "llama 4")
        if "/" in key:
            key = key.split("/", 1)[1]
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique


# ── Helpers ──

def _parse_feed_date(entry) -> Optional[datetime]:
    """Parse feedparser entry date into UTC datetime."""
    for date_field in ("published_parsed", "updated_parsed"):
        parsed = entry.get(date_field)
        if parsed:
            try:
                return datetime(*parsed[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return None
