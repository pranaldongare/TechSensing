"""
Experience Memory — persists and loads run summaries for self-learning.

Storage: data/{user_id}/sensing/memory/run_summaries/{domain_slug}.jsonl
Each line is a JSON object representing one pipeline run's outcomes and
self-evaluation scores.

The memory is injected into prompts so the LLM can learn from past runs:
what it did well, what it missed, and what to focus on next time.

Concurrency: a per-file asyncio lock guards the read-modify-write so two
report pipelines completing near-simultaneously cannot clobber each
other's saved entries.

Durability: writes are atomic — we write to a sibling ``.tmp`` file and
``os.replace`` it into place, so a crash mid-write leaves the previous
file intact instead of producing a truncated JSONL.
"""

import asyncio
import json
import logging
import os
import re
import traceback
from datetime import datetime
from typing import Dict, List

import aiofiles

logger = logging.getLogger("sensing.experience_memory")

MAX_RUNS = 20  # Keep only last N runs per domain

# Per-path locks: serializes save_run_summary calls targeting the same file
# so concurrent pipeline runs cannot lose entries via interleaved
# read-modify-write. Keyed by absolute path.
_PATH_LOCKS: Dict[str, asyncio.Lock] = {}


def _domain_slug(domain: str) -> str:
    """Convert domain name to a safe filename slug."""
    slug = re.sub(r"[^a-z0-9]+", "_", domain.lower()).strip("_")
    return slug or "default"


def _summaries_path(user_id: str, domain: str) -> str:
    """Return the JSONL file path for a domain's run summaries."""
    slug = _domain_slug(domain)
    return os.path.join("data", user_id, "sensing", "memory", "run_summaries", f"{slug}.jsonl")


def _get_lock(abs_path: str) -> asyncio.Lock:
    """Lazy per-path lock so the same file is never written by two coroutines at once."""
    lock = _PATH_LOCKS.get(abs_path)
    if lock is None:
        lock = asyncio.Lock()
        _PATH_LOCKS[abs_path] = lock
    return lock


async def save_run_summary(user_id: str, domain: str, summary: dict) -> None:
    """Append a run summary to the domain's JSONL file.

    - Per-file asyncio lock to serialize concurrent saves.
    - Atomic write via temp file + os.replace.
    - Trims to MAX_RUNS entries to prevent unbounded growth.
    """
    path = _summaries_path(user_id, domain)
    abs_path = os.path.abspath(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    lock = _get_lock(abs_path)
    async with lock:
        # Read existing lines
        lines: List[str] = []
        existed = os.path.exists(path)
        if existed:
            try:
                async with aiofiles.open(path, "r", encoding="utf-8") as f:
                    content = await f.read()
                lines = [line for line in content.strip().split("\n") if line.strip()]
                logger.debug(
                    f"[ExperienceMemory] Read existing file ({len(lines)} lines) at {abs_path}"
                )
            except Exception as read_err:
                logger.error(
                    f"[ExperienceMemory] Failed to read existing file at {abs_path}: "
                    f"{type(read_err).__name__}: {read_err} — starting fresh\n"
                    f"{traceback.format_exc()}"
                )
                lines = []

        # Serialize the new summary (catches non-serializable fields explicitly
        # so the user sees the actual offending value rather than a silent skip).
        try:
            new_line = json.dumps(summary, ensure_ascii=False, default=str)
        except (TypeError, ValueError) as ser_err:
            logger.error(
                f"[ExperienceMemory] Failed to JSON-serialize run summary: "
                f"{type(ser_err).__name__}: {ser_err}\n"
                f"  summary keys: {list(summary.keys())}\n"
                f"{traceback.format_exc()}"
            )
            return

        lines.append(new_line)

        # Trim to MAX_RUNS (keep newest)
        trimmed = False
        if len(lines) > MAX_RUNS:
            lines = lines[-MAX_RUNS:]
            trimmed = True

        # Atomic write: temp file then rename so a partial write can't corrupt
        # the existing file.
        tmp_path = path + ".tmp"
        try:
            async with aiofiles.open(tmp_path, "w", encoding="utf-8") as f:
                await f.write("\n".join(lines) + "\n")
            os.replace(tmp_path, path)
        except Exception as write_err:
            logger.error(
                f"[ExperienceMemory] Failed to write run summary to {abs_path}: "
                f"{type(write_err).__name__}: {write_err}\n"
                f"{traceback.format_exc()}"
            )
            # Best-effort cleanup of stale temp
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
            return

        try:
            size = os.path.getsize(path)
        except Exception:
            size = -1

        logger.info(
            f"[ExperienceMemory] SAVED run summary for '{domain}' "
            f"({len(lines)} total runs stored, {size} bytes, "
            f"trimmed={trimmed}, file_existed={existed}) -> {abs_path}"
        )


async def load_recent_summaries(
    user_id: str,
    domain: str,
    max_runs: int = 5,
) -> List[dict]:
    """Load the most recent N run summaries for a domain.

    Always logs the outcome (including the count and absolute path)
    so an absent log line cleanly signals 'load was never called'.
    Returns an empty list if no summaries exist.
    """
    path = _summaries_path(user_id, domain)
    abs_path = os.path.abspath(path)

    if not os.path.exists(path):
        logger.info(
            f"[ExperienceMemory] LOADED 0 summaries for '{domain}' "
            f"— file does not exist at {abs_path}"
        )
        return []

    try:
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            content = await f.read()

        lines = [line for line in content.strip().split("\n") if line.strip()]
        recent = lines[-max_runs:]

        summaries: List[dict] = []
        parse_failures = 0
        for line in recent:
            try:
                summaries.append(json.loads(line))
            except json.JSONDecodeError:
                parse_failures += 1
                continue

        logger.info(
            f"[ExperienceMemory] LOADED {len(summaries)} recent summaries "
            f"for '{domain}' (of {len(lines)} total, "
            f"{parse_failures} unparseable) from {abs_path}"
        )
        return summaries

    except Exception as e:
        logger.error(
            f"[ExperienceMemory] LOAD FAILED for '{domain}' at {abs_path}: "
            f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
        )
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
