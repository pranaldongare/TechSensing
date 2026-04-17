"""
Company Analysis — on-demand per-company strategic positioning report.

For a given Tech Sensing report, run web searches and LLM synthesis to
produce a CompanyAnalysisReport describing what each requested company is
doing with each selected technology.
"""

import asyncio
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Callable, List, Optional

import aiofiles

from core.constants import GPU_SENSING_COMPANY_ANALYSIS_LLM, SENSING_FEATURES
from core.llm.client import invoke_llm
from core.llm.output_schemas.company_analysis import (
    CompanyAnalysisReport,
    CompanyProfile,
    CompanyTechFinding,
    ComparativeRow,
)
from core.llm.output_schemas.source_evidence import downgrade_single_source
from core.llm.prompts.company_prompts import (
    company_comparative_prompt,
    company_profile_prompt,
)
from core.sensing.ingest import RawArticle, extract_full_text
from core.sensing.run_context import (
    RunContext,
    build_run_context,
    gather_via_providers,
)

logger = logging.getLogger("sensing.company_analysis")


MAX_COMPANIES = 10
MAX_TECHNOLOGIES = 8
TOP_ARTICLES_PER_COMPANY = 10
PER_COMPANY_CONCURRENCY = 3
EXTRACT_CONCURRENCY = 5


async def _load_parent_report(user_id: str, report_tracking_id: str) -> dict:
    """Load the parent Tech Sensing report JSON from disk."""
    report_path = os.path.join(
        "data", user_id, "sensing", f"report_{report_tracking_id}.json"
    )
    if not os.path.exists(report_path):
        raise FileNotFoundError(
            f"Parent report not found: {report_path}"
        )
    async with aiofiles.open(report_path, "r", encoding="utf-8") as f:
        raw = await f.read()
    return json.loads(raw)


def _select_technologies(
    report: dict,
    requested: List[str],
) -> List[str]:
    """Return the final ordered list of technologies to analyze.

    If requested is empty, pick top-MAX_TECHNOLOGIES radar items by
    signal_strength. Otherwise honor requested order, capped at
    MAX_TECHNOLOGIES.
    """
    radar_items = report.get("report", {}).get("radar_items", [])
    radar_names = [r.get("name", "") for r in radar_items if r.get("name")]

    if requested:
        # Honor user order, but filter to names actually in the radar
        # (case-insensitive match) and dedup
        radar_lookup = {n.lower(): n for n in radar_names}
        seen = set()
        selected: List[str] = []
        for name in requested:
            canonical = radar_lookup.get(name.lower(), name)
            key = canonical.lower()
            if key in seen:
                continue
            seen.add(key)
            selected.append(canonical)
            if len(selected) >= MAX_TECHNOLOGIES:
                break
        return selected

    # No request → pick top by signal_strength
    sortable = [
        (r.get("signal_strength", 0.0), r.get("name", ""))
        for r in radar_items
        if r.get("name")
    ]
    sortable.sort(key=lambda t: t[0], reverse=True)
    return [name for _, name in sortable[:MAX_TECHNOLOGIES]]


def _build_queries(company: str, domain: str, technologies: List[str]) -> List[str]:
    """Build DDG queries for one company across its target technologies."""
    queries = [
        f"{company} {tech}" for tech in technologies
    ]
    queries.append(f"{company} {domain} strategy announcements")
    queries.append(f"{company} {domain} latest news")
    return queries


def _dedup_articles(articles: List[RawArticle]) -> List[RawArticle]:
    """Dedup by URL, preserving first-seen order."""
    seen = set()
    unique: List[RawArticle] = []
    for a in articles:
        if not a.url or a.url in seen:
            continue
        seen.add(a.url)
        unique.append(a)
    return unique


