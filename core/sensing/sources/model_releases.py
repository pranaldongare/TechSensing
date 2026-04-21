"""
Model Releases — structured sourcing for recent AI model releases.

Tier 1 (Primary):   Artificial Analysis API — curated, both open + proprietary
Tier 2 (Complement): HuggingFace Hub API — fills gaps for niche open-weight models
"""

import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import httpx

from core.sensing.config import (
    ARTIFICIAL_ANALYSIS_API_URL,
    HF_KNOWN_ORGS,
    HF_MIN_DOWNLOADS,
    HF_MIN_LIKES,
)

logger = logging.getLogger("sensing.sources.model_releases")

HF_API_URL = "https://huggingface.co/api/models"

# ── File-based daily cache for AA API ──
_AA_CACHE_DIR = Path("data/sensing_cache/aa")
_AA_CACHE_TTL = 24 * 3600  # 24 hours
_aa_mem_cache: Dict[str, Tuple[float, list]] = {}  # in-memory hot cache
_aa_rate_limited = False  # set True when 429 hit, skip further API calls


def _aa_cache_path(endpoint: str) -> Path:
    """Return the file cache path for an AA endpoint."""
    safe_name = endpoint.strip("/").replace("/", "_")
    return _AA_CACHE_DIR / f"{safe_name}.json"


def _aa_read_file_cache(endpoint: str) -> Optional[list]:
    """Read AA data from file cache if fresh enough."""
    fpath = _aa_cache_path(endpoint)
    if not fpath.exists():
        return None
    try:
        data = json.loads(fpath.read_text(encoding="utf-8"))
        cached_at = data.get("cached_at", 0)
        if time.time() - cached_at > _AA_CACHE_TTL:
            return None  # expired
        return data.get("models", [])
    except Exception:
        return None


