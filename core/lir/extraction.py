"""
LIR signal extraction — batches raw items and sends them through
the LLM to extract forward-looking technology signals.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import List

from core.constants import GPU_LIR_EXTRACT_LLM
from core.lir.config import EXTRACTION_BATCH_SIZE
from core.lir.models import LIRRawItem, LIRSignalRecord
from core.llm.client import invoke_llm
from core.llm.output_schemas.lir_outputs import LIRSignalExtraction
from core.llm.prompts.lir_prompts import lir_extraction_prompt

logger = logging.getLogger("lir.extraction")


def _format_items_for_prompt(items: List[LIRRawItem]) -> str:
    """Format a batch of raw items into a text block for the LLM prompt."""
    parts = []
    for i, item in enumerate(items, 1):
        parts.append(
            f"--- ITEM {i} ---\n"
            f"Title: {item.title}\n"
            f"Source: {item.source_id} ({item.tier})\n"
            f"Date: {item.published_date}\n"
            f"Authors: {item.authors}\n"
            f"Categories: {item.categories}\n"
            f"Content: {item.content[:2000]}\n"
        )
    return "\n".join(parts)


async def extract_signals(
    items: List[LIRRawItem],
    domain: str = "Technology",
) -> List[LIRSignalRecord]:
    """Extract weak signals from raw items using LLM.

    Processes items in batches to stay within context limits.
    Returns LIRSignalRecord instances ready for canonicalization.
    """
    if not items:
        return []

    all_signals: List[LIRSignalRecord] = []
    now_iso = datetime.now(timezone.utc).isoformat()

    # Build item lookup for linking signals back to source items
    item_lookup = {item.item_id: item for item in items}

    # Process in batches
    for batch_start in range(0, len(items), EXTRACTION_BATCH_SIZE):
        batch = items[batch_start : batch_start + EXTRACTION_BATCH_SIZE]
        batch_num = batch_start // EXTRACTION_BATCH_SIZE + 1
        total_batches = (len(items) + EXTRACTION_BATCH_SIZE - 1) // EXTRACTION_BATCH_SIZE

        logger.info(
            f"Extracting signals: batch {batch_num}/{total_batches} "
            f"({len(batch)} items)"
        )

        items_text = _format_items_for_prompt(batch)
        prompt = lir_extraction_prompt(items_text, domain)

        try:
            result: LIRSignalExtraction = await invoke_llm(
                gpu_model=GPU_LIR_EXTRACT_LLM.model,
                response_schema=LIRSignalExtraction,
                contents=prompt,
                port=GPU_LIR_EXTRACT_LLM.port,
            )

            for sig in result.signals:
                # Find the best matching source item for this signal
                source_item = _match_signal_to_item(sig, batch)

                signal_id = f"sig:{uuid.uuid4().hex[:12]}"
                all_signals.append(
                    LIRSignalRecord(
                        signal_id=signal_id,
                        item_id=source_item.item_id if source_item else batch[0].item_id,
                        source_id=source_item.source_id if source_item else batch[0].source_id,
                        tier=source_item.tier if source_item else batch[0].tier,
                        concept_label=sig.concept_label,
                        stated_novelty=max(0.0, min(1.0, sig.stated_novelty)),
                        relevance_score=max(0.0, min(1.0, sig.relevance_score)),
                        summary=sig.summary,
                        evidence_quote=sig.evidence_quote,
                        url=source_item.url if source_item else "",
                        published_date=source_item.published_date if source_item else "",
                        extracted_at=now_iso,
                    )
                )

            logger.info(
                f"Batch {batch_num}: extracted {len(result.signals)} signals"
            )

        except Exception as e:
            logger.warning(f"Extraction batch {batch_num} failed: {e}")
            continue

    logger.info(
        f"Signal extraction complete: {len(all_signals)} signals "
        f"from {len(items)} items"
    )
    return all_signals


def _match_signal_to_item(
    signal,
    batch: List[LIRRawItem],
) -> LIRRawItem | None:
    """Best-effort match an extracted signal back to its source item.

    Uses simple keyword overlap between the signal's evidence_quote
    and item titles/content.
    """
    if len(batch) == 1:
        return batch[0]

    best_item = None
    best_score = 0

    evidence_words = set(signal.evidence_quote.lower().split())
    concept_words = set(signal.concept_label.lower().split())
    search_words = evidence_words | concept_words

    for item in batch:
        item_text = f"{item.title} {item.content}".lower()
        overlap = sum(1 for w in search_words if w in item_text)
        if overlap > best_score:
            best_score = overlap
            best_item = item

    return best_item
