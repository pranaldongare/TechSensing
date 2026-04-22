"""
AI Leaderboard — structured leaderboard data from Artificial Analysis API.

Reuses the cached AA API data (24h file cache + in-memory hot cache)
but returns ALL models sorted by ranking metrics instead of filtering
by release date.
"""

import logging
import os
from typing import Any, Dict, List

import httpx

from core.sensing.sources.model_releases import _aa_fetch_cached

logger = logging.getLogger("sensing.sources.ai_leaderboard")


async def get_ai_leaderboard() -> Dict[str, List[Dict[str, Any]]]:
    """Fetch all AA data and return structured leaderboard categories.

    Returns dict with keys:
      - llm_quality: sorted by intelligence_index desc
      - llm_speed: sorted by median_output_tokens_per_second desc
      - llm_price: sorted by price_1m_blended_3_to_1 asc
      - image_generation: sorted by elo desc
      - video_generation: sorted by elo desc (text-to-video + image-to-video merged)
      - speech: sorted by elo desc
    """
    api_key = os.environ.get("ARTIFICIAL_ANALYSIS_API_KEY", "")
    if not api_key:
        logger.info("AA API key not set, returning empty leaderboard")
        return _empty_result()

    rate_limited: list = [False]
    result: Dict[str, List[Dict[str, Any]]] = {}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            # ── LLM models ──
            llm_models = await _aa_fetch_cached(
                client, "/data/llms/models", api_key, rate_limited
            ) or []

            result["llm_quality"] = _build_llm_quality(llm_models)
            result["llm_speed"] = _build_llm_speed(llm_models)
            result["llm_price"] = _build_llm_price(llm_models)

            # ── Media models ──
            rate_limited[0] = False

            t2i = await _aa_fetch_cached(
                client, "/data/media/text-to-image", api_key, rate_limited
            ) or []
            result["image_generation"] = _build_media_leaderboard(t2i)

            t2v = await _aa_fetch_cached(
                client, "/data/media/text-to-video", api_key, rate_limited
            ) or []
            i2v = await _aa_fetch_cached(
                client, "/data/media/image-to-video", api_key, rate_limited
            ) or []
            result["video_generation"] = _build_media_leaderboard(t2v + i2v)

            tts = await _aa_fetch_cached(
                client, "/data/media/text-to-speech", api_key, rate_limited
            ) or []
            result["speech"] = _build_media_leaderboard(tts)

        logger.info(
            f"AI Leaderboard: "
            f"quality={len(result['llm_quality'])}, "
            f"speed={len(result['llm_speed'])}, "
            f"price={len(result['llm_price'])}, "
            f"image={len(result['image_generation'])}, "
            f"video={len(result['video_generation'])}, "
            f"speech={len(result['speech'])}"
        )
    except Exception as e:
        logger.warning(f"AI Leaderboard fetch failed: {e}")
        return _empty_result()

    return result


def _empty_result() -> Dict[str, list]:
    return {
        "llm_quality": [], "llm_speed": [], "llm_price": [],
        "image_generation": [], "video_generation": [], "speech": [],
    }


def _build_llm_quality(models: list) -> List[Dict[str, Any]]:
    entries = []
    for m in models:
        evals = m.get("evaluations") or {}
        if not isinstance(evals, dict):
            continue
        idx = evals.get("artificial_analysis_intelligence_index")
        if idx is None:
            continue
        creator = m.get("model_creator") or {}
        org = creator.get("name", "") if isinstance(creator, dict) else ""
        pricing = m.get("pricing") or {}
        entries.append({
            "model_name": m.get("name", ""),
            "organization": org,
            "intelligence_index": idx,
            "mmlu_pro": evals.get("mmlu_pro"),
            "gpqa": evals.get("gpqa"),
            "speed": m.get("median_output_tokens_per_second"),
            "price": pricing.get("price_1m_blended_3_to_1") if isinstance(pricing, dict) else None,
            "slug": m.get("slug", ""),
            "release_date": m.get("release_date", ""),
        })
    entries.sort(key=lambda x: x["intelligence_index"] or 0, reverse=True)
    for i, e in enumerate(entries):
        e["rank"] = i + 1
    return entries


def _build_llm_speed(models: list) -> List[Dict[str, Any]]:
    entries = []
    for m in models:
        speed = m.get("median_output_tokens_per_second")
        if speed is None:
            continue
        creator = m.get("model_creator") or {}
        org = creator.get("name", "") if isinstance(creator, dict) else ""
        evals = m.get("evaluations") or {}
        pricing = m.get("pricing") or {}
        entries.append({
            "model_name": m.get("name", ""),
            "organization": org,
            "tokens_per_second": speed,
            "intelligence_index": evals.get("artificial_analysis_intelligence_index") if isinstance(evals, dict) else None,
            "price": pricing.get("price_1m_blended_3_to_1") if isinstance(pricing, dict) else None,
            "slug": m.get("slug", ""),
            "release_date": m.get("release_date", ""),
        })
    entries.sort(key=lambda x: x["tokens_per_second"] or 0, reverse=True)
    for i, e in enumerate(entries):
        e["rank"] = i + 1
    return entries


def _build_llm_price(models: list) -> List[Dict[str, Any]]:
    entries = []
    for m in models:
        pricing = m.get("pricing") or {}
        price = pricing.get("price_1m_blended_3_to_1") if isinstance(pricing, dict) else None
        if price is None:
            continue
        creator = m.get("model_creator") or {}
        org = creator.get("name", "") if isinstance(creator, dict) else ""
        evals = m.get("evaluations") or {}
        entries.append({
            "model_name": m.get("name", ""),
            "organization": org,
            "price": price,
            "intelligence_index": evals.get("artificial_analysis_intelligence_index") if isinstance(evals, dict) else None,
            "speed": m.get("median_output_tokens_per_second"),
            "slug": m.get("slug", ""),
            "release_date": m.get("release_date", ""),
        })
    entries.sort(key=lambda x: x["price"] or float("inf"))
    for i, e in enumerate(entries):
        e["rank"] = i + 1
    return entries


def _build_media_leaderboard(models: list) -> List[Dict[str, Any]]:
    entries = []
    seen_names: set = set()
    for m in models:
        elo = m.get("elo")
        if elo is None:
            continue
        name = m.get("name", "")
        if not name or name in seen_names:
            continue
        seen_names.add(name)
        creator = m.get("model_creator") or {}
        org = creator.get("name", "") if isinstance(creator, dict) else ""
        entries.append({
            "model_name": name,
            "organization": org,
            "elo": elo,
            "release_date": m.get("release_date", ""),
            "slug": m.get("slug", ""),
        })
    entries.sort(key=lambda x: x["elo"] or 0, reverse=True)
    for i, e in enumerate(entries):
        e["rank"] = i + 1
    return entries
