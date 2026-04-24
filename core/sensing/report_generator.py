"""
Final report generation via LLM.
Takes classified articles and produces the complete TechSensingReport.

Uses a four-phase approach to stay within output token limits:
  Phase 1 (Core):     report_title, executive_summary, headline_moves, key_trends
  Phase 2 (Radar):    radar_items (15-30 entries)
  Phase 3 (Insights): market_signals, report_sections, recommendations, notable_articles
  Phase 4 (Details):  radar_item_details for every radar item (batched, ≤5 per call)

The four phases are merged into the final TechSensingReport.
"""

import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import List

from core.constants import GPU_SENSING_REPORT_LLM
from core.llm.client import invoke_llm
from core.llm.output_schemas.sensing_outputs import (
    ClassifiedArticle,
    HeadlineMove,
    MarketSignal,
    RadarDetailsOutput,
    ReportCore,
    ReportInsights,
    ReportRadar,
    TechSensingReport,
)
from core.llm.prompts.sensing_prompts import (
    sensing_details_prompt,
    sensing_report_core_prompt,
    sensing_report_insights_prompt,
    sensing_report_radar_prompt,
)
from core.sensing.config import get_preset_for_domain

logger = logging.getLogger("sensing.report")


ROLE_PROMPTS = {
    "cto": (
        "AUDIENCE: Chief Technology Officer. "
        "Emphasize strategic implications, competitive positioning, build-vs-buy decisions, "
        "technology bets, organizational readiness, and 12-24 month horizon."
    ),
    "engineering_lead": (
        "AUDIENCE: Engineering Lead / Architect. "
        "Emphasize technical architecture, integration complexity, migration paths, "
        "team skill requirements, and 3-12 month adoption timelines."
    ),
    "developer": (
        "AUDIENCE: Software Developer. "
        "Emphasize getting-started guides, API quality, documentation maturity, "
        "community ecosystem, and practical hands-on evaluation."
    ),
    "product_manager": (
        "AUDIENCE: Product Manager. "
        "Emphasize user impact, market differentiation, competitor adoption, "
        "time-to-value, and feature parity analysis."
    ),
    "general": "",
}


