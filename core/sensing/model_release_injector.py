"""
Inject Artificial Analysis model releases into a generated TechSensing report.

For GenAI-related domains, this stage:
  1. Filters AA model releases against the existing report (dedupes against
     radar items by name).
  2. Web-searches each candidate via DuckDuckGo for context.
  3. Calls the LLM to decide per model whether to include it and to produce
     fully-formed top events, radar items, deep dives, and an optional
     exec-summary mention.
  4. Merges accepted decisions into report.top_events, report.radar_items,
     report.radar_item_details, report.report_sections, and (for prominent
     models) appends a paragraph to report.executive_summary.

Failure here is non-fatal: we log a warning and leave the report unchanged.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from core.constants import GPU_SENSING_REPORT_LLM
from core.llm.client import invoke_llm
from core.llm.output_schemas.sensing_outputs import (
    ModelInjectionOutput,
    ModelRelease,
    ReportSection,
    TechSensingReport,
)
from core.llm.prompts.sensing_prompts import model_release_injection_prompt

logger = logging.getLogger("sensing.model_release_injector")

# Bound LLM cost — at most this many candidates per report.
MAX_CANDIDATES = 15

# Per-model web search results (after dedup of news + text endpoints).
MAX_SNIPPETS_PER_MODEL = 5


def _normalize_name(name: str) -> str:
    """Lowercase + strip non-alphanumeric for fuzzy match."""
    return "".join(ch.lower() for ch in (name or "") if ch.isalnum())


def _is_already_covered(model_name: str, existing_names: List[str]) -> bool:
    """Case-insensitive substring match — covered if model_name's normalized
    form is a substring of any existing radar_item name (or vice versa)."""
    norm = _normalize_name(model_name)
    if not norm:
        return False
    for existing in existing_names:
        e_norm = _normalize_name(existing)
        if not e_norm:
            continue
        if norm == e_norm or norm in e_norm or e_norm in norm:
            return True
    return False


def _filter_candidates(
    releases: List[ModelRelease],
    existing_radar_names: List[str],
) -> List[ModelRelease]:
    """Keep only AA-sourced releases not already covered by radar items.
    Cap to MAX_CANDIDATES, sorted by release_date descending."""
    filtered: List[ModelRelease] = []
    for r in releases:
        if (r.data_source or "") != "Artificial Analysis":
            continue
        if _is_already_covered(r.model_name, existing_radar_names):
            continue
        filtered.append(r)

    filtered.sort(key=lambda r: r.release_date or "", reverse=True)
    return filtered[:MAX_CANDIDATES]


async def _websearch_model(model_name: str, organization: str) -> List[Dict[str, str]]:
    """Run a focused DuckDuckGo search for a single model release.
    Returns up to MAX_SNIPPETS_PER_MODEL deduped {title, url, snippet} dicts."""
    from core.sensing.ingest import _ddgs_news, _ddgs_search

    query = f'"{model_name}" {organization} announcement benchmark'.strip()

    try:
        news_results, text_results = await asyncio.gather(
            asyncio.to_thread(_ddgs_news, query, 5, "m"),
            asyncio.to_thread(_ddgs_search, query, 5, "m"),
            return_exceptions=False,
        )
    except Exception as e:
        logger.debug(f"[ModelInjector] Web search failed for '{model_name}': {e}")
        return []

    snippets: List[Dict[str, str]] = []
    seen_urls: set = set()

    for result in (list(news_results) + list(text_results)):
        url = result.get("url") or result.get("href") or result.get("link") or ""
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        snippets.append({
            "title": result.get("title", "") or "",
            "url": url,
            "snippet": result.get("body") or result.get("snippet") or result.get("excerpt") or "",
        })
        if len(snippets) >= MAX_SNIPPETS_PER_MODEL:
            break

    return snippets


def _build_section_content(
    section_intro: str,
    included_decisions: List[Any],
    candidates_by_name: Dict[str, ModelRelease],
) -> str:
    """Compose the markdown body of the new 'Notable Model Releases' section."""
    lines: List[str] = []
    if section_intro and section_intro.strip():
        lines.append(section_intro.strip())
        lines.append("")

    for d in included_decisions:
        ev = d.top_event
        if not ev:
            continue
        original = candidates_by_name.get(d.model_name)
        org = ev.actor or (original.organization if original else "")
        rel_date = original.release_date if original else ""
        date_str = f", {rel_date}" if rel_date else ""

        line = f"- **{d.model_name}** ({org}{date_str}) — {ev.headline}"
        lines.append(line)
        if ev.recommendation:
            lines.append(f"  - *Recommendation:* {ev.recommendation}")

    return "\n".join(lines).strip()


async def inject_model_releases(
    report: TechSensingReport,
    model_releases: List[ModelRelease],
    domain: str,
    date_range: str,
) -> None:
    """Mutate the report in place by injecting AA-sourced model releases into
    top_events, radar_items, radar_item_details, executive_summary, and
    report_sections. Safe to call on any report — does nothing if no AA
    candidates remain after filtering. Failure is logged and swallowed."""

    if not model_releases:
        logger.info("[ModelInjector] No model releases to inject — skipping")
        return

    existing_radar_names = [r.name for r in (report.radar_items or [])]
    candidates = _filter_candidates(model_releases, existing_radar_names)

    if not candidates:
        logger.info(
            "[ModelInjector] No AA candidates after dedup against radar items — skipping"
        )
        return

    logger.info(
        f"[ModelInjector] {len(candidates)} AA candidates after filtering "
        f"(from {len(model_releases)} total releases)"
    )

    # --- Web search all candidates concurrently ---
    try:
        snippets_per_candidate = await asyncio.gather(
            *(_websearch_model(c.model_name, c.organization) for c in candidates),
            return_exceptions=False,
        )
    except Exception as e:
        logger.warning(f"[ModelInjector] Web search batch failed: {e}")
        snippets_per_candidate = [[] for _ in candidates]

    candidate_dicts: List[Dict[str, Any]] = []
    for c, snippets in zip(candidates, snippets_per_candidate):
        candidate_dicts.append({
            "model_name": c.model_name,
            "organization": c.organization,
            "release_date": c.release_date,
            "modality": c.modality,
            "parameters": c.parameters,
            "license": c.license,
            "is_open_source": c.is_open_source,
            "notable_features": c.notable_features,
            "source_url": c.source_url,
            "web_snippets": snippets,
        })

    # --- Build prompt context from the existing report ---
    existing_radar = [
        {"name": r.name, "quadrant": r.quadrant, "ring": r.ring}
        for r in (report.radar_items or [])
    ]
    existing_events = [
        {"actor": e.actor, "headline": e.headline}
        for e in (report.top_events or [])
    ]
    existing_section_titles = [s.section_title for s in (report.report_sections or [])]

    prompt = model_release_injection_prompt(
        candidates=candidate_dicts,
        existing_radar_items=existing_radar,
        existing_top_events=existing_events,
        existing_section_titles=existing_section_titles,
        executive_summary=report.executive_summary or "",
        domain=domain,
        date_range=date_range,
    )

    # --- LLM call ---
    try:
        result = await invoke_llm(
            gpu_model=GPU_SENSING_REPORT_LLM.model,
            response_schema=ModelInjectionOutput,
            contents=prompt,
            port=GPU_SENSING_REPORT_LLM.port,
        )
        output = ModelInjectionOutput.model_validate(result)
    except Exception as e:
        logger.warning(f"[ModelInjector] LLM call failed: {e}")
        return

    if not output.decisions:
        logger.info("[ModelInjector] LLM returned no decisions — nothing to inject")
        return

    candidates_by_name = {c.model_name: c for c in candidates}
    included = [d for d in output.decisions if (d.decision or "").lower() == "include"]
    skipped = [d for d in output.decisions if (d.decision or "").lower() == "skip"]

    logger.info(
        f"[ModelInjector] LLM included {len(included)} / {len(output.decisions)} "
        f"(skipped {len(skipped)})"
    )

    if not included:
        return

    # --- Merge accepted decisions ---
    if report.top_events is None:
        report.top_events = []
    if report.radar_items is None:
        report.radar_items = []
    if report.radar_item_details is None:
        report.radar_item_details = []
    if report.report_sections is None:
        report.report_sections = []

    appended_events = 0
    appended_radar = 0
    appended_details = 0

    for d in included:
        if d.top_event is not None:
            report.top_events.append(d.top_event)
            appended_events += 1
        if d.radar_item is not None:
            report.radar_items.append(d.radar_item)
            appended_radar += 1
        if d.radar_detail is not None:
            report.radar_item_details.append(d.radar_detail)
            appended_details += 1

    # New report section
    section_content = _build_section_content(
        output.section_intro or "",
        included,
        candidates_by_name,
    )
    if section_content:
        all_source_urls: List[str] = []
        seen: set = set()
        for d in included:
            if d.top_event and d.top_event.source_urls:
                for u in d.top_event.source_urls:
                    if u and u not in seen:
                        seen.add(u)
                        all_source_urls.append(u)

        report.report_sections.append(ReportSection(
            section_title=f"Notable Model Releases ({date_range})",
            content=section_content,
            source_urls=all_source_urls,
        ))

    # Executive summary append for prominent models
    prominent_mentions = [
        d.exec_summary_mention.strip()
        for d in included
        if d.is_prominent and d.exec_summary_mention and d.exec_summary_mention.strip()
    ]
    if prominent_mentions:
        addendum = "\n\n**Notable model releases this period:** " + " ".join(prominent_mentions)
        report.executive_summary = (report.executive_summary or "") + addendum

    logger.info(
        f"[ModelInjector] Merged: {appended_events} top_events, "
        f"{appended_radar} radar_items, {appended_details} radar_details, "
        f"{1 if section_content else 0} report_sections, "
        f"{len(prominent_mentions)} prominent exec-summary mentions"
    )
