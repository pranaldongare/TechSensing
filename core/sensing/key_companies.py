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
from datetime import datetime, timedelta, timezone
from typing import Callable, List, Optional, Set

import aiofiles

from core.constants import GPU_SENSING_COMPANY_ANALYSIS_LLM
from core.llm.client import invoke_llm
from core.llm.output_schemas.key_companies import (
    CompanyBriefing,
    CompanyUpdate,
    KeyCompaniesReport,
    UPDATE_CATEGORIES,
)
from core.llm.prompts.key_company_prompts import (
    company_weekly_brief_prompt,
    key_companies_cross_prompt,
)
from core.sensing.ingest import (
    RawArticle,
    extract_full_text,
    search_duckduckgo,
)

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
    company: str,
    highlight_domain: str,
    period_days: int,
) -> List[RawArticle]:
    """Run DDG queries for one company, dedup, and extract top articles."""
    queries = _build_queries(company, highlight_domain)
    results: List[RawArticle] = []

    try:
        batch = await search_duckduckgo(
            queries=queries,
            domain=highlight_domain or "Technology",
            lookback_days=period_days,
        )
        results.extend(batch)
    except Exception as e:
        logger.warning(f"[{company}] DDG search failed: {e}")

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


async def _brief_company(
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
            company, highlight_domain, period_days
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
        result = await invoke_llm(
            gpu_model=GPU_SENSING_COMPANY_ANALYSIS_LLM.model,
            response_schema=CompanyBriefing,
            contents=prompt,
            port=GPU_SENSING_COMPANY_ANALYSIS_LLM.port,
        )
        briefing = CompanyBriefing.model_validate(result)
        briefing.company = company
        briefing.sources_used = len(useful)
        return _sanitize_briefing(briefing, window_start, window_end)
    except Exception as e:
        logger.error(f"[{company}] briefing failed: {e}")
        return _empty_briefing(company)


async def _build_cross_view(
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
        result = await invoke_llm(
            gpu_model=GPU_SENSING_COMPANY_ANALYSIS_LLM.model,
            response_schema=KeyCompaniesReport,
            contents=prompt,
            port=GPU_SENSING_COMPANY_ANALYSIS_LLM.port,
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
) -> KeyCompaniesReport:
    """
    Run a Key Companies weekly briefing.

    Stages:
    1. Validate inputs and compute the window (now - period_days → now).
    2. Per-company search + extract (parallel, bounded).
    3. Per-company LLM synthesis (parallel, bounded).
    4. Cross-company LLM synthesis.
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

    logger.info(
        f"Key Companies: {len(companies)} companies, window "
        f"{period_start} → {period_end}, highlight='{hd or 'cross-domain'}'"
    )

    await _emit(5, f"Starting weekly briefing for {len(companies)} companies...")

    sem = asyncio.Semaphore(PER_COMPANY_CONCURRENCY)
    step = 80 / max(len(companies), 1)
    completed = 0

    async def _run_one(company: str) -> CompanyBriefing:
        nonlocal completed
        async with sem:
            briefing = await _brief_company(
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
        companies=companies,
        briefings=list(briefings),
        period_start=period_start,
        period_end=period_end,
        period_days=period_days,
        highlight_domain=hd,
    )

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
