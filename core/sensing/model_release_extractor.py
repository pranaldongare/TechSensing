"""
Model Release Extractor — uses LLM to extract structured model release info
from search result articles.
"""

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from core.constants import GPU_SENSING_REPORT_LLM
from core.llm.client import invoke_llm
from core.llm.output_schemas.sensing_outputs import ModelRelease, ModelReleasesOutput
from core.llm.prompts.shared import tense_rules_block
from core.sensing.ingest import RawArticle

logger = logging.getLogger("sensing.model_release_extractor")

# Buffer on lookback_days for release-date verification. Announcements
# occasionally lag the actual release by a few days, so we allow a small
# grace window.
RELEASE_DATE_BUFFER = 1.25

# How far into the future we accept announced-but-not-yet-shipped models.
# An article announcing a launch 6 months out is still a valid "this week"
# signal for the radar; beyond that it is usually speculation.
FUTURE_RELEASE_HORIZON_DAYS = 180

_ISO_DATE_RE = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")


def _parse_release_date(value: str) -> Optional[datetime]:
    """Parse an LLM-provided release_date string to a tz-aware datetime."""
    if not value:
        return None
    cleaned = value.strip()
    try:
        dt = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        pass
    m = _ISO_DATE_RE.search(cleaned)
    if m:
        try:
            return datetime(
                int(m.group(1)), int(m.group(2)), int(m.group(3)),
                tzinfo=timezone.utc,
            )
        except (ValueError, TypeError):
            return None
    return None


_OPEN_LICENSE_HINTS = (
    "apache", "mit", "bsd", "gpl", "cc-by", "cc by",
    "llama community", "llama license", "open rail", "openrail",
    "mistral research", "mistral community", "open model",
    "open weights", "open-weight", "open source",
)
_CLOSED_LICENSE_HINTS = (
    "proprietary", "closed", "commercial only", "api only",
    "not released", "internal", "tos-only",
)


def _normalize_open_source(value: str, license_text: str) -> str:
    """Coerce free-form open/closed labels to Open / Closed / Mixed / Unknown."""
    v = (value or "").strip().lower()
    if v.startswith(("open", "oss")):
        return "Mixed" if "partial" in v or "mixed" in v else "Open"
    if v in {"closed", "proprietary", "private", "no", "false"}:
        return "Closed"
    if v in {"mixed", "partial", "partially open"}:
        return "Mixed"

    lic = (license_text or "").lower()
    if any(h in lic for h in _OPEN_LICENSE_HINTS):
        return "Open"
    if any(h in lic for h in _CLOSED_LICENSE_HINTS):
        return "Closed"
    return "Unknown"


_MODALITY_CANON = {
    "text": "Text", "language": "Text", "llm": "Text", "chat": "Text",
    "multimodal": "Multimodal", "vision-language": "Multimodal", "vlm": "Multimodal",
    "image": "Image", "image generation": "Image", "image-generation": "Image",
    "diffusion": "Image",
    "video": "Video", "video generation": "Video", "video-generation": "Video",
    "audio": "Audio", "music": "Audio", "sound": "Audio",
    "speech": "Speech", "tts": "Speech", "asr": "Speech", "voice": "Speech",
    "code": "Code", "coding": "Code", "programming": "Code",
    "world model": "World Model", "world-model": "World Model",
    "world models": "World Model", "simulation": "World Model",
    "action": "Action", "robot": "Action", "robotics": "Action",
    "vla": "Action", "agent": "Action",
    "embedding": "Embedding", "embeddings": "Embedding",
    "retrieval": "Embedding", "encoder": "Embedding",
    "3d": "3D", "scene": "3D",
    "reasoning": "Reasoning", "math": "Reasoning",
}


def _normalize_modality(value: str) -> str:
    v = (value or "").strip().lower()
    if not v:
        return "Other"
    if v in _MODALITY_CANON:
        return _MODALITY_CANON[v]
    matches = [canon for hint, canon in _MODALITY_CANON.items() if hint in v]
    if matches:
        return matches[0]
    return value.strip().title() or "Other"


