"""
Tech Sensing Pipeline — orchestrates Ingest -> Dedup -> Extract -> Classify -> Report -> Verify -> Movement.

Main entry point called by the route handler.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, List, Optional

from core.llm.output_schemas.sensing_outputs import TechSensingReport, TrendingVideoItem
from core.sensing.classify import classify_articles
from core.sensing.config import DEFAULT_DOMAIN, LOOKBACK_DAYS, get_preset_for_domain
from core.sensing.dedup import deduplicate_articles
from core.sensing.ingest import (
    RawArticle,
    extract_full_text,
    fetch_rss_feeds,
    search_duckduckgo,
)
from core.sensing.movement import detect_radar_movements
from core.sensing.report_generator import generate_report
from core.sensing.signal_score import compute_signal_strengths
from core.sensing.sources.arxiv_search import fetch_arxiv_papers
from core.sensing.sources.github_trending import fetch_github_trending
from core.sensing.sources.hackernews import fetch_hackernews
from core.sensing.sources.epo_patent_search import search_epo_patents
from core.sensing.sources.patent_search import search_patents
from core.sensing.sources.youtube_videos import fetch_youtube_videos
from core.sensing.verifier import verify_report

logger = logging.getLogger("sensing.pipeline")


@dataclass
class SensingPipelineResult:
    """Result of a complete tech sensing run."""

    report: TechSensingReport
    raw_article_count: int
    deduped_article_count: int
    classified_article_count: int
    execution_time_seconds: float
    alerts: list = None  # List[SensingAlert], default None for compat


async def run_sensing_pipeline(
    domain: str = DEFAULT_DOMAIN,
    custom_requirements: str = "",
    feed_urls: Optional[List[str]] = None,
    search_queries: Optional[List[str]] = None,
    must_include: Optional[List[str]] = None,
    dont_include: Optional[List[str]] = None,
    lookback_days: int = LOOKBACK_DAYS,
    progress_callback: Optional[Callable] = None,
    user_id: Optional[str] = None,
    key_people: Optional[List[str]] = None,
) -> SensingPipelineResult:
    """
    Full tech sensing pipeline execution.

    Args:
        domain: Target domain (e.g., "Generative AI", "Robotics", "Quantum Computing").
        custom_requirements: User-provided additional guidance.
        feed_urls: Override default RSS feeds.
        search_queries: Override default search queries.
        must_include: Keywords that articles should contain (boosts relevance).
        dont_include: Keywords to filter out from results.
        lookback_days: Number of days to look back for articles.
        progress_callback: Async callable(stage, progress_pct, detail_msg).
    """
    start = time.time()

    def _elapsed():
        return f"{time.time() - start:.1f}s"

    async def _emit(stage: str, pct: int, msg: str = ""):
        if progress_callback:
            await progress_callback(stage, pct, msg)

    logger.info(
        f"========== SENSING PIPELINE START (domain={domain}, "
        f"lookback={lookback_days}d, must_include={must_include}, "
        f"dont_include={dont_include}) =========="
    )

    # Default key_people from domain preset when caller doesn't provide any
    if not key_people:
        preset = get_preset_for_domain(domain)
        if preset.key_people:
            key_people = preset.key_people
            logger.info(f"Using default key_people from preset: {key_people}")

    # Build keyword filter instructions for prompts
    keyword_instructions = _build_keyword_instructions(
        domain, must_include, dont_include
    )
    full_requirements = custom_requirements
    if keyword_instructions:
        full_requirements = (
            f"{custom_requirements}\n\n{keyword_instructions}"
            if custom_requirements
            else keyword_instructions
        )

    # --- Stage 1: Ingest ---
    logger.info(f"[Stage 1/7] INGEST — starting RSS feeds... [{_elapsed()}]")
    await _emit("ingest", 10, "Fetching RSS feeds...")
    rss_articles = await fetch_rss_feeds(
        feed_urls, lookback_days=lookback_days, domain=domain
    )
    logger.info(
        f"[Stage 1/7] RSS done: {len(rss_articles)} articles [{_elapsed()}]"
    )

    await _emit("ingest", 18, "Searching DuckDuckGo...")
    logger.info(f"[Stage 1/7] INGEST — starting DuckDuckGo... [{_elapsed()}]")
    ddg_articles = await search_duckduckgo(
        search_queries, domain,
        lookback_days=lookback_days,
        must_include=must_include,
    )
    logger.info(
        f"[Stage 1/7] DDG done: {len(ddg_articles)} articles [{_elapsed()}]"
    )

    # GitHub trending repos
    await _emit("ingest", 19, "Searching GitHub trending...")
    logger.info(f"[Stage 1/7] INGEST — starting GitHub... [{_elapsed()}]")
    github_articles = await fetch_github_trending(domain, lookback_days=lookback_days)
    logger.info(f"[Stage 1/7] GitHub done: {len(github_articles)} repos [{_elapsed()}]")

    # arXiv papers
    await _emit("ingest", 20, "Searching arXiv...")
    logger.info(f"[Stage 1/7] INGEST — starting arXiv... [{_elapsed()}]")
    arxiv_articles = await fetch_arxiv_papers(
        domain, lookback_days=lookback_days, must_include=must_include,
    )
    logger.info(f"[Stage 1/7] arXiv done: {len(arxiv_articles)} papers [{_elapsed()}]")

    # Hacker News
    await _emit("ingest", 21, "Searching Hacker News...")
    logger.info(f"[Stage 1/7] INGEST — starting HN... [{_elapsed()}]")
    hn_articles = await fetch_hackernews(domain, lookback_days=lookback_days)
    logger.info(f"[Stage 1/7] HN done: {len(hn_articles)} stories [{_elapsed()}]")

    # USPTO Patents (longer lookback since patents publish slowly)
    await _emit("ingest", 22, "Searching USPTO patents...")
    logger.info(f"[Stage 1/7] INGEST — starting patent search... [{_elapsed()}]")
    patent_articles = await search_patents(
        domain, lookback_days=max(lookback_days, 365), must_include=must_include,
    )
    logger.info(f"[Stage 1/7] USPTO done: {len(patent_articles)} patents [{_elapsed()}]")

    # EPO Patents (global coverage — complements USPTO)
    await _emit("ingest", 23, "Searching EPO patents...")
    logger.info(f"[Stage 1/7] INGEST — starting EPO patent search... [{_elapsed()}]")
    epo_articles = await search_epo_patents(
        domain, lookback_days=max(lookback_days, 365), must_include=must_include,
    )
    logger.info(f"[Stage 1/7] EPO done: {len(epo_articles)} patents [{_elapsed()}]")

    all_raw = (
        rss_articles + ddg_articles + github_articles + arxiv_articles
        + hn_articles + patent_articles + epo_articles
    )
    await _emit("ingest", 24, f"Found {len(all_raw)} raw articles from 7 sources")
    logger.info(
        f"[Stage 1/7] INGEST COMPLETE: {len(all_raw)} total raw articles "
        f"(RSS={len(rss_articles)}, DDG={len(ddg_articles)}, "
        f"GitHub={len(github_articles)}, arXiv={len(arxiv_articles)}, "
        f"HN={len(hn_articles)}, USPTO={len(patent_articles)}, "
        f"EPO={len(epo_articles)}) [{_elapsed()}]"
    )

    # --- Stage 2: Dedup ---
    logger.info(f"[Stage 2/7] DEDUP — starting... [{_elapsed()}]")
    await _emit("dedup", 25, "Deduplicating...")
    unique_articles = deduplicate_articles(all_raw)

    # Apply dont_include keyword filter
    if dont_include:
        before_filter = len(unique_articles)
        dont_lower = [kw.lower() for kw in dont_include]
        unique_articles = [
            a for a in unique_articles
            if not _matches_exclusion(a, dont_lower)
        ]
        filtered_out = before_filter - len(unique_articles)
        logger.info(
            f"[Stage 2/7] Keyword filter removed {filtered_out} articles "
            f"(dont_include={dont_include})"
        )

    await _emit("dedup", 30, f"{len(unique_articles)} unique articles")
    logger.info(
        f"[Stage 2/7] DEDUP COMPLETE: {len(all_raw)} -> {len(unique_articles)} unique [{_elapsed()}]"
    )

    # --- Stage 3: Extract full text (parallel, throttled) ---
    logger.info(
        f"[Stage 3/7] EXTRACT — extracting full text for {len(unique_articles)} articles... [{_elapsed()}]"
    )
    await _emit("extract", 35, "Extracting article text...")
    sem = asyncio.Semaphore(5)  # Max 5 concurrent HTTP fetches

    async def _extract_with_sem(article: RawArticle) -> RawArticle:
        async with sem:
            return await extract_full_text(article)

    enriched = await asyncio.gather(
        *[_extract_with_sem(a) for a in unique_articles]
    )

    content_count = sum(1 for a in enriched if a.content and len(a.content) > 50)
    await _emit("extract", 45, "Text extraction complete")
    logger.info(
        f"[Stage 3/7] EXTRACT COMPLETE: {content_count}/{len(enriched)} with substantial content [{_elapsed()}]"
    )

    # Load org context early so custom quadrant names are available for classification
    org_context_str = ""
    custom_quadrant_names = None
    if user_id:
        try:
            from core.sensing.org_context import build_org_context_prompt, load_org_context
            org_ctx = await load_org_context(user_id)
            if org_ctx:
                org_context_str = build_org_context_prompt(org_ctx)
                logger.info(f"Org context loaded for {user_id}")
                if org_ctx.radar_customization and org_ctx.radar_customization.quadrants:
                    custom_quadrant_names = [
                        q.name for q in org_ctx.radar_customization.quadrants
                    ]
                    logger.info(f"Custom radar quadrants: {custom_quadrant_names}")
        except Exception as e:
            logger.warning(f"Failed to load org context: {e}")

    # --- Stage 4: Classify ---
    logger.info(
        f"[Stage 4/7] CLASSIFY — classifying {len(enriched)} articles via LLM... [{_elapsed()}]"
    )
    await _emit("classify", 50, "Classifying articles with LLM...")
    classified = await classify_articles(
        list(enriched), domain=domain, custom_requirements=full_requirements,
        key_people=key_people,
        custom_quadrant_names=custom_quadrant_names,
    )
    await _emit("classify", 65, f"{len(classified)} articles classified")
    logger.info(
        f"[Stage 4/7] CLASSIFY COMPLETE: {len(classified)} classified articles [{_elapsed()}]"
    )

    # Build URL→content excerpt map so report LLM gets real article text
    url_content_map = {
        a.url: (a.content or "")[:800]
        for a in enriched
        if a.url and a.content and len(a.content) > 50
    }
    logger.info(f"[Pipeline] Content map: {len(url_content_map)} articles with excerpts")

    # --- Stage 5: Generate report ---
    logger.info(f"[Stage 5/7] REPORT — generating final report via LLM... [{_elapsed()}]")
    await _emit("report", 70, "Generating report with LLM...")
    now = datetime.now(timezone.utc)
    if lookback_days > 0:
        lookback_start = now - timedelta(days=lookback_days)
        date_range = f"{lookback_start.strftime('%b %d')} - {now.strftime('%b %d, %Y')}"
    else:
        date_range = f"All time (as of {now.strftime('%b %d, %Y')})"

    report = await generate_report(
        classified_articles=classified,
        domain=domain,
        date_range=date_range,
        custom_requirements=full_requirements,
        org_context=org_context_str,
        article_content_map=url_content_map,
        key_people=key_people,
        custom_quadrant_names=custom_quadrant_names,
    )
    await _emit("report", 85, "Report generated, verifying relevance...")
    logger.info(
        f"[Stage 5/7] REPORT COMPLETE [{_elapsed()}]"
    )

    # --- Stage 6: Verify relevance ---
    logger.info(
        f"[Stage 6/7] VERIFY — checking report relevance against '{domain}'... [{_elapsed()}]"
    )
    await _emit("verify", 88, "Verifying report relevance...")
    report = await verify_report(
        report=report,
        domain=domain,
        must_include=must_include,
        dont_include=dont_include,
    )
    await _emit("verify", 92, "Verification complete")
    logger.info(f"[Stage 6/7] VERIFY COMPLETE [{_elapsed()}]")

    # --- Stage 7: Movement detection ---
    if user_id:
        logger.info(
            f"[Stage 7/7] MOVEMENT — detecting radar movements... [{_elapsed()}]"
        )
        await _emit("movement", 95, "Detecting technology movements...")
        report = await detect_radar_movements(
            new_report=report,
            user_id=user_id,
            domain=domain,
        )
        logger.info(f"[Stage 7/7] MOVEMENT COMPLETE [{_elapsed()}]")
    else:
        logger.info("[Stage 7/7] MOVEMENT — skipped (no user_id)")

    # Signal strength scoring
    logger.info(f"Computing signal strengths... [{_elapsed()}]")
    await _emit("scoring", 96, "Computing signal strengths...")
    report = compute_signal_strengths(report, classified)

    # --- Technology Relationship Extraction ---
    if user_id:
        logger.info(f"Extracting technology relationships... [{_elapsed()}]")
        await _emit("relationships", 97, "Mapping technology relationships...")
        try:
            from core.sensing.relationships import extract_relationships
            rel_map = await extract_relationships(report, classified, domain)
            report.relationships = rel_map
            logger.info(
                f"Relationships: {len(rel_map.relationships)} edges, "
                f"{len(rel_map.clusters)} clusters [{_elapsed()}]"
            )
        except Exception as e:
            logger.warning(f"Relationship extraction failed (non-fatal): {e}")

    # --- Weak Signal Detection ---
    if user_id:
        logger.info(f"Detecting weak signals... [{_elapsed()}]")
        await _emit("weak_signals", 97, "Detecting emerging signals...")
        try:
            from core.sensing.weak_signals import detect_weak_signals

            weak = await detect_weak_signals(
                report=report,
                classified_articles=classified,
                user_id=user_id,
            )
            report.weak_signals = weak
            logger.info(f"Weak signals: {len(weak)} detected [{_elapsed()}]")
        except Exception as e:
            logger.warning(f"Weak signal detection failed (non-fatal): {e}")
            report.weak_signals = []

    # --- Alert Detection ---
    alerts = []
    if user_id:
        logger.info(f"Detecting alerts... [{_elapsed()}]")
        try:
            from core.sensing.alerts import detect_alerts
            from core.sensing.movement import load_previous_report
            from core.sensing.org_context import load_org_context

            previous_report = await load_previous_report(user_id, domain)
            org_ctx = None
            try:
                org_ctx = await load_org_context(user_id)
            except Exception:
                pass

            alerts = await detect_alerts(
                new_report=report,
                user_id=user_id,
                domain=domain,
                previous_report_data=previous_report,
                org_tech_stack=org_ctx.tech_stack if org_ctx else None,
                weak_signals=getattr(report, "weak_signals", []),
            )
            logger.info(f"Alerts: {len(alerts)} generated [{_elapsed()}]")
        except Exception as e:
            logger.warning(f"Alert detection failed (non-fatal): {e}")

    # --- YouTube Video Enrichment ---
    logger.info(f"Enriching with YouTube videos... [{_elapsed()}]")
    await _emit("videos", 98, "Finding trending YouTube videos...")
    try:
        sorted_radar = sorted(
            report.radar_items,
            key=lambda r: r.signal_strength,
            reverse=True,
        )
        tech_names = [item.name for item in sorted_radar[:10]]

        raw_videos = await fetch_youtube_videos(tech_names)

        report.trending_videos = [
            TrendingVideoItem(
                technology_name=v.technology_name,
                title=v.title,
                url=v.url,
                description=v.description,
                uploader=v.uploader,
                duration=v.duration,
                published=v.published,
                view_count=v.view_count,
                thumbnail_url=v.thumbnail_url,
            )
            for v in raw_videos
        ]
        logger.info(
            f"YouTube enrichment: {len(report.trending_videos)} videos "
            f"for {len(tech_names)} technologies [{_elapsed()}]"
        )
    except Exception as e:
        logger.warning(f"YouTube video enrichment failed (non-fatal): {e}")
        report.trending_videos = []

    await _emit("complete", 100, "Report ready")

    elapsed = time.time() - start
    logger.info(
        f"========== SENSING PIPELINE COMPLETE in {elapsed:.1f}s =========="
    )
    logger.info(
        f"  Raw={len(all_raw)} | Deduped={len(unique_articles)} | "
        f"Classified={len(classified)} | Trends={len(report.key_trends)} | "
        f"Radar items={len(report.radar_items)}"
    )

    return SensingPipelineResult(
        report=report,
        raw_article_count=len(all_raw),
        deduped_article_count=len(unique_articles),
        classified_article_count=len(classified),
        execution_time_seconds=round(elapsed, 2),
        alerts=alerts or None,
    )


def _matches_exclusion(article: RawArticle, dont_lower: list[str]) -> bool:
    """Check if an article matches any exclusion keyword."""
    text = f"{article.title} {article.snippet} {article.content}".lower()
    return any(kw in text for kw in dont_lower)


def _build_keyword_instructions(
    domain: str,
    must_include: list[str] | None,
    dont_include: list[str] | None,
) -> str:
    """Build keyword filter instructions for LLM prompts."""
    parts = []
    if must_include:
        kw_list = ", ".join(must_include)
        parts.append(
            f"MUST INCLUDE: Prioritize articles and technologies related to "
            f"these keywords: {kw_list}. Give higher relevance scores to "
            f"articles mentioning these topics."
        )
    if dont_include:
        kw_list = ", ".join(dont_include)
        parts.append(
            f"DON'T INCLUDE: Exclude or deprioritize articles and technologies "
            f"related to these keywords: {kw_list}. Give low relevance scores "
            f"to articles primarily about these topics."
        )
    return "\n".join(parts)


async def run_sensing_pipeline_from_document(
    file_path: str,
    file_name: str,
    domain: str = DEFAULT_DOMAIN,
    custom_requirements: str = "",
    must_include: Optional[List[str]] = None,
    dont_include: Optional[List[str]] = None,
    progress_callback: Optional[Callable] = None,
    user_id: Optional[str] = None,
) -> SensingPipelineResult:
    """Sensing pipeline variant that uses an uploaded document as the sole
    source.

    Skips the normal ingest stage (RSS / DDG / GitHub / arXiv / HN) and the
    full-text extraction stage — the parsed document IS the source.

    Stages: Parse → Split → Classify → Report → Verify → Movement + Scoring.
    """
    start = time.time()

    def _elapsed():
        return f"{time.time() - start:.1f}s"

    async def _emit(stage: str, pct: int, msg: str = ""):
        if progress_callback:
            await progress_callback(stage, pct, msg)

    logger.info(
        f"========== DOCUMENT SENSING START "
        f"(file={file_name}, domain={domain}) =========="
    )

    keyword_instructions = _build_keyword_instructions(
        domain, must_include, dont_include
    )
    full_requirements = custom_requirements
    if keyword_instructions:
        full_requirements = (
            f"{custom_requirements}\n\n{keyword_instructions}"
            if custom_requirements
            else keyword_instructions
        )

    # --- Stage 1: Parse Document ---
    logger.info(
        f"[Stage 1/6] PARSE DOCUMENT — {file_name}... [{_elapsed()}]"
    )
    await _emit("parse", 10, f"Parsing {file_name}...")

    from core.parsers.main import extract_document

    doc = await extract_document(
        path=file_path,
        title=file_name,
        file_name=file_name,
        user_id=user_id or "sensing",
        thread_id="sensing",
    )

    if not doc or not doc.full_text:
        raise ValueError(f"Failed to parse document: {file_name}")

    await _emit("parse", 20, f"Document parsed ({len(doc.full_text)} chars)")
    logger.info(
        f"[Stage 1/6] PARSE COMPLETE: {len(doc.full_text)} chars [{_elapsed()}]"
    )

    # --- Stage 2: Convert to pseudo-articles ---
    logger.info(
        f"[Stage 2/6] SPLIT — creating pseudo-articles... [{_elapsed()}]"
    )
    await _emit("split", 25, "Splitting document into sections...")

    from core.sensing.document_source import document_to_articles

    pseudo_articles = document_to_articles(
        full_text=doc.full_text,
        file_name=file_name,
        title=file_name,
    )

    # Apply dont_include filter
    if dont_include:
        dont_lower = [kw.lower() for kw in dont_include]
        pseudo_articles = [
            a for a in pseudo_articles if not _matches_exclusion(a, dont_lower)
        ]

    all_raw_count = len(pseudo_articles)
    await _emit("split", 30, f"{all_raw_count} sections created from document")
    logger.info(
        f"[Stage 2/6] SPLIT COMPLETE: {all_raw_count} pseudo-articles "
        f"[{_elapsed()}]"
    )

    # --- Stage 3: Classify ---
    logger.info(
        f"[Stage 3/6] CLASSIFY — {len(pseudo_articles)} sections... "
        f"[{_elapsed()}]"
    )
    await _emit("classify", 40, "Classifying document sections with LLM...")
    classified = await classify_articles(
        list(pseudo_articles),
        domain=domain,
        custom_requirements=full_requirements,
    )
    await _emit("classify", 60, f"{len(classified)} sections classified")
    logger.info(
        f"[Stage 3/6] CLASSIFY COMPLETE: {len(classified)} [{_elapsed()}]"
    )

    # Build content excerpt map
    url_content_map = {
        a.url: (a.content or "")[:800]
        for a in pseudo_articles
        if a.url and a.content
    }

    # --- Stage 4: Generate report ---
    logger.info(f"[Stage 4/6] REPORT — generating... [{_elapsed()}]")
    await _emit("report", 65, "Generating report with LLM...")

    date_range = f"Document: {file_name}"

    org_context_str = ""
    if user_id:
        try:
            from core.sensing.org_context import (
                build_org_context_prompt,
                load_org_context,
            )

            org_ctx = await load_org_context(user_id)
            if org_ctx:
                org_context_str = build_org_context_prompt(org_ctx)
        except Exception as e:
            logger.warning(f"Failed to load org context: {e}")

    report = await generate_report(
        classified_articles=classified,
        domain=domain,
        date_range=date_range,
        custom_requirements=full_requirements,
        org_context=org_context_str,
        article_content_map=url_content_map,
    )
    await _emit("report", 80, "Report generated, verifying...")
    logger.info(f"[Stage 4/6] REPORT COMPLETE [{_elapsed()}]")

    # --- Stage 5: Verify ---
    logger.info(f"[Stage 5/6] VERIFY... [{_elapsed()}]")
    await _emit("verify", 85, "Verifying report relevance...")
    report = await verify_report(
        report=report,
        domain=domain,
        must_include=must_include,
        dont_include=dont_include,
    )
    logger.info(f"[Stage 5/6] VERIFY COMPLETE [{_elapsed()}]")

    # --- Stage 6: Movement detection ---
    if user_id:
        await _emit("movement", 90, "Detecting movements...")
        report = await detect_radar_movements(
            new_report=report,
            user_id=user_id,
            domain=domain,
        )

    # Signal scoring
    report = compute_signal_strengths(report, classified)

    # Weak signals
    if user_id:
        try:
            from core.sensing.weak_signals import detect_weak_signals

            weak = await detect_weak_signals(report, classified, user_id)
            report.weak_signals = weak
        except Exception as e:
            logger.warning(f"Weak signal detection failed (non-fatal): {e}")
            report.weak_signals = []

    # Alert detection
    alerts = []
    if user_id:
        try:
            from core.sensing.alerts import detect_alerts
            from core.sensing.movement import load_previous_report
            from core.sensing.org_context import load_org_context

            previous_report = await load_previous_report(user_id, domain)
            org_ctx = None
            try:
                org_ctx = await load_org_context(user_id)
            except Exception:
                pass

            alerts = await detect_alerts(
                new_report=report,
                user_id=user_id,
                domain=domain,
                previous_report_data=previous_report,
                org_tech_stack=org_ctx.tech_stack if org_ctx else None,
                weak_signals=getattr(report, "weak_signals", []),
            )
        except Exception as e:
            logger.warning(f"Alert detection failed (non-fatal): {e}")

    # No YouTube for document-based runs
    report.trending_videos = []

    await _emit("complete", 100, "Report ready")

    elapsed = time.time() - start
    logger.info(
        f"========== DOCUMENT SENSING COMPLETE in {elapsed:.1f}s =========="
    )

    return SensingPipelineResult(
        report=report,
        raw_article_count=all_raw_count,
        deduped_article_count=all_raw_count,
        classified_article_count=len(classified),
        execution_time_seconds=round(elapsed, 2),
        alerts=alerts or None,
    )
