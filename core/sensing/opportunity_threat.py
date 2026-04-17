"""Opportunity / threat framing for Company Analysis (#33).

Takes the fully generated ``CompanyAnalysisReport`` plus the user's org
context and produces an ``OpportunityThreatFraming`` via one additional
LLM pass.

Gated behind ``SENSING_FEATURES["opportunity_threat"]``.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from core.constants import GPU_SENSING_REPORT_LLM, SENSING_FEATURES
from core.llm.client import invoke_llm
from core.llm.output_schemas.analysis_extensions import OpportunityThreatFraming
from core.llm.prompts.analysis_prompts import opportunity_threat_prompt

logger = logging.getLogger("sensing.opportunity_threat")


async def generate_opportunity_threat(
    report: Any,
    org_context: str,
) -> Optional[Dict[str, Any]]:
    """Run OT framing on a completed CompanyAnalysisReport.

    *report* may be either the Pydantic model or a dict (we handle both).
    *org_context* is the user-provided org description from the
    ``/sensing/org-context`` endpoint.

    Returns a dict matching ``OpportunityThreatFraming`` fields, or
    ``None`` on failure / feature-off.
    """
    if not SENSING_FEATURES.get("opportunity_threat", True):
        return None

    if not org_context.strip():
        logger.debug("No org context set — skipping OT framing.")
        return None

    prompt = opportunity_threat_prompt(report, org_context)
    try:
        result = await invoke_llm(
            gpu_model=GPU_SENSING_REPORT_LLM.model,
            response_schema=OpportunityThreatFraming,
            contents=prompt,
            port=GPU_SENSING_REPORT_LLM.port,
        )
        if isinstance(result, OpportunityThreatFraming):
            return result.model_dump()
        return None
    except Exception as e:
        logger.warning(f"OT framing failed: {e}")
        return None