_STATUS_CANON = {
    "released": "Released", "release": "Released", "ga": "Released",
    "generally available": "Released", "live": "Released",
    "available": "Released", "shipped": "Released", "launched": "Released",
    "out": "Released",
    "announced": "Announced", "announcement": "Announced",
    "unveiled": "Announced", "revealed": "Announced",
    "waitlist": "Announced", "waitlisted": "Announced",
    "early access": "Announced", "private preview": "Announced",
    "upcoming": "Upcoming", "planned": "Upcoming", "scheduled": "Upcoming",
    "coming soon": "Upcoming", "future": "Upcoming",
    "preview": "Preview", "beta": "Preview", "public preview": "Preview",
    "public beta": "Preview",
    "unknown": "Unknown", "": "Unknown",
}


def _normalize_release_status(
    value: str,
    release_dt: Optional[datetime],
    now_dt: datetime,
) -> str:
    """Coerce free-form status to Released/Announced/Upcoming/Preview/Unknown.

    Falls back to date-based inference when the LLM did not emit a useful
    label: a future-dated event becomes 'Upcoming', otherwise 'Released'.
    """
    v = (value or "").strip().lower()
    if v in _STATUS_CANON:
        canon = _STATUS_CANON[v]
    else:
        canon = "Unknown"
        for hint, label in _STATUS_CANON.items():
            if hint and hint in v:
                canon = label
                break

    if canon == "Unknown" and release_dt is not None:
        canon = "Upcoming" if release_dt > now_dt else "Released"
    # Safety net: if LLM said 'Released' but the date is clearly in the
    # future, override. The tense-rules block instructs the LLM not to do
    # this, but we don't want to ship a report that says "Released" for
    # something shipping next month.
    if canon == "Released" and release_dt is not None and release_dt > now_dt:
        canon = "Upcoming"
    return canon


async def extract_model_releases(
    articles: List[RawArticle],
    lookback_days: int = 30,
) -> List[ModelRelease]:
    """Extract structured model release info from articles via LLM.

    Takes raw articles about model announcements and returns deduplicated,
    structured ModelRelease entries.
    """
    if not articles:
        return []

    # Prepare article content for LLM
    articles_json = json.dumps(
        [
            {
                "title": a.title,
                "source": a.source,
                "url": a.url,
                "snippet": a.snippet,
                "content": (a.content or "")[:1500],
            }
            for a in articles
            if a.title
        ][:25],  # Limit to 25 articles
        indent=2,
        ensure_ascii=False,
    )

    schema_json = json.dumps(
        ModelReleasesOutput.model_json_schema(), indent=2
    )

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    prompt = [
        {
            "role": "system",
            "parts": (
                "You are an AI model release tracker. Given a collection of articles "
                "about AI model announcements, extract structured information about "
                "each distinct model release.\n\n"
                f"TODAY IS {today_str}. Include models that were either\n"
                f"  (a) released within the last {lookback_days} days, OR\n"
                f"  (b) publicly ANNOUNCED within the last {lookback_days} days "
                f"with a release scheduled for a date AFTER {today_str}.\n"
                "If an article merely mentions or retrospectively discusses an "
                "older model, DO NOT emit an entry for it. If you cannot "
                "confidently establish either a release date or an announcement "
                "within the window, SKIP that model entirely.\n\n"
                "CRITICAL — ACTUAL vs SYNDICATION DATE:\n"
                "News aggregators re-syndicate old model announcements with fresh "
                "dates. The release_date you output must be the ACTUAL date the "
                "model was released or announced, NOT the article's publication "
                "date. Determine the true release date from the article CONTENT.\n"
                "EXAMPLES of OLD models to REJECT:\n"
                "- OpenAI Sora (Dec 2024) — now discontinued\n"
                "- Alibaba Wan 2.1 (Feb 2025)\n"
                "- Google Gemma 3 (Mar 2025)\n"
                "- LTX-2 (2025)\n"
                "- Llama 3 (2024), GPT-4/GPT-4o (2023-2024)\n"
                "These are old releases. If you see them, SKIP them.\n\n"
                + tense_rules_block(today_str)
                + "For each model, extract:\n"
                "- model_name: Official name (e.g., 'GPT-4.1', 'Llama 4 Scout')\n"
                "- organization: Who released it\n"
                "- release_date: Exact date in YYYY-MM-DD format. If only month "
                "is known, use the first of the month. MAY be a FUTURE date if "
                "the model has been announced but not yet shipped (e.g., "
                "'plans to release on 2026-05-01' → release_date='2026-05-01'). "
                "Leave EMPTY if not derivable.\n"
                "- release_status: Exactly one of 'Released', 'Announced', "
                "'Upcoming', 'Preview', or 'Unknown'. Use 'Released' ONLY when "
                f"the model is already publicly available on or before "
                f"{today_str} (GA, weights downloadable, or API live). Use "
                "'Announced' when it has been publicly announced but is not "
                "yet available (waitlist, private preview, upcoming launch "
                "with a future date). Use 'Upcoming' when a specific future "
                "launch date is named. Use 'Preview' for public preview/beta "
                "accessible to some users. Use 'Unknown' if the article does "
                "not make the status clear.\n"
                "- parameters: Parameter count if known (e.g., '70B', '400B MoE (17B active)')\n"
                "- license: Specific license text if stated (e.g., 'Apache 2.0', "
                "'Llama Community', 'Proprietary', 'API only')\n"
                "- is_open_source: Exactly one of 'Open', 'Closed', 'Mixed', or "
                "'Unknown'. Use 'Open' when weights are publicly downloadable "
                "under an OSI/open-weights license (MIT, Apache 2.0, BSD, GPL, "
                "Llama Community, Mistral-style, OpenRAIL, etc.). Use 'Closed' "
                "for API-only or proprietary releases with no public weights. "
                "Use 'Mixed' when only some sizes/variants are open. Use "
                "'Unknown' if the article does not state it.\n"
                "- model_type: Architecture type (Transformer, MoE, Mamba, "
                "Hybrid, Diffusion, State-space, Flow-matching, etc.)\n"
                "- modality: Pick ONE primary category from: 'Text' (LLM/chat), "
                "'Multimodal' (accepts multiple input modalities), 'Image' "
                "(image generation/editing), 'Video' (video generation or "
                "understanding), 'Audio' (music/general audio), 'Speech' "
                "(ASR/TTS/voice), 'Code' (code generation), 'World Model' "
                "(world simulation/predictive world models), 'Action' "
                "(robotics / VLA / agentic control), 'Embedding' "
                "(retrieval/encoder), '3D' (3D/scene generation), "
                "'Reasoning' (reasoning-focused), or 'Other'.\n"
                "- notable_features: 1-2 sentence summary of what's notable. "
                "Use future/progressive wording (\"is expected to\", \"will "
                "offer\") when release_status is 'Upcoming' or 'Announced'.\n"
                "- source_url: Best URL for the announcement\n\n"
                "DEDUPLICATION: If multiple articles mention the same model, merge "
                "into a single entry with the most complete info.\n\n"
                "OUTPUT REQUIREMENT:\n"
                "Return the entire response strictly as a valid JSON object matching "
                "the schema below.\n"
                "Do NOT include markdown, comments, or text outside the JSON object.\n\n"
                f"OUTPUT SCHEMA:\n```json\n{schema_json}\n```\n\n"
                "OUTPUT RULES:\n"
                "- Output must be valid JSON only, no markdown fencing.\n"
                "- Newlines inside string values MUST be written as \\n.\n"
                '- Double quotes inside string values MUST be escaped as \\".\n'
            ),
        },
        {
            "role": "user",
            "parts": (
                f"ARTICLES:\n\n{articles_json}\n\n"
                "Extract all distinct model releases that were either released "
                f"within the last {lookback_days} days of {today_str}, OR "
                f"announced within the last {lookback_days} days with a "
                "release date in the future. Set release_status correctly "
                "for each (Released / Announced / Upcoming / Preview). "
                "Return ONLY valid JSON."
            ),
        },
    ]

    try:
        result = await invoke_llm(
            gpu_model=GPU_SENSING_REPORT_LLM.model,
            response_schema=ModelReleasesOutput,
            contents=prompt,
            port=GPU_SENSING_REPORT_LLM.port,
        )
        validated = ModelReleasesOutput.model_validate(result)

        # ── Date cutoff for post-extraction filtering ───────────────────
        # LLMs occasionally emit older models despite the prompt; enforce
        # the release-date window here with a small buffer. Upcoming
        # (future-dated) announcements are allowed up to
        # FUTURE_RELEASE_HORIZON_DAYS ahead so we don't drop models that
        # were announced this week but ship next month.
        now_dt = datetime.now(timezone.utc)
        max_age_days = max(int(lookback_days * RELEASE_DATE_BUFFER), lookback_days)
        cutoff_dt = now_dt - timedelta(days=max_age_days)
        future_horizon_dt = now_dt + timedelta(days=FUTURE_RELEASE_HORIZON_DAYS)

        # Deduplicate by normalized model name, filter by date, normalize fields
        seen_names: set = set()
        unique: List[ModelRelease] = []
        dropped_old = 0
        dropped_far_future = 0
        dropped_undated = 0

        for m in validated.model_releases:
            key = m.model_name.lower().strip()
            if not key or key in seen_names:
                continue

            release_dt = _parse_release_date(m.release_date)
            if release_dt is None:
                # No parseable date — don't trust it for a "new models" list.
                dropped_undated += 1
                continue
            if release_dt < cutoff_dt:
                dropped_old += 1
                continue
            if release_dt > future_horizon_dt:
                # More than ~6 months out → almost always speculation.
                dropped_far_future += 1
                continue
            # Preserve the LLM's future date — this is how we surface
            # "announced but upcoming" releases correctly in the UI.
            m.release_date = release_dt.strftime("%Y-%m-%d")

            # Canonicalize classification fields.
            m.is_open_source = _normalize_open_source(m.is_open_source, m.license)
            m.modality = _normalize_modality(m.modality)
            m.release_status = _normalize_release_status(
                m.release_status, release_dt, now_dt
            )

            seen_names.add(key)
            unique.append(m)

        logger.info(
            f"Model release extraction: {len(unique)} unique models "
            f"from {len(articles)} articles "
            f"(dropped {dropped_old} out-of-window, "
            f"{dropped_far_future} far-future, {dropped_undated} undated)"
        )
        return unique

    except Exception as e:
        logger.warning(f"Model release extraction failed: {e}")
        return []


# ═══════════════════════════════════════════════════════════════════
# Tier 1: Direct HuggingFace → ModelRelease conversion (no LLM)
# ═══════════════════════════════════════════════════════════════════

def build_releases_from_hf(hf_models: List[dict]) -> List[ModelRelease]:
    """Convert HuggingFace API model dicts directly to ModelRelease objects.

    No LLM needed — structured API data maps directly to schema fields.
    """
    from core.sensing.sources.model_releases import (
        _HF_PIPELINE_TO_MODALITY,
        _extract_license_from_tags,
        _extract_model_type_from_tags,
        _extract_params_from_tags,
    )

    releases: List[ModelRelease] = []

    for model in hf_models:
        model_id = model.get("modelId") or model.get("id", "")
        if not model_id:
            continue

        # Parse author/org from model_id (format: "org/model-name")
        org = model_id.split("/")[0] if "/" in model_id else "Unknown"

        tags = model.get("tags", [])
        pipeline_tag = model.get("pipeline_tag", "")
        downloads = model.get("downloads", 0) or 0
        likes = model.get("likes", 0) or 0

        # Extract release date from createdAt
        created = model.get("createdAt", "")
        release_date = ""
        if created:
            try:
                dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                release_date = dt.strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                pass

        # Map fields
        modality = _HF_PIPELINE_TO_MODALITY.get(pipeline_tag, "Other")
        parameters = _extract_params_from_tags(tags, model_id)
        license_text = _extract_license_from_tags(tags)
        model_type = _extract_model_type_from_tags(tags)

        # Build notable features summary
        features_parts = []
        if pipeline_tag:
            features_parts.append(pipeline_tag.replace("-", " "))
        if downloads >= 1000:
            features_parts.append(f"{downloads:,} downloads")
        if likes >= 10:
            features_parts.append(f"{likes} likes")
        # Add a few interesting tags (skip generic ones)
        _skip_tags = {"transformers", "pytorch", "safetensors", "en", "text-generation"}
        interesting_tags = [
            t for t in tags[:8]
            if t.lower() not in _skip_tags
            and not t.startswith("license")
            and not _extract_params_from_tags([t])
        ]
        if interesting_tags:
            features_parts.append(", ".join(interesting_tags[:3]))

        releases.append(
            ModelRelease(
                model_name=model_id,
                organization=org,
                release_date=release_date,
                release_status="Released",
                parameters=parameters,
                license=license_text,
                is_open_source="Open",
                model_type=model_type,
                modality=modality,
                notable_features=". ".join(features_parts) if features_parts else "",
                source_url=f"https://huggingface.co/{model_id}",
            )
        )

    logger.info(f"Built {len(releases)} ModelRelease entries from HuggingFace data")
    return releases


