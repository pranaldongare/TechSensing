"""
Diagnose the TechSensing self-learning memory system.

Walks ``data/`` under the current working directory, lists every
run-summaries JSONL, prompt-patches JSON, topic-preferences JSON, and
annotations JSON it finds with absolute paths, entry counts, and last
modified times.

Useful when a user reports "memory only saved for one run". Run this
on the server to confirm:

  1. The CWD matches where the backend was started (relative paths can
     drift across systemd vs. ad-hoc launches).
  2. Each domain has the run count you expect.
  3. The latest entry's timestamp matches your most recent report run.
  4. Two runs for the same domain didn't accidentally produce two slugs
     (e.g. "Generative AI" → ``generative_ai.jsonl`` vs "GenAI" →
     ``genai.jsonl``).

Usage:
    python scripts/diagnose_memory.py
    python scripts/diagnose_memory.py --root /path/to/techsensing
    python scripts/diagnose_memory.py --user default_user
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import List, Optional


def _fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


def _fmt_mtime(path: Path) -> str:
    try:
        ts = path.stat().st_mtime
        return dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except OSError:
        return "?"


def _count_jsonl_lines(path: Path) -> tuple[int, int]:
    """Return (total_lines, parseable_json_objects)."""
    total = 0
    parseable = 0
    try:
        with path.open(encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                total += 1
                try:
                    json.loads(line)
                    parseable += 1
                except json.JSONDecodeError:
                    pass
    except OSError:
        pass
    return total, parseable


def _last_entry(path: Path) -> Optional[dict]:
    last = None
    try:
        with path.open(encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    last = json.loads(line)
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return last


def _diag_run_summaries(data_root: Path, user_filter: Optional[str]) -> int:
    print("=" * 72)
    print("RUN SUMMARIES  (data/<user>/sensing/memory/run_summaries/<slug>.jsonl)")
    print("=" * 72)
    pattern = "*/sensing/memory/run_summaries/*.jsonl"
    found = 0
    for path in sorted(data_root.glob(pattern)):
        user = path.parts[-5] if len(path.parts) >= 5 else "?"
        if user_filter and user != user_filter:
            continue
        slug = path.stem
        size = path.stat().st_size if path.exists() else 0
        total, parseable = _count_jsonl_lines(path)
        last = _last_entry(path)
        last_run_date = (last or {}).get("run_date", "?")
        last_overall = ((last or {}).get("eval_scores") or {}).get("overall", "?")
        print(
            f"\n  user='{user}'  slug='{slug}'\n"
            f"    path:    {path.resolve()}\n"
            f"    size:    {_fmt_size(size)}\n"
            f"    mtime:   {_fmt_mtime(path)}\n"
            f"    entries: {parseable} parseable / {total} total\n"
            f"    last:    run_date={last_run_date}, overall={last_overall}"
        )
        found += 1
    if found == 0:
        print("\n  (none found)")
    return found


def _diag_prompt_patches(data_root: Path, user_filter: Optional[str]) -> int:
    print("\n" + "=" * 72)
    print("PROMPT PATCHES  (data/<user>/sensing/memory/prompt_patches/<slug>.json)")
    print("=" * 72)
    pattern = "*/sensing/memory/prompt_patches/*.json"
    found = 0
    for path in sorted(data_root.glob(pattern)):
        user = path.parts[-5] if len(path.parts) >= 5 else "?"
        if user_filter and user != user_filter:
            continue
        slug = path.stem
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            data = {"_error": f"{type(e).__name__}: {e}"}
        keys = sorted(data.keys())
        print(
            f"\n  user='{user}'  slug='{slug}'\n"
            f"    path:        {path.resolve()}\n"
            f"    mtime:       {_fmt_mtime(path)}\n"
            f"    keys:        {keys}\n"
            f"    updated_at:  {data.get('updated_at', '?')}\n"
            f"    rationale:   {(data.get('rationale') or '')[:200]}"
        )
        found += 1
    if found == 0:
        print("\n  (none found)")
    return found


def _diag_topic_prefs(data_root: Path, user_filter: Optional[str]) -> int:
    print("\n" + "=" * 72)
    print("TOPIC PREFERENCES  (data/<user>/sensing/topic_prefs_<slug>.json)")
    print("=" * 72)
    pattern = "*/sensing/topic_prefs_*.json"
    found = 0
    for path in sorted(data_root.glob(pattern)):
        user = path.parts[-3] if len(path.parts) >= 3 else "?"
        if user_filter and user != user_filter:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        interested = data.get("interested", [])
        not_interested = data.get("not_interested", [])
        print(
            f"\n  user='{user}'  domain='{data.get('domain', '?')}'\n"
            f"    path:           {path.resolve()}\n"
            f"    interested:     {len(interested)}  {interested[:5]}\n"
            f"    not_interested: {len(not_interested)}  {not_interested[:5]}"
        )
        found += 1
    if found == 0:
        print("\n  (none found)")
    return found


def _diag_annotations(data_root: Path, user_filter: Optional[str]) -> int:
    print("\n" + "=" * 72)
    print("ANNOTATIONS  (data/<user>/sensing/annotations.json)")
    print("=" * 72)
    pattern = "*/sensing/annotations.json"
    found = 0
    for path in sorted(data_root.glob(pattern)):
        user = path.parts[-3] if len(path.parts) >= 3 else "?"
        if user_filter and user != user_filter:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        print(
            f"\n  user='{user}'\n"
            f"    path:    {path.resolve()}\n"
            f"    entries: {len(data)}"
        )
        found += 1
    if found == 0:
        print("\n  (none found)")
    return found


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".", help="Project root containing 'data/' (default: CWD)")
    parser.add_argument("--user", default=None, help="Filter to a single user_id")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    data_root = root / "data"

    print(f"Project root: {root}")
    print(f"Data root:    {data_root} (exists={data_root.exists()})")
    if not data_root.exists():
        print("\nERROR: data/ directory does not exist under this root. Is the CWD correct?")
        return 1

    summary_count = _diag_run_summaries(data_root, args.user)
    patch_count = _diag_prompt_patches(data_root, args.user)
    pref_count = _diag_topic_prefs(data_root, args.user)
    annot_count = _diag_annotations(data_root, args.user)

    print("\n" + "=" * 72)
    print("SUMMARY")
    print("=" * 72)
    print(f"  Run summary files:    {summary_count}")
    print(f"  Prompt patch files:   {patch_count}")
    print(f"  Topic preference:     {pref_count}")
    print(f"  Annotation files:     {annot_count}")
    print()
    print("Interpretation hints:")
    print("  - If you generated N reports for one domain and you see <N entries")
    print("    in run_summaries, the save block failed on some runs. Check logs")
    print("    for '[SelfLearning] save_run_summary FAILED' or '[ExperienceMemory]'")
    print("    error lines.")
    print("  - If you see two slugs under one user for what should be the same")
    print("    domain (e.g. 'generative_ai' AND 'genai'), the domain string is")
    print("    varying between runs.")
    print("  - If the data root above isn't what you expect, the backend was")
    print("    likely started from a different working directory.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
