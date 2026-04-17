"""
Leading Indicator Radar (LIR) API — trend detection from weak signals.

Endpoints:
  POST /lir/refresh                  — trigger pipeline run
  GET  /lir/status/{tracking_id}     — poll for completion
  GET  /lir/candidates               — ranked candidate list
  GET  /lir/concepts                 — search concept registry
  GET  /lir/concepts/{concept_id}    — full concept detail + evidence
  GET  /lir/concepts/{concept_id}/timeseries — score history
  GET  /lir/sources                  — configured adapters + health
"""

import asyncio
import json
import logging
import os
import traceback
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Body, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from core.utils.generation_status import (
    read_generation_status,
    write_failed_status,
    write_pending_status,
    write_result,
)

logger = logging.getLogger("lir.routes")

router = APIRouter(prefix="/lir", tags=["Leading Indicator Radar"])

LIR_STATUS_DIR = "data/lir/status"
LIR_STALE_TIMEOUT_MINUTES = 30


# ──────────────────────── Request models ────────────────────────


class LIRRefreshRequest(BaseModel):
    lookback_days: int = Field(
        default=90,
        description="How far back to poll sources (days)",
    )
    max_per_source: int = Field(
        default=100,
        description="Maximum items per source adapter",
    )


# ──────────────────────── Helpers ────────────────────────


def _status_path(tracking_id: str) -> str:
    os.makedirs(LIR_STATUS_DIR, exist_ok=True)
    return os.path.join(LIR_STATUS_DIR, f"lir_status_{tracking_id}.json")


# ──────────────────────── POST /lir/refresh ────────────────────────


@router.post("/refresh")
async def lir_refresh(
    request: Request,
    body: LIRRefreshRequest = Body(LIRRefreshRequest()),
):
    """Start an async LIR pipeline run."""
    from core.constants import sensing_feature

    if not sensing_feature("lir_enabled"):
        raise HTTPException(
            status_code=403,
            detail="LIR feature is disabled. Set SENSING_FEATURE_LIR=1 to enable.",
        )

    tracking_id = str(uuid.uuid4())
    status_file = _status_path(tracking_id)
    await write_pending_status(status_file)

    async def _run():
        try:
            from core.lir.pipeline import run_lir_pipeline

            result = await run_lir_pipeline(
                lookback_days=body.lookback_days,
                max_per_source=body.max_per_source,
            )

            result_data = {
                "candidates": [asdict(c) for c in result.candidates],
                "meta": {
                    "tracking_id": tracking_id,
                    "total_items_ingested": result.total_items_ingested,
                    "total_items_after_dedup": result.total_items_after_dedup,
                    "total_signals_extracted": result.total_signals_extracted,
                    "total_concepts": result.total_concepts,
                    "new_concepts": result.new_concepts,
                    "execution_time_seconds": result.execution_time_seconds,
                    "sources_polled": result.sources_polled,
                    "errors": result.errors,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                },
            }

            await write_result(status_file, result_data)
            logger.info(
                f"LIR pipeline complete: {len(result.candidates)} candidates, "
                f"{result.execution_time_seconds:.1f}s"
            )

        except Exception:
            error_details = traceback.format_exc()
            await write_failed_status(status_file, error_details)
            logger.error(f"LIR pipeline failed: {error_details}")

    asyncio.create_task(_run())

    return JSONResponse(
        content={
            "status": "pending",
            "tracking_id": tracking_id,
            "message": "LIR pipeline started",
        }
    )


# ──────────────────────── GET /lir/status/{tracking_id} ────────────────────────


@router.get("/status/{tracking_id}")
async def lir_status(tracking_id: str):
    """Poll for LIR pipeline completion."""
    status_file = _status_path(tracking_id)
    gen_status = await read_generation_status(status_file)

    if gen_status is None:
        raise HTTPException(status_code=404, detail="LIR run not found")

    if gen_status["state"] == "pending":
        return JSONResponse(content={"status": "pending"})
    elif gen_status["state"] == "failed":
        return JSONResponse(
            content={"status": "failed", "error": gen_status.get("error", "")}
        )
    else:
        return JSONResponse(
            content={"status": "completed", "data": gen_status["data"]}
        )


