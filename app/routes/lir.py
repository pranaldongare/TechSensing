"""
Leading Indicator Radar (LIR) API — trend detection from weak signals.

Endpoints:
  POST /lir/refresh                  — trigger pipeline run
  GET  /lir/status/{tracking_id}     — poll for completion
  GET  /lir/candidates               — ranked candidate list
  GET  /lir/concepts                 — search concept registry
  GET  /lir/concepts/{concept_id}    — full concept detail + evidence
  GET  /lir/concepts/{concept_id}/timeseries — score history
  GET  /lir/concepts/{concept_id}/rationale — LLM rationale (cached)
  GET  /lir/sources                  — configured adapters + health
  GET  /lir/patterns                 — fingerprint pattern library
  POST /lir/backtest/run             — kick off backtest
  GET  /lir/backtest/{run_id}        — backtest results
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

import aiofiles
from fastapi import APIRouter, Body, HTTPException, Query, Request

from core.llm.client import tracking_id_var
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
        tracking_id_var.set(tracking_id)
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

    concepts = await load_concepts()
    if not concepts:
        return JSONResponse(content={"candidates": [], "total": 0})

    scores_raw = await load_latest_scores()
    signals = await load_signals()
    concept_signals = await load_concept_signals()

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
            persistence=score_data.get("persistence", 0.0),
            cross_platform=score_data.get("cross_platform", 0.0),
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

    concepts = await load_concepts()
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

    concepts = await load_concepts()
    if concept_id not in concepts:
        raise HTTPException(status_code=404, detail="Concept not found")

    concept = concepts[concept_id]
    scores_raw = await load_latest_scores()
    score_data = scores_raw.get(concept_id, {})
    score_set = LIRScoreSet(
        convergence=score_data.get("convergence", 0.0),
        velocity=score_data.get("velocity", 0.0),
        novelty=score_data.get("novelty", 0.5),
        authority=score_data.get("authority", 0.5),
        pattern_match=score_data.get("pattern_match", 0.0),
    )

    # Get all linked signals
    signals = await load_signals()
    concept_signals = await load_concept_signals()
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

    history = await load_signal_history(concept_id)
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


# ──────────────────────── GET /lir/concepts/{id}/rationale ────────────────────────


@router.get("/concepts/{concept_id}/rationale")
async def lir_concept_rationale(concept_id: str):
    """Generate or return cached LLM rationale for a concept."""
    import os as _os

    from core.lir.storage import load_concept_signals, load_concepts, load_latest_scores, load_signals

    # Check cache first
    cache_dir = "data/lir/rationales"
    _os.makedirs(cache_dir, exist_ok=True)
    cache_path = _os.path.join(cache_dir, f"{concept_id}.json")

    if _os.path.exists(cache_path):
        try:
            async with aiofiles.open(cache_path, "r", encoding="utf-8") as f:
                cached = json.loads(await f.read())
            return JSONResponse(content=cached)
        except Exception:
            pass

    # Load concept data
    concepts = await load_concepts()
    if concept_id not in concepts:
        raise HTTPException(status_code=404, detail="Concept not found")

    concept = concepts[concept_id]
    scores_raw = await load_latest_scores()
    score_data = scores_raw.get(concept_id, {})

    from core.lir.config import score_to_ring
    from core.lir.models import LIRScoreSet

    score_set = LIRScoreSet(
        convergence=score_data.get("convergence", 0.0),
        velocity=score_data.get("velocity", 0.0),
        novelty=score_data.get("novelty", 0.5),
        authority=score_data.get("authority", 0.5),
        pattern_match=score_data.get("pattern_match", 0.0),
    )
    ring = score_to_ring(score_set.composite)

    # Build top evidence
    signals = await load_signals()
    concept_signals_map = await load_concept_signals()
    sig_ids = concept_signals_map.get(concept_id, [])
    concept_sigs = [signals[sid] for sid in sig_ids if sid in signals]

    top_evidence = []
    for sig in sorted(concept_sigs, key=lambda s: s.relevance_score, reverse=True)[:5]:
        top_evidence.append({
            "url": sig.url,
            "title": sig.summary[:100] if sig.summary else "",
            "source": sig.source_id,
            "date": sig.published_date,
        })

    # Pattern matches
    from core.lir.patterns import find_matching_patterns
    from core.lir.pipeline import _weekly_signal_counts

    weekly = _weekly_signal_counts(concept_sigs, weeks=52)
    pattern_matches = find_matching_patterns(weekly)

    # Generate rationale via LLM
    try:
        from core.constants import GPU_LIR_EXTRACT_LLM
        from core.llm.client import invoke_llm
        from core.llm.output_schemas.lir_outputs import LIRRationale
        from core.llm.prompts.lir_prompts import lir_rationale_prompt

        prompt = lir_rationale_prompt(
            concept_name=concept.canonical_name,
            description=concept.description,
            scores=asdict(score_set),
            signal_count=len(concept_sigs),
            source_tiers=concept.source_tiers,
            top_evidence=top_evidence,
            ring=ring,
            pattern_matches=pattern_matches or None,
        )

        result: LIRRationale = await invoke_llm(
            gpu_model=GPU_LIR_EXTRACT_LLM.model,
            response_schema=LIRRationale,
            contents=prompt,
            port=GPU_LIR_EXTRACT_LLM.port,
        )

        rationale_data = {
            "concept_id": concept_id,
            "summary": result.summary,
            "key_drivers": result.key_drivers,
            "risk_factors": result.risk_factors,
            "recommended_action": result.recommended_action,
            "pattern_matches": pattern_matches,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        # Cache the result
        try:
            async with aiofiles.open(cache_path, "w", encoding="utf-8") as f:
                await f.write(json.dumps(rationale_data, ensure_ascii=False, indent=2))
        except Exception as cache_err:
            logger.warning(f"Failed to cache rationale: {cache_err}")

        return JSONResponse(content=rationale_data)

    except Exception as e:
        logger.warning(f"Rationale generation failed for {concept_id}: {e}")
        # Return a basic rationale without LLM
        fallback = {
            "concept_id": concept_id,
            "summary": (
                f"{concept.canonical_name} is currently in the '{ring}' ring "
                f"with {len(concept_sigs)} signals from {len(concept.source_tiers)} source tiers."
            ),
            "key_drivers": [],
            "risk_factors": [],
            "recommended_action": "",
            "pattern_matches": pattern_matches,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        return JSONResponse(content=fallback)


# ──────────────────────── GET /lir/patterns ────────────────────────


@router.get("/patterns")
async def lir_patterns():
    """List available fingerprint patterns."""
    from core.lir.patterns import load_fingerprints

    fps = load_fingerprints()
    patterns = []
    for fp_id, fp in fps.items():
        patterns.append({
            "pattern_id": fp.pattern_id,
            "name": fp.name,
            "description": fp.description,
            "duration_weeks": fp.duration_weeks,
            "expected_ring": fp.expected_ring,
            "consensus_week": fp.consensus_week,
            "tags": fp.tags,
        })

    return JSONResponse(content={"patterns": patterns, "total": len(patterns)})


# ──────────────────────── POST /lir/backtest/run ────────────────────────


class BacktestRequest(BaseModel):
    start_date: Optional[str] = Field(None, description="ISO start date")
    end_date: Optional[str] = Field(None, description="ISO end date")
    step_weeks: int = Field(4, description="Weeks between scoring snapshots")
    concept_ids: Optional[List[str]] = Field(None, description="Filter to specific concepts")


@router.post("/backtest/run")
async def lir_backtest_run(
    request: Request,
    body: BacktestRequest = Body(BacktestRequest()),
):
    """Start an async backtest run."""
    from core.constants import sensing_feature

    if not sensing_feature("lir_enabled"):
        raise HTTPException(status_code=403, detail="LIR feature is disabled")

    tracking_id = str(uuid.uuid4())
    status_file = _status_path(f"bt_{tracking_id}")
    await write_pending_status(status_file)

    async def _run_bt():
        tracking_id_var.set(tracking_id)
        try:
            from core.lir.backtest import run_backtest

            result = await run_backtest(
                start_date=body.start_date,
                end_date=body.end_date,
                step_weeks=body.step_weeks,
                concept_filter=body.concept_ids,
            )

            result_data = {
                "run_id": result.run_id,
                "start_date": result.start_date,
                "end_date": result.end_date,
                "weights_used": result.weights_used,
                "total_concepts": result.total_concepts,
                "execution_time_seconds": result.execution_time_seconds,
                "errors": result.errors,
                "concept_results": [
                    {
                        "concept_id": cr.concept_id,
                        "canonical_name": cr.canonical_name,
                        "first_assess_week": cr.first_assess_week,
                        "first_trial_week": cr.first_trial_week,
                        "first_adopt_week": cr.first_adopt_week,
                        "snapshots": [
                            {
                                "week_offset": s.week_offset,
                                "date": s.date,
                                "signal_count": s.signal_count,
                                "scores": s.scores,
                                "composite": s.composite,
                                "ring": s.ring,
                            }
                            for s in cr.snapshots
                        ],
                    }
                    for cr in result.concept_results
                ],
            }

            await write_result(status_file, result_data)
            logger.info(f"Backtest complete: {result.total_concepts} concepts, {result.execution_time_seconds:.1f}s")

        except Exception:
            error_details = traceback.format_exc()
            await write_failed_status(status_file, error_details)
            logger.error(f"Backtest failed: {error_details}")

    asyncio.create_task(_run_bt())

    return JSONResponse(
        content={
            "status": "pending",
            "tracking_id": tracking_id,
            "run_id": f"bt_{tracking_id}",
            "message": "Backtest started",
        }
    )


# ──────────────────────── GET /lir/backtest/{tracking_id} ────────────────────────


@router.get("/backtest/{tracking_id}")
async def lir_backtest_status(tracking_id: str):
    """Poll for backtest completion."""
    status_file = _status_path(f"bt_{tracking_id}")
    gen_status = await read_generation_status(status_file)

    if gen_status is None:
        raise HTTPException(status_code=404, detail="Backtest run not found")

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


# ──────────────────────── POST /lir/sources/{id}/refresh ────────────────────────


@router.post("/sources/{source_id}/refresh")
async def lir_source_refresh(source_id: str):
    """Manual pull for a single source adapter."""
    from core.lir.adapters import get_enabled_lir_adapters

    adapters = get_enabled_lir_adapters()
    adapter = next((a for a in adapters if a.source_id == source_id), None)

    if not adapter:
        raise HTTPException(status_code=404, detail=f"Source '{source_id}' not found or not enabled")

    try:
        from datetime import timedelta
        since = datetime.now(timezone.utc) - timedelta(days=90)
        items = await adapter.poll(since, max_results=50)
        return JSONResponse(content={
            "source_id": source_id,
            "items_fetched": len(items),
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
