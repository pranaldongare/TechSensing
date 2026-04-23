"""
LIR storage — async JSON file I/O for concepts, signals, scores, and raw items.

All LIR data is global (not user-scoped), stored under data/lir/.
"""

import json
import logging
import os
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Dict, List, Optional

import aiofiles

from core.lir.models import (
    LIRConcept,
    LIRRawItem,
    LIRSignalRecord,
)

logger = logging.getLogger("lir.storage")

LIR_DATA_DIR = "data/lir"


def _ensure_dir(path: str) -> None:
    os.makedirs(os.path.dirname(path) if not os.path.isdir(path) else path, exist_ok=True)


def _lir_path(*parts: str) -> str:
    return os.path.join(LIR_DATA_DIR, *parts)


# ──────────────────────── Concepts ────────────────────────

async def load_concepts() -> Dict[str, LIRConcept]:
    """Load concept registry from JSON."""
    path = _lir_path("concepts.json")
    if not os.path.exists(path):
        return {}
    try:
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            data = json.loads(await f.read())
        return {
            cid: LIRConcept(**cdata)
            for cid, cdata in data.items()
        }
    except Exception as e:
        logger.warning(f"Failed to load concepts: {e}")
        return {}


async def save_concepts(concepts: Dict[str, LIRConcept]) -> None:
    """Save concept registry to JSON."""
    path = _lir_path("concepts.json")
    _ensure_dir(LIR_DATA_DIR)
    try:
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(
                {cid: asdict(c) for cid, c in concepts.items()},
                ensure_ascii=False,
                indent=2,
            ))
    except Exception as e:
        logger.error(f"Failed to save concepts: {e}")


# ──────────────────────── Signals ────────────────────────

async def load_signals() -> Dict[str, LIRSignalRecord]:
    """Load all signal records."""
    path = _lir_path("signals.json")
    if not os.path.exists(path):
        return {}
    try:
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            data = json.loads(await f.read())
        return {
            sid: LIRSignalRecord(**sdata)
            for sid, sdata in data.items()
        }
    except Exception as e:
        logger.warning(f"Failed to load signals: {e}")
        return {}


async def save_signals(signals: Dict[str, LIRSignalRecord]) -> None:
    """Save signal records to JSON."""
    path = _lir_path("signals.json")
    _ensure_dir(LIR_DATA_DIR)
    try:
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(
                {sid: asdict(s) for sid, s in signals.items()},
                ensure_ascii=False,
                indent=2,
            ))
    except Exception as e:
        logger.error(f"Failed to save signals: {e}")


# ──────────────────────── Concept-Signal mapping ────────────────────────

async def load_concept_signals() -> Dict[str, List[str]]:
    """Load concept_id -> [signal_ids] mapping."""
    path = _lir_path("concept_signals.json")
    if not os.path.exists(path):
        return {}
    try:
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            return json.loads(await f.read())
    except Exception as e:
        logger.warning(f"Failed to load concept_signals: {e}")
        return {}


async def save_concept_signals(mapping: Dict[str, List[str]]) -> None:
    """Save concept_id -> [signal_ids] mapping."""
    path = _lir_path("concept_signals.json")
    _ensure_dir(LIR_DATA_DIR)
    try:
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(mapping, ensure_ascii=False, indent=2))
    except Exception as e:
        logger.error(f"Failed to save concept_signals: {e}")


# ──────────────────────── Scores ────────────────────────

async def save_scores(
    scores: Dict[str, dict],
    date_str: Optional[str] = None,
) -> None:
    """Save score snapshot. Also writes latest.json."""
    if date_str is None:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    scores_dir = _lir_path("scores")
    _ensure_dir(scores_dir)

    # Daily snapshot
    daily_path = os.path.join(scores_dir, f"{date_str}.json")
    try:
        async with aiofiles.open(daily_path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(scores, ensure_ascii=False, indent=2))
    except Exception as e:
        logger.error(f"Failed to save daily scores: {e}")

    # Latest
    latest_path = os.path.join(scores_dir, "latest.json")
    try:
        async with aiofiles.open(latest_path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(scores, ensure_ascii=False, indent=2))
    except Exception as e:
        logger.error(f"Failed to save latest scores: {e}")


async def load_latest_scores() -> Dict[str, dict]:
    """Load the most recent score snapshot."""
    path = _lir_path("scores", "latest.json")
    if not os.path.exists(path):
        return {}
    try:
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            return json.loads(await f.read())
    except Exception as e:
        logger.warning(f"Failed to load latest scores: {e}")
        return {}


# ──────────────────────── Raw items (daily batches) ────────────────────────

async def save_raw_items(items: List[LIRRawItem], date_str: Optional[str] = None) -> None:
    """Save a batch of raw items under data/lir/raw_items/{date}/."""
    if date_str is None:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    batch_dir = _lir_path("raw_items", date_str)
    _ensure_dir(batch_dir)

    path = os.path.join(batch_dir, "batch.json")
    try:
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(
                [asdict(item) for item in items],
                ensure_ascii=False,
                indent=2,
            ))
        logger.info(f"Saved {len(items)} raw items to {path}")
    except Exception as e:
        logger.error(f"Failed to save raw items: {e}")


# ──────────────────────── Signal history (timeseries) ────────────────────────

async def load_signal_history(concept_id: str) -> List[dict]:
    """Load weekly signal history for a concept."""
    path = _lir_path("signal_history", f"{concept_id}.json")
    if not os.path.exists(path):
        return []
    try:
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            return json.loads(await f.read())
    except Exception as e:
        logger.warning(f"Failed to load signal history for {concept_id}: {e}")
        return []


async def save_signal_history(concept_id: str, history: List[dict]) -> None:
    """Save weekly signal history for a concept."""
    hist_dir = _lir_path("signal_history")
    _ensure_dir(hist_dir)

    path = os.path.join(hist_dir, f"{concept_id}.json")
    try:
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(history, ensure_ascii=False, indent=2))
    except Exception as e:
        logger.error(f"Failed to save signal history for {concept_id}: {e}")
