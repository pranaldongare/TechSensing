"""
Model Releases — 3-tier structured sourcing for recent AI model releases.

Tier 1 (Primary): HuggingFace Hub API — open-weight models with real metadata
Tier 2 (Curated): Major AI lab blog RSS — proprietary models (OpenAI, Anthropic, etc.)
Tier 3 (Fallback): DDG search — only used when Tiers 1+2 yield very few results
"""

import asyncio
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import feedparser
import httpx

from core.sensing.config import (
    ARTIFICIAL_ANALYSIS_API_URL,
    HF_KNOWN_ORGS,
    HF_MIN_DOWNLOADS,
    HF_MIN_LIKES,
    MAJOR_LAB_BLOG_FEEDS,
    MODEL_ANNOUNCEMENT_KEYWORDS,
    PROPRIETARY_LAB_QUERIES,
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
# Tier 2: Proprietary model detection (blogs + targeted DDG)
# ═══════════════════════════════════════════════════════════════════

def _is_model_announcement(title: str) -> bool:
    """Check if a blog post title looks like a model announcement."""
    title_lower = title.lower()
    return any(kw in title_lower for kw in MODEL_ANNOUNCEMENT_KEYWORDS)


# Regex patterns for extracting model names from blog/article titles
_TITLE_MODEL_PATTERNS = [
    # "Introducing Claude 4.7", "Announcing GPT-Rosalind", "Meet Gemini 2.5 Flash"
    re.compile(
        r"(?:introducing|announcing|meet|presenting|unveiling)\s+"
        r"([A-Z][A-Za-z]*(?:[-\s][\w.]+){1,3})",
        re.IGNORECASE,
    ),
    # "Claude 4.7 is now available", "GPT-5.4-Cyber release",
    # "Mistral-Large-2 launch"
    re.compile(
        r"((?:Claude|GPT|Gemini|Grok|Command|Mistral|Llama|Phi|Copilot|Qwen)"
        r"(?:[-\s][\w.]+){1,3})",
        re.IGNORECASE,
    ),
]

# Stop words that signal end of model name
_NAME_STOP_WORDS = {
    "is", "are", "was", "for", "the", "a", "an", "and", "or", "with",
    "now", "has", "have", "can", "will", "our", "your", "this", "that",
    "release", "released", "releases", "launch", "launched", "launches",
    "available", "here",
    "brings", "powers", "enables", "hits", "reaches", "gets", "adds",
    "api", "sdk", "users", "update", "updates", "review", "pricing",
    "features", "vs", "compared", "benchmark", "benchmarks",
    "announcement", "announced", "latest", "new", "ai", "code",
    "multi-agent", "multimodal", "model", "beta", "alpha", "preview",
}

# Names that look like model names but aren't actual model releases
_FALSE_POSITIVE_NAMES = {
    "claude code", "gemini ai", "gemini api", "gpt store",
    "copilot pro", "copilot workspace",
}

# Map source/lab name to organization for proprietary releases
_LAB_ORG_MAP = {
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "google ai": "Google",
    "google": "Google",
    "deepmind": "Google DeepMind",
    "cohere": "Cohere",
    "mistral": "Mistral AI",
    "xai": "xAI",
    "meta": "Meta",
}


def _extract_model_from_title(title: str) -> Optional[str]:
    """Try to extract a model name from a blog/article title.

    Returns the model name string if found, None otherwise.
    Only accepts names that are predominantly ASCII (model names always are).
    """
    for pattern in _TITLE_MODEL_PATTERNS:
        m = pattern.search(title)
        if m:
            raw_name = m.group(1).strip()
            # Trim: keep tokens until first stop word or non-ASCII token
            parts = raw_name.split()
            trimmed = []
            for p in parts:
                if p.lower() in _NAME_STOP_WORDS:
                    break
                # Stop at non-ASCII tokens (CJK, etc.)
                if not p.isascii():
                    break
                trimmed.append(p)
            name = " ".join(trimmed) if trimmed else ""
            # Filter out generic words that aren't model names
            if len(name) < 3 or name.lower() in {"new", "our", "the", "a"}:
                continue
            # Reject known false positives
            if name.lower() in _FALSE_POSITIVE_NAMES:
                continue
            # Model releases must have a version indicator (digit or codename)
            # e.g., "Claude 4.7", "GPT-5.4-Cyber", "Gemini 2.5 Flash"
            # Reject bare brand names like "Gemini AI" or "Gemini"
            has_version = bool(re.search(r"\d", name))
            # Codename: multi-word OR hyphenated with uppercase after hyphen
            tokens = name.replace("-", " ").split()
            has_codename = len(tokens) >= 2 and any(
                t[0].isupper() for t in tokens[1:]
            )
            if not has_version and not has_codename:
                continue
            return name
    return None


def _build_release_from_article(
    title: str,
    url: str,
    source: str,
    published_date: Optional[str],
    snippet: str = "",
) -> Optional[object]:
    """Build a ModelRelease directly from article metadata without LLM.

    Only works for clear model announcement titles. Returns None if
    the model name cannot be confidently extracted.
    """
    from core.llm.output_schemas.sensing_outputs import ModelRelease

    model_name = _extract_model_from_title(title)
    if not model_name:
        return None

    # Infer organization from source, model name, or URL
    org = _LAB_ORG_MAP.get(source.lower(), "")
    if not org:
        # Try to infer from model name prefix
        name_lower = model_name.lower()
        if name_lower.startswith("gpt") or name_lower.startswith("o1") or name_lower.startswith("o3"):
            org = "OpenAI"
        elif name_lower.startswith("claude"):
            org = "Anthropic"
        elif name_lower.startswith("gemini"):
            org = "Google"
        elif name_lower.startswith("grok"):
            org = "xAI"
        elif name_lower.startswith("command"):
            org = "Cohere"
        elif name_lower.startswith("mistral"):
            org = "Mistral AI"
        elif name_lower.startswith("llama") or name_lower.startswith("phi"):
            org = "Meta"
        elif name_lower.startswith("qwen"):
            org = "Alibaba"
        else:
            org = source  # fallback to source field

    # Determine release date
    release_date = ""
    if published_date:
        try:
            dt = datetime.fromisoformat(
                published_date.replace("Z", "+00:00")
            )
            release_date = dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            release_date = published_date[:10] if len(published_date) >= 10 else ""

    return ModelRelease(
        model_name=model_name,
        organization=org,
        release_date=release_date,
        release_status="Released",
        parameters="",
        license="Proprietary",
        is_open_source="Closed",
        model_type="",
        modality="Text",
        notable_features=snippet[:200] if snippet else "",
        source_url=url,
    )


async def fetch_major_lab_blogs(
    lookback_days: int = 30,
) -> List[RawArticle]:
    """Tier 2a: Fetch model announcements from major AI lab blog RSS feeds.

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


async def search_proprietary_releases_ddg(
    lookback_days: int = 30,
    max_results: int = 10,
) -> List[RawArticle]:
    """Tier 2b: Targeted DDG search for proprietary model announcements.

    Always runs (not just as fallback) to catch Claude, GPT, Gemini, etc.
    Uses lab-specific queries for higher precision.
    """
    year = datetime.now(timezone.utc).year
    queries = [f"{q} {year}" for q in PROPRIETARY_LAB_QUERIES]

    try:
        articles = await search_duckduckgo(
            queries=queries,
            domain="Generative AI",
            lookback_days=lookback_days,
        )
        logger.info(
            f"Proprietary lab DDG search: {len(articles)} raw articles"
        )

        # Keep undated articles — DDG rarely provides dates for recent
        # results, but our year-specific queries already scope them.
        # Only drop articles with dates clearly outside the window.
        articles = filter_articles_by_date(
            articles, lookback_days,
            buffer_multiplier=1.5,
            drop_undated=False,
            label="proprietary-releases-ddg",
        )

        return articles[:max_results]
    except Exception as e:
        logger.warning(f"Proprietary lab DDG search failed: {e}")
        return []


# ═══════════════════════════════════════════════════════════════════
# Tier 2c: Artificial Analysis API (structured, covers open + proprietary)
# ═══════════════════════════════════════════════════════════════════

async def fetch_artificial_analysis_releases(
    lookback_days: int = 30,
    max_results: int = 25,
) -> "List":
    """Tier 2c: Fetch model data from Artificial Analysis API.

    Returns ModelRelease objects for models tracked by artificialanalysis.ai.
    Covers both open-weight and proprietary models with benchmark data.
    Requires ARTIFICIAL_ANALYSIS_API_KEY env var; gracefully skips if unset.
    """
    from core.llm.output_schemas.sensing_outputs import ModelRelease

    api_key = os.environ.get("ARTIFICIAL_ANALYSIS_API_KEY", "")
    if not api_key:
        logger.debug("Artificial Analysis API key not set, skipping Tier 2c")
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    releases: list = []

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            # Fetch LLM models
            resp = await client.get(
                f"{ARTIFICIAL_ANALYSIS_API_URL}/data/llms/models",
                headers={"x-api-key": api_key},
            )
            resp.raise_for_status()
            models = resp.json()

            if not isinstance(models, list):
                logger.warning("Artificial Analysis API returned unexpected format")
                return []

            for model in models:
                # Check release date within lookback window
                release_date_str = model.get("release_date") or ""
                if not release_date_str:
                    continue
                try:
                    release_dt = datetime.fromisoformat(
                        release_date_str.replace("Z", "+00:00")
                    )
                    if release_dt < cutoff:
                        continue
                except (ValueError, TypeError):
                    continue

                name = model.get("name", "")
                if not name:
                    continue

                creator = model.get("model_creator", {})
                org = creator.get("name", "") if isinstance(creator, dict) else ""

                # Build notable features from available metrics
                features_parts = []
                evals = model.get("evaluations", {})
                if isinstance(evals, dict):
                    for key in ("intelligence_index", "mmlu_pro", "gpqa"):
                        val = evals.get(key)
                        if val:
                            features_parts.append(f"{key}: {val}")

                speed = model.get("median_output_tokens_per_second")
                if speed:
                    features_parts.append(f"{speed} tok/s")

                releases.append(ModelRelease(
                    model_name=name,
                    organization=org,
                    release_date=release_dt.strftime("%Y-%m-%d"),
                    release_status="Released",
                    parameters="",
                    license="",
                    is_open_source="",  # AA tracks both
                    model_type="",
                    modality="Text",
                    notable_features="; ".join(features_parts)[:200],
                    source_url=f"https://artificialanalysis.ai/models/{model.get('slug', '')}",
                ))

            # Also fetch media models (text-to-image, video, etc.)
            for endpoint, modality in [
                ("/data/media/text-to-image", "Image"),
                ("/data/media/text-to-video", "Video"),
                ("/data/media/text-to-speech", "Speech"),
            ]:
                try:
                    media_resp = await client.get(
                        f"{ARTIFICIAL_ANALYSIS_API_URL}{endpoint}",
                        headers={"x-api-key": api_key},
                    )
                    if media_resp.status_code != 200:
                        continue
                    media_models = media_resp.json()
                    if not isinstance(media_models, list):
                        continue

                    for mm in media_models:
                        rd = mm.get("release_date") or ""
                        if not rd:
                            continue
                        try:
                            rdt = datetime.fromisoformat(rd.replace("Z", "+00:00"))
                            if rdt < cutoff:
                                continue
                        except (ValueError, TypeError):
                            continue

                        mm_name = mm.get("name", "")
                        if not mm_name:
                            continue
                        mm_creator = mm.get("model_creator", {})
                        mm_org = mm_creator.get("name", "") if isinstance(mm_creator, dict) else ""

                        releases.append(ModelRelease(
                            model_name=mm_name,
                            organization=mm_org,
                            release_date=rdt.strftime("%Y-%m-%d"),
                            release_status="Released",
                            parameters="",
                            license="",
                            is_open_source="",
                            model_type="",
                            modality=modality,
                            notable_features="",
                            source_url=f"https://artificialanalysis.ai/models/{mm.get('slug', '')}",
                        ))
                except Exception:
                    continue

        logger.info(
            f"Artificial Analysis: {len(releases)} models in last {lookback_days} days"
        )

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            logger.warning("Artificial Analysis API key invalid (401)")
        else:
            logger.warning(f"Artificial Analysis API error: {e}")
    except Exception as e:
        logger.warning(f"Artificial Analysis fetch failed: {e}")

    return releases[:max_results]


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
    """Unified model release sourcing: HF + blogs + Artificial Analysis + DDG.

    Returns List[ModelRelease] — import is deferred to avoid circular imports.
    """
    from core.sensing.model_release_extractor import (
        build_releases_from_hf,
        extract_model_releases,
        extract_releases_from_blogs,
    )

    all_releases = []

    # Tier 1: HuggingFace (structured, reliable — open-weight models)
    hf_models = await fetch_huggingface_releases(lookback_days)
    if hf_models:
        hf_releases = build_releases_from_hf(hf_models)
        all_releases.extend(hf_releases)
        logger.info(f"Tier 1 (HuggingFace): {len(hf_releases)} releases")

    # Tier 2a: Major lab blog RSS (for proprietary models)
    blog_articles = await fetch_major_lab_blogs(lookback_days)
    blog_releases_count = 0
    if blog_articles:
        # First try: title-based extraction (no LLM needed)
        title_extracted = []
        remaining_articles = []
        for article in blog_articles:
            release = _build_release_from_article(
                title=article.title,
                url=article.url,
                source=article.source,
                published_date=article.published_date,
                snippet=article.snippet,
            )
            if release:
                title_extracted.append(release)
            else:
                remaining_articles.append(article)

        all_releases.extend(title_extracted)
        blog_releases_count += len(title_extracted)

        # Second try: LLM extraction for remaining articles
        if remaining_articles:
            try:
                llm_releases = await extract_releases_from_blogs(
                    remaining_articles, lookback_days
                )
                all_releases.extend(llm_releases)
                blog_releases_count += len(llm_releases)
            except Exception as e:
                logger.debug(f"Blog LLM extraction failed (non-fatal): {e}")

        logger.info(f"Tier 2a (Blogs): {blog_releases_count} releases")

    # Tier 2b: Targeted DDG search for proprietary labs (always runs)
    proprietary_articles = await search_proprietary_releases_ddg(lookback_days)
    prop_count = 0
    if proprietary_articles:
        # First try: title-based extraction (no LLM needed)
        title_extracted = []
        remaining_articles = []
        for article in proprietary_articles:
            release = _build_release_from_article(
                title=article.title,
                url=article.url,
                source=article.source,
                published_date=article.published_date,
                snippet=article.snippet,
            )
            if release:
                title_extracted.append(release)
            else:
                remaining_articles.append(article)

        all_releases.extend(title_extracted)
        prop_count += len(title_extracted)

        # Second try: LLM extraction for remaining
        if remaining_articles:
            try:
                prop_llm = await extract_releases_from_blogs(
                    remaining_articles, lookback_days
                )
                all_releases.extend(prop_llm)
                prop_count += len(prop_llm)
            except Exception as e:
                logger.debug(
                    f"Proprietary LLM extraction failed (non-fatal): {e}"
                )

    if prop_count:
        logger.info(f"Tier 2b (Proprietary DDG): {prop_count} releases")

    # Tier 2c: Artificial Analysis API (structured, both open + proprietary)
    aa_releases = await fetch_artificial_analysis_releases(lookback_days)
    if aa_releases:
        all_releases.extend(aa_releases)
        logger.info(f"Tier 2c (Artificial Analysis): {len(aa_releases)} releases")

    # Tier 3: Generic DDG fallback (only if all above yield very few)
    if len(all_releases) < 3:
        logger.info("All tiers yielded <3 results, activating generic DDG fallback...")
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
