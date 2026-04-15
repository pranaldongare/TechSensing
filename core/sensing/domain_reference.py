"""
Domain Reference — persistent domain intelligence that accumulates across runs.

Storage: data/domain_references/{domain_slug}.json

Each file contains the latest LLM-generated intelligence merged with historical
data, plus metadata about when it was created, last updated, and run count.
"""

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import List, Optional

import aiofiles
from pydantic import BaseModel, Field

from core.llm.output_schemas.sensing_outputs import DomainIntelligence

logger = logging.getLogger("sensing.domain_reference")

DOMAIN_REFERENCES_DIR = "data/domain_references"


# ── Stored reference schema (persisted to disk) ──────────────────────


class StoredDomainReference(BaseModel):
    """Persistent domain reference file stored on disk."""

    # Metadata
    domain_name: str
    domain_slug: str
    created_at: str = Field(description="ISO timestamp of first creation")
    last_updated: str = Field(description="ISO timestamp of most recent update")
    run_count: int = Field(default=0, description="Pipeline runs that updated this")

    # Intelligence data (accumulated across runs)
    domain_summary: str = ""
    topic_categories: List[str] = Field(default_factory=list)
    industry_segments: List[str] = Field(default_factory=list)
    key_people: List[str] = Field(default_factory=list)
    search_queries: List[str] = Field(default_factory=list)
    rss_feed_urls: List[str] = Field(default_factory=list)
    arxiv_categories: List[str] = Field(default_factory=list)
    patent_keywords: List[str] = Field(default_factory=list)
    technology_keywords: List[str] = Field(default_factory=list)
    generic_terms_blocklist: List[str] = Field(default_factory=list)
    legacy_terms_blocklist: List[str] = Field(default_factory=list)

    # Web-discovered sources (populated by source_discovery.py)
    discovered_rss_feeds: List[str] = Field(
        default_factory=list,
        description="RSS feed URLs discovered via web search and validated.",
    )
    discovered_sources_metadata: List[dict] = Field(
        default_factory=list,
        description="Metadata for web-discovered sources (name, type, description).",
    )
    sources_last_discovered: str = Field(
        default="",
        description="ISO timestamp of last source discovery run. Empty = never run.",
    )


# ── Helpers ───────────────────────────────────────────────────────────