def _aa_write_file_cache(endpoint: str, models: list) -> None:
    """Persist AA data to file cache."""
    try:
        _AA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        fpath = _aa_cache_path(endpoint)
        fpath.write_text(
            json.dumps(
                {"cached_at": time.time(), "endpoint": endpoint, "models": models},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except Exception as e:
        logger.debug(f"Failed to write AA cache for {endpoint}: {e}")


def _aa_read_stale_cache(endpoint: str) -> Optional[list]:
    """Read AA data from file cache even if expired (last resort fallback)."""
    fpath = _aa_cache_path(endpoint)
    if not fpath.exists():
        return None
    try:
        data = json.loads(fpath.read_text(encoding="utf-8"))
        models = data.get("models", [])
        if models:
            age_hours = (time.time() - data.get("cached_at", 0)) / 3600
            logger.info(
                f"Using stale AA cache for {endpoint} "
                f"({age_hours:.1f}h old, {len(models)} models)"
            )
        return models or None
    except Exception:
        return None

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
_PARAM_TAG_PATTERN = re.compile(r"^(\d+\.?\d*)[bB]$", re.IGNORECASE)
_PARAM_NAME_PATTERN = re.compile(r"[-_](\d+\.?\d*)[bB](?:[-_]|$)")


def _extract_params_from_tags(tags: List[str], model_id: str = "") -> str:
    """Extract parameter count from HuggingFace model tags or model name."""
    for tag in tags:
        m = _PARAM_TAG_PATTERN.match(tag.strip())
        if m:
            return f"{m.group(1)}B"
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
    return "Transformer"


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

    quant_indicators = ("gguf", "gptq", "awq", "exl2", "bnb", "fp8")
    if any(q in name_lower for q in quant_indicators):
        return True
    if tags & {"gguf", "gptq", "awq", "exl2"}:
        return True

    quant_uploaders = {"mradermacher", "thebloke", "unsloth", "bartowski"}
    author = model_id.split("/")[0].lower() if "/" in model_id else ""
    if author in quant_uploaders:
        return True

    return False


def _is_significant_model(model: dict) -> bool:
    """Check if a HuggingFace model passes the significance threshold."""
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
# Tier 1: Artificial Analysis API (primary — open + proprietary)
# ═══════════════════════════════════════════════════════════════════

async def _aa_fetch_cached(
    client: httpx.AsyncClient,
    endpoint: str,
    api_key: str,
) -> Optional[list]:
    """Fetch an AA endpoint with daily file cache and retry on 429.

    Cache strategy (layered):
    1. In-memory hot cache (avoids disk reads within same process)
    2. File cache in data/sensing_cache/aa/ (survives restarts, 24h TTL)
    3. API call with retry on 429
    4. Stale file cache (any age) as last resort
    """
    now = time.monotonic()

    # Layer 1: in-memory hot cache
    mem = _aa_mem_cache.get(endpoint)
    if mem and (now - mem[0]) < 3600:  # 1h in-memory TTL
        return mem[1]

    # Layer 2: file cache (24h TTL)
    file_data = _aa_read_file_cache(endpoint)
    if file_data is not None:
        _aa_mem_cache[endpoint] = (now, file_data)
        return file_data

    # Layer 3: API call with retry (skip if already rate-limited this run)
    global _aa_rate_limited
    if not _aa_rate_limited:
        for attempt in range(3):
            try:
                resp = await client.get(
                    f"{ARTIFICIAL_ANALYSIS_API_URL}{endpoint}",
                    headers={"x-api-key": api_key},
                )
                if resp.status_code == 429:
                    _aa_rate_limited = True  # skip other endpoints immediately
                    if attempt < 2:
                        wait = 2 ** attempt
                        logger.info(f"AA 429 rate-limited, retrying in {wait}s...")
                        await asyncio.sleep(wait)
                        continue
                    else:
                        logger.warning("AA still rate-limited after retries")
                        break
                resp.raise_for_status()
                payload = resp.json()
                if isinstance(payload, dict):
                    data = payload.get("data", [])
                elif isinstance(payload, list):
                    data = payload
                else:
                    break
                # Success — update both caches, clear rate-limit flag
                _aa_mem_cache[endpoint] = (now, data)
                _aa_write_file_cache(endpoint, data)
                _aa_rate_limited = False
                return data
            except httpx.HTTPStatusError:
                raise
            except Exception as e:
                logger.debug(f"AA fetch attempt {attempt + 1} failed: {e}")
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)

    # Layer 4: stale file cache (any age) as last resort
    stale = _aa_read_stale_cache(endpoint)
    if stale:
        _aa_mem_cache[endpoint] = (now, stale)
        return stale

    if _aa_rate_limited:
        logger.debug(f"AA {endpoint}: skipped (rate-limited), no cache available")
    else:
        logger.warning(f"AA endpoint {endpoint}: no data available (API + cache)")
    return None


async def fetch_artificial_analysis_releases(
    lookback_days: int = 30,
    max_results: int = 30,
) -> "List":
    """Tier 1: Fetch model data from Artificial Analysis API.

    Returns ModelRelease objects for models tracked by artificialanalysis.ai.
    Covers both open-weight and proprietary models with benchmark data.
    Requires ARTIFICIAL_ANALYSIS_API_KEY env var; gracefully skips if unset.
    """
    from core.llm.output_schemas.sensing_outputs import ModelRelease

    api_key = os.environ.get("ARTIFICIAL_ANALYSIS_API_KEY", "")
    if not api_key:
        logger.debug("Artificial Analysis API key not set, skipping Tier 1")
        return []

    # Use naive date for comparison — AA dates are plain "YYYY-MM-DD"
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
        days=lookback_days
    )
    releases: list = []

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            # Fetch LLM models
            models = await _aa_fetch_cached(
                client, "/data/llms/models", api_key
            )
            if models is None:
                return []

            for model in models:
                release_date_str = model.get("release_date") or ""
                if not release_date_str:
                    continue
                try:
                    release_dt = datetime.fromisoformat(release_date_str)
                    if release_dt.tzinfo is not None:
                        release_dt = release_dt.replace(tzinfo=None)
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
                    for key in (
                        "artificial_analysis_intelligence_index",
                        "mmlu_pro",
                        "gpqa",
                    ):
                        val = evals.get(key)
                        if val is not None:
                            features_parts.append(f"{key}: {val}")

                speed = model.get("median_output_tokens_per_second")
                if speed:
                    features_parts.append(f"{speed} tok/s")

                pricing = model.get("pricing", {})
                if isinstance(pricing, dict):
                    blended = pricing.get("price_1m_blended_3_to_1")
                    if blended is not None:
                        features_parts.append(f"${blended}/1M tokens")

                releases.append(ModelRelease(
                    model_name=name,
                    organization=org,
                    release_date=release_dt.strftime("%Y-%m-%d"),
                    release_status="Released",
                    parameters="",
                    license="",
                    is_open_source="",
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
                    media_models = await _aa_fetch_cached(
                        client, endpoint, api_key
                    )
                    if not media_models:
                        continue

                    for mm in media_models:
                        rd = mm.get("release_date") or ""
                        if not rd:
                            continue
                        try:
                            rdt = datetime.fromisoformat(rd)
                            if rdt.tzinfo is not None:
                                rdt = rdt.replace(tzinfo=None)
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
# Tier 2: HuggingFace Hub API (complement — niche open-weight models)
# ═══════════════════════════════════════════════════════════════════

async def fetch_huggingface_releases(
    lookback_days: int = 30,
    max_results: int = 20,
) -> List[dict]:
    """Tier 2: Fetch recent significant models from HuggingFace Hub API.

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

                        if _is_quantization(model):
                            continue

                        downloads = model.get("downloads", 0) or 0
                        likes = model.get("likes", 0) or 0
                        if downloads >= 100 or likes >= 5:
                            seen_ids.add(model_id)
                            significant_models.append(model)

                except Exception:
                    continue

            # Strategy 2: Fetch recent models sorted by downloads
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
# Unified orchestrator
# ═══════════════════════════════════════════════════════════════════

async def get_model_releases(lookback_days: int = 30) -> "List":
    """Unified model release sourcing: Artificial Analysis + HuggingFace.

    Artificial Analysis is the primary source (curated, covers both open +
    proprietary with benchmarks and pricing). HuggingFace adds niche
    open-weight models not yet tracked by AA.

    Returns List[ModelRelease] — import is deferred to avoid circular imports.
    """
    from core.sensing.model_release_extractor import build_releases_from_hf

    all_releases = []

    # Tier 1: Artificial Analysis (primary — curated, structured)
    aa_releases = await fetch_artificial_analysis_releases(lookback_days)
    all_releases.extend(aa_releases)
    if aa_releases:
        logger.info(f"Tier 1 (Artificial Analysis): {len(aa_releases)} releases")

    # Tier 2: HuggingFace (complement — niche open-weight models)
    hf_models = await fetch_huggingface_releases(lookback_days)
    if hf_models:
        hf_releases = build_releases_from_hf(hf_models)
        all_releases.extend(hf_releases)
        logger.info(f"Tier 2 (HuggingFace): {len(hf_releases)} releases")

    # Deduplicate — AA results take priority (listed first)
    all_releases = _deduplicate_releases(all_releases)

    logger.info(
        f"Model releases total: {len(all_releases)} (after dedup)"
    )
    return all_releases


def _deduplicate_releases(releases: list) -> list:
    """Deduplicate releases by normalized model name. First occurrence wins."""
    seen: set = set()
    unique = []
    for r in releases:
        key = r.model_name.lower().strip().replace("-", " ").replace("_", " ")
        # Strip org prefix (e.g., "meta-llama/Llama-4" → "llama 4")
        if "/" in key:
            key = key.split("/", 1)[1]
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique
