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
from core.sensing.ingest import RawArticle

logger = logging.getLogger("sensing.model_release_extractor")

# Buffer on lookback_days for release-date verification. Announcements
# occasionally lag the actual release by a few days, so we allow a small
# grace window.
RELEASE_DATE_BUFFER = 1.25

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
                f"TODAY IS {today_str}. Only include models whose FIRST PUBLIC "
                f"RELEASE is within the last {lookback_days} days of this date. "
                "If an article merely mentions or retrospectively discusses an "
                "older model, DO NOT emit an entry for it. If you cannot "
                "confidently establish a release date inside the window from "
                "the article text, SKIP that model entirely.\n\n"
                "For each model, extract:\n"
                "- model_name: Official name (e.g., 'GPT-4.1', 'Llama 4 Scout')\n"
                "- organization: Who released it\n"
                "- release_date: Exact date in YYYY-MM-DD format. If only month is "
                "known, use the first of the month. Leave EMPTY if not derivable.\n"
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
                "- notable_features: 1-2 sentence summary of what's notable\n"
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
                "Extract all distinct model releases whose release date falls "
                f"within the last {lookback_days} days of {today_str}. Return "
                "ONLY valid JSON."
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
        # the release-date window here with a small buffer.
        now_dt = datetime.now(timezone.utc)
        max_age_days = max(int(lookback_days * RELEASE_DATE_BUFFER), lookback_days)
        cutoff_dt = now_dt - timedelta(days=max_age_days)

        # Deduplicate by normalized model name, filter by date, normalize fields
        seen_names: set = set()
        unique: List[ModelRelease] = []
        dropped_old = 0
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
            # Clamp future-dated announcements to today.
            if release_dt > now_dt:
                release_dt = now_dt
            m.release_date = release_dt.strftime("%Y-%m-%d")

            # Canonicalize classification fields.
            m.is_open_source = _normalize_open_source(m.is_open_source, m.license)
            m.modality = _normalize_modality(m.modality)

            seen_names.add(key)
            unique.append(m)

        logger.info(
            f"Model release extraction: {len(unique)} unique models "
            f"from {len(articles)} articles "
            f"(dropped {dropped_old} out-of-window, {dropped_undated} undated)"
        )
        return unique

    except Exception as e:
        logger.warning(f"Model release extraction failed: {e}")
        return []
