"""Hallucination probe for generated profiles (#27).

Takes a Company Analysis ``CompanyProfile`` JSON and the articles that
fed into it, then asks the LLM to flag any claim NOT supported by the
articles.

Gated behind ``SENSING_FEATURES["hallucination_probe"]``.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from core.constants import GPU_SENSING_REPORT_LLM, SENSING_FEATURES
from core.llm.client import invoke_llm
from core.llm.output_schemas.analysis_extensions import UnsupportedClaim
from core.llm.prompts.analysis_prompts import (
    UnsupportedClaimList,
    hallucination_probe_prompt,
)

logger = logging.getLogger("sensing.hallucination_probe")


async def probe_profile(
    profile_json: str,
    articles_digest: str,
) -> List[UnsupportedClaim]:
    """Run the hallucination probe for a single company profile.

    *profile_json*: serialized ``CompanyProfile`` dict.
    *articles_digest*: newline-separated title + snippets of the source
    articles.

    Returns a list of ``UnsupportedClaim`` items (may be empty).
    """
    if not SENSING_FEATURES.get("hallucination_probe", True):
        return []

    prompt = hallucination_probe_prompt(profile_json, articles_digest)
    try:
        result = await invoke_llm(
            gpu_model=GPU_SENSING_REPORT_LLM.model,
            response_schema=UnsupportedClaimList,
            contents=prompt,
            port=GPU_SENSING_REPORT_LLM.port,
        )
        if isinstance(result, UnsupportedClaimList):
            return result.claims
        return []
    except Exception as e:
        logger.warning(f"Hallucination probe failed: {e}")
        return []


async def probe_all_profiles(
    report_data: Dict[str, Any],
    article_index: Dict[str, List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """Run probes across every profile in a CA report.

    *article_index* maps ``"company_name"`` → list of raw article dicts.

    Returns a flat list of unsupported-claim dicts, each enriched with
    ``company``.
    """
    all_claims: List[Dict[str, Any]] = []
    for profile in report_data.get("company_profiles", []):
        company = profile.get("company", "")
        articles = article_index.get(company, [])
        if not articles:
            continue

        digest = "\n\n".join(
            f"[{a.get('title','')}] {a.get('url','')}\n"
            f"{(a.get('snippet') or a.get('content') or '')[:400]}"
            for a in articles[:10]
        )

        profile_str = json.dumps(profile, indent=2, ensure_ascii=False)[:8000]
        claims = await probe_profile(profile_str, digest)
        for c in claims:
            d = c.model_dump() if hasattr(c, "model_dump") else dict(c)
            d["company"] = company
            all_claims.append(d)
    return all_claims
