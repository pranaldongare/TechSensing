"""Cross-domain rollup for Key Companies reports (#29).

Aggregates per-briefing activity into a flat
``List[DomainRollupEntry]`` the UI can render as a stacked bar or
summary row. Pure function — zero LLM or network cost.
"""

from __future__ import annotations

from typing import Dict, List

from core.llm.output_schemas.analysis_extensions import DomainRollupEntry
from core.llm.output_schemas.key_companies import CompanyBriefing


def compute_domain_rollup(
    briefings: List[CompanyBriefing],
) -> List[DomainRollupEntry]:
    """Count updates and distinct active companies per domain."""
    counts: Dict[str, int] = {}
    companies_by_domain: Dict[str, set] = {}

    for b in briefings or []:
        company = (b.company or "").strip() or "Unknown"
        # Collect per-update domain
        for u in b.updates or []:
            d = (u.domain or "").strip()
            if not d:
                continue
            counts[d] = counts.get(d, 0) + 1
            companies_by_domain.setdefault(d, set()).add(company)
        # Some briefings only populate domains_active without per-update
        # domain; fold those in as well so quiet weeks still show the
        # domains a company "touches".
        for d in (b.domains_active or []):
            d = d.strip()
            if not d:
                continue
            companies_by_domain.setdefault(d, set()).add(company)
            counts.setdefault(d, 0)

    entries = [
        DomainRollupEntry(
            domain=d,
            update_count=counts.get(d, 0),
            company_count=len(companies_by_domain.get(d, set())),
        )
        for d in companies_by_domain.keys()
    ]
    entries.sort(
        key=lambda e: (e.update_count, e.company_count),
        reverse=True,
    )
    return entries