async def generate_report(
    classified_articles: List[ClassifiedArticle],
    domain: str = "Technology",
    date_range: str = "",
    custom_requirements: str = "",
    org_context: str = "",
    article_content_map: dict[str, str] | None = None,
    key_people: list[str] | None = None,
    custom_quadrant_names: list[str] | None = None,
    preset=None,
    dynamic_generic_blocklist: set[str] | None = None,
    dynamic_legacy_blocklist: set[str] | None = None,
    stakeholder_role: str = "general",
) -> TechSensingReport:
    """
    Generate the complete Tech Sensing Report from classified articles.

    Four-phase generation:
      Phase 1 — Core (executive summary, headline moves, key trends)
      Phase 2 — Radar (technology radar entries)
      Phase 3 — Insights (signals, sections, recommendations, notable articles)
      Phase 4 — Details (detailed write-up for each radar item, batched)
    """
    # Inject stakeholder role prompt into custom_requirements
    role_prompt = ROLE_PROMPTS.get(stakeholder_role, "")
    if role_prompt:
        custom_requirements = f"{role_prompt}\n\n{custom_requirements}" if custom_requirements else role_prompt

    # Truncate to top 50 by relevance if too many (avoid context overflow)
    sorted_articles = sorted(
        classified_articles, key=lambda a: a.relevance_score, reverse=True
    )[:50]

    logger.info(
        f"Generating report from {len(sorted_articles)} articles "
        f"(domain={domain}, range={date_range})"
    )

    # Merge content excerpts from extracted articles for grounding
    article_dicts = []
    for a in sorted_articles:
        d = a.model_dump()
        if article_content_map and a.url in article_content_map:
            d["content_excerpt"] = article_content_map[a.url]
        article_dicts.append(d)

    articles_json = json.dumps(
        article_dicts,
        indent=2,
        ensure_ascii=False,
    )
    logger.info(f"Articles JSON payload size: {len(articles_json)} chars")

    if preset is None:
        preset = get_preset_for_domain(domain)

    # ── Phase 1: Core (executive summary, headline moves, key trends) ──
    core_prompt = sensing_report_core_prompt(
        classified_articles_json=articles_json,
        domain=domain,
        date_range=date_range,
        custom_requirements=custom_requirements,
        org_context=org_context,
        key_people=key_people,
        industry_segments_text=preset.industry_segments,
    )

    phase1_start = time.time()
    logger.info("[Phase 1/4] Generating report core...")

    core_result = await invoke_llm(
        gpu_model=GPU_SENSING_REPORT_LLM.model,
        response_schema=ReportCore,
        contents=core_prompt,
        port=GPU_SENSING_REPORT_LLM.port,
    )

    core = ReportCore.model_validate(core_result)
    phase1_time = time.time() - phase1_start

    logger.info(
        f"[Phase 1/4] Core generated in {phase1_time:.1f}s — "
        f"top_events={len(core.top_events)}, trends={len(core.key_trends)}"
    )

    # ── Phase 2: Radar (technology radar entries) ──────────────────────
    core_context = {
        "top_events": [
            {"headline": e.headline, "actor": e.actor, "event_type": e.event_type, "segment": e.segment}
            for e in core.top_events
        ],
        "key_trends": [
            {"trend_name": t.trend_name, "description": t.description}
            for t in core.key_trends
        ],
    }
    core_context_json = json.dumps(core_context, indent=2, ensure_ascii=False)

    radar_prompt = sensing_report_radar_prompt(
        classified_articles_json=articles_json,
        core_context_json=core_context_json,
        domain=domain,
        date_range=date_range,
        custom_quadrant_names=custom_quadrant_names,
        custom_requirements=custom_requirements,
    )

    phase2_start = time.time()
    logger.info("[Phase 2/4] Generating radar items...")

    radar_result = await invoke_llm(
        gpu_model=GPU_SENSING_REPORT_LLM.model,
        response_schema=ReportRadar,
        contents=radar_prompt,
        port=GPU_SENSING_REPORT_LLM.port,
    )

    radar = ReportRadar.model_validate(radar_result)
    phase2_time = time.time() - phase2_start

    logger.info(
        f"[Phase 2/4] Radar generated in {phase2_time:.1f}s — "
        f"radar_items={len(radar.radar_items)}"
    )

    # ── Phase 3: Insights (signals, sections, recommendations) ─────────
    radar_context = [
        {"name": item.name, "quadrant": item.quadrant, "ring": item.ring}
        for item in radar.radar_items
    ]
    radar_context_json = json.dumps(radar_context, indent=2, ensure_ascii=False)

    insights_prompt = sensing_report_insights_prompt(
        classified_articles_json=articles_json,
        core_context_json=core_context_json,
        radar_context_json=radar_context_json,
        domain=domain,
        date_range=date_range,
        custom_requirements=custom_requirements,
        key_people=key_people,
        industry_segments_text=preset.industry_segments,
    )

    phase3_start = time.time()
    logger.info("[Phase 3/4] Generating insights...")

    insights_result = await invoke_llm(
        gpu_model=GPU_SENSING_REPORT_LLM.model,
        response_schema=ReportInsights,
        contents=insights_prompt,
        port=GPU_SENSING_REPORT_LLM.port,
    )

    insights = ReportInsights.model_validate(insights_result)
    phase3_time = time.time() - phase3_start

    logger.info(
        f"[Phase 3/4] Insights generated in {phase3_time:.1f}s — "
        f"sections={len(insights.report_sections)}, "
        f"recommendations={len(insights.recommendations)}, "
        f"blind_spots={len(insights.blind_spots)}"
    )

    # ── Phase 4: Radar item details (batched to avoid output truncation) ─
    DETAILS_BATCH_SIZE = 5
    all_radar_items = list(radar.radar_items)
    batches = [
        all_radar_items[i : i + DETAILS_BATCH_SIZE]
        for i in range(0, len(all_radar_items), DETAILS_BATCH_SIZE)
    ]

    phase4_start = time.time()
    logger.info(
        f"[Phase 4/4] Generating details for {len(all_radar_items)} radar items "
        f"in {len(batches)} batch(es) of ≤{DETAILS_BATCH_SIZE}..."
    )

    all_details = []
    seen_detail_names: set[str] = set()  # Track across batches to prevent duplicates

    for batch_idx, batch in enumerate(batches, 1):
        batch_json = json.dumps(
            [
                {"name": item.name, "quadrant": item.quadrant, "ring": item.ring}
                for item in batch
            ],
            indent=2,
            ensure_ascii=False,
        )

        batch_prompt = sensing_details_prompt(
            radar_items_json=batch_json,
            classified_articles_json=articles_json,
            domain=domain,
            custom_requirements=custom_requirements,
            org_context=org_context,
        )

        logger.info(
            f"[Phase 4/4] Batch {batch_idx}/{len(batches)}: "
            f"{', '.join(item.name for item in batch)}"
        )

        batch_result = await invoke_llm(
            gpu_model=GPU_SENSING_REPORT_LLM.model,
            response_schema=RadarDetailsOutput,
            contents=batch_prompt,
            port=GPU_SENSING_REPORT_LLM.port,
        )

        batch_details = RadarDetailsOutput.model_validate(batch_result)

        # Cross-batch dedup: skip details we've already seen
        for detail in batch_details.radar_item_details:
            norm_name = _normalize_name(detail.technology_name)
            if norm_name in seen_detail_names:
                logger.info(
                    f"[Phase 4/4] Skipping cross-batch duplicate detail: "
                    f"{detail.technology_name}"
                )
                continue
            seen_detail_names.add(norm_name)
            all_details.append(detail)

        logger.info(
            f"[Phase 4/4] Batch {batch_idx}/{len(batches)} done — "
            f"{len(batch_details.radar_item_details)} details"
        )

    details = RadarDetailsOutput(radar_item_details=all_details)
    phase4_time = time.time() - phase4_start

    logger.info(
        f"[Phase 4/4] Details generated in {phase4_time:.1f}s — "
        f"{len(details.radar_item_details)} detail entries across {len(batches)} batches"
    )

    # ── Post-processing: dedup, recency, specificity ─────────────────
    filtered_radar, filtered_details = _postprocess_radar(
        radar.radar_items, details.radar_item_details, classified_articles,
        domain=domain,
        dynamic_generic_blocklist=dynamic_generic_blocklist,
        dynamic_legacy_blocklist=dynamic_legacy_blocklist,
    )
    radar.radar_items = filtered_radar
    details = RadarDetailsOutput(radar_item_details=filtered_details)

    logger.info(
        f"Post-processing: {len(all_radar_items)} -> {len(filtered_radar)} radar items "
        f"after dedup/recency/specificity filtering"
    )

    # ── Link trends to report sections (deep_dive) ──────────────────
    linked_trends = _link_trends_to_sections(
        core.key_trends, insights.report_sections
    )

    # ── Merge into final report ────────────────────────────────────────
    core_data = core.model_dump()
    core_data["key_trends"] = [t.model_dump() for t in linked_trends]
    insights_data = insights.model_dump()

    report = TechSensingReport(
        **core_data,
        **radar.model_dump(),
        **insights_data,
        radar_item_details=details.radar_item_details,
        schema_version="2.0",
    )

    # ── Backfill legacy fields from top_events ────────────────────────
    _backfill_legacy_fields(report)

    total_time = phase1_time + phase2_time + phase3_time + phase4_time
    logger.info(
        f"Report complete in {total_time:.1f}s "
        f"(p1={phase1_time:.1f}s, p2={phase2_time:.1f}s, "
        f"p3={phase3_time:.1f}s, p4={phase4_time:.1f}s) — "
        f"trends={len(report.key_trends)}, radar_items={len(report.radar_items)}, "
        f"details={len(report.radar_item_details)}, recommendations={len(report.recommendations)}"
    )

    return report


