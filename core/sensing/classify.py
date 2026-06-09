"""
LLM-based article classification for Technology Radar placement.
"""

import json
import logging
import os
import time
from dataclasses import replace
from datetime import datetime, timezone
from typing import List, Optional

from core.constants import GPU_SENSING_CLASSIFY_LLM, SWITCHES
from core.llm.client import invoke_llm, tracking_id_var
from core.llm.configurations.internal_llm import InternalFilterBlockedError
from core.llm.output_schemas.sensing_outputs import (
    ArticleBatchClassification,
    ClassifiedArticle,
)
from core.llm.prompts.sensing_prompts import sensing_classify_prompt
from core.sensing.cache import cache_classification, get_cached_classification
from core.sensing.config import ARTICLE_BATCH_SIZE, MIN_RELEVANCE_SCORE, get_preset_for_domain
from core.sensing.ingest import RawArticle

logger = logging.getLogger("sensing.classify")


def _pick_classify_prompt(china_focus: bool):
    """Return the China-focused classify prompt builder when in China mode,
    otherwise the general one. Kept fully separate for reliability."""
    if china_focus:
        from core.llm.prompts.china_prompts import china_classify_prompt
        return china_classify_prompt
    return sensing_classify_prompt

# When routing through the corporate INTERNAL LLM, large batches occasionally
# trip the content filter (FR-201) — the bigger prompt has more surface area
# for a filter to flag. Drop to 3 articles per batch in that case. The Ollama
# / Gemini / OpenAI paths keep the default ARTICLE_BATCH_SIZE (6).
_INTERNAL_BATCH_SIZE = 3


async def classify_articles(
    articles: List[RawArticle],
    domain: str = "Generative AI",
    custom_requirements: str = "",
    key_people: list[str] | None = None,
    custom_quadrant_names: list[str] | None = None,
    preset=None,
    date_range: str = "",
    china_focus: bool = False,
) -> List[ClassifiedArticle]:
    """
    Classify articles into Technology Radar quadrants/rings via LLM.
    Processes in batches to stay within context window.
    """
    all_classified: List[ClassifiedArticle] = []

    # Check cache for already-classified articles
    uncached_articles: List[RawArticle] = []
    cache_hits = 0
    for article in articles:
        cached = await get_cached_classification(article.url)
        if cached and cached.relevance_score >= MIN_RELEVANCE_SCORE:
            all_classified.append(cached)
            cache_hits += 1
        else:
            uncached_articles.append(article)

    # Hybrid mode: classifier alone goes to GPU even when USE_INTERNAL=true.
    # When on, batch size and cascade revert to the pre-INTERNAL defaults
    # since GPU doesn't have the FR-201 filter.
    bypass_classifier = SWITCHES.get("INTERNAL_BYPASS_CLASSIFIER", False)

    # Effective batch size: smaller when actually going through INTERNAL to
    # reduce filter-block (FR-201) risk; default otherwise (incl. bypass).
    use_internal_for_classifier = (
        SWITCHES.get("USE_INTERNAL", False) and not bypass_classifier
    )
    effective_batch_size = (
        _INTERNAL_BATCH_SIZE if use_internal_for_classifier else ARTICLE_BATCH_SIZE
    )

    # When USE_INTERNAL AND INTERNAL_NO_FALLBACK are both on (and the
    # classifier isn't bypassed to GPU), run through the filter-aware
    # cascade (skip-and-continue + retry + per-article escalation).
    # Otherwise stick with the simple sequential flow.
    use_cascade = (
        use_internal_for_classifier
        and SWITCHES.get("INTERNAL_NO_FALLBACK", False)
    )

    logger.info(
        f"Cache: {cache_hits}/{len(articles)} hits, "
        f"{len(uncached_articles)} articles need LLM classification "
        f"(batch_size={effective_batch_size}, "
        f"USE_INTERNAL={SWITCHES.get('USE_INTERNAL', False)}, "
        f"NO_FALLBACK={SWITCHES.get('INTERNAL_NO_FALLBACK', False)}, "
        f"BYPASS_CLASSIFIER={bypass_classifier}, "
        f"cascade={'ON' if use_cascade else 'OFF'})"
    )

    if preset is None:
        preset = get_preset_for_domain(domain)

    if use_cascade:
        cascade_results = await _classify_with_filter_cascade(
            uncached_articles,
            effective_batch_size,
            domain=domain,
            custom_requirements=custom_requirements,
            key_people=key_people,
            custom_quadrant_names=custom_quadrant_names,
            preset=preset,
            date_range=date_range,
            china_focus=china_focus,
        )
        all_classified.extend(cascade_results)
        logger.info(
            f"Classification complete (cascade): "
            f"{len(all_classified)} total classified articles"
        )
        return all_classified

    total_batches = (len(uncached_articles) + effective_batch_size - 1) // effective_batch_size if uncached_articles else 0

    for i in range(0, len(uncached_articles), effective_batch_size):
        batch_num = i // effective_batch_size + 1
        batch = uncached_articles[i : i + effective_batch_size]
        articles_text = _format_batch_for_prompt(batch)

        prompt = _pick_classify_prompt(china_focus)(
            articles_text=articles_text,
            domain=domain,
            custom_requirements=custom_requirements,
            key_people=key_people,
            topic_categories_text=preset.topic_categories,
            industry_segments_text=preset.industry_segments,
            custom_quadrant_names=custom_quadrant_names,
            date_range=date_range,
        )

        try:
            batch_start = time.time()
            logger.info(
                f"[Batch {batch_num}/{total_batches}] Sending {len(batch)} articles to LLM..."
            )

            result = await invoke_llm(
                gpu_model=GPU_SENSING_CLASSIFY_LLM.model,
                response_schema=ArticleBatchClassification,
                contents=prompt,
                port=GPU_SENSING_CLASSIFY_LLM.port,
                bypass_internal=bypass_classifier,
            )

            validated = ArticleBatchClassification.model_validate(result)
            batch_classified = 0

            for article in validated.articles:
                # Cache every classified article (regardless of score)
                await cache_classification(article)
                if article.relevance_score >= MIN_RELEVANCE_SCORE:
                    all_classified.append(article)
                    batch_classified += 1

            batch_time = time.time() - batch_start
            logger.info(
                f"[Batch {batch_num}/{total_batches}] Done in {batch_time:.1f}s — "
                f"{batch_classified} classified (total so far: {len(all_classified)})"
            )

        except Exception as e:
            logger.error(
                f"[Batch {batch_num}/{total_batches}] FAILED: {e}"
            )
            continue

    logger.info(f"Classification complete: {len(all_classified)} total classified articles")
    return all_classified


