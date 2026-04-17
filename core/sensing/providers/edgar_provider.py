"""SEC / EDGAR provider — recent 8-K / 10-K / 10-Q filings.

Uses the public EDGAR full-text search endpoint — no API key required,
only a descriptive ``User-Agent`` per SEC fair-access rules.

We only run for companies that appear in ``ticker_map.json``; the
provider silently returns ``[]`` for private companies or unmapped
names rather than spamming EDGAR with futile queries.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import httpx

from core.sensing.ingest import RawArticle

logger = logging.getLogger("sensing.providers.edgar")

_TICKER_MAP_PATH = os.path.join(
    os.path.dirname(__file__), "ticker_map.json"
)

EDGAR_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
EDGAR_BASE = "https://www.sec.gov"

_ticker_cache: Dict[str, str] | None = None


def _load_ticker_map() -> Dict[str, str]:
    global _ticker_cache
    if _ticker_cache is not None:
        return _ticker_cache
    try:
        with open(_TICKER_MAP_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        _ticker_cache = {
            str(k).strip().lower(): str(v).strip()
            for k, v in raw.items()
            if str(v).strip()
        }
    except Exception as e:
        logger.warning(f"[edgar] ticker map unavailable: {e}")
        _ticker_cache = {}
    return _ticker_cache


def _lookup_ticker(company: str) -> Optional[str]:
    if not company:
        return None
    return _load_ticker_map().get(company.strip().lower())


def _user_agent() -> str:
    # SEC requires a descriptive UA with contact info. Allow override via env.
    return os.environ.get(
        "SEC_EDGAR_USER_AGENT",
        "TechSensing research-agent contact@example.com",
    )


async def _search_edgar(
    ticker: str, *, lookback_days: int, max_results: int
) -> List[Dict]:
    end = datetime.now(timezone.utc).date()
    start = (end - timedelta(days=max(lookback_days, 30)))

    params = {
        "q": f'"{ticker}"',
        "dateRange": "custom",
        "startdt": start.strftime("%Y-%m-%d"),
        "enddt": end.strftime("%Y-%m-%d"),
        "forms": "8-K,10-K,10-Q,6-K",
    }

    headers = {
        "User-Agent": _user_agent(),
        "Accept": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                EDGAR_SEARCH_URL, params=params, headers=headers
            )
            if resp.status_code >= 400:
                logger.warning(
                    f"[edgar] search {ticker}: HTTP {resp.status_code}"
                )
                return []
            data = resp.json()
    except Exception as e:
        logger.warning(f"[edgar] search failed for {ticker!r}: {e}")
        return []

    hits = (data.get("hits") or {}).get("hits") or []
    return hits[:max_results]


def _hit_to_article(hit: Dict, ticker: str) -> Optional[RawArticle]:
    source = hit.get("_source") or {}
    adsh = hit.get("_id") or ""
    # EDGAR filing id format: <ADSH>:<sequence> — split to build URL.
    acc = adsh.split(":")[0] if adsh else ""
    cik_arr = source.get("ciks") or []
    cik = (cik_arr[0] if cik_arr else "") or ""
    form = (source.get("form") or "").strip()
    filed = source.get("file_date") or ""
    display = (source.get("display_names") or ["Unknown"])[0]

    if not acc or not cik:
        return None

    acc_nodash = acc.replace("-", "")
    # Standard EDGAR filing-index URL.
    url = (
        f"{EDGAR_BASE}/cgi-bin/browse-edgar?action=getcompany"
        f"&CIK={cik}&type={form}&dateb=&owner=include&count=40"
    )
    # More specific per-filing index:
    per_filing = (
        f"{EDGAR_BASE}/Archives/edgar/data/{int(cik)}/"
        f"{acc_nodash}/{acc}-index.htm"
    )

    title = f"{display} — {form} filing ({filed})"
    snippet = f"SEC {form} filing for {ticker}, filed {filed}"
    return RawArticle(
        title=title,
        url=per_filing or url,
        source="SEC EDGAR",
        published_date=filed,
        snippet=snippet,
        content="",
    )


class EdgarProvider:
    """SEC EDGAR filing provider (ticker-gated)."""

    name = "edgar"

    async def search(
        self,
        company: str,
        *,
        queries: List[str],  # noqa: ARG002 — ticker drives query
        domain: str = "",  # noqa: ARG002
        lookback_days: int = 60,
        max_results: int = 10,
    ) -> List[RawArticle]:
        ticker = _lookup_ticker(company)
        if not ticker:
            logger.info(f"[edgar] no ticker for {company!r}; skipping")
            return []

        hits = await _search_edgar(
            ticker, lookback_days=lookback_days, max_results=max_results
        )
        articles: List[RawArticle] = []
        for hit in hits:
            art = _hit_to_article(hit, ticker)
            if art:
                articles.append(art)

        logger.info(
            f"[edgar] {company!r} ({ticker}): {len(articles)} filing(s)"
        )
        return articles[:max_results]
