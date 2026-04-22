"""
Model Release Extractor — converts HuggingFace API data to ModelRelease objects.
"""

import logging
from datetime import datetime
from typing import List

from core.llm.output_schemas.sensing_outputs import ModelRelease

logger = logging.getLogger("sensing.model_release_extractor")


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
                data_source="HuggingFace",
            )
        )

    logger.info(f"Built {len(releases)} ModelRelease entries from HuggingFace data")
    return releases
