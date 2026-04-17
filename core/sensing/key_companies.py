"""
Key Companies — on-demand weekly cross-domain briefings for user-selected
companies.

Unlike Company Analysis (which is anchored to a Tech Sensing report and its
radar items), Key Companies is domain-agnostic: the user provides only a
list of company names plus an optional "highlight domain". For each
company we run web search over the last 7 days, extract top articles, and
synthesize a structured weekly briefing of technical and business updates.
"""

import asyncio
import json
import logging
import os
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable, List, Optional, Set

import aiofiles

from core.constants import GPU_SENSING_COMPANY_ANALYSIS_LLM, SENSING_FEATURES
from core.llm.client import invoke_llm
from core.llm.output_schemas.key_companies import (
    CompanyBriefing,
    CompanyUpdate,
    KeyCompaniesReport,
    UPDATE_CATEGORIES,
)
from core.llm.output_schemas.source_evidence import downgrade_single_source
from core.llm.prompts.key_company_prompts import (
    company_weekly_brief_prompt,
    key_companies_cross_prompt,
)
from core.sensing.cross_domain import compute_domain_rollup
from core.sensing.date_filter import filter_articles_by_date
from core.sensing.ingest import RawArticle, extract_full_text
from core.sensing.momentum import compute_momentum
from core.sensing.run_context import (
    RunContext,
    build_run_context,
    gather_via_providers,
)
from core.sensing.sentiment import score_update

logger = logging.getLogger("sensing.key_companies")


MAX_COMPANIES = 12
DEFAULT_PERIOD_DAYS = 7
TOP_ARTICLES_PER_COMPANY = 10
MAX_UNIQUE_PER_COMPANY = 18
PER_COMPANY_CONCURRENCY = 3
EXTRACT_CONCURRENCY = 5

_CATEGORY_SET = {c.lower(): c for c in UPDATE_CATEGORIES}
_ISO_DATE_RE = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")


def _build_queries(company: str, highlight_domain: str) -> List[str]:
    """Build DDG queries for one company's weekly cross-domain sweep."""
    queries = [
        f"{company} announcement this week",
        f"{company} news latest",
        f"{company} product launch release",
        f"{company} funding investment acquisition",
        f"{company} partnership collaboration",
        f"{company} research paper breakthrough",
    ]
    hd = (highlight_domain or "").strip()
    if hd:
        queries.insert(0, f"{company} {hd} announcement")
        queries.append(f"{company} {hd} strategy")
    return queries