def _format_batch_for_prompt(articles: List[RawArticle]) -> str:
    """Format a batch of articles for the classification prompt."""
    parts = []
    for idx, a in enumerate(articles, 1):
        parts.append(
            f"--- Article {idx} ---\n"
            f"Title: {a.title}\n"
            f"Source: {a.source}\n"
            f"URL: {a.url}\n"
            f"Date: {a.published_date or 'Unknown'}\n"
            f"Content:\n{(a.content or a.snippet or a.title)[:2000]}\n"
        )
    return "\n".join(parts)


async def _classify_one_batch(
    batch: List[RawArticle],
    *,
    domain: str,
    custom_requirements: str,
    key_people: Optional[list[str]],
    custom_quadrant_names: Optional[list[str]],
    preset,
    date_range: str,
    china_focus: bool = False,
    label: str = "",
) -> List[ClassifiedArticle]:
    """Send a single batch through ``invoke_llm`` and return the classified
    articles whose relevance clears MIN_RELEVANCE_SCORE.

    Every successfully-classified article is also written to the cache,
    regardless of relevance score.

    Raises:
        InternalFilterBlockedError — propagates straight through so the
            caller (cascade) can defer or split the batch.
        Other exceptions — also propagate; cascade catches generically.
    """
    articles_text = _format_batch_for_prompt(batch)
    prompt = _pick_classify_prompt(china_focus)(
        articles_text=articles_text,
        domain=domain,
        custom_requirements=custom_requirements,
        key_people=key_people,
        topic_categories_text=preset.topic_categories,
        industry_segments_text=preset.industry_segments,
        custom_quadrant_names=custom_quadrant_names,
        date_range=date_range,
    )

    t0 = time.time()
    if label:
        logger.info(f"{label} Sending {len(batch)} article(s) to LLM...")
    result = await invoke_llm(
        gpu_model=GPU_SENSING_CLASSIFY_LLM.model,
        response_schema=ArticleBatchClassification,
        contents=prompt,
        port=GPU_SENSING_CLASSIFY_LLM.port,
    )
    validated = ArticleBatchClassification.model_validate(result)

    out: List[ClassifiedArticle] = []
    for article in validated.articles:
        await cache_classification(article)
        if article.relevance_score >= MIN_RELEVANCE_SCORE:
            out.append(article)
    if label:
        logger.info(
            f"{label} done in {time.time() - t0:.1f}s — "
            f"{len(out)} above relevance threshold"
        )
    return out


