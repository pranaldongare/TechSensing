"""Investment-signal aggregator (#30).

Scans an already-synthesized :class:`CompanyAnalysisReport` for
dollar amounts, funding rounds, acquisitions, and hiring signals.

Pure function — regex-only, no LLM cost. The regex is intentionally
forgiving: ``$2B``, ``$2 billion``, ``$500M``, ``$1.2m``, ``$120K``,
``€150M``, ``£1bn`` all parse. The extractor looks at per-finding
``investment_signal``, ``recent_developments`` and ``summary``.

Emits :class:`InvestmentEvent` entries with ``amount_usd`` best-effort
resolved (currency symbol preserved in ``amount_text``).
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Iterable, List, Literal

from core.llm.output_schemas.analysis_extensions import InvestmentEvent

if TYPE_CHECKING:  # pragma: no cover
    from core.llm.output_schemas.company_analysis import (
        CompanyAnalysisReport,
        CompanyTechFinding,
    )

logger = logging.getLogger("sensing.investment")


EventType = Literal[
    "Funding",
    "Acquisition",
    "IPO",
    "Divestiture",
    "Partnership",
    "Hiring",
    "Other",
]


# Rough FX → USD (good enough for bucket charts). Extend as needed.
_FX_TO_USD: dict[str, float] = {
    "$": 1.0,
    "US$": 1.0,
    "USD": 1.0,
    "€": 1.08,
    "EUR": 1.08,
    "£": 1.25,
    "GBP": 1.25,
    "¥": 0.0068,
    "JPY": 0.0068,
    "₹": 0.012,
    "INR": 0.012,
    "C$": 0.73,
    "CAD": 0.73,
    "A$": 0.66,
    "AUD": 0.66,
}


# Match amounts like "$2B", "$500 million", "€1.5bn", "USD 2 billion"
_AMOUNT_RE = re.compile(
    r"""
    (?P<sym>
        US\$|C\$|A\$|USD|EUR|GBP|JPY|INR|CAD|AUD|[$€£¥₹]
    )
    \s*
    (?P<num>\d+(?:[.,]\d+)?)
    \s*
    (?P<mag>
        billion|bn|million|mn|m|thousand|k|b
    )?
    """,
    re.IGNORECASE | re.VERBOSE,
)

_MAGNITUDES: dict[str, float] = {
    "thousand": 1e3,
    "k": 1e3,
    "million": 1e6,
    "mn": 1e6,
    "m": 1e6,
    "billion": 1e9,
    "bn": 1e9,
    "b": 1e9,
}


def _parse_amount(text: str) -> tuple[float, str] | None:
    m = _AMOUNT_RE.search(text)
    if not m:
        return None
    sym = m.group("sym") or "$"
    raw_num = (m.group("num") or "0").replace(",", "")
    try:
        base = float(raw_num)
    except ValueError:
        return None
    mag_token = (m.group("mag") or "").lower()
    base *= _MAGNITUDES.get(mag_token, 1.0)
    fx = _FX_TO_USD.get(sym.upper(), _FX_TO_USD.get(sym, 1.0))
    amount_usd = base * fx
    raw_text = m.group(0).strip()
    return amount_usd, raw_text


_EVENT_PATTERNS: list[tuple[EventType, re.Pattern[str]]] = [
    ("Acquisition", re.compile(r"\b(acquir(e|ed|ing|isition)|takeover|buyout|merger)\b", re.I)),
    ("IPO", re.compile(r"\b(IPO|initial public offering|going public|direct listing)\b", re.I)),
    ("Divestiture", re.compile(r"\b(divest|spin[\- ]off|sold off)\b", re.I)),
    ("Funding", re.compile(r"\b(funding|raise[ds]?|series [a-h]|seed|pre[\- ]seed|round|venture)\b", re.I)),
    ("Partnership", re.compile(r"\b(partner(ship)?|alliance|collabora(tion|ted with))\b", re.I)),
    ("Hiring", re.compile(r"\b(hire[ds]?|hiring|appoint(ed|s)?|joins as|cto|cfo|cpo|head of|chief)\b", re.I)),
]


def _classify_event(text: str) -> EventType:
    for kind, pat in _EVENT_PATTERNS:
        if pat.search(text):
            return kind
    return "Other"


def _iter_finding_texts(
    f: "CompanyTechFinding",
) -> Iterable[tuple[str, str]]:
    """Yield (text, source_url) pairs worth scanning."""
    url = (f.source_urls or [""])[0] if f.source_urls else ""
    if f.investment_signal:
        yield f.investment_signal, url
    for dev in f.recent_developments or []:
        if dev:
            yield dev, url
    if f.summary:
        yield f.summary, url


def compute_investment_signals(
    report: "CompanyAnalysisReport",
    *,
    min_amount_usd: float = 100_000.0,
) -> List[InvestmentEvent]:
    """Walk the report and emit InvestmentEvent records.

    ``min_amount_usd`` drops trivial matches (e.g. "$5" in a comment)
    that slip past the regex.
    """
    events: List[InvestmentEvent] = []
    seen_keys: set[tuple] = set()

    for profile in report.company_profiles or []:
        company = (profile.company or "").strip()
        if not company:
            continue
        for finding in profile.technology_findings or []:
            for text, url in _iter_finding_texts(finding):
                parsed = _parse_amount(text)
                if not parsed:
                    # Still capture hiring / partnership events without
                    # a dollar amount.
                    kind = _classify_event(text)
                    if kind in ("Hiring", "Partnership"):
                        key = (company, kind, text[:80])
                        if key in seen_keys:
                            continue
                        seen_keys.add(key)
                        events.append(
                            InvestmentEvent(
                                company=company,
                                event_type=kind,
                                amount_usd=0.0,
                                amount_text="",
                                description=text[:280],
                                source_url=url,
                            )
                        )
                    continue

                amount_usd, amount_text = parsed
                if amount_usd < min_amount_usd:
                    continue
                kind = _classify_event(text)
                key = (company, kind, round(amount_usd, 2), amount_text)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                events.append(
                    InvestmentEvent(
                        company=company,
                        event_type=kind,
                        amount_usd=round(amount_usd, 2),
                        amount_text=amount_text,
                        description=text[:280],
                        source_url=url,
                    )
                )

    events.sort(key=lambda e: e.amount_usd, reverse=True)
    logger.info(f"[investment] extracted {len(events)} signal(s)")
    return events


__all__ = ["compute_investment_signals"]
