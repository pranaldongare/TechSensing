"""
Experience Memory — persists and loads run summaries for self-learning.

Storage: data/{user_id}/sensing/memory/run_summaries/{domain_slug}.jsonl
Each line is a JSON object representing one pipeline run's outcomes and
self-evaluation scores.

The memory is injected into prompts so the LLM can learn from past runs:
what it did well, what it missed, and what to focus on next time.
"""

import json
import logging
import os
import re
from datetime import datetime
from typing import List, Optional

import aiofiles

logger = logging.getLogger("sensing.experience_memory")

MAX_RUNS = 20  # Keep only last N runs per domain


def _domain_slug(domain: str) -> str:
    """Convert domain name to a safe filename slug."""
    slug = re.sub(r"[^a-z0-9]+", "_", domain.lower()).strip("_")
    return slug or "default"


def _summaries_path(user_id: str, domain: str) -> str:
    """Return the JSONL file path for a domain's run summaries."""
    slug = _domain_slug(domain)
    return os.path.join("data", user_id, "sensing", "memory", "run_summaries", f"{slug}.jsonl")


async def save_run_summary(user_id: str, domain: str, summary: dict) -> None:
    """Append a run summary to the domain's JSONL file.

    Trims to MAX_RUNS entries to prevent unbounded growth.
    """
    path = _summaries_path(user_id, domain)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    # Read existing lines
    lines = []
    if os.path.exists(path):
        try:
            async with aiofiles.open(path, "r", encoding="utf-8") as f:
                content = await f.read()
            lines = [line for line in content.strip().split("\n") if line.strip()]
        except Exception:
            lines = []

    # Append new summary
    lines.append(json.dumps(summary, ensure_ascii=False))

    # Trim to MAX_RUNS (keep newest)
    if len(lines) > MAX_RUNS:
        lines = lines[-MAX_RUNS:]

    # Rewrite file
    async with aiofiles.open(path, "w", encoding="utf-8") as f:
        await f.write("\n".join(lines) + "\n")

    logger.info(
        f"[ExperienceMemory] Saved run summary for '{domain}' "
        f"({len(lines)} total runs stored)"
    )


async def load_recent_summaries(
    user_id: str,
    domain: str,
    max_runs: int = 5,
) -> List[dict]:
    """Load the most recent N run summaries for a domain.

    Returns an empty list if no summaries exist.
    """
    path = _summaries_path(user_id, domain)
    if not os.path.exists(path):
        return []

    try:
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            content = await f.read()

        lines = [line for line in content.strip().split("\n") if line.strip()]
        recent = lines[-max_runs:]

        summaries = []
        for line in recent:
            try:
                summaries.append(json.loads(line))
            except json.JSONDecodeError:
                continue

        logger.info(
            f"[ExperienceMemory] Loaded {len(summaries)} recent summaries "
            f"for '{domain}'"
        )
        return summaries

    except Exception as e:
        logger.warning(f"[ExperienceMemory] Failed to load summaries: {e}")
        return []


def build_experience_block(summaries: List[dict]) -> str:
    """Format run summaries into a prompt block for injection.

    Returns an empty string if no summaries are available.
    """
    if not summaries:
        return ""

    parts = ["LEARNING FROM PREVIOUS RUNS:"]

    for i, s in enumerate(reversed(summaries)):
        run_date = s.get("run_date", "unknown")
        # Parse and format date nicely
        try:
            dt = datetime.fromisoformat(run_date)
            date_str = dt.strftime("%b %d")
        except (ValueError, TypeError):
            date_str = run_date[:10] if len(run_date) >= 10 else "unknown"

        scores = s.get("eval_scores", {})
        coverage = scores.get("coverage", "?")
        specificity = scores.get("specificity", "?")
        novelty = scores.get("novelty_accuracy", "?")
        overall = scores.get("overall", "?")

        label = "Last run" if i == 0 else f"Run {i + 1} ago"
        line = f"- {label} ({date_str}): coverage={coverage}/5, specificity={specificity}/5, novelty={novelty}/5, overall={overall}/5"

        weaknesses = s.get("weaknesses", [])
        if weaknesses:
            line += f". Weakness: \"{weaknesses[0]}\""

        reflection = s.get("reflection", "")
        if reflection:
            line += f". Reflection: \"{reflection}\""

        parts.append(line)

    # Compute recurring patterns across summaries
    all_scores = [s.get("eval_scores", {}) for s in summaries]

    # Find lowest-scoring criterion on average
    criteria = ["coverage", "specificity", "novelty_accuracy", "actionability", "coherence"]
    avg_scores = {}
    for criterion in criteria:
        values = [sc.get(criterion, 3) for sc in all_scores if isinstance(sc.get(criterion), (int, float))]
        if values:
            avg_scores[criterion] = sum(values) / len(values)

    if avg_scores:
        weakest = min(avg_scores, key=avg_scores.get)
        weakest_avg = avg_scores[weakest]
        if weakest_avg < 4.0:
            parts.append(
                f"- Recurring weakness: {weakest} (avg {weakest_avg:.1f}/5) — "
                f"pay extra attention to this criterion."
            )

    # Collect missed topics
    all_missed = set()
    for s in summaries[-3:]:  # Last 3 runs only
        for topic in s.get("missed_topics", []):
            all_missed.add(topic)

    if all_missed:
        parts.append(
            f"- Previously missed topics: {', '.join(sorted(all_missed))} — "
            f"watch for these."
        )

    return "\n".join(parts)
