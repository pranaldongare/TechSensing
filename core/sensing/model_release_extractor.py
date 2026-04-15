"""
Model Release Extractor — uses LLM to extract structured model release info
from search result articles.
"""

import json
import logging
from typing import List

from core.constants import GPU_SENSING_REPORT_LLM
from core.llm.client import invoke_llm
from core.llm.output_schemas.sensing_outputs import ModelRelease, ModelReleasesOutput
from core.sensing.ingest import RawArticle

logger = logging.getLogger("sensing.model_release_extractor")


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

    prompt = [
        {
            "role": "system",
            "parts": (
                "You are an AI model release tracker. Given a collection of articles "
                "about AI model announcements, extract structured information about "
                "each distinct model release.\n\n"
                f"Only include models released within the last {lookback_days} days.\n\n"
                "For each model, extract:\n"
                "- model_name: Official name (e.g., 'GPT-4.1', 'Llama 4 Scout')\n"
                "- organization: Who released it\n"
                "- release_date: Approximate date (YYYY-MM-DD)\n"
                "- parameters: Parameter count if known\n"
                "- license: Open source license or 'Proprietary'\n"
                "- model_type: Architecture (Transformer, MoE, Hybrid, Diffusion, etc.)\n"
                "- modality: Text, Multimodal, Image, Code, Audio, Video, etc.\n"
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
                "Extract all distinct model releases. Return ONLY valid JSON."
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

        # Deduplicate by normalized model name
        seen_names: set = set()
        unique: List[ModelRelease] = []
        for m in validated.model_releases:
            key = m.model_name.lower().strip()
            if key not in seen_names:
                seen_names.add(key)
                unique.append(m)

        logger.info(
            f"Model release extraction: {len(unique)} unique models "
            f"from {len(articles)} articles"
        )
        return unique

    except Exception as e:
        logger.warning(f"Model release extraction failed: {e}")
        return []
