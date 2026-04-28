"""
Prompt Evolver — generates prompt patches based on accumulated experience.

Triggers periodically (every 5th run or when quality drops) to analyze
run summaries and produce targeted prompt improvements for the classifier,
radar generator, and verifier.

Patches are stored as JSON and injected into prompts on subsequent runs.
Uses the lightweight classify LLM.
"""

import json
import logging
import os
import re
import time
from typing import List, Optional

import aiofiles

from core.constants import GPU_SENSING_CLASSIFY_LLM
from core.llm.client import invoke_llm
from core.llm.output_schemas.sensing_outputs import PromptPatchOutput

logger = logging.getLogger("sensing.prompt_evolver")

EVOLVE_EVERY_N_RUNS = 5
QUALITY_THRESHOLD = 3.5  # Trigger evolution if avg overall score drops below this


def _domain_slug(domain: str) -> str:
    """Convert domain name to a safe filename slug."""
    slug = re.sub(r"[^a-z0-9]+", "_", domain.lower()).strip("_")
    return slug or "default"


def _patches_path(user_id: str, domain: str) -> str:
    """Return the JSON file path for a domain's prompt patches."""
    slug = _domain_slug(domain)
    return os.path.join("data", user_id, "sensing", "memory", "prompt_patches", f"{slug}.json")


async def load_prompt_patches(user_id: str, domain: str) -> dict:
    """Load saved prompt patches for a domain.

    Returns an empty dict if no patches exist.
    """
    if not user_id:
        return {}

    path = _patches_path(user_id, domain)
    if not os.path.exists(path):
        return {}

    try:
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            data = json.loads(await f.read())
        logger.info(
            f"[PromptEvolver] Loaded patches for '{domain}' "
            f"(updated: {data.get('updated_at', 'unknown')})"
        )
        return data
    except Exception as e:
        logger.warning(f"[PromptEvolver] Failed to load patches: {e}")
        return {}


def _should_evolve(summaries: List[dict]) -> bool:
    """Check if prompt evolution should trigger based on run count and quality."""
    run_count = len(summaries)

    # Every Nth run
    if run_count > 0 and run_count % EVOLVE_EVERY_N_RUNS == 0:
        logger.info(
            f"[PromptEvolver] Triggering evolution: run count {run_count} "
            f"(every {EVOLVE_EVERY_N_RUNS} runs)"
        )
        return True

    # Quality drop — check average of last 3 runs
    recent = summaries[-3:] if len(summaries) >= 3 else summaries
    overall_scores = [
        s.get("eval_scores", {}).get("overall", 3.0)
        for s in recent
        if isinstance(s.get("eval_scores", {}).get("overall"), (int, float))
    ]

    if overall_scores:
        avg = sum(overall_scores) / len(overall_scores)
        if avg < QUALITY_THRESHOLD:
            logger.info(
                f"[PromptEvolver] Triggering evolution: avg quality "
                f"{avg:.1f} < {QUALITY_THRESHOLD}"
            )
            return True

    return False


