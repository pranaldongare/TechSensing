"""Shared per-run context for Company Analysis + Key Companies.

Bundles user-scoped state (aliases, exclusions, BYO URLs, provider list,
telemetry collector) so the two orchestrators don't each grow 7 extra
keyword arguments.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from core.constants import SENSING_FEATURES
from core.llm.telemetry import TelemetryCollector
from core.sensing.aliases import expand_company, load_aliases
from core.sensing.byo_urls import fetch_byo_articles, load_byo_urls
from core.sensing.exclusions import apply_exclusions, load_exclusions
from core.sensing.ingest import RawArticle
from core.sensing.providers import (
    SourceProvider,
    aggregate_sources,
    get_enabled_providers,
)

logger = logging.getLogger("sensing.run_context")


@dataclass
class RunContext:
    """Per-run state shared by one orchestrator invocation."""

    user_id: str
    tracking_id: str
    kind: str  # 'company_analysis' | 'key_companies'
    aliases: Dict[str, List[str]] = field(default_factory=dict)
    exclusions: Dict[str, Any] = field(default_factory=dict)
    byo_urls_map: Dict[str, List[str]] = field(default_factory=dict)
    providers: List[SourceProvider] = field(default_factory=list)
    telemetry: Optional[TelemetryCollector] = None

    # ── Query expansion via aliases ────────────────────────────
    def expand(self, company: str) -> List[str]:
        if not company:
            return []
        if SENSING_FEATURES.get("aliases", True) and self.aliases:
            return expand_company(company, self.aliases)
        return [company]

    # ── Apply exclusions post-search ────────────────────────────
    def filter_exclusions(
        self, articles: List[RawArticle], company: str = ""
    ) -> List[RawArticle]:
        if (
            not SENSING_FEATURES.get("exclusions", True)
            or not self.exclusions
        ):
            return articles
        return apply_exclusions(articles, self.exclusions, company)

    # ── Append BYO articles ─────────────────────────────────────
    async def byo_for(self, company: str) -> List[RawArticle]:
        if (
            not SENSING_FEATURES.get("byo_urls", True)
            or not self.byo_urls_map
        ):
            return []
        urls = self.byo_urls_map.get(company.strip(), [])
        if not urls:
            return []
        # Reuse fetch_byo_articles but with the preloaded map to avoid
        # re-reading the file.
        return await fetch_byo_articles(self.user_id, company)


async def build_run_context(
    *,
    user_id: str,
    tracking_id: str,
    kind: str,
    extra_providers: Sequence[SourceProvider] = (),
) -> RunContext:
    """Load all per-user state for a run.

    ``extra_providers`` lets the caller force-enable providers beyond
    the current feature-flag defaults (useful for tests / scheduled
    runs that pre-select a provider set).
    """
    aliases = await load_aliases(user_id)
    exclusions = await load_exclusions(user_id)
    byo = await load_byo_urls(user_id)

    providers: List[SourceProvider] = list(
        get_enabled_providers(
            user_id=user_id,
            include_ddg=True,
            include_rss=SENSING_FEATURES.get("rss_provider", False),
            include_github=SENSING_FEATURES.get("github_provider", False),
            include_arxiv=SENSING_FEATURES.get("arxiv_provider", False),
            include_press_wire=SENSING_FEATURES.get("press_wire_provider", False),
            include_youtube=SENSING_FEATURES.get("youtube_provider", False),
            include_edgar=SENSING_FEATURES.get("edgar_provider", False),
            include_patents=SENSING_FEATURES.get("patents_provider", False),
        )
    )
    providers.extend(extra_providers)

    telemetry = None
    if SENSING_FEATURES.get("telemetry", True):
        telemetry = TelemetryCollector(
            user_id=user_id, tracking_id=tracking_id, kind=kind
        )

    return RunContext(
        user_id=user_id,
        tracking_id=tracking_id,
        kind=kind,
        aliases=aliases,
        exclusions=exclusions,
        byo_urls_map=byo,
        providers=providers,
        telemetry=telemetry,
    )


async def gather_via_providers(
    ctx: RunContext,
    company: str,
    queries: List[str],
    *,
    domain: str = "",
    lookback_days: int = 30,
    max_results_per_provider: int = 15,
) -> List[RawArticle]:
    """Run the context's providers in parallel and return merged articles."""
    return await aggregate_sources(
        ctx.providers,
        company,
        queries=queries,
        domain=domain,
        lookback_days=lookback_days,
        max_results_per_provider=max_results_per_provider,
    )