# ═══════════════════════════════════════════════════════════════════
# Tier 2: Blog articles → ModelRelease via LLM (stricter extraction)
# ═══════════════════════════════════════════════════════════════════

async def extract_releases_from_blogs(
    articles: List[RawArticle],
    lookback_days: int = 30,
) -> List[ModelRelease]:
    """Extract model releases from major AI lab blog articles via LLM.

    Similar to extract_model_releases() but with a stricter prompt since
    these are curated blog posts from known labs.
    """
    if not articles:
        return []

    articles_json = json.dumps(
        [
            {
                "title": a.title,
                "source": a.source,
                "url": a.url,
                "snippet": a.snippet,
                "published_date": a.published_date,
            }
            for a in articles
            if a.title
        ][:15],
        indent=2,
        ensure_ascii=False,
    )

    schema_json = json.dumps(
        ModelReleasesOutput.model_json_schema(), indent=2
    )

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    prompt = [
        {
            "role": "system",
            "parts": (
                "You are an AI model release tracker. You are given blog posts "
                "from official AI lab blogs (OpenAI, Anthropic, Google, etc.). "
                "Extract ONLY entries where a NEW MODEL is being released or "
                "announced. Do NOT extract entries about product features, "
                "safety research, partnerships, or general company news.\n\n"
                f"TODAY IS {today_str}.\n\n"
                "For each genuine model release/announcement, extract:\n"
                "- model_name: Official model name\n"
                "- organization: The lab releasing it\n"
                "- release_date: From the blog post date (YYYY-MM-DD)\n"
                "- release_status: 'Released' if available now, "
                "'Announced' if coming soon\n"
                "- parameters: If mentioned\n"
                "- license: If mentioned\n"
                "- is_open_source: 'Open', 'Closed', 'Mixed', or 'Unknown'\n"
                "- model_type: Architecture if mentioned\n"
                "- modality: Primary modality\n"
                "- notable_features: 1-2 sentence summary\n"
                "- source_url: The blog post URL\n\n"
                "CRITICAL: Only extract if a SPECIFIC MODEL NAME is mentioned "
                "and it is being RELEASED or ANNOUNCED. Skip posts about "
                "research, safety, policy, features, or general updates.\n\n"
                f"OUTPUT SCHEMA:\n```json\n{schema_json}\n```\n\n"
                "Return ONLY valid JSON matching the schema. "
                "If no model releases found, return {\"model_releases\": []}.\n"
            ),
        },
        {
            "role": "user",
            "parts": (
                f"BLOG POSTS:\n\n{articles_json}\n\n"
                "Extract model releases. Return ONLY valid JSON."
            ),
        },
    ]

    try:
        result = await invoke_llm(
            gpu_model=GPU_SENSING_REPORT_LLM.model,
            response_schema=ModelReleasesOutput,
            contents=prompt,
            port=GPU_SENSING_REPORT_LLM.port,
        )
        validated = ModelReleasesOutput.model_validate(result)

        # Apply same normalization as the main extractor
        now_dt = datetime.now(timezone.utc)
        releases: List[ModelRelease] = []

        for m in validated.model_releases:
            if not m.model_name.strip():
                continue

            release_dt = _parse_release_date(m.release_date)
            if release_dt:
                m.release_date = release_dt.strftime("%Y-%m-%d")

            m.is_open_source = _normalize_open_source(m.is_open_source, m.license)
            m.modality = _normalize_modality(m.modality)
            m.release_status = _normalize_release_status(
                m.release_status, release_dt, now_dt
            )
            releases.append(m)

        logger.info(
            f"Blog extraction: {len(releases)} releases "
            f"from {len(articles)} blog posts"
        )
        return releases

    except Exception as e:
        logger.warning(f"Blog model release extraction failed: {e}")
        return []