def _strip_content(article: RawArticle) -> RawArticle:
    """Return a copy of ``article`` with content+snippet stripped down to
    just the title-derived signal. Used by cascade phase 3b — same
    classifier prompt, but with much less surface for the corporate
    content filter to flag."""
    return replace(
        article,
        content="",
        snippet=(article.title or "")[:200],
    )


def _drops_log_path() -> str:
    """Per-run JSONL file capturing articles dropped by the cascade.

    File is keyed by the request's tracking_id when available so each run
    gets its own log. Falls back to a single file if tracking_id isn't set.
    """
    tracking_id = (tracking_id_var.get("") or "").strip()
    base = os.path.join("DEBUG", "classify_drops")
    os.makedirs(base, exist_ok=True)
    name = f"{tracking_id}.jsonl" if tracking_id else "no_tracking_id.jsonl"
    return os.path.join(base, name)


def _write_drops_log(drops: list[dict]) -> None:
    """Append ``drops`` entries to the per-run drops log."""
    if not drops:
        return
    path = _drops_log_path()
    try:
        with open(path, "a", encoding="utf-8") as f:
            for entry in drops:
                f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        logger.info(
            f"[ClassifyCascade] Wrote {len(drops)} drop record(s) to {path}"
        )
    except Exception as e:
        logger.warning(f"[ClassifyCascade] Failed to write drops log: {e}")


