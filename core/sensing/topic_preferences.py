"""
Topic Preferences — per-domain user interest tracking.

Users can mark technologies as "interested" or "not_interested".
On the next pipeline run:
- **Interested** items get boosted (added to must_include)
- **Not Interested** items get suppressed (added to dont_include)
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Literal, Optional

import aiofiles
from pydantic import BaseModel, Field

logger = logging.getLogger("sensing.topic_preferences")


class TopicPreferences(BaseModel):
    """Per-domain topic interest preferences."""

    domain: str = Field(description="Domain these preferences apply to.")
    interested: list[str] = Field(
        default_factory=list,
        description="Technologies the user is interested in.",
    )
    not_interested: list[str] = Field(
        default_factory=list,
        description="Technologies the user is not interested in.",
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )


def _prefs_path(user_id: str, domain: str) -> str:
    """File path for topic preferences."""
    slug = domain.lower().replace(" ", "_").replace("/", "_")
    return f"data/{user_id}/sensing/topic_prefs_{slug}.json"


async def load_topic_preferences(
    user_id: str, domain: str
) -> TopicPreferences:
    """Load topic preferences for a user+domain. Returns empty prefs if none."""
    fpath = _prefs_path(user_id, domain)
    if not os.path.exists(fpath):
        return TopicPreferences(domain=domain)
    try:
        async with aiofiles.open(fpath, "r", encoding="utf-8") as f:
            data = json.loads(await f.read())
        return TopicPreferences(**data)
    except Exception:
        return TopicPreferences(domain=domain)


async def save_topic_preferences(
    user_id: str, domain: str, prefs: TopicPreferences
) -> None:
    """Persist topic preferences to disk."""
    fpath = _prefs_path(user_id, domain)
    os.makedirs(os.path.dirname(fpath), exist_ok=True)
    prefs.updated_at = datetime.now(timezone.utc).isoformat()
    async with aiofiles.open(fpath, "w", encoding="utf-8") as f:
        await f.write(
            json.dumps(prefs.model_dump(), ensure_ascii=False, indent=2)
        )


async def mark_topic(
    user_id: str,
    domain: str,
    technology_name: str,
    interest: Literal["interested", "not_interested", "neutral"],
) -> TopicPreferences:
    """Mark a technology as interested/not_interested/neutral.

    Returns the updated preferences.
    """
    prefs = await load_topic_preferences(user_id, domain)
    name = technology_name.strip()

    # Remove from both lists first
    prefs.interested = [t for t in prefs.interested if t.lower() != name.lower()]
    prefs.not_interested = [
        t for t in prefs.not_interested if t.lower() != name.lower()
    ]

    # Add to the appropriate list
    if interest == "interested":
        prefs.interested.append(name)
    elif interest == "not_interested":
        prefs.not_interested.append(name)
    # "neutral" = removed from both, nothing to add

    await save_topic_preferences(user_id, domain, prefs)
    logger.info(
        f"Topic preference: '{name}' -> {interest} for {domain} "
        f"(user={user_id})"
    )
    return prefs