async def maybe_evolve_prompts(
    user_id: str,
    domain: str,
    summaries: List[dict],
) -> Optional[dict]:
    """Check if prompt evolution is needed and generate new patches if so.

    Returns the new patch dict if evolution occurred, None otherwise.
    """
    if not user_id or not summaries:
        return None

    if not _should_evolve(summaries):
        return None

    evolve_start = time.time()

    # Build compact summary of last 5 runs for the evolver
    recent = summaries[-5:]
    runs_text = []
    for s in recent:
        scores = s.get("eval_scores", {})
        run_info = (
            f"  Run ({s.get('run_date', '?')[:10]}): "
            f"coverage={scores.get('coverage', '?')}, "
            f"specificity={scores.get('specificity', '?')}, "
            f"novelty={scores.get('novelty_accuracy', '?')}, "
            f"actionability={scores.get('actionability', '?')}, "
            f"coherence={scores.get('coherence', '?')}, "
            f"overall={scores.get('overall', '?')}"
        )
        weaknesses = s.get("weaknesses", [])
        if weaknesses:
            run_info += f"\n    Weaknesses: {'; '.join(weaknesses)}"
        missed = s.get("missed_topics", [])
        if missed:
            run_info += f"\n    Missed: {', '.join(missed)}"
        reflection = s.get("reflection", "")
        if reflection:
            run_info += f"\n    Reflection: {reflection}"
        runs_text.append(run_info)

    # Compute criterion averages
    criteria = ["coverage", "specificity", "novelty_accuracy", "actionability", "coherence"]
    avg_scores = {}
    for criterion in criteria:
        values = [
            s.get("eval_scores", {}).get(criterion, 3)
            for s in recent
            if isinstance(s.get("eval_scores", {}).get(criterion), (int, float))
        ]
        if values:
            avg_scores[criterion] = round(sum(values) / len(values), 1)

    avg_text = ", ".join(f"{k}={v}" for k, v in avg_scores.items())

    prompt = [
        {
            "role": "system",
            "parts": (
                "You are a prompt engineering specialist. Your task is to analyze "
                "the performance history of a tech sensing pipeline and generate "
                "targeted prompt improvements.\n\n"
                "You will see evaluation scores and feedback from recent runs. "
                "Based on RECURRING patterns (not one-off issues), generate "
                "concise, actionable guidance to inject into future prompts.\n\n"
                "RULES:\n"
                "- Only address criteria that consistently score below 4/5.\n"
                "- Write guidance as direct instructions (imperative mood).\n"
                "- Keep each guidance field to 1-3 sentences max.\n"
                "- Leave fields EMPTY (empty string) if no improvement is needed "
                "for that stage.\n"
                "- Do NOT repeat generic advice that's already in the base prompts.\n"
                "- Focus on DOMAIN-SPECIFIC patterns the pipeline has been missing.\n"
                "- Be conservative — only suggest changes supported by clear evidence.\n\n"
                "OUTPUT RULES:\n"
                "- Return ONLY valid JSON.\n"
                "- Do NOT include schema definitions, $defs, $ref, properties, "
                "or type metadata.\n"
            ),
        },
        {
            "role": "user",
            "parts": (
                f"DOMAIN: {domain}\n\n"
                f"AVERAGE SCORES (last {len(recent)} runs): {avg_text}\n\n"
                f"RUN HISTORY:\n" + "\n".join(runs_text) + "\n\n"
                "Based on these patterns, generate prompt improvements. "
                "Only target consistently weak areas."
            ),
        },
    ]

    try:
        logger.info(
            f"[PromptEvolver] Evolving prompts for '{domain}' "
            f"based on {len(recent)} recent runs..."
        )

        result = await invoke_llm(
            gpu_model=GPU_SENSING_CLASSIFY_LLM.model,
            response_schema=PromptPatchOutput,
            contents=prompt,
            port=GPU_SENSING_CLASSIFY_LLM.port,
        )

        patch = PromptPatchOutput.model_validate(result)

        # Save the patch
        patch_data = {
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "run_count_at_update": len(summaries),
            "classification_guidance": patch.classification_guidance,
            "radar_guidance": patch.radar_guidance,
            "verification_guidance": patch.verification_guidance,
            "rationale": patch.rationale,
        }

        path = _patches_path(user_id, domain)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(patch_data, indent=2, ensure_ascii=False))

        elapsed = time.time() - evolve_start
        logger.info(
            f"[PromptEvolver] Evolution complete in {elapsed:.1f}s — "
            f"rationale: {patch.rationale}"
        )
        if patch.classification_guidance:
            logger.info(f"[PromptEvolver] Classification patch: {patch.classification_guidance}")
        if patch.radar_guidance:
            logger.info(f"[PromptEvolver] Radar patch: {patch.radar_guidance}")
        if patch.verification_guidance:
            logger.info(f"[PromptEvolver] Verification patch: {patch.verification_guidance}")

        return patch_data

    except Exception as e:
        logger.warning(f"[PromptEvolver] Evolution failed (non-fatal): {e}")
        return None
