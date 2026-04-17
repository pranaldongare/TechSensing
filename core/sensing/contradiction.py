"""Contradiction detection across sources (#26).

For each (company, technology) pair in a Company Analysis run, we cluster
the source articles and run a small LLM pass to find factual conflicts.

Gated behind ``SENSING_FEATURES["contradictions"]``.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from core.constants import GPU_SENSING_REPORT_LLM, SENSING_FEATURES
from core.llm.client import invoke_llm
from core.llm.output_schemas.analysis_extensions import ContradictionFlag
from core.llm.prompts.analysis_prompts import ContradictionList, contradiction_prompt

logger = logging.getLogger("sensing.contradiction")


async def detect_contradictions(
    company: str,
    tech: str,
    articles: List[Dict[str, Any]],
) -> List[ContradictionFlag]:
    """Run contradiction detection for one (company, tech) article cluster.

    *articles* should be a list of dicts with at least ``title``, ``url``,
    ``snippet`` or ``content``.

    Returns a list of ``ContradictionFlag`` items. Empty list when no
    contradictions are found.
    """
    if not SENSING_FEATURES.get("contradictions", True):
        return []

    if len(articles) < 2:
        # Need at least two sources to contradict.
        return []

    bundle = json.dumps(
        [
            {
                "title": a.get("title", ""),
                "url": a.get("url", ""),
                "snippet": (a.get("snippet") or a.get("content") or "")[:600],
            }
            for a in articles[:12]
        ],
        indent=2,
        ensure_ascii=False,
    )

    prompt = contradiction_prompt(company, tech, bundle)
    try:
        result = await invoke_llm(
            gpu_model=GPU_SENSING_REPORT_LLM.model,
            response_schema=ContradictionList,
            contents=prompt,
            port=GPU_SENSING_REPORT_LLM.port,
        )
        if isinstance(result, ContradictionList):
            return result.contradictions
        return []
    except Exception as e:
        logger.warning(f"Contradiction detection failed for {company}/{tech}: {e}")
        return []


async def detect_all_contradictions(
    report_data: Dict[str, Any],
    article_index: Dict[str, List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """Convenience: run detection across all profiles in a CA report.

    *article_index* maps ``"{company}:{technology}"`` → list of raw
    article dicts.

    Returns a list of contradiction dicts suitable for storing in the
    report JSON.
    """
    all_flags: List[Dict[str, Any]] = []
    for profile in report_data.get("company_profiles", []):
        company = profile.get("company", "")
        for finding in profile.get("technology_findings", []):
            tech = finding.get("technology", "")
            key = f"{company}:{tech}"
            articles = article_index.get(key, [])
            if len(articles) < 2:
                continue
            flags = await detect_contradictions(company, tech, articles)
            for f in flags:
                d = f.model_dump() if hasattr(f, "model_dump") else dict(f)
                d["company"] = company
                d["technology"] = tech
                all_flags.append(d)
    return all_flags
