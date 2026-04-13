"""
Collaborative Radar — share reports, vote on ring placements, and comment.

Storage: data/shared_reports/{share_id}.json
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import List, Optional

import aiofiles
from pydantic import BaseModel, Field

logger = logging.getLogger("sensing.collaboration")

SHARED_DIR = "data/shared_reports"


class RadarVote(BaseModel):
    vote_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    user_name: str
    radar_item_name: str
    suggested_ring: str
    reasoning: str = ""
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class RadarComment(BaseModel):
    comment_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    user_name: str
    radar_item_name: str = ""  # empty = general comment
    text: str
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class SharedReport(BaseModel):
    share_id: str
    report_tracking_id: str
    owner_user_id: str
    votes: List[RadarVote] = Field(default_factory=list)
    comments: List[RadarComment] = Field(default_factory=list)
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


def _shared_path(share_id: str) -> str:
    return os.path.join(SHARED_DIR, f"{share_id}.json")


async def create_shared_report(
    report_tracking_id: str,
    owner_user_id: str,
) -> SharedReport:
    """Create a new shared report."""
    os.makedirs(SHARED_DIR, exist_ok=True)

    share_id = str(uuid.uuid4())[:8]  # short ID for sharing
    shared = SharedReport(
        share_id=share_id,
        report_tracking_id=report_tracking_id,
        owner_user_id=owner_user_id,
    )

    async with aiofiles.open(_shared_path(share_id), "w", encoding="utf-8") as f:
        await f.write(json.dumps(shared.model_dump(), ensure_ascii=False, indent=2))

    logger.info(f"Shared report created: {share_id} for report {report_tracking_id}")
    return shared


async def load_shared_report(share_id: str) -> Optional[SharedReport]:
    """Load a shared report by ID."""
    fpath = _shared_path(share_id)
    if not os.path.exists(fpath):
        return None
    try:
        async with aiofiles.open(fpath, "r", encoding="utf-8") as f:
            data = json.loads(await f.read())
        return SharedReport(**data)
    except Exception as e:
        logger.error(f"Failed to load shared report {share_id}: {e}")
        return None


async def _save_shared(shared: SharedReport) -> None:
    """Save shared report to disk."""
    async with aiofiles.open(_shared_path(shared.share_id), "w", encoding="utf-8") as f:
        await f.write(json.dumps(shared.model_dump(), ensure_ascii=False, indent=2))


async def add_vote(
    share_id: str,
    user_id: str,
    user_name: str,
    radar_item_name: str,
    suggested_ring: str,
    reasoning: str = "",
) -> Optional[RadarVote]:
    """Add a ring vote to a shared report."""
    shared = await load_shared_report(share_id)
    if not shared:
        return None

    vote = RadarVote(
        user_id=user_id,
        user_name=user_name,
        radar_item_name=radar_item_name,
        suggested_ring=suggested_ring,
        reasoning=reasoning,
    )
    shared.votes.append(vote)
    await _save_shared(shared)
    logger.info(f"Vote added to {share_id}: {radar_item_name} -> {suggested_ring}")
    return vote


async def add_comment(
    share_id: str,
    user_id: str,
    user_name: str,
    text: str,
    radar_item_name: str = "",
) -> Optional[RadarComment]:
    """Add a comment to a shared report."""
    shared = await load_shared_report(share_id)
    if not shared:
        return None

    comment = RadarComment(
        user_id=user_id,
        user_name=user_name,
        radar_item_name=radar_item_name,
        text=text,
    )
    shared.comments.append(comment)
    await _save_shared(shared)
    logger.info(f"Comment added to {share_id} by {user_name}")
    return comment


async def get_feedback(share_id: str) -> Optional[dict]:
    """Get all feedback (votes + comments) for a shared report."""
    shared = await load_shared_report(share_id)
    if not shared:
        return None

    # Aggregate votes per radar item
    vote_summary: dict[str, dict] = {}
    for vote in shared.votes:
        name = vote.radar_item_name
        if name not in vote_summary:
            vote_summary[name] = {"votes": [], "ring_counts": {}}
        vote_summary[name]["votes"].append(vote.model_dump())
        ring = vote.suggested_ring
        vote_summary[name]["ring_counts"][ring] = (
            vote_summary[name]["ring_counts"].get(ring, 0) + 1
        )

    return {
        "share_id": shared.share_id,
        "votes": [v.model_dump() for v in shared.votes],
        "comments": [c.model_dump() for c in shared.comments],
        "vote_summary": vote_summary,
        "total_votes": len(shared.votes),
        "total_comments": len(shared.comments),
    }