async def _gather_articles_for_company(
    ctx: RunContext,
    company: str,
    domain: str,
    technologies: List[str],
) -> List[RawArticle]:
    """Run providers + BYO URLs + exclusions for one company, then extract."""
    # Expand base queries across alias forms.
    aliases = ctx.expand(company)
    queries: List[str] = []
    for alias in aliases:
        queries.extend(_build_queries(alias, domain, technologies))

    results: List[RawArticle] = []
    try:
        batch = await gather_via_providers(
            ctx,
            company,
            queries=queries,
            domain=domain,
            lookback_days=90,
            max_results_per_provider=15,
        )
        results.extend(batch)
    except Exception as e:
        logger.warning(f"[{company}] provider aggregation failed: {e}")

    # BYO URLs — user-curated sources.
    try:
        byo = await ctx.byo_for(company)
        if byo:
            logger.info(f"[{company}] appending {len(byo)} BYO articles")
            results.extend(byo)
    except Exception as e:
        logger.warning(f"[{company}] BYO fetch failed: {e}")

    # Apply exclusions before dedup so we don't extract dropped items.
    results = ctx.filter_exclusions(results, company)

    unique = _dedup_articles(results)[:15]
    logger.info(
        f"[{company}] {len(unique)} unique articles after dedup"
    )

    # Extract full text on top candidates
    sem = asyncio.Semaphore(EXTRACT_CONCURRENCY)

    async def _extract(a: RawArticle) -> RawArticle:
        async with sem:
            try:
                return await extract_full_text(a)
            except Exception as e:
                logger.debug(f"[{company}] extract failed for {a.url}: {e}")
                return a

    enriched = await asyncio.gather(
        *[_extract(a) for a in unique[:TOP_ARTICLES_PER_COMPANY]]
    )
    return enriched


def _articles_to_prompt_text(articles: List[RawArticle]) -> str:
    """Render articles for inclusion in the LLM prompt."""
    parts = []
    for idx, a in enumerate(articles, 1):
        body = (a.content or a.snippet or "")[:2000]
        parts.append(
            f"--- Article {idx} ---\n"
            f"Title: {a.title}\n"
            f"Source: {a.source}\n"
            f"URL: {a.url}\n"
            f"Date: {a.published_date or 'Unknown'}\n"
            f"Content:\n{body}\n"
        )
    return "\n".join(parts)


def _empty_profile(company: str, technologies: List[str]) -> CompanyProfile:
    """Return a profile with 'no visible activity' for every tech."""
    findings = [
        CompanyTechFinding(
            technology=tech,
            summary=f"No evidence found for {company}'s activity in {tech} within the search window.",
            stance="no visible activity",
            confidence=0.0,
        )
        for tech in technologies
    ]
    return CompanyProfile(
        company=company,
        overall_summary=(
            f"No visible activity was surfaced for {company} in this domain "
            "within the searched sources."
        ),
        technology_findings=findings,
        strengths=[],
        gaps=list(technologies),
        sources_used=0,
    )


async def _invoke_with_telemetry(
    ctx: RunContext,
    *,
    label: str,
    response_schema,
    contents: str,
):
    """Route LLM calls through the telemetry collector when available."""
    if ctx.telemetry is not None:
        return await ctx.telemetry.invoke_llm(
            label=label,
            gpu_model=GPU_SENSING_COMPANY_ANALYSIS_LLM.model,
            response_schema=response_schema,
            contents=contents,
            port=GPU_SENSING_COMPANY_ANALYSIS_LLM.port,
        )
    return await invoke_llm(
        gpu_model=GPU_SENSING_COMPANY_ANALYSIS_LLM.model,
        response_schema=response_schema,
        contents=contents,
        port=GPU_SENSING_COMPANY_ANALYSIS_LLM.port,
    )


def _apply_single_source_downgrade(profile: CompanyProfile) -> None:
    """Cap confidence at 0.4 when a finding has ≤1 supporting source (#13)."""
    if not SENSING_FEATURES.get("single_source_downgrade", True):
        return
    for f in profile.technology_findings:
        if len(f.source_urls or []) <= 1 and f.confidence > 0.4:
            f.confidence = 0.4
        if f.evidence:
            f.evidence = downgrade_single_source(f.evidence)


async def _analyze_company(
    ctx: RunContext,
    company: str,
    domain: str,
    technologies: List[str],
    date_range: str,
) -> CompanyProfile:
    """Run search → extract → LLM synthesis for one company."""
    try:
        articles = await _gather_articles_for_company(
            ctx, company, domain, technologies
        )
        useful = [a for a in articles if (a.content or a.snippet)]
        if not useful:
            logger.warning(f"[{company}] no useful articles — empty profile")
            return _empty_profile(company, technologies)

        articles_text = _articles_to_prompt_text(useful)
        prompt = company_profile_prompt(
            company=company,
            domain=domain,
            technologies=technologies,
            articles_text=articles_text,
            date_range=date_range,
        )

        logger.info(
            f"[{company}] invoking LLM with {len(useful)} articles"
        )
        result = await _invoke_with_telemetry(
            ctx,
            label=f"profile:{company}",
            response_schema=CompanyProfile,
            contents=prompt,
        )
        profile = CompanyProfile.model_validate(result)
        # Ensure company name and source count are authoritative
        profile.company = company
        profile.sources_used = len(useful)
        _apply_single_source_downgrade(profile)
        return profile
    except Exception as e:
        logger.error(f"[{company}] analysis failed: {e}")
        return _empty_profile(company, technologies)