# ── Legacy backfill + trend linking helpers ────────────────────────────


def _backfill_legacy_fields(report: TechSensingReport) -> None:
    """Populate legacy headline_moves and market_signals from top_events.

    This ensures old frontends that don't know about top_events still get data.
    """
    if not report.top_events:
        return

    # headline_moves: simple mapping
    if not report.headline_moves:
        report.headline_moves = [
            HeadlineMove(
                headline=e.headline,
                actor=e.actor,
                segment=e.segment,
                source_urls=e.source_urls,
            )
            for e in report.top_events
        ]

    # market_signals: only for events with strategic_intent
    if not report.market_signals:
        report.market_signals = [
            MarketSignal(
                company_or_player=e.actor,
                signal=e.headline,
                strategic_intent=e.strategic_intent or "",
                industry_impact=e.impact_summary or "",
                segment=e.segment,
                related_technologies=e.related_technologies,
                source_urls=e.source_urls,
            )
            for e in report.top_events
            if e.strategic_intent
        ]


def _link_trends_to_sections(trends, sections) -> list:
    """Match report_sections to key_trends by title similarity and populate deep_dive.

    Uses word-overlap heuristic: if a section title shares >50% of words with
    a trend name, the section content becomes that trend's deep_dive.
    """
    if not sections:
        return list(trends)

    linked = list(trends)
    used_sections: set[int] = set()

    for trend in linked:
        trend_words = set(trend.trend_name.lower().split())
        best_idx = -1
        best_overlap = 0.0

        for i, section in enumerate(sections):
            if i in used_sections:
                continue
            section_words = set(section.section_title.lower().split())
            if not trend_words or not section_words:
                continue
            overlap = len(trend_words & section_words) / min(len(trend_words), len(section_words))
            if overlap > best_overlap:
                best_overlap = overlap
                best_idx = i

        if best_idx >= 0 and best_overlap >= 0.5:
            trend.deep_dive = sections[best_idx].content
            used_sections.add(best_idx)

    return linked


