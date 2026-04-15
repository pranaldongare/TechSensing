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
from core.sensing.config import DEFAULT_DOMAIN, GENERAL_RSS_FEEDS, LOOKBACK_DAYS, get_feeds_for_domain, get_search_queries_for_domain
from core.sensing.domain_reference import StoredDomainReference, ensure_domain_reference, reference_to_preset
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
from core.sensing.sources.google_patent_search import search_google_patents
from core.sensing.sources.reddit_search import search_reddit
from core.sensing.sources.semantic_scholar import fetch_semantic_scholar
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
    include_videos: bool = False,
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

    # --- Stage 0: Domain Intelligence ---
    logger.info(f"[Stage 0] DOMAIN INTELLIGENCE — generating for '{domain}'... [{_elapsed()}]")
    await _emit("domain_intel", 2, f"Analyzing domain: {domain}...")

    domain_ref = await ensure_domain_reference(
        domain=domain,
        custom_requirements=custom_requirements,
        progress_callback=progress_callback,
    )
    preset = reference_to_preset(domain_ref)

    logger.info(
        f"[Stage 0] DOMAIN INTELLIGENCE COMPLETE: run_count={domain_ref.run_count}, "
        f"feeds={len(domain_ref.rss_feed_urls)}, "
        f"discovered_feeds={len(domain_ref.discovered_rss_feeds)}, "
        f"queries={len(domain_ref.search_queries)}, "
        f"key_people={len(domain_ref.key_people)} [{_elapsed()}]"
    )

    # Default key_people from dynamic domain reference
    if not key_people:
        if domain_ref.key_people:
            key_people = list(domain_ref.key_people)
            logger.info(f"Using dynamic key_people: {key_people}")

    # --- Topic Preferences: boost interested, suppress not-interested ---
    if user_id:
        try:
            from core.sensing.topic_preferences import load_topic_preferences

            topic_prefs = await load_topic_preferences(user_id, domain)
            if topic_prefs.interested:
                boosted = [t for t in topic_prefs.interested if t not in (must_include or [])]
                if boosted:
                    must_include = list(must_include or []) + boosted
                    logger.info(f"Topic prefs: boosted {len(boosted)} interested topics")
            if topic_prefs.not_interested:
                suppressed = [t for t in topic_prefs.not_interested if t not in (dont_include or [])]
                if suppressed:
                    dont_include = list(dont_include or []) + suppressed
                    logger.info(f"Topic prefs: suppressed {len(suppressed)} not-interested topics")
        except Exception as e:
            logger.warning(f"Topic preferences load failed (non-fatal): {e}")

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

    # --- Stage 1: Ingest (all 8 sources in parallel) ---
    logger.info(f"[Stage 1/7] INGEST — launching all sources in parallel... [{_elapsed()}]")
    await _emit("ingest", 10, "Fetching all sources in parallel...")

    effective_feeds = feed_urls or _merge_feeds(domain, domain_ref)
    effective_queries = search_queries or _merge_queries(domain, domain_ref, must_include)
    effective_patent_kw = _merge_patent_keywords(domain_ref, must_include)

    (
        rss_articles,
        ddg_articles,
        github_articles,
        arxiv_articles,
        hn_articles,
        google_patent_articles,
        s2_articles,
        reddit_articles,
    ) = await asyncio.gather(
        fetch_rss_feeds(effective_feeds, lookback_days=lookback_days, domain=domain),
        search_duckduckgo(effective_queries, domain, lookback_days=lookback_days, must_include=must_include),
        fetch_github_trending(domain, lookback_days=lookback_days),
        fetch_arxiv_papers(domain, lookback_days=lookback_days, must_include=must_include),
        fetch_hackernews(domain, lookback_days=lookback_days),
        search_google_patents(domain, lookback_days=max(lookback_days, 365), must_include=effective_patent_kw),
        fetch_semantic_scholar(domain, lookback_days=lookback_days, must_include=must_include),
        search_reddit(domain, lookback_days=lookback_days, must_include=must_include),
    )

    all_raw = (
        rss_articles + ddg_articles + github_articles + arxiv_articles
        + hn_articles + google_patent_articles
        + s2_articles + reddit_articles
    )
    await _emit("ingest", 25, f"Found {len(all_raw)} raw articles from 8 sources")
    logger.info(
        f"[Stage 1/7] INGEST COMPLETE: {len(all_raw)} total raw articles "
        f"(RSS={len(rss_articles)}, DDG={len(ddg_articles)}, "
        f"GitHub={len(github_articles)}, arXiv={len(arxiv_articles)}, "
        f"HN={len(hn_articles)}, GooglePat={len(google_patent_articles)}, "
        f"S2={len(s2_articles)}, Reddit={len(reddit_articles)}) [{_elapsed()}]"
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

    # Date filter: remove articles outside the allowed time window
    before_date_filter = len(unique_articles)
    unique_articles = _filter_by_date(unique_articles, lookback_days)
    if len(unique_articles) < before_date_filter:
        logger.info(
            f"[Stage 2/7] Date filter: {before_date_filter} -> {len(unique_articles)} "
            f"(removed {before_date_filter - len(unique_articles)} old articles)"
        )

    # Load org context early so custom quadrant names are available for classification
    org_context_str = ""
    custom_quadrant_names = None
    stakeholder_role = "general"
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
                if org_ctx.stakeholder_role:
                    stakeholder_role = org_ctx.stakeholder_role
        except Exception as e:
            logger.warning(f"Failed to load org context: {e}")

    # Compute date range early (used by classifier recency rules and report generation)
    now = datetime.now(timezone.utc)
    if lookback_days > 0:
        lookback_start = now - timedelta(days=lookback_days)
        date_range = f"{lookback_start.strftime('%b %d')} - {now.strftime('%b %d, %Y')}"
    else:
        date_range = f"All time (as of {now.strftime('%b %d, %Y')})"

    # --- Stage 3: Classify (using title + snippet + any pre-existing content) ---
    logger.info(
        f"[Stage 3/7] CLASSIFY — classifying {len(unique_articles)} articles via LLM... [{_elapsed()}]"
    )
    await _emit("classify", 35, "Classifying articles with LLM...")
    classified = await classify_articles(
        list(unique_articles), domain=domain, custom_requirements=full_requirements,
        key_people=key_people,
        custom_quadrant_names=custom_quadrant_names,
        preset=preset,
        date_range=date_range,
    )
    await _emit("classify", 55, f"{len(classified)} articles classified")
    logger.info(
        f"[Stage 3/7] CLASSIFY COMPLETE: {len(classified)} classified articles [{_elapsed()}]"
    )

    # --- Stage 4: Extract full text (only for classified articles) ---
    classified_urls = {a.url for a in classified}
    to_extract = [a for a in unique_articles if a.url in classified_urls]
    logger.info(
        f"[Stage 4/7] EXTRACT — extracting full text for {len(to_extract)} classified articles "
        f"(skipped {len(unique_articles) - len(to_extract)} irrelevant) [{_elapsed()}]"
    )
    await _emit("extract", 58, f"Extracting text for {len(to_extract)} relevant articles...")
    sem = asyncio.Semaphore(5)

    async def _extract_with_sem(article: RawArticle) -> RawArticle:
        async with sem:
            return await extract_full_text(article)

    enriched = await asyncio.gather(
        *[_extract_with_sem(a) for a in to_extract]
    )

    content_count = sum(1 for a in enriched if a.content and len(a.content) > 50)
    await _emit("extract", 65, "Text extraction complete")
    logger.info(
        f"[Stage 4/7] EXTRACT COMPLETE: {content_count}/{len(enriched)} with substantial content [{_elapsed()}]"
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

    report = await generate_report(
        classified_articles=classified,
        domain=domain,
        date_range=date_range,
        custom_requirements=full_requirements,
        org_context=org_context_str,
        article_content_map=url_content_map,
        key_people=key_people,
        custom_quadrant_names=custom_quadrant_names,
        preset=preset,
        dynamic_generic_blocklist=set(domain_ref.generic_terms_blocklist),
        dynamic_legacy_blocklist=set(domain_ref.legacy_terms_blocklist),
        stakeholder_role=stakeholder_role,
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
    await _emit("scoring", 94, "Computing signal strengths...")
    report = await compute_signal_strengths(report, classified, user_id=user_id)

    # Technology lifecycle detection
    from core.sensing.lifecycle import detect_lifecycle_stages
    report = detect_lifecycle_stages(report, classified)

    # Report confidence scoring
    report.report_confidence, report.confidence_factors = _compute_report_confidence(
        raw_article_count=len(all_raw),
        deduped_count=len(unique_articles),
        classified_count=len(classified),
        content_extraction_count=content_count,
        source_names=set(a.source for a in unique_articles),
        radar_item_count=len(report.radar_items),
    )
    logger.info(f"Report confidence: {report.report_confidence} [{_elapsed()}]")

    # Funding signal enrichment
    await _emit("funding", 95, "Checking funding signals...")
    try:
        from core.sensing.sources.funding_signals import enrich_with_funding_signals

        tech_names = [item.name for item in report.radar_items[:15]]
        funding_signals = await enrich_with_funding_signals(tech_names, domain)

        funding_map = {s.technology_name.lower(): s for s in funding_signals if s.has_recent_funding}
        for item in report.radar_items:
            signal = funding_map.get(item.name.lower())
            if signal:
                item.funding_signal = signal.funding_summary
                item.signal_strength = min(1.0, item.signal_strength + 0.15)
    except Exception as e:
        logger.warning(f"Funding enrichment failed (non-fatal): {e}")

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
                domain=domain,
                generic_blocklist=set(domain_ref.generic_terms_blocklist),
                legacy_blocklist=set(domain_ref.legacy_terms_blocklist),
            )
            report.weak_signals = weak
            logger.info(f"Weak signals: {len(weak)} detected [{_elapsed()}]")
        except Exception as e:
            logger.warning(f"Weak signal detection failed (non-fatal): {e}")
            report.weak_signals = []

    # --- YouTube Video Enrichment ---
    # YouTube video enrichment (opt-in)
    if include_videos:
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
    else:
        report.trending_videos = []

    # --- Model Releases (GenAI domains only) ---
    if _is_ai_domain(domain):
        logger.info(f"Searching for model releases... [{_elapsed()}]")
        await _emit("model_releases", 99, "Finding recent model releases...")
        try:
            from core.sensing.sources.model_releases import search_model_releases
            from core.sensing.model_release_extractor import extract_model_releases

            mr_articles = await search_model_releases(lookback_days=lookback_days)
            if mr_articles:
                releases = await extract_model_releases(mr_articles, lookback_days=lookback_days)
                report.model_releases = releases
                logger.info(f"Model releases: {len(releases)} found [{_elapsed()}]")
            else:
                report.model_releases = []
        except Exception as e:
            logger.warning(f"Model releases extraction failed (non-fatal): {e}")
            report.model_releases = []

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
        alerts=None,
    )


def _is_ai_domain(domain: str) -> bool:
    """Check if the domain is AI-related (triggers model releases extraction)."""
    d = domain.lower()
    return any(kw in d for kw in ("ai", "generative", "llm", "machine learning", "deep learning"))


def _merge_feeds(domain: str, ref: StoredDomainReference) -> list[str]:
    """Merge dynamic + web-discovered + static domain feeds, deduped.

    Priority order:
    1. LLM-generated feeds (from domain intelligence)
    2. Web-discovered feeds (validated via source discovery)
    3. Static domain-specific feeds (from config.py)
    4. General tech feeds (only if < 5 domain-specific feeds)
    """
    feeds: list[str] = []

    # Start with dynamic LLM-generated feeds (most domain-relevant)
    if ref.rss_feed_urls:
        feeds.extend(ref.rss_feed_urls)

    # Add web-discovered feeds (validated, real sources)
    if ref.discovered_rss_feeds:
        for url in ref.discovered_rss_feeds:
            if url not in feeds:
                feeds.append(url)

    # Add static domain-specific feeds
    static_feeds = get_feeds_for_domain(domain)
    for url in static_feeds:
        if url not in feeds:
            feeds.append(url)

    # Only include general tech feeds if we have very few domain-specific feeds.
    # For specialized domains the general feeds drown out domain content with
    # unrelated GenAI / big-tech noise.
    domain_specific_count = len(feeds)
    if domain_specific_count < 5:
        for url in GENERAL_RSS_FEEDS:
            if url not in feeds:
                feeds.append(url)

    return feeds


def _merge_queries(
    domain: str, ref: StoredDomainReference, must_include: list[str] | None,
) -> list[str]:
    """Merge dynamic + static search queries."""
    queries = list(ref.search_queries) if ref.search_queries else []
    static_queries = get_search_queries_for_domain(domain, must_include)
    for q in static_queries:
        if q not in queries:
            queries.append(q)
    return queries


def _merge_patent_keywords(
    ref: StoredDomainReference, must_include: list[str] | None,
) -> list[str] | None:
    """Merge dynamic patent keywords with user must_include."""
    keywords = list(ref.patent_keywords) if ref.patent_keywords else []
    if must_include:
        for kw in must_include:
            if kw not in keywords:
                keywords.append(kw)
    return keywords or must_include


def _filter_by_date(
    articles: List[RawArticle],
    lookback_days: int,
    buffer_multiplier: float = 2.0,
) -> List[RawArticle]:
    """Remove articles with published_date outside the allowed window.

    Articles with no date or unparseable dates are KEPT (benefit of doubt).
    Buffer multiplier allows 2x the lookback window to account for
    articles published slightly before the range but still relevant.
    """
    if lookback_days <= 0:
        return articles

    cutoff = datetime.now(timezone.utc) - timedelta(
        days=int(lookback_days * buffer_multiplier)
    )
    kept = []
    filtered = 0
    for a in articles:
        if not a.published_date:
            kept.append(a)
            continue
        try:
            pub_dt = datetime.fromisoformat(
                a.published_date.replace("Z", "+00:00")
            )
            if pub_dt.tzinfo is None:
                pub_dt = pub_dt.replace(tzinfo=timezone.utc)
            if pub_dt < cutoff:
                filtered += 1
                continue
        except (ValueError, TypeError):
            pass
        kept.append(a)

    if filtered:
        logger.info(
            f"Date filter: removed {filtered} articles older than "
            f"{int(lookback_days * buffer_multiplier)} days"
        )
    return kept


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


def _compute_report_confidence(
    raw_article_count: int,
    deduped_count: int,
    classified_count: int,
    content_extraction_count: int,
    source_names: set,
    radar_item_count: int,
) -> tuple[str, dict]:
    """Compute overall report confidence score."""
    scores = {}

    # Volume score (0-1)
    if classified_count >= 80:
        scores["article_volume"] = 1.0
    elif classified_count >= 40:
        scores["article_volume"] = 0.7
    elif classified_count >= 15:
        scores["article_volume"] = 0.4
    else:
        scores["article_volume"] = 0.2

    # Source diversity (0-1)
    source_count = len(source_names)
    if source_count >= 6:
        scores["source_diversity"] = 1.0
    elif source_count >= 4:
        scores["source_diversity"] = 0.7
    elif source_count >= 2:
        scores["source_diversity"] = 0.4
    else:
        scores["source_diversity"] = 0.2

    # Content extraction rate (0-1) — based on classified articles only
    if classified_count > 0:
        extraction_rate = content_extraction_count / classified_count
        scores["content_extraction"] = round(min(1.0, extraction_rate * 1.2), 2)
    else:
        scores["content_extraction"] = 0.0

    # Radar coverage (0-1)
    if radar_item_count >= 15:
        scores["radar_coverage"] = 1.0
    elif radar_item_count >= 8:
        scores["radar_coverage"] = 0.7
    elif radar_item_count >= 3:
        scores["radar_coverage"] = 0.4
    else:
        scores["radar_coverage"] = 0.2

    # Weighted average
    weights = {
        "article_volume": 0.3,
        "source_diversity": 0.3,
        "content_extraction": 0.2,
        "radar_coverage": 0.2,
    }
    weighted = sum(scores[k] * weights[k] for k in scores)

    if weighted >= 0.7:
        confidence = "high"
    elif weighted >= 0.4:
        confidence = "medium"
    else:
        confidence = "low"

    factors = {
        **scores,
        "weighted_score": round(weighted, 2),
        "articles_analyzed": classified_count,
        "sources_used": source_count,
        "source_names": sorted(source_names),
    }

    return confidence, factors


async def _extract_document_topics(
    document_text: str,
    domain: str,
    custom_requirements: str = "",
):
    """Use LLM to extract key topics and search queries from document text."""
    from core.constants import GPU_SENSING_CLASSIFY_LLM
    from core.llm.client import invoke_llm
    from core.llm.output_schemas.sensing_outputs import DocumentTopicExtraction
    from core.llm.prompts.sensing_prompts import (
        sensing_document_topic_extraction_prompt,
    )

    prompt = sensing_document_topic_extraction_prompt(
        document_text=document_text,
        domain=domain,
        custom_requirements=custom_requirements,
    )

    result = await invoke_llm(
        gpu_model=GPU_SENSING_CLASSIFY_LLM.model,
        response_schema=DocumentTopicExtraction,
        contents=prompt,
        port=GPU_SENSING_CLASSIFY_LLM.port,
    )

    return DocumentTopicExtraction.model_validate(result)


async def run_sensing_pipeline_from_document(
    file_path: str,
    file_name: str,
    domain: str = DEFAULT_DOMAIN,
    custom_requirements: str = "",
    must_include: Optional[List[str]] = None,
    dont_include: Optional[List[str]] = None,
    lookback_days: int = LOOKBACK_DAYS,
    progress_callback: Optional[Callable] = None,
    user_id: Optional[str] = None,
    key_people: Optional[List[str]] = None,
    include_videos: bool = False,
) -> SensingPipelineResult:
    """Hybrid sensing pipeline: parse an uploaded document, extract key themes
    via LLM, then use those themes to drive the full web search pipeline.

    The document pseudo-articles are combined with web-sourced articles so the
    final report reflects both the document's content and current web
    intelligence.

    Stages: Parse → Extract Topics → Split → Web Ingest → Dedup → Extract
             Text → Classify → Report → Verify → Movement + Scoring.
    """
    start = time.time()

    def _elapsed():
        return f"{time.time() - start:.1f}s"

    async def _emit(stage: str, pct: int, msg: str = ""):
        if progress_callback:
            await progress_callback(stage, pct, msg)

    logger.info(
        f"========== HYBRID DOCUMENT SENSING START "
        f"(file={file_name}, domain={domain}, lookback={lookback_days}d) =========="
    )

    # --- Stage 0: Domain Intelligence ---
    logger.info(f"[Stage 0] DOMAIN INTELLIGENCE — generating for '{domain}'... [{_elapsed()}]")
    await _emit("domain_intel", 2, f"Analyzing domain: {domain}...")

    domain_ref = await ensure_domain_reference(
        domain=domain,
        custom_requirements=custom_requirements,
        progress_callback=progress_callback,
    )
    preset = reference_to_preset(domain_ref)

    logger.info(
        f"[Stage 0] DOMAIN INTELLIGENCE COMPLETE: run_count={domain_ref.run_count}, "
        f"feeds={len(domain_ref.rss_feed_urls)}, "
        f"discovered_feeds={len(domain_ref.discovered_rss_feeds)}, "
        f"queries={len(domain_ref.search_queries)}, "
        f"key_people={len(domain_ref.key_people)} [{_elapsed()}]"
    )

    # Default key_people from dynamic domain reference
    if not key_people:
        if domain_ref.key_people:
            key_people = list(domain_ref.key_people)

    # --- Stage 1: Parse Document ---
    logger.info(
        f"[Stage 1/9] PARSE DOCUMENT — {file_name}... [{_elapsed()}]"
    )
    await _emit("parse", 5, f"Parsing {file_name}...")

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

    await _emit("parse", 10, f"Document parsed ({len(doc.full_text)} chars)")
    logger.info(
        f"[Stage 1/9] PARSE COMPLETE: {len(doc.full_text)} chars [{_elapsed()}]"
    )

    # --- Stage 2: Extract topics from document via LLM ---
    logger.info(f"[Stage 2/9] EXTRACT TOPICS... [{_elapsed()}]")
    await _emit("extract_topics", 10, "Analyzing document themes...")

    effective_search_queries = None
    effective_must_include = list(must_include or [])
    effective_key_people = list(key_people or [])
    doc_context = ""

    try:
        topics = await _extract_document_topics(
            document_text=doc.full_text,
            domain=domain,
            custom_requirements=custom_requirements,
        )
        effective_search_queries = list(topics.search_queries)
        for kw in topics.technology_keywords:
            if kw not in effective_must_include:
                effective_must_include.append(kw)
        for entity in topics.key_entities:
            if entity not in effective_key_people:
                effective_key_people.append(entity)
        search_domain = topics.refined_domain or domain
        doc_context = (
            f"DOCUMENT CONTEXT: This report combines analysis of the uploaded "
            f"document '{file_name}' with current web sources. "
            f"Document summary: {topics.document_summary}\n\n"
        )
        logger.info(
            f"[Stage 2/9] Extracted topics: {len(topics.search_queries)} queries, "
            f"{len(topics.technology_keywords)} keywords, "
            f"{len(topics.key_entities)} entities, "
            f"refined_domain='{search_domain}' [{_elapsed()}]"
        )
    except Exception as e:
        logger.warning(
            f"[Stage 2/9] Topic extraction failed (using defaults): {e}"
        )
        search_domain = domain

    await _emit(
        "extract_topics", 15,
        f"Found {len(effective_must_include)} technology keywords"
    )

    # --- Topic Preferences: boost interested, suppress not-interested ---
    if user_id:
        try:
            from core.sensing.topic_preferences import load_topic_preferences

            topic_prefs = await load_topic_preferences(user_id, domain)
            if topic_prefs.interested:
                for t in topic_prefs.interested:
                    if t not in effective_must_include:
                        effective_must_include.append(t)
            if topic_prefs.not_interested:
                dont_include = list(dont_include or [])
                for t in topic_prefs.not_interested:
                    if t not in dont_include:
                        dont_include.append(t)
        except Exception as e:
            logger.warning(f"Topic preferences load failed (non-fatal): {e}")

    # Build keyword filter instructions
    keyword_instructions = _build_keyword_instructions(
        domain, effective_must_include or None, dont_include
    )
    full_requirements = doc_context + (custom_requirements or "")
    if keyword_instructions:
        full_requirements += f"\n\n{keyword_instructions}"

    # --- Stage 3: Split document into pseudo-articles ---
    logger.info(f"[Stage 3/9] SPLIT — creating pseudo-articles... [{_elapsed()}]")
    await _emit("split", 16, "Splitting document into sections...")

    from core.sensing.document_source import document_to_articles

    pseudo_articles = document_to_articles(
        full_text=doc.full_text,
        file_name=file_name,
        title=file_name,
    )

    # Apply dont_include filter to document sections
    if dont_include:
        dont_lower = [kw.lower() for kw in dont_include]
        pseudo_articles = [
            a for a in pseudo_articles if not _matches_exclusion(a, dont_lower)
        ]

    logger.info(
        f"[Stage 3/9] SPLIT COMPLETE: {len(pseudo_articles)} pseudo-articles [{_elapsed()}]"
    )

    # --- Stage 4: Web Ingest (all 8 sources in parallel, driven by extracted topics) ---
    logger.info(f"[Stage 4/9] WEB INGEST — launching all sources in parallel... [{_elapsed()}]")
    await _emit("ingest", 18, "Fetching all sources in parallel...")

    effective_feeds = _merge_feeds(search_domain, domain_ref)
    effective_patent_kw = _merge_patent_keywords(domain_ref, effective_must_include or None)

    (
        rss_articles,
        ddg_articles,
        github_articles,
        arxiv_articles,
        hn_articles,
        google_patent_articles,
        s2_articles,
        reddit_articles,
    ) = await asyncio.gather(
        fetch_rss_feeds(feed_urls=effective_feeds, lookback_days=lookback_days, domain=search_domain),
        search_duckduckgo(queries=effective_search_queries, domain=search_domain, lookback_days=lookback_days, must_include=effective_must_include or None),
        fetch_github_trending(search_domain, lookback_days=lookback_days),
        fetch_arxiv_papers(search_domain, lookback_days=lookback_days, must_include=effective_must_include or None),
        fetch_hackernews(search_domain, lookback_days=lookback_days),
        search_google_patents(search_domain, lookback_days=max(lookback_days, 365), must_include=effective_patent_kw),
        fetch_semantic_scholar(search_domain, lookback_days=lookback_days, must_include=effective_must_include or None),
        search_reddit(search_domain, lookback_days=lookback_days, must_include=effective_must_include or None),
    )

    all_web = (
        rss_articles + ddg_articles + github_articles + arxiv_articles
        + hn_articles + google_patent_articles
        + s2_articles + reddit_articles
    )
    all_raw = pseudo_articles + all_web

    await _emit(
        "ingest", 33,
        f"{len(pseudo_articles)} document sections + {len(all_web)} web articles"
    )
    logger.info(
        f"[Stage 4/9] WEB INGEST COMPLETE: {len(all_web)} web articles + "
        f"{len(pseudo_articles)} doc sections = {len(all_raw)} total [{_elapsed()}]"
    )

    # --- Stage 5: Dedup ---
    logger.info(f"[Stage 5/9] DEDUP — starting... [{_elapsed()}]")
    await _emit("dedup", 31, "Deduplicating...")
    unique_articles = deduplicate_articles(all_raw)

    if dont_include:
        before_filter = len(unique_articles)
        dont_lower = [kw.lower() for kw in dont_include]
        unique_articles = [
            a for a in unique_articles
            if not _matches_exclusion(a, dont_lower)
        ]
        filtered_out = before_filter - len(unique_articles)
        if filtered_out:
            logger.info(f"[Stage 5/9] Keyword filter removed {filtered_out} articles")

    await _emit("dedup", 35, f"{len(unique_articles)} unique articles")
    logger.info(
        f"[Stage 5/9] DEDUP COMPLETE: {len(all_raw)} -> {len(unique_articles)} unique [{_elapsed()}]"
    )

    # Date filter: remove articles outside the allowed time window
    before_date_filter = len(unique_articles)
    unique_articles = _filter_by_date(unique_articles, lookback_days)
    if len(unique_articles) < before_date_filter:
        logger.info(
            f"[Stage 5/9] Date filter: {before_date_filter} -> {len(unique_articles)} "
            f"(removed {before_date_filter - len(unique_articles)} old articles)"
        )

    # Load org context for custom quadrant names
    org_context_str = ""
    custom_quadrant_names = None
    stakeholder_role = "general"
    if user_id:
        try:
            from core.sensing.org_context import build_org_context_prompt, load_org_context
            org_ctx = await load_org_context(user_id)
            if org_ctx:
                org_context_str = build_org_context_prompt(org_ctx)
                if org_ctx.radar_customization and org_ctx.radar_customization.quadrants:
                    custom_quadrant_names = [
                        q.name for q in org_ctx.radar_customization.quadrants
                    ]
                if org_ctx.stakeholder_role:
                    stakeholder_role = org_ctx.stakeholder_role
        except Exception as e:
            logger.warning(f"Failed to load org context: {e}")

    # Compute date range early (used by classifier recency rules and report generation)
    now = datetime.now(timezone.utc)
    if lookback_days > 0:
        lookback_start = now - timedelta(days=lookback_days)
        date_range = (
            f"Document: {file_name} + Web: "
            f"{lookback_start.strftime('%b %d')} - {now.strftime('%b %d, %Y')}"
        )
    else:
        date_range = f"Document: {file_name} + Web (all time)"

    # --- Stage 6: Classify (using title + snippet + any pre-existing content) ---
    logger.info(
        f"[Stage 6/9] CLASSIFY — {len(unique_articles)} articles via LLM... [{_elapsed()}]"
    )
    await _emit("classify", 38, "Classifying articles with LLM...")
    classified = await classify_articles(
        list(unique_articles), domain=domain, custom_requirements=full_requirements,
        key_people=effective_key_people or None,
        custom_quadrant_names=custom_quadrant_names,
        preset=preset,
        date_range=date_range,
    )
    await _emit("classify", 55, f"{len(classified)} articles classified")
    logger.info(
        f"[Stage 6/9] CLASSIFY COMPLETE: {len(classified)} [{_elapsed()}]"
    )

    # --- Stage 7: Extract full text (only for classified articles) ---
    classified_urls = {a.url for a in classified}
    to_extract = [a for a in unique_articles if a.url in classified_urls]
    logger.info(
        f"[Stage 7/9] EXTRACT — extracting full text for {len(to_extract)} classified articles "
        f"(skipped {len(unique_articles) - len(to_extract)} irrelevant) [{_elapsed()}]"
    )
    await _emit("extract", 58, f"Extracting text for {len(to_extract)} relevant articles...")
    sem = asyncio.Semaphore(5)

    async def _extract_with_sem(article: RawArticle) -> RawArticle:
        async with sem:
            return await extract_full_text(article)

    enriched = await asyncio.gather(
        *[_extract_with_sem(a) for a in to_extract]
    )

    content_count = sum(1 for a in enriched if a.content and len(a.content) > 50)
    await _emit("extract", 65, "Text extraction complete")
    logger.info(
        f"[Stage 7/9] EXTRACT COMPLETE: {content_count}/{len(enriched)} with content [{_elapsed()}]"
    )

    # Build URL→content excerpt map for report grounding
    url_content_map = {
        a.url: (a.content or "")[:800]
        for a in enriched
        if a.url and a.content and len(a.content) > 50
    }

    # --- Stage 8: Generate report ---
    logger.info(f"[Stage 8/9] REPORT — generating... [{_elapsed()}]")
    await _emit("report", 70, "Generating report with LLM...")

    report = await generate_report(
        classified_articles=classified,
        domain=domain,
        date_range=date_range,
        custom_requirements=full_requirements,
        org_context=org_context_str,
        article_content_map=url_content_map,
        key_people=effective_key_people or None,
        custom_quadrant_names=custom_quadrant_names,
        preset=preset,
        dynamic_generic_blocklist=set(domain_ref.generic_terms_blocklist),
        dynamic_legacy_blocklist=set(domain_ref.legacy_terms_blocklist),
        stakeholder_role=stakeholder_role,
    )
    await _emit("report", 85, "Report generated, verifying relevance...")
    logger.info(f"[Stage 8/9] REPORT COMPLETE [{_elapsed()}]")

    # --- Stage 9: Verify + post-processing ---
    logger.info(f"[Stage 9/9] VERIFY... [{_elapsed()}]")
    await _emit("verify", 88, "Verifying report relevance...")
    report = await verify_report(
        report=report,
        domain=domain,
        must_include=effective_must_include or None,
        dont_include=dont_include,
    )
    logger.info(f"[Stage 9/9] VERIFY COMPLETE [{_elapsed()}]")

    # Movement detection
    if user_id:
        await _emit("movement", 92, "Detecting technology movements...")
        report = await detect_radar_movements(
            new_report=report,
            user_id=user_id,
            domain=domain,
        )

    # Signal strength scoring
    await _emit("scoring", 92, "Computing signal strengths...")
    report = await compute_signal_strengths(report, classified, user_id=user_id)

    # Technology lifecycle detection
    from core.sensing.lifecycle import detect_lifecycle_stages
    report = detect_lifecycle_stages(report, classified)

    # Report confidence scoring
    report.report_confidence, report.confidence_factors = _compute_report_confidence(
        raw_article_count=len(all_raw),
        deduped_count=len(unique_articles),
        classified_count=len(classified),
        content_extraction_count=content_count,
        source_names=set(a.source for a in unique_articles),
        radar_item_count=len(report.radar_items),
    )
    logger.info(f"Report confidence: {report.report_confidence} [{_elapsed()}]")

    # Funding signal enrichment
    await _emit("funding", 94, "Checking funding signals...")
    try:
        from core.sensing.sources.funding_signals import enrich_with_funding_signals

        tech_names = [item.name for item in report.radar_items[:15]]
        funding_signals = await enrich_with_funding_signals(tech_names, domain)

        funding_map = {s.technology_name.lower(): s for s in funding_signals if s.has_recent_funding}
        for item in report.radar_items:
            signal = funding_map.get(item.name.lower())
            if signal:
                item.funding_signal = signal.funding_summary
                item.signal_strength = min(1.0, item.signal_strength + 0.15)
    except Exception as e:
        logger.warning(f"Funding enrichment failed (non-fatal): {e}")

    # Technology Relationship Extraction
    if user_id:
        try:
            from core.sensing.relationships import extract_relationships
            rel_map = await extract_relationships(report, classified, domain)
            report.relationships = rel_map
        except Exception as e:
            logger.warning(f"Relationship extraction failed (non-fatal): {e}")

    # Weak signals
    if user_id:
        await _emit("weak_signals", 95, "Detecting emerging signals...")
        try:
            from core.sensing.weak_signals import detect_weak_signals
            weak = await detect_weak_signals(
                report=report,
                classified_articles=classified,
                user_id=user_id,
                domain=domain,
                generic_blocklist=set(domain_ref.generic_terms_blocklist),
                legacy_blocklist=set(domain_ref.legacy_terms_blocklist),
            )
            report.weak_signals = weak
        except Exception as e:
            logger.warning(f"Weak signal detection failed (non-fatal): {e}")
            report.weak_signals = []

    # YouTube video enrichment (opt-in)
    if include_videos:
        await _emit("videos", 98, "Finding trending YouTube videos...")
        try:
            sorted_radar = sorted(
                report.radar_items, key=lambda r: r.signal_strength, reverse=True,
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
        except Exception as e:
            logger.warning(f"YouTube enrichment failed (non-fatal): {e}")
            report.trending_videos = []
    else:
        report.trending_videos = []

    # --- Model Releases (GenAI domains only) ---
    if _is_ai_domain(domain):
        logger.info(f"Searching for model releases... [{_elapsed()}]")
        await _emit("model_releases", 99, "Finding recent model releases...")
        try:
            from core.sensing.sources.model_releases import search_model_releases
            from core.sensing.model_release_extractor import extract_model_releases

            mr_articles = await search_model_releases(lookback_days=lookback_days)
            if mr_articles:
                releases = await extract_model_releases(mr_articles, lookback_days=lookback_days)
                report.model_releases = releases
                logger.info(f"Model releases: {len(releases)} found [{_elapsed()}]")
            else:
                report.model_releases = []
        except Exception as e:
            logger.warning(f"Model releases extraction failed (non-fatal): {e}")
            report.model_releases = []

    await _emit("complete", 100, "Report ready")

    elapsed = time.time() - start
    logger.info(
        f"========== HYBRID DOCUMENT SENSING COMPLETE in {elapsed:.1f}s =========="
    )
    logger.info(
        f"  Doc sections={len(pseudo_articles)} | Web={len(all_web)} | "
        f"Deduped={len(unique_articles)} | Classified={len(classified)} | "
        f"Radar items={len(report.radar_items)}"
    )

    return SensingPipelineResult(
        report=report,
        raw_article_count=len(all_raw),
        deduped_article_count=len(unique_articles),
        classified_article_count=len(classified),
        execution_time_seconds=round(elapsed, 2),
        alerts=None,
    )