def domain_to_slug(domain: str) -> str:
    """Normalize a domain name to a filesystem-safe slug."""
    slug = domain.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", " ", slug)
    slug = re.sub(r"\s+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    slug = slug.strip("-")
    return slug or "unknown-domain"


def _reference_path(domain_slug: str) -> str:
    return os.path.join(DOMAIN_REFERENCES_DIR, f"{domain_slug}.json")


# ── Load / Save ───────────────────────────────────────────────────────


async def load_domain_reference(domain: str) -> Optional[StoredDomainReference]:
    """Load an existing domain reference from disk. Returns None if not found."""
    slug = domain_to_slug(domain)
    fpath = _reference_path(slug)
    if not os.path.exists(fpath):
        return None
    try:
        async with aiofiles.open(fpath, "r", encoding="utf-8") as f:
            data = json.loads(await f.read())
        return StoredDomainReference(**data)
    except Exception as e:
        logger.warning(f"Failed to load domain reference for '{domain}': {e}")
        return None


async def save_domain_reference(ref: StoredDomainReference) -> None:
    """Save a domain reference to disk."""
    fpath = _reference_path(ref.domain_slug)
    os.makedirs(os.path.dirname(fpath), exist_ok=True)
    async with aiofiles.open(fpath, "w", encoding="utf-8") as f:
        await f.write(json.dumps(ref.model_dump(), ensure_ascii=False, indent=2))
    logger.info(
        f"Domain reference saved: {ref.domain_slug} "
        f"(run_count={ref.run_count}, feeds={len(ref.rss_feed_urls)}, "
        f"discovered_feeds={len(ref.discovered_rss_feeds)}, "
        f"queries={len(ref.search_queries)}, people={len(ref.key_people)})"
    )


# ── Merge ─────────────────────────────────────────────────────────────


def merge_intelligence_into_reference(
    existing: Optional[StoredDomainReference],
    new_intel: DomainIntelligence,
    domain: str,
) -> StoredDomainReference:
    """
    Merge newly LLM-generated intelligence into an existing reference.

    Uses a "trust the LLM" strategy: the prompt explicitly told the LLM
    to keep valid existing items and add/remove as needed, so its output
    IS the merged result.  A programmatic union would never remove stale items.
    """
    now = datetime.now(timezone.utc).isoformat()
    slug = domain_to_slug(domain)

    return StoredDomainReference(
        domain_name=new_intel.domain_name or domain,
        domain_slug=slug,
        created_at=existing.created_at if existing else now,
        last_updated=now,
        run_count=(existing.run_count + 1) if existing else 1,
        domain_summary=new_intel.domain_summary,
        topic_categories=new_intel.topic_categories,
        industry_segments=new_intel.industry_segments,
        key_people=new_intel.key_people,
        search_queries=new_intel.search_queries,
        rss_feed_urls=new_intel.rss_feed_urls,
        arxiv_categories=new_intel.arxiv_categories or [],
        patent_keywords=new_intel.patent_keywords,
        technology_keywords=new_intel.technology_keywords,
        generic_terms_blocklist=new_intel.generic_terms_blocklist,
        legacy_terms_blocklist=new_intel.legacy_terms_blocklist,
    )


# ── LLM generation ───────────────────────────────────────────────────


async def generate_domain_intelligence(
    domain: str,
    existing_reference: Optional[StoredDomainReference] = None,
    custom_requirements: str = "",
) -> DomainIntelligence:
    """Call the LLM to generate domain intelligence."""
    from core.constants import GPU_SENSING_CLASSIFY_LLM
    from core.llm.client import invoke_llm
    from core.llm.prompts.sensing_prompts import sensing_domain_intelligence_prompt

    existing_text = ""
    if existing_reference:
        existing_text = json.dumps(
            existing_reference.model_dump(
                exclude={"domain_slug", "created_at", "last_updated", "run_count"}
            ),
            indent=2,
            ensure_ascii=False,
        )

    prompt = sensing_domain_intelligence_prompt(
        domain=domain,
        existing_reference=existing_text,
        custom_requirements=custom_requirements,
    )

    result = await invoke_llm(
        gpu_model=GPU_SENSING_CLASSIFY_LLM.model,
        response_schema=DomainIntelligence,
        contents=prompt,
        port=GPU_SENSING_CLASSIFY_LLM.port,
    )

    return DomainIntelligence.model_validate(result)


# ── Convert to DomainPreset ──────────────────────────────────────────


def reference_to_preset(ref: StoredDomainReference):
    """Convert a StoredDomainReference into a DomainPreset for prompts."""
    from core.sensing.config import DomainPreset

    topic_lines = "\n".join(f"- {cat}" for cat in ref.topic_categories)
    topic_text = f"TOPIC CATEGORY DEFINITIONS:\n{topic_lines}\n"

    segment_lines = "\n".join(f"- {seg}" for seg in ref.industry_segments)
    segment_text = (
        "INDUSTRY SEGMENTS (use these for headline_moves and market_signals):\n"
        f"{segment_lines}\n"
    )

    return DomainPreset(
        topic_categories=topic_text,
        industry_segments=segment_text,
        key_people=list(ref.key_people),
    )


# ── Static fallback ──────────────────────────────────────────────────


def _build_static_fallback(domain: str) -> StoredDomainReference:
    """
    Build a minimal StoredDomainReference from static config.py data.
    Used when both LLM call and existing reference are unavailable.
    """
    from core.sensing.config import (
        get_feeds_for_domain,
        get_patent_queries_for_domain,
        get_preset_for_domain,
        get_search_queries_for_domain,
    )

    preset = get_preset_for_domain(domain)
    slug = domain_to_slug(domain)
    now = datetime.now(timezone.utc).isoformat()

    topic_lines = [
        line.strip("- ").strip()
        for line in preset.topic_categories.split("\n")
        if line.strip().startswith("-")
    ]
    segment_lines = [
        line.strip("- ").strip()
        for line in preset.industry_segments.split("\n")
        if line.strip().startswith("-")
    ]

    return StoredDomainReference(
        domain_name=domain,
        domain_slug=slug,
        created_at=now,
        last_updated=now,
        run_count=0,
        domain_summary=f"Static fallback configuration for {domain}.",
        topic_categories=topic_lines,
        industry_segments=segment_lines,
        key_people=preset.key_people,
        search_queries=get_search_queries_for_domain(domain),
        rss_feed_urls=get_feeds_for_domain(domain),
        arxiv_categories=[],
        patent_keywords=get_patent_queries_for_domain(domain),
        technology_keywords=[],
        generic_terms_blocklist=[],
        legacy_terms_blocklist=[],
    )


# ── Top-level orchestrator ────────────────────────────────────────────


async def ensure_domain_reference(
    domain: str,
    custom_requirements: str = "",
    progress_callback=None,
) -> StoredDomainReference:
    """
    Stage 0 entry point called by both pipelines.

    1. Load existing reference (if any)
    2. Call LLM to generate/update domain intelligence
    3. Merge into stored reference
    4. Save to disk
    5. Return the reference for use by the pipeline

    On LLM failure, falls back to existing reference or static config.
    """
    async def _emit(msg: str):
        if progress_callback:
            await progress_callback("domain_intel", 3, msg)

    await _emit(f"Loading domain intelligence for '{domain}'...")

    existing = await load_domain_reference(domain)
    if existing:
        logger.info(
            f"Loaded existing domain reference: {existing.domain_slug} "
            f"(run_count={existing.run_count}, last_updated={existing.last_updated})"
        )

    try:
        await _emit("Generating domain intelligence via LLM...")
        new_intel = await generate_domain_intelligence(
            domain=domain,
            existing_reference=existing,
            custom_requirements=custom_requirements,
        )
        logger.info(
            f"LLM domain intelligence generated: "
            f"{len(new_intel.search_queries)} queries, "
            f"{len(new_intel.rss_feed_urls)} feeds, "
            f"{len(new_intel.key_people)} key people"
        )

        merged = merge_intelligence_into_reference(existing, new_intel, domain)

    except Exception as e:
        logger.error(f"Domain intelligence generation failed: {e}")
        await _emit("Domain intelligence LLM failed, using fallback...")

        if existing:
            logger.info("Falling back to existing domain reference")
            merged = existing
        else:
            logger.info("No existing reference; building from static config")
            merged = _build_static_fallback(domain)

    # --- Source Discovery (web-powered, runs on TTL expiry only) ---
    try:
        from core.sensing.source_discovery import (
            discover_domain_sources,
            should_rediscover_sources,
        )

        # Carry forward existing discovered sources
        if existing and existing.discovered_rss_feeds:
            merged.discovered_rss_feeds = list(existing.discovered_rss_feeds)
            merged.discovered_sources_metadata = list(
                existing.discovered_sources_metadata
            )
            merged.sources_last_discovered = existing.sources_last_discovered

        if should_rediscover_sources(merged.sources_last_discovered):
            await _emit("Discovering domain sources via web search...")
            logger.info(
                f"[Source Discovery] Running for '{domain}' "
                "(TTL expired or first run)"
            )

            all_known_feeds = list(set(
                merged.rss_feed_urls + merged.discovered_rss_feeds
            ))

            sources, validated_feeds = await discover_domain_sources(
                domain=domain,
                domain_summary=merged.domain_summary,
                existing_feeds=all_known_feeds,
                progress_callback=progress_callback,
            )

            merged.discovered_rss_feeds = validated_feeds
            merged.discovered_sources_metadata = [
                s.model_dump() for s in sources
            ]
            merged.sources_last_discovered = (
                datetime.now(timezone.utc).isoformat()
            )
            logger.info(
                f"[Source Discovery] Complete: {len(validated_feeds)} feeds, "
                f"{len(sources)} sources discovered"
            )
        else:
            logger.info(
                f"[Source Discovery] Skipped (last discovered: "
                f"{merged.sources_last_discovered})"
            )

    except Exception as e:
        logger.warning(f"[Source Discovery] Failed (non-fatal): {e}")
        # Carry forward existing discovered sources on failure
        if existing and existing.discovered_rss_feeds:
            merged.discovered_rss_feeds = list(existing.discovered_rss_feeds)
            merged.discovered_sources_metadata = list(
                existing.discovered_sources_metadata
            )
            merged.sources_last_discovered = existing.sources_last_discovered

    await save_domain_reference(merged)
    await _emit("Domain intelligence ready")
    return merged
