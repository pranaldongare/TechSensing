"""
LIR concept canonicalization — links extracted concept labels to
the canonical concept registry using LLM adjudication.

Phase 1: LLM-only (all existing concepts sent in prompt).
Phase 2: TF-IDF pre-filter when registry > 500 concepts.
"""

import logging
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from core.constants import GPU_LIR_CANON_LLM
from core.lir.config import CANONICALIZATION_BATCH_SIZE
from core.lir.models import LIRConcept, LIRSignalRecord
from core.llm.client import invoke_llm
from core.llm.output_schemas.lir_outputs import LIRCanonicalization
from core.llm.prompts.lir_prompts import lir_canonicalization_prompt

logger = logging.getLogger("lir.canonicalization")

# Threshold for switching to TF-IDF pre-filter
_TFIDF_THRESHOLD = 500
_TFIDF_TOP_K = 5


def _slugify(name: str) -> str:
    """Convert a concept name to a slug ID."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug[:80]


def _tfidf_nearest_concepts(
    label: str,
    concepts: Dict[str, LIRConcept],
    top_k: int = _TFIDF_TOP_K,
) -> Dict[str, LIRConcept]:
    """Use TF-IDF cosine similarity to find the nearest existing concepts.

    Called when the registry has > _TFIDF_THRESHOLD concepts to avoid
    sending the full registry in the LLM prompt.
    """
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
    except ImportError:
        logger.warning("scikit-learn not installed, falling back to full registry")
        return concepts

    # Build corpus: label is index 0, then each concept's text
    concept_ids = list(concepts.keys())
    corpus = [label.lower()]
    for cid in concept_ids:
        c = concepts[cid]
        text = f"{c.canonical_name} {' '.join(c.aliases)} {c.description}"
        corpus.append(text.lower())

    try:
        vectorizer = TfidfVectorizer(
            max_features=3000,
            stop_words="english",
            ngram_range=(1, 2),
        )
        tfidf_matrix = vectorizer.fit_transform(corpus)
        sims = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:]).flatten()

        # Get top-k indices
        top_indices = sims.argsort()[-top_k:][::-1]
        nearest = {}
        for idx in top_indices:
            if sims[idx] > 0.05:  # Minimum similarity threshold
                cid = concept_ids[idx]
                nearest[cid] = concepts[cid]

        if nearest:
            logger.debug(
                f"TF-IDF pre-filter for '{label}': {len(nearest)} candidates "
                f"(scores: {[f'{sims[i]:.2f}' for i in top_indices[:3]]})"
            )
            return nearest

    except Exception as e:
        logger.warning(f"TF-IDF pre-filter failed: {e}")

    # Fallback: return full registry
    return concepts


def _registry_for_prompt(
    concepts: Dict[str, LIRConcept],
    labels: Optional[List[str]] = None,
) -> dict:
    """Format concept registry for the LLM prompt.

    When the registry is large (> _TFIDF_THRESHOLD) and labels are provided,
    uses TF-IDF pre-filter to send only the nearest concepts per label.
    """
    if len(concepts) <= _TFIDF_THRESHOLD or not labels:
        return {
            cid: {
                "canonical_name": c.canonical_name,
                "aliases": c.aliases,
                "description": c.description,
            }
            for cid, c in concepts.items()
        }

    # Phase 2: TF-IDF pre-filter — collect nearest concepts for all labels
    merged: Dict[str, LIRConcept] = {}
    for label in labels:
        nearest = _tfidf_nearest_concepts(label, concepts)
        merged.update(nearest)

    logger.info(
        f"TF-IDF pre-filter: {len(concepts)} concepts -> "
        f"{len(merged)} candidates for {len(labels)} labels"
    )

    return {
        cid: {
            "canonical_name": c.canonical_name,
            "aliases": c.aliases,
            "description": c.description,
        }
        for cid, c in merged.items()
    }


async def canonicalize_signals(
    signals: List[LIRSignalRecord],
    concepts: Dict[str, LIRConcept],
) -> Tuple[List[LIRSignalRecord], Dict[str, LIRConcept], int]:
    """Link signal concept_labels to canonical concepts.

    For each unique concept label in the signals:
    1. Ask the LLM if it matches an existing concept, is an alias, or is new.
    2. Update the concept registry accordingly.
    3. Set canonical_concept_id on each signal.

    Returns:
        (updated_signals, updated_concepts, new_concept_count)
    """
    if not signals:
        return signals, concepts, 0

    # Collect unique raw labels
    unique_labels = list({s.concept_label for s in signals})
    logger.info(f"Canonicalizing {len(unique_labels)} unique concept labels")

    # Phase 1: LLM adjudication for all labels
    label_to_concept_id: Dict[str, str] = {}
    new_count = 0
    now_iso = datetime.now(timezone.utc).isoformat()

    for batch_start in range(0, len(unique_labels), CANONICALIZATION_BATCH_SIZE):
        batch = unique_labels[batch_start : batch_start + CANONICALIZATION_BATCH_SIZE]
        batch_num = batch_start // CANONICALIZATION_BATCH_SIZE + 1

        logger.info(f"Canonicalization batch {batch_num}: {len(batch)} labels")

        registry = _registry_for_prompt(concepts, labels=batch)
        prompt = lir_canonicalization_prompt(batch, registry)

        try:
            result: LIRCanonicalization = await invoke_llm(
                gpu_model=GPU_LIR_CANON_LLM.model,
                response_schema=LIRCanonicalization,
                contents=prompt,
                port=GPU_LIR_CANON_LLM.port,
            )

            for match in result.matches:
                raw = match.raw_label
                action = match.action.lower().strip()

                if action in ("match", "alias") and match.matched_concept_id:
                    cid = match.matched_concept_id
                    if cid in concepts:
                        label_to_concept_id[raw] = cid
                        # Add alias if it's a new name
                        if action == "alias" and raw not in concepts[cid].aliases:
                            concepts[cid].aliases.append(raw)
                            concepts[cid].updated_at = now_iso
                        logger.debug(f"  '{raw}' -> {action} '{cid}'")
                    else:
                        # Matched concept doesn't exist — treat as new
                        logger.warning(
                            f"  '{raw}' matched non-existent '{cid}', treating as new"
                        )
                        action = "new"

                if action == "new":
                    canonical = match.canonical_name or raw
                    cid = _slugify(canonical)
                    # Avoid ID collision
                    if cid in concepts:
                        cid = f"{cid}-{len(concepts)}"

                    concepts[cid] = LIRConcept(
                        concept_id=cid,
                        canonical_name=canonical,
                        aliases=[raw] if raw.lower() != canonical.lower() else [],
                        description=match.description or "",
                        domain_tags=match.domain_tags or [],
                        created_at=now_iso,
                        updated_at=now_iso,
                    )
                    label_to_concept_id[raw] = cid
                    new_count += 1
                    logger.debug(f"  '{raw}' -> new concept '{cid}' ({canonical})")

        except Exception as e:
            logger.warning(f"Canonicalization batch {batch_num} failed: {e}")
            # Fallback: create new concepts for each label in the failed batch
            for raw in batch:
                cid = _slugify(raw)
                if cid not in concepts:
                    concepts[cid] = LIRConcept(
                        concept_id=cid,
                        canonical_name=raw,
                        description="",
                        domain_tags=[],
                        created_at=now_iso,
                        updated_at=now_iso,
                    )
                    new_count += 1
                label_to_concept_id[raw] = cid

    # Link signals to canonical concepts
    for signal in signals:
        cid = label_to_concept_id.get(signal.concept_label)
        if cid:
            signal.canonical_concept_id = cid
            # Update concept metadata
            if cid in concepts:
                concepts[cid].signal_count += 1
                if signal.tier not in concepts[cid].source_tiers:
                    concepts[cid].source_tiers.append(signal.tier)
                concepts[cid].updated_at = now_iso

    logger.info(
        f"Canonicalization complete: {new_count} new concepts, "
        f"{len(concepts)} total in registry"
    )
    return signals, concepts, new_count
