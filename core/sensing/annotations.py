"""
Annotations — per-user notes on report items (radar techs, trends, etc.).

Storage: data/{user_id}/sensing/annotations.json
Key format: {tracking_id}:{item_type}:{item_key}
"""

import json
import logging
import os
from typing import Dict, Optional

import aiofiles

logger = logging.getLogger("sensing.annotations")


def _annotations_path(user_id: str) -> str:
    return f"data/{user_id}/sensing/annotations.json"


async def load_annotations(
    user_id: str,
    tracking_id: Optional[str] = None,
) -> Dict[str, dict]:
    """Load annotations, optionally filtered by tracking_id prefix."""
    path = _annotations_path(user_id)
    if not os.path.exists(path):
        return {}

    try:
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            data = json.loads(await f.read())
    except Exception as e:
        logger.warning(f"Failed to load annotations: {e}")
        return {}

    if not isinstance(data, dict):
        return {}

    if tracking_id:
        prefix = f"{tracking_id}:"
        return {k: v for k, v in data.items() if k.startswith(prefix)}

    return data


async def save_annotation(
    user_id: str,
    key: str,
    note: str,
    item_type: str = "radar",
) -> Dict[str, dict]:
    """Save or update a single annotation. Returns the full annotations dict."""
    all_annotations = await load_annotations(user_id)

    if note.strip():
        all_annotations[key] = {
            "note": note,
            "item_type": item_type,
        }
    else:
        # Empty note = delete
        all_annotations.pop(key, None)

    path = _annotations_path(user_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    async with aiofiles.open(path, "w", encoding="utf-8") as f:
        await f.write(json.dumps(all_annotations, ensure_ascii=False, indent=2))

    return all_annotations


async def delete_annotation(
    user_id: str,
    key: str,
) -> Dict[str, dict]:
    """Delete an annotation by key. Returns the remaining annotations."""
    all_annotations = await load_annotations(user_id)
    all_annotations.pop(key, None)

    path = _annotations_path(user_id)
    if all_annotations:
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(all_annotations, ensure_ascii=False, indent=2))
    elif os.path.exists(path):
        os.remove(path)

    return all_annotations