# ──────────────────────── GET /lir/candidates ────────────────────────


@router.get("/candidates")
async def lir_candidates(
    ring: Optional[str] = Query(None, description="Filter by ring: adopt/trial/assess/hold"),
    limit: int = Query(50, ge=1, le=200),
    min_score: float = Query(0.0, ge=0.0, le=1.0),
):
    """Return ranked candidate trends from the latest scoring run."""
    from core.lir.config import LIR_MIN_COMPOSITE_SCORE
    from core.lir.models import LIRScoreSet
    from core.lir.storage import (
        load_concept_signals,
        load_concepts,
        load_latest_scores,
        load_signals,
    )
    from core.lir.config import score_to_ring

    concepts = load_concepts()
    if not concepts:
        return JSONResponse(content={"candidates": [], "total": 0})

    scores_raw = load_latest_scores()
    signals = load_signals()
    concept_signals = load_concept_signals()

    candidates = []
    effective_min = max(min_score, LIR_MIN_COMPOSITE_SCORE)

    for cid, concept in concepts.items():
        score_data = scores_raw.get(cid, {})
        score_set = LIRScoreSet(
            convergence=score_data.get("convergence", 0.0),
            velocity=score_data.get("velocity", 0.0),
            novelty=score_data.get("novelty", 0.5),
            authority=score_data.get("authority", 0.5),
            pattern_match=score_data.get("pattern_match", 0.0),
        )
        composite = score_set.composite

        if composite < effective_min:
            continue

        concept_ring = score_to_ring(composite)
        if ring and concept_ring != ring:
            continue

        # Get signal details
        sig_ids = concept_signals.get(cid, [])
        concept_sigs = [signals[sid] for sid in sig_ids if sid in signals]

        top_evidence = []
        seen_urls = set()
        for sig in sorted(concept_sigs, key=lambda s: s.relevance_score, reverse=True)[:5]:
            if sig.url and sig.url not in seen_urls:
                seen_urls.add(sig.url)
                top_evidence.append({
                    "url": sig.url,
                    "title": sig.summary[:100] if sig.summary else "",
                    "source": sig.source_id,
                    "date": sig.published_date,
                })

        dates = [s.published_date for s in concept_sigs if s.published_date]

        candidates.append({
            "concept_id": cid,
            "canonical_name": concept.canonical_name,
            "description": concept.description,
            "ring": concept_ring,
            "scores": asdict(score_set),
            "composite_score": round(composite, 4),
            "signal_count": len(concept_sigs),
            "source_tiers": concept.source_tiers,
            "domain_tags": concept.domain_tags,
            "top_evidence": top_evidence,
            "first_seen": min(dates) if dates else "",
            "last_seen": max(dates) if dates else "",
        })

    candidates.sort(key=lambda c: c["composite_score"], reverse=True)
    candidates = candidates[:limit]

    return JSONResponse(content={"candidates": candidates, "total": len(candidates)})


# ──────────────────────── GET /lir/concepts ────────────────────────


@router.get("/concepts")
async def lir_concepts_search(
    q: Optional[str] = Query(None, description="Search query"),
    tag: Optional[str] = Query(None, description="Filter by domain tag"),
    limit: int = Query(100, ge=1, le=500),
):
    """Search the concept registry."""
    from core.lir.storage import load_concepts

    concepts = load_concepts()
    results = []

    for cid, concept in concepts.items():
        # Filter by query
        if q:
            q_lower = q.lower()
            match = (
                q_lower in concept.canonical_name.lower()
                or q_lower in concept.description.lower()
                or any(q_lower in alias.lower() for alias in concept.aliases)
            )
            if not match:
                continue

        # Filter by tag
        if tag:
            if tag.lower() not in [t.lower() for t in concept.domain_tags]:
                continue

        results.append({
            "concept_id": cid,
            "canonical_name": concept.canonical_name,
            "aliases": concept.aliases,
            "description": concept.description,
            "domain_tags": concept.domain_tags,
            "signal_count": concept.signal_count,
            "source_tiers": concept.source_tiers,
            "created_at": concept.created_at,
        })

    results.sort(key=lambda c: c["signal_count"], reverse=True)
    return JSONResponse(content={"concepts": results[:limit], "total": len(results)})


