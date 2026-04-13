"""
Structured generation-status file utilities.

Replaces the old "empty lock file" pattern with a JSON status file that
tracks pending / failed / completed states, plus a stale-detection timeout
so a crashed generation never leaves the UI spinning forever.

Status file contents:
  - Pending:   {"_status": "pending", "started_at": "<ISO timestamp>"}
  - Failed:    {"_status": "failed",  "error": "...", "failed_at": "<ISO>"}
  - Completed: <actual result JSON — no _status key>
"""

from datetime import datetime, timezone
import json
import os

import aiofiles

# If a pending status file is older than this many minutes it is considered
# stale (i.e. the background task crashed without writing a result or error).
STALE_TIMEOUT_MINUTES = 8


# ------------------------------------------------------------------
# Writers (called from background generation tasks)
# ------------------------------------------------------------------


async def write_pending_status(file_path: str) -> None:
    """Create / overwrite the status file with a *pending* marker."""
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    payload = {
        "_status": "pending",
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
        await f.write(json.dumps(payload, ensure_ascii=False))


async def write_failed_status(file_path: str, error: str) -> None:
    """Overwrite the status file with a *failed* marker."""
    payload = {
        "_status": "failed",
        "error": error,
        "failed_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(payload, ensure_ascii=False))
    except Exception:
        # Last-resort: if we can't even write the error, leave the file as-is
        pass


async def write_result(file_path: str, result_data: dict) -> None:
    """Write the successful result to the status file (no _status key)."""
    async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
        await f.write(json.dumps(result_data, ensure_ascii=False, indent=2))


# ------------------------------------------------------------------
# Reader (called from route handlers when polling)
# ------------------------------------------------------------------


async def read_generation_status(file_path: str) -> dict | None:
    """
    Return the current generation state from the status file.

    Returns
    -------
    None
        File does not exist — no generation has been started.
    {"state": "pending"}
        Generation is in progress (status file has _status=="pending"
        and is not yet stale).
    {"state": "failed", "error": "..."}
        Generation failed, or the pending marker has gone stale.
    {"state": "completed", "data": { ... }}
        Generation succeeded; ``data`` is the parsed result dict.
    """
    if not os.path.exists(file_path):
        return None

    try:
        async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
            content = await f.read()
    except Exception:
        return None

    # Legacy: empty file left by old code — treat as stale/failed
    if not content.strip():
        return {
            "state": "failed",
            "error": "Generation appears to have failed (empty status file). Please retry.",
        }

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return {"state": "failed", "error": "Corrupted status file. Please retry."}

    if not isinstance(data, dict):
        return {
            "state": "failed",
            "error": "Unexpected status file format. Please retry.",
        }

    status_field = data.get("_status")

    # ---- Pending ----
    if status_field == "pending":
        started_at = data.get("started_at")
        if started_at:
            try:
                started = datetime.fromisoformat(started_at)
                elapsed = (datetime.now(timezone.utc) - started).total_seconds()
                if elapsed > STALE_TIMEOUT_MINUTES * 60:
                    return {
                        "state": "failed",
                        "error": f"Generation timed out (no result after {STALE_TIMEOUT_MINUTES} minutes). Please retry.",
                    }
            except (ValueError, TypeError):
                pass
        return {"state": "pending"}

    # ---- Failed ----
    if status_field == "failed":
        return {"state": "failed", "error": data.get("error", "Unknown error")}

    # ---- Completed (no _status key) ----
    return {"state": "completed", "data": data}
