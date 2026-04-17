"""Strategic-theme extraction (#11).

One small LLM pass over an already-generated
:class:`CompanyAnalysisReport` that returns 3–6 cross-company
:class:`ThemeCluster` entries. Safe to skip or fail silently — the
report still renders without themes.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List

from core.llm.client import invoke_llm
from core.llm.output_schemas.analysis_extensions import ThemeCluster
from core.llm.prompts.analysis_prompts import (
    ThemeClusterList,
    strategic_themes_prompt,
)

if TYPE_CHECKING:  # pragma: no cover
    from core.llm.output_schemas.company_analysis import CompanyAnalysisReport
    from core.sensing.run_context import RunContext

logger = logging.getLogger("sensing.themes")


async def extract_strategic_themes(
    report: "CompanyAnalysisReport",
    *,
    ctx: "RunContext | None" = None,
    max_themes: int = 6,
    gpu_model: str = "gemini",
    port: int = 0,
) -> List[ThemeCluster]:
    """Run the themes pass and return a list of ThemeClusters.

    Returns ``[]`` on any failure; callers should set
    ``report.strategic_themes = await extract_strategic_themes(...)``
    directly.
    """
    if not report.company_profiles or len(report.company_profiles) < 2:
        # Themes require ≥2 companies to say anything cross-company.
        return []

    prompt = strategic_themes_prompt(report, max_themes=max_themes)

    try:
        if ctx is not None and getattr(ctx, "telemetry", None) is not None:
            result = await ctx.telemetry.invoke_llm(
                label="strategic_themes",
                gpu_model=gpu_model,
                response_schema=ThemeClusterList,
                contents=prompt,
                port=port,
            )
        else:
            result = await invoke_llm(
                gpu_model=gpu_model,
                response_schema=ThemeClusterList,
                contents=prompt,
                port=port,
            )
    except Exception as e:
        logger.warning(f"[themes] LLM pass failed: {e}")
        return []

    if not isinstance(result, ThemeClusterList):
        return []

    themes = [
        t
        for t in (result.themes or [])
        if (t.theme or "").strip() and len(t.companies) >= 2
    ]
    logger.info(f"[themes] extracted {len(themes)} cross-company themes")
    return themes[:max_themes]


__all__ = ["extract_strategic_themes"]