def _fallback_comparative_matrix(
    profiles: List[CompanyProfile], technologies: List[str]
) -> List[ComparativeRow]:
    """Pick the highest-confidence company per technology as a fallback."""
    rows: List[ComparativeRow] = []
    for tech in technologies:
        best_company = "Unclear"
        best_conf = -1.0
        best_reason = "No clear leader based on available evidence."
        for p in profiles:
            for f in p.technology_findings:
                if f.technology.lower() == tech.lower() and f.confidence > best_conf:
                    best_conf = f.confidence
                    best_company = p.company
                    best_reason = (
                        f"{p.company} had the strongest evidence "
                        f"(confidence {f.confidence:.1f})."
                    )
        rows.append(
            ComparativeRow(
                technology=tech,
                leader=best_company if best_conf > 0 else "Unclear",
                rationale=best_reason,
            )
        )
    return rows


async def _build_comparative_view(
    ctx: RunContext,
    report_tracking_id: str,
    domain: str,
    companies: List[str],
    technologies: List[str],
    profiles: List[CompanyProfile],
) -> CompanyAnalysisReport:
    """Run the comparative LLM call to produce the final report."""
    profiles_json = json.dumps(
        [p.model_dump() for p in profiles], indent=2, ensure_ascii=False
    )
    prompt = company_comparative_prompt(
        report_tracking_id=report_tracking_id,
        domain=domain,
        companies=companies,
        technologies=technologies,
        profiles_json=profiles_json,
    )

    try:
        result = await _invoke_with_telemetry(
            ctx,
            label="company_analysis:comparative",
            response_schema=CompanyAnalysisReport,
            contents=prompt,
        )
        report = CompanyAnalysisReport.model_validate(result)
        # Enforce invariants
        report.report_tracking_id = report_tracking_id
        report.domain = domain
        report.companies_analyzed = companies
        report.technologies_analyzed = technologies
        # Replace profiles with verbatim source to avoid LLM drift
        report.company_profiles = profiles
        return report
    except Exception as e:
        logger.error(f"Comparative synthesis failed: {e} — using fallback")
        return CompanyAnalysisReport(
            report_tracking_id=report_tracking_id,
            domain=domain,
            companies_analyzed=companies,
            technologies_analyzed=technologies,
            executive_summary=(
                "Comparative synthesis was unavailable. Per-company profiles "
                "are provided below."
            ),
            company_profiles=profiles,
            comparative_matrix=_fallback_comparative_matrix(
                profiles, technologies
            ),
        )