# ── Post-processing helpers ────────────────────────────────────────────

# ── Domain-aware blocklists ───────────────────────────────────────────
# Company / org names that should NEVER be standalone radar items,
# regardless of domain.  (The *specific technology* is fine — e.g.,
# "NVIDIA Isaac Sim" is ok but "NVIDIA" alone is not.)
_COMPANY_BLOCKLIST = {
    "openai", "google", "meta", "microsoft", "anthropic", "nvidia",
    "amazon", "apple", "ibm", "intel", "amd", "qualcomm", "tesla",
    "deepmind", "google deepmind", "hugging face", "huggingface",
    "stability ai", "mistral ai", "cohere", "databricks", "snowflake",
    "salesforce", "boston dynamics", "universal robots", "fanuc", "abb",
    "coinbase", "binance",
}

# Overly generic terms that are too broad in ANY domain.
_UNIVERSAL_GENERIC = {
    "technology", "innovation", "software", "hardware", "platform",
    "framework", "ecosystem", "startup", "open source",
}

# Domain-specific generic terms and broad product families.
# Only applied when the domain matches the key.
_DOMAIN_GENERIC: dict[str, set[str]] = {
    "ai": {
        "chatgpt", "gemini", "claude", "copilot", "gpt", "dall-e", "midjourney",
        "artificial intelligence", "machine learning", "deep learning",
        "neural network", "neural networks", "large language model",
        "large language models", "llm", "llms", "generative ai", "gen ai",
        "ai", "ml",
    },
    "cloud": {
        "aws", "azure", "gcp", "google cloud", "cloud computing", "cloud",
        "serverless", "containers",
    },
    "blockchain": {
        "cryptocurrency", "crypto", "blockchain", "web3", "defi",
        "nft", "token",
    },
    "quantum": {
        "quantum computing", "quantum", "qubit",
    },
    "cybersecurity": {
        "cybersecurity", "security", "hacking", "malware",
    },
    "robotics": {
        "robotics", "robot", "automation",
    },
}