def _dedup_articles(articles: List[RawArticle]) -> List[RawArticle]:
    """Dedup by URL, preserving first-seen order."""
    seen: Set[str] = set()
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
    highlight_domain: str,
    period_days: int,
) -> List[RawArticle]:
    """Run providers + BYO URLs + exclusions for one company, then extract."""
    # Expand the base queries across canonical + alias forms so we surface
    # e.g. "Facebook" hits under "Meta".
    aliases = ctx.expand(company)
    queries: List[str] = []
    for alias in aliases:
        queries.extend(_build_queries(alias, highlight_domain))

    results: List[RawArticle] = []
    try:
        batch = await gather_via_providers(
            ctx,
            company,
            queries=queries,
            domain=highlight_domain or "Technology",
            lookback_days=period_days,
            max_results_per_provider=15,
        )
        results.extend(batch)
    except Exception as e:
        logger.warning(f"[{company}] provider aggregation failed: {e}")

    # Append BYO URLs — user-curated inputs always survive dedup as they
    # were hand-picked.
    try:
        byo = await ctx.byo_for(company)
        if byo:
            logger.info(f"[{company}] appending {len(byo)} BYO articles")
            results.extend(byo)
    except Exception as e:
        logger.warning(f"[{company}] BYO fetch failed: {e}")

    # Apply user exclusions before dedup so we don't pay to extract dropped
    # items.
    results = ctx.filter_exclusions(results, company)

    # Quick pre-extraction filter — catches articles whose title/snippet
    # already reveals an old date (cheap, runs on all results).
    results = filter_articles_by_date(
        results, period_days, buffer_multiplier=1.5, label=company,
    )

    unique = _dedup_articles(results)[:MAX_UNIQUE_PER_COMPANY]
    logger.info(f"[{company}] {len(unique)} unique articles after dedup")

    sem = asyncio.Semaphore(EXTRACT_CONCURRENCY)

    async def _extract(a: RawArticle) -> RawArticle:
        async with sem:
            try:
                return await extract_full_text(a)
            except Exception as e:
                logger.debug(f"[{company}] extract failed for {a.url}: {e}")
                return a

    enriched = list(await asyncio.gather(
        *[_extract(a) for a in unique[:TOP_ARTICLES_PER_COMPANY]]
    ))

    # Post-extraction date filter — now that trafilatura has populated
    # published_date and full content, re-filter to drop articles that
    # are actually old.  This is the key filter that catches DDG results
    # whose age was unknown from the snippet alone.
    before = len(enriched)
    enriched = filter_articles_by_date(
        enriched, period_days, buffer_multiplier=1.5,
        drop_undated=True,
        label=f"{company}/post-extract",
    )
    if len(enriched) < before:
        logger.info(
            f"[{company}] Post-extraction date filter: "
            f"{before - len(enriched)} old articles removed"
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


def _normalize_category(value: str) -> str:
    """Coerce a free-form category to one of the UPDATE_CATEGORIES."""
    v = (value or "").strip().lower()
    if not v:
        return "Other"
    if v in _CATEGORY_SET:
        return _CATEGORY_SET[v]
    # Fuzzy hint matching
    if any(h in v for h in ("launch", "release", "unveil", "rollout", "ship")):
        return "Product Launch"
    if any(h in v for h in ("fund", "raise", "series", "investment", "ipo")):
        return "Funding"
    if "acqui" in v or "merger" in v:
        return "Acquisition"
    if "partner" in v or "collaborat" in v or "deal" in v:
        return "Partnership"
    if "research" in v or "paper" in v or "publication" in v:
        return "Research"
    if "regulat" in v or "policy" in v or "compliance" in v or "ban " in v:
        return "Regulatory"
    if "hire" in v or "ceo" in v or "exec" in v or "appoint" in v or "resign" in v:
        return "People"
    if "technical" in v or "model" in v or "infra" in v or "benchmark" in v:
        return "Technical"
    return "Other"


def _parse_update_date(value: str) -> Optional[datetime]:
    """Parse YYYY-MM-DD from an LLM-provided date string."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        pass
    m = _ISO_DATE_RE.search(value)
    if m:
        try:
            return datetime(
                int(m.group(1)), int(m.group(2)), int(m.group(3)),
                tzinfo=timezone.utc,
            )
        except (ValueError, TypeError):
            return None
    return None


def _sanitize_briefing(
    briefing: CompanyBriefing,
    window_start: datetime,
    window_end: datetime,
) -> CompanyBriefing:
    """Normalize categories, drop out-of-window updates, rebuild domains_active."""
    # Permit a 1-day buffer either side to accommodate timezone drift in
    # article publication dates.
    lower = window_start - timedelta(days=1)
    upper = window_end + timedelta(days=1)

    cleaned: List[CompanyUpdate] = []
    domains: Set[str] = set()
    for u in briefing.updates:
        u.category = _normalize_category(u.category)
        dt = _parse_update_date(u.date)
        if dt is None:
            # No parseable date — keep only if we have an article source URL.
            if not u.source_url:
                continue
            u.date = ""
        else:
            if dt < lower or dt > upper:
                continue
            u.date = dt.strftime("%Y-%m-%d")
        if u.domain and u.domain.strip():
            domains.add(u.domain.strip())

        # Rule-based sentiment scorer (#9). Cheap — always on when flag set.
        if SENSING_FEATURES.get("sentiment", True):
            try:
                u.sentiment = score_update(
                    headline=u.headline,
                    summary=u.summary,
                    category=u.category,
                )
            except Exception:
                u.sentiment = "neutral"

        # Evidence + single-source confidence downgrade (#13, #25).
        if SENSING_FEATURES.get("single_source_downgrade", True) and u.evidence:
            u.evidence = downgrade_single_source(u.evidence)

        cleaned.append(u)

    briefing.updates = cleaned
    if domains:
        briefing.domains_active = sorted(domains)
    elif not briefing.domains_active:
        briefing.domains_active = []
    return briefing


def _empty_briefing(company: str) -> CompanyBriefing:
    """Return a briefing indicating no notable activity this week."""
    return CompanyBriefing(
        company=company,
        overall_summary=(
            f"No notable activity surfaced for **{company}** during the "
            "briefing window."
        ),
        domains_active=[],
        updates=[],
        key_themes=[],
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


async def _brief_company(
    ctx: RunContext,
    company: str,
    period_start: str,
    period_end: str,
    highlight_domain: str,
    period_days: int,
    window_start: datetime,
    window_end: datetime,
) -> CompanyBriefing:
    """Run search → extract → LLM synthesis for one company."""
    try:
        articles = await _gather_articles_for_company(
            ctx, company, highlight_domain, period_days
        )
        useful = [a for a in articles if (a.content or a.snippet)]
        if not useful:
            logger.warning(f"[{company}] no useful articles — empty briefing")
            return _empty_briefing(company)

        articles_text = _articles_to_prompt_text(useful)
        prompt = company_weekly_brief_prompt(
            company=company,
            articles_text=articles_text,
            period_start=period_start,
            period_end=period_end,
            highlight_domain=highlight_domain,
        )

        logger.info(f"[{company}] invoking LLM with {len(useful)} articles")
        result = await _invoke_with_telemetry(
            ctx,
            label=f"briefing:{company}",
            response_schema=CompanyBriefing,
            contents=prompt,
        )
        briefing = CompanyBriefing.model_validate(result)
        briefing.company = company
        briefing.sources_used = len(useful)
        briefing = _sanitize_briefing(briefing, window_start, window_end)

        # Momentum roll-up per briefing (#8).
        if SENSING_FEATURES.get("momentum", True):
            try:
                briefing.momentum = compute_momentum(briefing)
            except Exception as e:
                logger.debug(f"[{company}] momentum calc failed: {e}")

        return briefing
    except Exception as e:
        logger.error(f"[{company}] briefing failed: {e}")
        return _empty_briefing(company)


async def _build_cross_view(
    ctx: RunContext,
    companies: List[str],
    briefings: List[CompanyBriefing],
    period_start: str,
    period_end: str,
    period_days: int,
    highlight_domain: str,
) -> KeyCompaniesReport:
    """Run the cross-company LLM synthesis and return the final report."""
    briefings_json = json.dumps(
        [b.model_dump() for b in briefings], indent=2, ensure_ascii=False
    )
    prompt = key_companies_cross_prompt(
        briefings_json=briefings_json,
        companies=companies,
        period_start=period_start,
        period_end=period_end,
        highlight_domain=highlight_domain,
    )

    try:
        result = await _invoke_with_telemetry(
            ctx,
            label="key_companies:cross_view",
            response_schema=KeyCompaniesReport,
            contents=prompt,
        )
        report = KeyCompaniesReport.model_validate(result)
        # Enforce invariants — we trust the per-company briefings more than
        # anything re-synthesized in the cross call.
        report.companies_analyzed = companies
        report.highlight_domain = highlight_domain
        report.period_days = period_days
        report.period_start = period_start
        report.period_end = period_end
        report.briefings = briefings
        return report
    except Exception as e:
        logger.error(f"Cross-company synthesis failed: {e} — using fallback")
        fallback_summary = (
            "Cross-company synthesis was unavailable. Per-company briefings "
            "are provided below."
        )
        return KeyCompaniesReport(
            companies_analyzed=companies,
            highlight_domain=highlight_domain,
            period_days=period_days,
            period_start=period_start,
            period_end=period_end,
            cross_company_summary=fallback_summary,
            briefings=briefings,
        )


async def run_key_companies(
    user_id: str,
    company_names: List[str],
    highlight_domain: str = "",
    period_days: int = DEFAULT_PERIOD_DAYS,
    progress_callback: Optional[Callable] = None,
    tracking_id: str = "",
    watchlist_id: str = "",
) -> KeyCompaniesReport:
    """
    Run a Key Companies weekly briefing.

    Stages:
    1. Validate inputs and compute the window (now - period_days → now).
    2. Build the per-run context (aliases, exclusions, BYO URLs, providers).
    3. Per-company search + extract (parallel, bounded).
    4. Per-company LLM synthesis (parallel, bounded).
    5. Cross-company LLM synthesis.
    6. Cross-domain rollup + telemetry persistence.
    """
    start = time.time()

    async def _emit(pct: int, msg: str):
        if progress_callback:
            await progress_callback("key_companies", pct, msg)

    companies = [c.strip() for c in company_names if c and c.strip()][:MAX_COMPANIES]
    if not companies:
        raise ValueError("At least one company name is required")

    period_days = max(1, min(int(period_days or DEFAULT_PERIOD_DAYS), 30))
    now_dt = datetime.now(timezone.utc)
    window_start = now_dt - timedelta(days=period_days)
    period_end = now_dt.strftime("%Y-%m-%d")
    period_start = window_start.strftime("%Y-%m-%d")
    hd = (highlight_domain or "").strip()

    tracking_id = (tracking_id or uuid.uuid4().hex).strip()

    logger.info(
        f"Key Companies: {len(companies)} companies, window "
        f"{period_start} → {period_end}, highlight='{hd or 'cross-domain'}', "
        f"tracking_id={tracking_id}"
    )

    await _emit(5, f"Starting weekly briefing for {len(companies)} companies...")

    ctx = await build_run_context(
        user_id=user_id,
        tracking_id=tracking_id,
        kind="key_companies",
    )

    sem = asyncio.Semaphore(PER_COMPANY_CONCURRENCY)
    step = 80 / max(len(companies), 1)
    completed = 0

    async def _run_one(company: str) -> CompanyBriefing:
        nonlocal completed
        async with sem:
            briefing = await _brief_company(
                ctx=ctx,
                company=company,
                period_start=period_start,
                period_end=period_end,
                highlight_domain=hd,
                period_days=period_days,
                window_start=window_start,
                window_end=now_dt,
            )
            completed += 1
            pct = 5 + int(step * completed)
            await _emit(pct, f"Briefed {company} ({completed}/{len(companies)})")
            return briefing

    briefings = await asyncio.gather(*[_run_one(c) for c in companies])

    await _emit(90, "Synthesizing cross-company digest...")
    report = await _build_cross_view(
        ctx=ctx,
        companies=companies,
        briefings=list(briefings),
        period_start=period_start,
        period_end=period_end,
        period_days=period_days,
        highlight_domain=hd,
    )

    # Cross-domain rollup (#29). Pure; no network.
    if SENSING_FEATURES.get("cross_domain_rollup", True):
        try:
            report.domain_rollup = compute_domain_rollup(report.briefings)
        except Exception as e:
            logger.debug(f"domain rollup failed: {e}")

    if watchlist_id:
        report.watchlist_id = watchlist_id

    # Diff vs previous run for same company set (#12). Best-effort;
    # failures are logged but never block the report.
    if SENSING_FEATURES.get("diff", True):
        try:
            from core.sensing.diff import annotate_key_companies_diff

            diff_summary = await annotate_key_companies_diff(
                user_id,
                report,
                current_tracking_id=tracking_id,
            )
            if diff_summary:
                report.diff_summary = diff_summary
        except Exception as e:
            logger.debug(f"kc_diff failed: {e}")

    # Persist telemetry (#28) — safe even when collector is None.
    if ctx.telemetry is not None:
        try:
            await ctx.telemetry.save()
        except Exception as e:
            logger.debug(f"telemetry save failed: {e}")

    elapsed = time.time() - start
    await _emit(100, "Key Companies briefing complete")
    logger.info(
        f"Key Companies complete in {elapsed:.1f}s — "
        f"{len(briefings)} briefings, "
        f"{sum(len(b.updates) for b in briefings)} total updates"
    )
    return report


async def save_key_companies(
    user_id: str,
    tracking_id: str,
    report: KeyCompaniesReport,
) -> str:
    """Persist the Key Companies report to disk. Returns the file path."""
    sensing_dir = os.path.join("data", user_id, "sensing")
    os.makedirs(sensing_dir, exist_ok=True)
    path = os.path.join(sensing_dir, f"key_companies_{tracking_id}.json")

    payload = {
        "report": report.model_dump(),
        "meta": {
            "tracking_id": tracking_id,
            "companies": report.companies_analyzed,
            "highlight_domain": report.highlight_domain,
            "period_days": report.period_days,
            "period_start": report.period_start,
            "period_end": report.period_end,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    }
    async with aiofiles.open(path, "w", encoding="utf-8") as f:
        await f.write(json.dumps(payload, ensure_ascii=False, indent=2))
    return path