async def run_company_analysis(
    user_id: str,
    company_names: List[str],
    technology_names: List[str],
    report_tracking_id: str = "",
    domain: Optional[str] = None,
    progress_callback: Optional[Callable] = None,
    tracking_id: str = "",
) -> CompanyAnalysisReport:
    """
    Run a company analysis.

    Two modes:
    - Report-linked: ``report_tracking_id`` is provided and a parent Tech
      Sensing report is loaded. ``domain`` and technology filter come from
      the parent when not explicitly overridden.
    - Standalone: ``report_tracking_id`` is empty. Caller must provide
      ``domain`` and ``technology_names`` (technologies are used verbatim,
      capped at ``MAX_TECHNOLOGIES``).

    Stages:
    1. Load parent report (if any) and select technologies
    2. Per-company search + extract (parallel, bounded)
    3. Per-company LLM synthesis (parallel, bounded)
    4. Cross-company comparative LLM call
    """
    start = time.time()

    async def _emit(pct: int, msg: str):
        if progress_callback:
            await progress_callback("company_analysis", pct, msg)

    companies = [c.strip() for c in company_names if c and c.strip()][:MAX_COMPANIES]
    if not companies:
        raise ValueError("At least one company name is required")

    # --- Stage 1: Load & select ---
    if report_tracking_id:
        await _emit(5, "Loading parent report...")
        parent = await _load_parent_report(user_id, report_tracking_id)
        parent_report = parent.get("report", {})
        meta = parent.get("meta", {})

        resolved_domain = (
            domain
            or parent_report.get("domain")
            or meta.get("domain")
            or "Technology"
        )
        date_range = parent_report.get("date_range", "")
        technologies = _select_technologies(parent, technology_names)
        if not technologies:
            raise ValueError(
                "No technologies to analyze — parent report has no radar items"
            )
    else:
        # Standalone mode: caller supplies everything
        await _emit(5, "Preparing standalone analysis...")
        resolved_domain = (domain or "Technology").strip() or "Technology"
        date_range = ""
        technologies = [
            t.strip() for t in (technology_names or []) if t and t.strip()
        ][:MAX_TECHNOLOGIES]
        if not technologies:
            raise ValueError(
                "At least one technology is required for standalone analysis"
            )

    # Use resolved_domain throughout the rest of the flow
    domain = resolved_domain

    tracking_id = (tracking_id or uuid.uuid4().hex).strip()

    logger.info(
        f"Company analysis: {len(companies)} companies x "
        f"{len(technologies)} technologies in domain '{domain}', "
        f"tracking_id={tracking_id}"
    )

    ctx = await build_run_context(
        user_id=user_id,
        tracking_id=tracking_id,
        kind="company_analysis",
    )

    # --- Stage 2 + 3: Per-company search + synthesis (parallel) ---
    await _emit(15, f"Researching {len(companies)} companies...")
    sem = asyncio.Semaphore(PER_COMPANY_CONCURRENCY)
    progress_step = 70 / max(len(companies), 1)
    completed = 0

    async def _run_one(company: str) -> CompanyProfile:
        nonlocal completed
        async with sem:
            profile = await _analyze_company(
                ctx=ctx,
                company=company,
                domain=domain,
                technologies=technologies,
                date_range=date_range,
            )
            completed += 1
            pct = 15 + int(progress_step * completed)
            await _emit(pct, f"Analyzed {company} ({completed}/{len(companies)})")
            return profile

    profiles = await asyncio.gather(*[_run_one(c) for c in companies])

    # --- Stage 4: Comparative synthesis ---
    await _emit(90, "Synthesizing cross-company comparison...")
    report = await _build_comparative_view(
        ctx=ctx,
        report_tracking_id=report_tracking_id,
        domain=domain,
        companies=companies,
        technologies=technologies,
        profiles=list(profiles),
    )

    # --- Stage 5: Phase-3 analytical layers (overlap, themes, investment) ---
    if SENSING_FEATURES.get("overlap_matrix", True):
        try:
            from core.sensing.overlap_matrix import compute_overlap_matrix
            report.overlap_matrix = compute_overlap_matrix(report)
        except Exception as e:
            logger.warning(f"[company_analysis] overlap matrix failed: {e}")

    if SENSING_FEATURES.get("investment_aggregator", True):
        try:
            from core.sensing.investment_aggregator import (
                compute_investment_signals,
            )
            report.investment_signals = compute_investment_signals(report)
        except Exception as e:
            logger.warning(f"[company_analysis] investment aggregate failed: {e}")

    if SENSING_FEATURES.get("strategic_themes", False):
        try:
            await _emit(95, "Extracting strategic themes...")
            from core.sensing.themes import extract_strategic_themes
            report.strategic_themes = await extract_strategic_themes(
                report, ctx=ctx
            )
        except Exception as e:
            logger.warning(f"[company_analysis] themes failed: {e}")

    # Persist telemetry (#28).
    if ctx.telemetry is not None:
        try:
            await ctx.telemetry.save()
        except Exception as e:
            logger.debug(f"telemetry save failed: {e}")

    elapsed = time.time() - start
    await _emit(100, "Company analysis complete")
    logger.info(
        f"Company analysis complete in {elapsed:.1f}s — "
        f"{len(profiles)} profiles, {len(report.comparative_matrix)} "
        f"comparative rows"
    )

    return report


async def save_company_analysis(
    user_id: str,
    tracking_id: str,
    report: CompanyAnalysisReport,
    companies: List[str],
    technologies: List[str],
) -> str:
    """Persist the company analysis report to disk. Returns the file path."""
    sensing_dir = os.path.join("data", user_id, "sensing")
    os.makedirs(sensing_dir, exist_ok=True)
    path = os.path.join(sensing_dir, f"company_analysis_{tracking_id}.json")

    payload = {
        "report": report.model_dump(),
        "meta": {
            "tracking_id": tracking_id,
            "report_tracking_id": report.report_tracking_id,
            "domain": report.domain,
            "companies": companies,
            "technologies": technologies,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    }
    async with aiofiles.open(path, "w", encoding="utf-8") as f:
        await f.write(json.dumps(payload, ensure_ascii=False, indent=2))
    return path