# Domain-specific legacy technologies.
# Only applied when the domain matches the key.
_DOMAIN_LEGACY: dict[str, set[str]] = {
    "ai": {
        # Very old models
        "word2vec", "glove", "elmo", "fasttext",
        "bert", "roberta", "albert", "t5",
        # GPT legacy
        "gpt-2", "gpt-3", "gpt2", "gpt3",
        "gpt-3.5", "gpt-3.5-turbo", "gpt3.5",
        "codex", "davinci", "text-davinci-003",
        # Superseded image models
        "stable diffusion 1.5", "stable diffusion 2", "stable diffusion 3",
        "stable diffusion 3.5",
        "dall-e 2", "dalle-2", "dalle 2",
        "midjourney v4", "midjourney v5",
        # Superseded LLMs
        "llama", "llama 2", "llama2",
        "palm", "palm 2", "palm2",
        "claude 2", "claude 2.1", "claude instant",
        "claude sonnet 3.5", "claude sonnet 4", "claude sonnet 4.5",
        "gemini 1.0", "gemini 1.5",
        "gpt-4", "gpt4",
        "whisper",
    },
    "cloud": {
        "mapreduce", "hadoop", "mesos",
    },
    "blockchain": {
        "ethereum 1.0", "bitcoin sv",
    },
}


def _get_generic_blocklist(
    domain: str, dynamic_terms: set[str] | None = None,
) -> set[str]:
    """Build the effective generic blocklist for a given domain."""
    blocklist = _COMPANY_BLOCKLIST | _UNIVERSAL_GENERIC
    domain_lower = domain.lower()
    for key, terms in _DOMAIN_GENERIC.items():
        if key in domain_lower:
            blocklist |= terms
    if dynamic_terms:
        blocklist |= {t.lower() for t in dynamic_terms}
    return blocklist


def _get_legacy_blocklist(
    domain: str, dynamic_terms: set[str] | None = None,
) -> set[str]:
    """Build the effective legacy blocklist for a given domain."""
    legacy: set[str] = set()
    domain_lower = domain.lower()
    for key, terms in _DOMAIN_LEGACY.items():
        if key in domain_lower:
            legacy |= terms
    if dynamic_terms:
        legacy |= {t.lower() for t in dynamic_terms}
    return legacy

_DEDUP_SIMILARITY_THRESHOLD = 0.75


def _normalize_name(name: str) -> str:
    """Lowercase and strip whitespace/punctuation for comparison."""
    return re.sub(r"[^a-z0-9 .]", "", name.lower()).strip()


def _is_duplicate(name_a: str, name_b: str) -> bool:
    """Check if two radar item names are duplicates (fuzzy match)."""
    na, nb = _normalize_name(name_a), _normalize_name(name_b)
    if na == nb:
        return True
    # One is a substring of the other (e.g., "GPT-4" in "GPT-4o")
    if na in nb or nb in na:
        return True
    # Word-overlap check: if two names share >70% of their words, likely duplicate
    # Catches "Vision Language Action Model" vs "Vision-Language-Action Models"
    words_a, words_b = set(na.split()), set(nb.split())
    if words_a and words_b:
        overlap = len(words_a & words_b)
        smaller = min(len(words_a), len(words_b))
        if smaller > 0 and overlap / smaller >= 0.7:
            return True
    return SequenceMatcher(None, na, nb).ratio() >= _DEDUP_SIMILARITY_THRESHOLD


def _is_generic(name: str, blocklist: set[str]) -> bool:
    """Check if a radar item name is a generic/blocked term."""
    return _normalize_name(name) in blocklist


def _is_legacy(name: str, blocklist: set[str]) -> bool:
    """Check if a radar item name refers to a legacy technology."""
    return _normalize_name(name) in blocklist


def _most_recent_mention(
    tech_name: str, classified_articles: list,
) -> str | None:
    """Find the most recent published_date for articles mentioning a technology."""
    norm = _normalize_name(tech_name)
    best_date: str | None = None
    for article in classified_articles:
        article_norm = _normalize_name(article.technology_name)
        # Match if the classified article's technology is the same or contains it
        text = f"{article.title} {article.summary}".lower()
        if article_norm == norm or norm in text:
            if article.published_date and (best_date is None or article.published_date > best_date):
                best_date = article.published_date
    return best_date


