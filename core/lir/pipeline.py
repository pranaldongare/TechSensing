"""
LIR pipeline orchestrator — ingest → dedup → extract → canonicalize → score → save.

Main entry point called by the route handler.
"""

import logging
import time
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional

from core.lir.adapters import aggregate_lir_sources
from core.lir.canonicalization import canonicalize_signals
from core.lir.config import (
    LIR_LOOKBACK_DAYS,
    LIR_MAX_CANDIDATES,
    LIR_MAX_PER_SOURCE,
    LIR_MIN_COMPOSITE_SCORE,
    score_to_ring,
)
from core.lir.dedup import deduplicate_lir_items
from core.lir.extraction import extract_signals
from core.lir.models import (
    CandidateTrend,
    LIRConcept,
    LIRPipelineResult,
    LIRScoreSet,
    LIRSignalRecord,
)
from core.lir.scoring import compute_scores
from core.lir.storage import (
    load_concept_signals,
    load_concepts,
    load_signals,
    save_concept_signals,
    save_concepts,
    save_raw_items,
    save_scores,
    save_signals,
)

logger = logging.getLogger("lir.pipeline")


async def run_lir_pipeline(
    lookback_days: int = LIR_LOOKBACK_DAYS,
    max_per_source: int = LIR_MAX_PER_SOURCE,
    progress_callback: Optional[Callable] = None,
) -> LIRPipelineResult:
    """Execute the full LIR pipeline.

    Steps:
        1. Ingest from enabled adapters
        2. Dedup against existing items
        3. Extract signals via LLM
        4. Canonicalize concepts via LLM
        5. Score all concepts
        6. Build candidate feed
        7. Persist everything

    Args:
        lookback_days: How far back to poll sources.
        max_per_source: Max items per adapter.
        progress_callback: Optional async callable(stage, pct, detail).

    Returns:
        LIRPipelineResult with ranked candidates.
    """
    start = time.time()
    errors: List[str] = []

    async def _progress(stage: str, pct: int, detail: str = ""):
        if progress_callback:
            try:
                await progress_callback(stage, pct, detail)
            except Exception:
                pass

    # ─── 1. Ingest ───
    await _progress("ingest", 0, "Polling LIR sources...")
    since = datetime.now(timezone.utc) - timedelta(days=lookback_days)

    try:
        raw_items = await aggregate_lir_sources(since, max_per_source)
    except Exception as e:
        logger.error(f"Ingestion failed: {e}")
        errors.append(f"Ingestion: {e}")
        raw_items = []

    total_ingested = len(raw_items)
    logger.info(f"Ingested {total_ingested} raw items")
    await _progress("ingest", 15, f"Ingested {total_ingested} items")

    if not raw_items:
        elapsed = time.time() - start
        return LIRPipelineResult(
            candidates=[],
            total_items_ingested=0,
            total_items_after_dedup=0,
            total_signals_extracted=0,
            total_concepts=0,
            new_concepts=0,
            execution_time_seconds=elapsed,
            errors=errors or ["No items ingested from any source"],
        )

    # ─── 2. Dedup ───
    await _progress("dedup", 20, "Deduplicating...")

    # Load existing signal item_ids to skip known items
    existing_signals = load_signals()
    existing_item_ids = {s.item_id for s in existing_signals.values()}

    deduped = deduplicate_lir_items(raw_items, existing_item_ids)
    logger.info(f"After dedup: {len(deduped)} new items (from {total_ingested})")
    await _progress("dedup", 25, f"{len(deduped)} new items after dedup")

    # Save raw items for audit trail
    save_raw_items(deduped)

    if not deduped:
        # No new items — still re-score existing data
        logger.info("No new items; re-scoring existing concepts")
        concepts = load_concepts()
        concept_signals_map = load_concept_signals()
        scores = compute_scores(concepts, existing_signals, concept_signals_map)
        candidates = _build_candidates(concepts, scores, existing_signals, concept_signals_map)
        save_scores({cid: asdict(s) for cid, s in scores.items()})
        elapsed = time.time() - start
        return LIRPipelineResult(
            candidates=candidates,
            total_items_ingested=total_ingested,
            total_items_after_dedup=0,
            total_signals_extracted=0,
            total_concepts=len(concepts),
            new_concepts=0,
            execution_time_seconds=elapsed,
        )

    # ─── 3. Extract signals ───
    await _progress("extract", 30, "Extracting signals via LLM...")

    try:
        new_signals = await extract_signals(deduped)
    except Exception as e:
        logger.error(f"Extraction failed: {e}")
        errors.append(f"Extraction: {e}")
        new_signals = []

    logger.info(f"Extracted {len(new_signals)} signals")
    await _progress("extract", 55, f"Extracted {len(new_signals)} signals")

    # ─── 4. Canonicalize concepts ───
    await _progress("canonicalize", 60, "Canonicalizing concepts...")

    concepts = load_concepts()

    try:
        new_signals, concepts, new_concept_count = await canonicalize_signals(
            new_signals, concepts
        )
    except Exception as e:
        logger.error(f"Canonicalization failed: {e}")
        errors.append(f"Canonicalization: {e}")
        new_concept_count = 0

    logger.info(f"Canonicalization: {new_concept_count} new concepts")
    await _progress("canonicalize", 75, f"{new_concept_count} new concepts")

    # ─── 5. Merge signals and build concept-signal map ───
    await _progress("score", 80, "Scoring concepts...")

    # Merge new signals into existing
    all_signals = existing_signals.copy()
    for sig in new_signals:
        all_signals[sig.signal_id] = sig

    # Build concept-signal mapping
    concept_signals_map = load_concept_signals()
    for sig in new_signals:
        if sig.canonical_concept_id:
            cid = sig.canonical_concept_id
            if cid not in concept_signals_map:
                concept_signals_map[cid] = []
            if sig.signal_id not in concept_signals_map[cid]:
                concept_signals_map[cid].append(sig.signal_id)

    # ─── 6. Score ───
    scores = compute_scores(concepts, all_signals, concept_signals_map)
    await _progress("score", 90, f"Scored {len(scores)} concepts")

    # ─── 7. Build candidates ───
    candidates = _build_candidates(concepts, scores, all_signals, concept_signals_map)
    logger.info(f"Built {len(candidates)} candidates above threshold")

    # ─── 8. Persist ───
    await _progress("save", 95, "Saving results...")

    save_concepts(concepts)
    save_signals(all_signals)
    save_concept_signals(concept_signals_map)
    save_scores({cid: asdict(s) for cid, s in scores.items()})

    elapsed = time.time() - start
    logger.info(f"LIR pipeline complete in {elapsed:.1f}s")
    await _progress("done", 100, "Complete")

    return LIRPipelineResult(
        candidates=candidates,
        total_items_ingested=total_ingested,
        total_items_after_dedup=len(deduped),
        total_signals_extracted=len(new_signals),
        total_concepts=len(concepts),
        new_concepts=new_concept_count,
        execution_time_seconds=elapsed,
        sources_polled=[item.source_id for item in deduped[:1]],  # Simplified
        errors=errors,
    )


