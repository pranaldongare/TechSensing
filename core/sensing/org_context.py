"""
Org Context — stores and retrieves organizational tech context for personalized sensing.

Storage: data/{user_id}/sensing/org_context.json
"""

import json
import logging
import os
from typing import List, Optional

import aiofiles
from pydantic import BaseModel, Field

logger = logging.getLogger("sensing.org_context")


class RadarQuadrantConfig(BaseModel):
    name: str = Field(description="Custom quadrant name")
    color: str = Field(default="", description="Hex color code (e.g., '#1ebccd')")


class RadarCustomization(BaseModel):
    quadrants: List[RadarQuadrantConfig] = Field(
        default_factory=lambda: [
            RadarQuadrantConfig(name="Techniques", color="#1ebccd"),
            RadarQuadrantConfig(name="Platforms", color="#f38a3e"),
            RadarQuadrantConfig(name="Tools", color="#86b82a"),
            RadarQuadrantConfig(name="Languages & Frameworks", color="#b32059"),
        ],
    )


class OrgTechContext(BaseModel):
    tech_stack: List[str] = Field(default_factory=list, description="Technologies in use")
    industry: str = Field(default="", description="Organization's industry")
    priorities: List[str] = Field(default_factory=list, description="Strategic tech priorities")
    radar_customization: Optional[RadarCustomization] = Field(
        default=None, description="Custom radar quadrant names and colors"
    )
    stakeholder_role: str = Field(
        default="general",
        description="User's role: 'cto', 'engineering_lead', 'developer', 'product_manager', 'general'",
    )


async def load_org_context(user_id: str) -> Optional[OrgTechContext]:
    """Load org context from disk. Returns None if not set."""
    fpath = _context_path(user_id)
    if not os.path.exists(fpath):
        return None
    try:
        async with aiofiles.open(fpath, "r", encoding="utf-8") as f:
            data = json.loads(await f.read())
        return OrgTechContext(**data)
    except Exception as e:
        logger.warning(f"Failed to load org context for {user_id}: {e}")
        return None


async def save_org_context(user_id: str, context: OrgTechContext) -> None:
    """Save org context to disk."""
    fpath = _context_path(user_id)
    os.makedirs(os.path.dirname(fpath), exist_ok=True)
    async with aiofiles.open(fpath, "w", encoding="utf-8") as f:
        await f.write(json.dumps(context.model_dump(), ensure_ascii=False, indent=2))
    logger.info(f"Org context saved for {user_id}: {len(context.tech_stack)} stack items")


def build_org_context_prompt(context: OrgTechContext) -> str:
    """Build the org context string for injection into report prompts."""
    parts = []
    if context.tech_stack:
        parts.append(f"Tech stack: {', '.join(context.tech_stack)}")
    if context.industry:
        parts.append(f"Industry: {context.industry}")
    if context.priorities:
        parts.append(f"Priorities: {', '.join(context.priorities)}")

    if not parts:
        return ""

    return (
        "ORGANIZATIONAL CONTEXT: The reader's organization uses the following. "
        + ". ".join(parts) + ". "
        "Tailor recommendations accordingly. Flag technologies that complement "
        "or replace their existing stack. Highlight alignment with their priorities."
    )


def _context_path(user_id: str) -> str:
    return f"data/{user_id}/sensing/org_context.json"
