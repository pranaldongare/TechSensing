"""
Diagnose Artificial Analysis video model retrieval.

Calls the AA video endpoints directly, lists every model with its raw
release_date, and shows which entries would pass/fail the date filter
for a given lookback. Useful to confirm whether a specific model
(e.g. "HappyHorse") is present in the AA response and whether our
filter is incorrectly rejecting it.

Usage:
    python scripts/diagnose_aa_video.py
    python scripts/diagnose_aa_video.py --lookback 60
    python scripts/diagnose_aa_video.py --search HappyHorse
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta

import httpx

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

API_BASE = "https://artificialanalysis.ai/api/v2"
VIDEO_ENDPOINTS = [
    "/data/media/text-to-video",
    "/data/media/image-to-video",
]


def parse_release_date(rd: str) -> tuple[datetime | None, str]:
    """Replicate the parsing logic in core/sensing/sources/model_releases.py
    so the diagnostic shows what the production code would compute.
    Returns (parsed_datetime, format_label)."""
    if not rd:
        return None, "empty"
    try:
        if len(rd) <= 7:
            base = datetime.strptime(rd, "%Y-%m")
            if base.month == 12:
                next_month_start = datetime(base.year + 1, 1, 1)
            else:
                next_month_start = datetime(base.year, base.month + 1, 1)
            return next_month_start - timedelta(days=1), "YYYY-MM (→ last day of month)"
        else:
            dt = datetime.fromisoformat(rd)
            if dt.tzinfo is not None:
                dt = dt.replace(tzinfo=None)
            return dt, "YYYY-MM-DD"
    except (ValueError, TypeError) as e:
        return None, f"unparsable ({e})"


async def fetch_endpoint(client: httpx.AsyncClient, endpoint: str, api_key: str) -> list:
    resp = await client.get(
        f"{API_BASE}{endpoint}",
        headers={"x-api-key": api_key},
    )
    resp.raise_for_status()
    payload = resp.json()
    if isinstance(payload, dict):
        return payload.get("data", [])
    if isinstance(payload, list):
        return payload
    return []


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lookback", type=int, default=30,
                        help="Lookback window in days (default 30)")
    parser.add_argument("--search", type=str, default="",
                        help="Case-insensitive substring to highlight (e.g. 'HappyHorse')")
    args = parser.parse_args()

    api_key = os.environ.get("ARTIFICIAL_ANALYSIS_API_KEY", "")
    if not api_key:
        print("ERROR: ARTIFICIAL_ANALYSIS_API_KEY not set in environment or .env")
        return 1

    now = datetime.utcnow()
    cutoff = now - timedelta(days=args.lookback)
    print(f"Now: {now.isoformat()}")
    print(f"Lookback: {args.lookback} days")
    print(f"Cutoff (anything before this is excluded): {cutoff.isoformat()}\n")

    found_search = []
    total_in_window = 0
    total_out_of_window = 0

    async with httpx.AsyncClient(timeout=30) as client:
        for endpoint in VIDEO_ENDPOINTS:
            print(f"=== {endpoint} ===")
            try:
                models = await fetch_endpoint(client, endpoint, api_key)
            except Exception as e:
                print(f"  FETCH FAILED: {type(e).__name__}: {e}\n")
                continue

            print(f"  Total models returned by AA: {len(models)}")
            in_win = 0
            out_win = 0
            no_date = 0

            for m in models:
                name = m.get("name", "?")
                creator = m.get("model_creator") or {}
                org = creator.get("name", "?") if isinstance(creator, dict) else "?"
                rd_raw = m.get("release_date", "")
                rd_dt, fmt = parse_release_date(rd_raw)

                # Status determination
                if rd_dt is None:
                    no_date += 1
                    status = f"NO DATE ({fmt})"
                elif rd_dt < cutoff:
                    out_win += 1
                    total_out_of_window += 1
                    status = f"OUT-OF-WINDOW ({rd_dt.date()})"
                else:
                    in_win += 1
                    total_in_window += 1
                    status = f"IN-WINDOW ({rd_dt.date()})"

                line = f"    - {name} ({org}) | raw={rd_raw!r} | {fmt} | {status}"

                if args.search and args.search.lower() in name.lower():
                    found_search.append((endpoint, m, rd_dt, status))
                    print(f"  *** MATCH: {line}")
                elif not args.search:
                    print(line)

            print(
                f"  Summary: in_window={in_win}, out_of_window={out_win}, "
                f"no_date={no_date}\n"
            )

    print("=" * 60)
    print(f"OVERALL: {total_in_window} in window, {total_out_of_window} out of window")
    if args.search:
        print(f"Searched for '{args.search}': {len(found_search)} matches")
        for endpoint, m, rd_dt, status in found_search:
            print(f"  Endpoint: {endpoint}")
            print(f"  Full record keys: {list(m.keys())}")
            print(f"  Status: {status}")
            print(f"  Full record: {m}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