def _build_candidates(
    concepts: Dict[str, LIRConcept],
    scores: Dict[str, LIRScoreSet],
    signals: Dict[str, LIRSignalRecord],
    concept_signals: Dict[str, List[str]],
) -> List[CandidateTrend]:
    """Build ranked candidate feed from scored concepts."""
    candidates: List[CandidateTrend] = []

    for cid, concept in concepts.items():
        score_set = scores.get(cid, LIRScoreSet())
        composite = score_set.composite

        if composite < LIR_MIN_COMPOSITE_SCORE:
            continue

        ring = score_to_ring(composite)

        # Gather evidence
        sig_ids = concept_signals.get(cid, [])
        concept_sigs = [signals[sid] for sid in sig_ids if sid in signals]

        # Top evidence URLs
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

        # Date range
        dates = [s.published_date for s in concept_sigs if s.published_date]
        first_seen = min(dates) if dates else ""
        last_seen = max(dates) if dates else ""

        # Weekly signal counts for sparkline (last 12 weeks)
        velocity_trend = _weekly_signal_counts(concept_sigs, weeks=12)

        candidates.append(
            CandidateTrend(
                concept_id=cid,
                canonical_name=concept.canonical_name,
                description=concept.description,
                ring=ring,
                scores=score_set,
                composite_score=round(composite, 4),
                signal_count=len(concept_sigs),
                source_tiers=concept.source_tiers,
                domain_tags=concept.domain_tags,
                top_evidence=top_evidence,
                first_seen=first_seen,
                last_seen=last_seen,
                velocity_trend=velocity_trend,
            )
        )

    # Sort by composite score descending
    candidates.sort(key=lambda c: c.composite_score, reverse=True)
    return candidates[:LIR_MAX_CANDIDATES]


def _weekly_signal_counts(
    signals: List[LIRSignalRecord],
    weeks: int = 12,
) -> List[float]:
    """Compute weekly signal counts for the last N weeks (oldest first)."""
    now = datetime.now(timezone.utc)
    counts = [0.0] * weeks

    for sig in signals:
        try:
            pub = datetime.fromisoformat(
                sig.published_date.replace("Z", "+00:00")
            )
            weeks_ago = (now - pub).days // 7
            if 0 <= weeks_ago < weeks:
                counts[weeks - 1 - weeks_ago] += 1.0
        except (ValueError, TypeError):
            continue

    return counts