# ──────────────────────── GET /lir/concepts/{concept_id} ────────────────────────


@router.get("/concepts/{concept_id}")
async def lir_concept_detail(concept_id: str):
    """Full concept detail with scores and evidence."""
    from core.lir.models import LIRScoreSet
    from core.lir.config import score_to_ring
    from core.lir.storage import (
        load_concept_signals,
        load_concepts,
        load_latest_scores,
        load_signals,
    )

    concepts = load_concepts()
    if concept_id not in concepts:
        raise HTTPException(status_code=404, detail="Concept not found")

    concept = concepts[concept_id]
    scores_raw = load_latest_scores()
    score_data = scores_raw.get(concept_id, {})
    score_set = LIRScoreSet(
        convergence=score_data.get("convergence", 0.0),
        velocity=score_data.get("velocity", 0.0),
        novelty=score_data.get("novelty", 0.5),
        authority=score_data.get("authority", 0.5),
        pattern_match=score_data.get("pattern_match", 0.0),
    )

    # Get all linked signals
    signals = load_signals()
    concept_signals = load_concept_signals()
    sig_ids = concept_signals.get(concept_id, [])
    concept_sigs = [signals[sid] for sid in sig_ids if sid in signals]

    evidence = []
    for sig in sorted(concept_sigs, key=lambda s: s.published_date or "", reverse=True):
        evidence.append({
            "signal_id": sig.signal_id,
            "source_id": sig.source_id,
            "tier": sig.tier,
            "url": sig.url,
            "summary": sig.summary,
            "evidence_quote": sig.evidence_quote,
            "stated_novelty": sig.stated_novelty,
            "relevance_score": sig.relevance_score,
            "published_date": sig.published_date,
        })

    composite = score_set.composite
    return JSONResponse(content={
        "concept_id": concept_id,
        "canonical_name": concept.canonical_name,
        "aliases": concept.aliases,
        "description": concept.description,
        "domain_tags": concept.domain_tags,
        "ring": score_to_ring(composite),
        "scores": asdict(score_set),
        "composite_score": round(composite, 4),
        "signal_count": len(concept_sigs),
        "source_tiers": concept.source_tiers,
        "created_at": concept.created_at,
        "updated_at": concept.updated_at,
        "evidence": evidence,
    })


# ──────────────────────── GET /lir/concepts/{id}/timeseries ────────────────────────


@router.get("/concepts/{concept_id}/timeseries")
async def lir_concept_timeseries(
    concept_id: str,
    weeks: int = Query(52, ge=1, le=104),
):
    """Score history for a concept (weekly snapshots)."""
    from core.lir.storage import load_signal_history

    history = load_signal_history(concept_id)
    if not history:
        return JSONResponse(content={"concept_id": concept_id, "timeseries": [], "weeks": weeks})

    # Return last N weeks
    return JSONResponse(content={
        "concept_id": concept_id,
        "timeseries": history[-weeks:],
        "weeks": len(history[-weeks:]),
    })


# ──────────────────────── GET /lir/sources ────────────────────────


@router.get("/sources")
async def lir_sources():
    """List configured LIR adapters and their status."""
    from core.lir.adapters import get_enabled_lir_adapters

    adapters = get_enabled_lir_adapters()
    sources = []
    for adapter in adapters:
        sources.append({
            "source_id": adapter.source_id,
            "tier": adapter.tier,
            "lead_time_prior_days": adapter.lead_time_prior_days,
            "authority_prior": adapter.authority_prior,
            "enabled": True,
        })

    return JSONResponse(content={"sources": sources, "total": len(sources)})
