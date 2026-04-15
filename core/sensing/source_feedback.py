"""
Source Quality Feedback — stores and applies user feedback on source quality.

Storage: data/{user_id}/sensing/source_feedback.json

Schema: {
    "source_name": {
        "upvotes": 5,
        "downvotes": 2,
        "user_authority_modifier": 0.15  # computed: (up - down) / (up + down) * 0.3
    }
}
"""

import json
import logging
import os
from typing import Optional

import aiofiles

logger = logging.getLogger("sensing.source_feedback")


async def load_source_feedback(user_id: str) -> dict:
    """Load source feedback for a user."""
    path = f"data/{user_id}/sensing/source_feedback.json"
    if not os.path.exists(path):
        return {}
    try:
        async with aiofiles.open(path, "r") as f:
            return json.loads(await f.read())
    except Exception:
        return {}


async def save_source_feedback(user_id: str, feedback: dict) -> None:
    """Save source feedback."""
    path = f"data/{user_id}/sensing/source_feedback.json"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    async with aiofiles.open(path, "w") as f:
        await f.write(json.dumps(feedback, indent=2))


async def record_vote(user_id: str, source_name: str, vote: str) -> dict:
    """Record an upvote or downvote for a source.

    Args:
        vote: "up" or "down"

    Returns updated feedback dict.
    """
    feedback = await load_source_feedback(user_id)

    if source_name not in feedback:
        feedback[source_name] = {"upvotes": 0, "downvotes": 0, "user_authority_modifier": 0.0}

    entry = feedback[source_name]
    if vote == "up":
        entry["upvotes"] += 1
    elif vote == "down":
        entry["downvotes"] += 1

    total = entry["upvotes"] + entry["downvotes"]
    if total > 0:
        # Range: -0.3 to +0.3
        entry["user_authority_modifier"] = round(
            (entry["upvotes"] - entry["downvotes"]) / total * 0.3, 3
        )

    await save_source_feedback(user_id, feedback)
    return feedback


def get_adjusted_authority(
    base_authority: float,
    source_name: str,
    user_feedback: dict,
) -> float:
    """Apply user feedback modifier to base source authority score."""
    entry = user_feedback.get(source_name, {})
    modifier = entry.get("user_authority_modifier", 0.0)
    return max(0.1, min(1.0, base_authority + modifier))