def _is_stale(tech_name: str, classified_articles: list, cutoff_days: int = 180) -> bool:
    """Check if a technology's most recent mention is older than cutoff_days.

    Technologies with no datable mentions are considered stale — if none of
    the supporting articles carry a date we cannot verify recency.
    """
    latest = _most_recent_mention(tech_name, classified_articles)
    if not latest:
        return True  # No date evidence — treat as stale
    try:
        # Handle common date formats: "2024-10-15", "2024-10-15T12:00:00Z", etc.
        date_str = latest[:10]  # Take YYYY-MM-DD portion
        pub_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        cutoff = datetime.now(timezone.utc) - timedelta(days=cutoff_days)
        return pub_date < cutoff
    except (ValueError, IndexError):
        return True  # Unparseable date — treat as stale


def _postprocess_radar(radar_items, radar_details, classified_articles,
                       domain: str = "",
                       dynamic_generic_blocklist: set[str] | None = None,
                       dynamic_legacy_blocklist: set[str] | None = None):
    """
    Post-process radar items to remove duplicates, legacy tech, generic items,
    and stale technologies.

    Uses domain-aware blocklists so non-AI domains aren't affected by AI-specific filters.
    Also performs programmatic recency checks using article publication dates.

    Returns (filtered_radar_items, filtered_details).
    """
    generic_blocklist = _get_generic_blocklist(domain, dynamic_generic_blocklist)
    legacy_blocklist = _get_legacy_blocklist(domain, dynamic_legacy_blocklist)

    # Step 1: Remove generic and legacy items
    filtered = []
    removed_generic = []
    removed_legacy = []

    for item in radar_items:
        if _is_generic(item.name, generic_blocklist):
            removed_generic.append(item.name)
            continue
        if _is_legacy(item.name, legacy_blocklist):
            removed_legacy.append(item.name)
            continue
        filtered.append(item)

    if removed_generic:
        logger.info(f"Removed generic radar items: {removed_generic}")
    if removed_legacy:
        logger.info(f"Removed legacy radar items: {removed_legacy}")

    # Step 2: Recency filter — remove items whose most recent article mention
    # is older than 180 days (programmatic enforcement, not just LLM discretion)
    recency_filtered = []
    removed_stale = []

    for item in filtered:
        if _is_stale(item.name, classified_articles, cutoff_days=180):
            removed_stale.append(item.name)
            continue
        recency_filtered.append(item)

    if removed_stale:
        logger.info(f"Removed stale radar items (>180 days old): {removed_stale}")

    # Step 3: Deduplicate — keep the one with higher signal_strength
    deduped = []
    removed_dupes = []

    for item in recency_filtered:
        duplicate_found = False
        for existing in deduped:
            if _is_duplicate(item.name, existing.name):
                # Keep whichever has higher signal_strength
                if item.signal_strength > existing.signal_strength:
                    removed_dupes.append(existing.name)
                    deduped.remove(existing)
                    deduped.append(item)
                else:
                    removed_dupes.append(item.name)
                duplicate_found = True
                break
        if not duplicate_found:
            deduped.append(item)

    if removed_dupes:
        logger.info(f"Removed duplicate radar items: {removed_dupes}")

    # Step 4: Filter details to match surviving radar items
    # Use normalized names for matching to handle whitespace/case differences
    surviving_norm_to_name = {_normalize_name(item.name): item.name for item in deduped}
    surviving_names = set(surviving_norm_to_name.values())

    # Deduplicate details themselves (cross-batch duplicates)
    seen_detail_names: set[str] = set()
    filtered_details = []
    for d in radar_details:
        norm = _normalize_name(d.technology_name)
        # Match via normalized name or exact name
        if d.technology_name in surviving_names or norm in surviving_norm_to_name:
            if norm not in seen_detail_names:
                seen_detail_names.add(norm)
                filtered_details.append(d)
            else:
                logger.debug(f"Removed duplicate detail: {d.technology_name}")

    return deduped, filtered_details