async def _classify_with_filter_cascade(
    uncached: List[RawArticle],
    effective_batch_size: int,
    *,
    domain: str,
    custom_requirements: str,
    key_people: Optional[list[str]],
    custom_quadrant_names: Optional[list[str]],
    preset,
    date_range: str,
    china_focus: bool = False,
) -> List[ClassifiedArticle]:
    """Three-phase classifier that survives INTERNAL content-filter blocks.

    Phase 1: try every batch via INTERNAL exactly once (invoke_llm with
             NO_FALLBACK gives us a single-shot semantics for filter blocks).
             On InternalFilterBlockedError, defer the batch.
    Phase 2: retry the deferred batches once. Many filter blocks are
             idempotent so this rarely helps, but it's a cheap insurance
             pass for transient throttling.
    Phase 3: for each batch that still fails, cascade per-article:
        3a) one-shot single-article INTERNAL call — rescues "innocent"
            articles in a poisoned batch
        3b) content-strip (drop the article.content body, keep just the
            title) and retry — rescues articles whose content trips the
            filter but whose title alone is clean
        3c) drop and log to DEBUG/classify_drops/{tracking_id}.jsonl
    """
    classified: List[ClassifiedArticle] = []
    if not uncached:
        return classified

    # Slice into batches
    batches: List[List[RawArticle]] = [
        uncached[i : i + effective_batch_size]
        for i in range(0, len(uncached), effective_batch_size)
    ]
    total = len(batches)

    # ── Phase 1: skip and continue on filter block ──
    deferred: List[List[RawArticle]] = []
    for idx, batch in enumerate(batches, 1):
        try:
            results = await _classify_one_batch(
                batch,
                domain=domain,
                custom_requirements=custom_requirements,
                key_people=key_people,
                custom_quadrant_names=custom_quadrant_names,
                preset=preset,
                date_range=date_range,
                china_focus=china_focus,
                label=f"[ClassifyCascade Pass 1] batch {idx}/{total}",
            )
            classified.extend(results)
        except InternalFilterBlockedError as e:
            logger.warning(
                f"[ClassifyCascade Pass 1] batch {idx}/{total} "
                f"filter-blocked (resultCode={e.filter_code!r}) — "
                f"deferring {len(batch)} article(s)"
            )
            deferred.append(batch)
        except Exception as e:
            logger.error(
                f"[ClassifyCascade Pass 1] batch {idx}/{total} "
                f"NON-FILTER failure: {type(e).__name__}: {e} — "
                f"deferring {len(batch)} article(s)"
            )
            deferred.append(batch)

    if not deferred:
        logger.info(
            f"[ClassifyCascade] All {total} batches passed in Phase 1 — "
            f"no escalation needed."
        )
        return classified

    # ── Phase 2: one retry per deferred batch ──
    logger.info(
        f"[ClassifyCascade Pass 2] Retrying {len(deferred)} deferred "
        f"batch(es) once..."
    )
    still_failed: List[List[RawArticle]] = []
    for idx, batch in enumerate(deferred, 1):
        try:
            results = await _classify_one_batch(
                batch,
                domain=domain,
                custom_requirements=custom_requirements,
                key_people=key_people,
                custom_quadrant_names=custom_quadrant_names,
                preset=preset,
                date_range=date_range,
                china_focus=china_focus,
                label=f"[ClassifyCascade Pass 2] retry {idx}/{len(deferred)}",
            )
            classified.extend(results)
            logger.info(
                f"[ClassifyCascade Pass 2] retry {idx}/{len(deferred)} "
                f"PASSED on second attempt"
            )
        except (InternalFilterBlockedError, Exception) as e:
            logger.warning(
                f"[ClassifyCascade Pass 2] retry {idx}/{len(deferred)} "
                f"still failing ({type(e).__name__}) — escalating to Phase 3"
            )
            still_failed.append(batch)

    if not still_failed:
        logger.info(
            f"[ClassifyCascade] All deferred batches recovered in Phase 2 — "
            f"no per-article cascade needed."
        )
        return classified

    # ── Phase 3: per-article cascade ──
    drops: list[dict] = []
    now = datetime.now(timezone.utc).isoformat()
    rescued_3a = 0
    rescued_3b = 0
    dropped = 0

    for batch_idx, batch in enumerate(still_failed, 1):
        logger.info(
            f"[ClassifyCascade Pass 3] batch {batch_idx}/{len(still_failed)} "
            f"with {len(batch)} article(s) — running per-article cascade"
        )
        for art_idx, article in enumerate(batch, 1):
            label_prefix = (
                f"[ClassifyCascade Pass 3 batch {batch_idx}/{len(still_failed)} "
                f"article {art_idx}/{len(batch)}]"
            )

            # 3a: single-article INTERNAL call
            try:
                results = await _classify_one_batch(
                    [article],
                    domain=domain,
                    custom_requirements=custom_requirements,
                    key_people=key_people,
                    custom_quadrant_names=custom_quadrant_names,
                    preset=preset,
                    date_range=date_range,
                    china_focus=china_focus,
                    label=f"{label_prefix} 3a (single-article)",
                )
                classified.extend(results)
                rescued_3a += 1
                continue
            except InternalFilterBlockedError as e_3a:
                err_3a = f"3a filter-blocked: code={e_3a.filter_code!r}"
                logger.info(
                    f"{label_prefix} 3a filter-blocked alone — trying 3b "
                    f"(content-strip)"
                )
            except Exception as e_3a:
                err_3a = f"3a {type(e_3a).__name__}: {e_3a}"
                logger.info(
                    f"{label_prefix} 3a failed ({err_3a}) — trying 3b"
                )

            # 3b: content-stripped retry
            try:
                stripped = _strip_content(article)
                results = await _classify_one_batch(
                    [stripped],
                    domain=domain,
                    custom_requirements=custom_requirements,
                    key_people=key_people,
                    custom_quadrant_names=custom_quadrant_names,
                    preset=preset,
                    date_range=date_range,
                    china_focus=china_focus,
                    label=f"{label_prefix} 3b (content-stripped)",
                )
                classified.extend(results)
                rescued_3b += 1
                continue
            except InternalFilterBlockedError as e_3b:
                err_3b = f"3b filter-blocked: code={e_3b.filter_code!r}"
            except Exception as e_3b:
                err_3b = f"3b {type(e_3b).__name__}: {e_3b}"

            # 3c: drop + log
            logger.warning(
                f"{label_prefix} 3c DROPPING article — both single-call "
                f"and content-stripped retries filter-blocked"
            )
            drops.append({
                "timestamp": now,
                "url": article.url,
                "title": article.title,
                "source": article.source,
                "published_date": article.published_date or "",
                "content_len": len(article.content or ""),
                "snippet_len": len(article.snippet or ""),
                "phase_dropped_at": "3c",
                "error_3a": err_3a,
                "error_3b": err_3b,
            })
            dropped += 1

    if drops:
        _write_drops_log(drops)

    logger.info(
        f"[ClassifyCascade] Phase 3 complete — "
        f"rescued via 3a (single-article): {rescued_3a}, "
        f"rescued via 3b (content-strip): {rescued_3b}, "
        f"dropped: {dropped}"
    )
    return classified
