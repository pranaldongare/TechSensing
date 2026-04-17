"""
Sensing Report Scheduler — asyncio-based recurring report generation.

Persists schedules to data/sensing_schedules.json.
Runs a background loop every 60s checking for due schedules.
"""

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import aiofiles

logger = logging.getLogger("sensing.scheduler")

SCHEDULE_FILE = "data/sensing_schedules.json"
CHECK_INTERVAL_SECONDS = 60

_scheduler_task: Optional[asyncio.Task] = None
_schedules: list[dict] = []


async def start_scheduler() -> None:
    """Start the background scheduler loop."""
    global _scheduler_task
    await _load_schedules()
    _scheduler_task = asyncio.create_task(_scheduler_loop())
    logger.info(f"Scheduler started with {len(_schedules)} schedules")


async def _scheduler_loop() -> None:
    """Main scheduler loop — checks every 60s for due schedules."""
    while True:
        try:
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)
            now = datetime.now(timezone.utc)

            for schedule in _schedules:
                if not schedule.get("enabled", True):
                    continue

                next_run_str = schedule.get("next_run")
                if not next_run_str:
                    continue

                next_run = datetime.fromisoformat(next_run_str)
                if now >= next_run:
                    logger.info(
                        f"Schedule {schedule['id']} is due — "
                        f"running for domain '{schedule['domain']}'"
                    )
                    asyncio.create_task(_run_scheduled(schedule))

                    # Advance next_run
                    schedule["next_run"] = _compute_next_run(
                        schedule["frequency"], now
                    ).isoformat()
                    schedule["last_run"] = now.isoformat()
                    await _save_schedules()

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Scheduler loop error: {e}")


async def _run_scheduled(schedule: dict) -> None:
    """Execute a scheduled run. Dispatches on ``kind`` (#16)."""
    kind = (schedule.get("kind") or "sensing").lower()
    if kind == "key_companies":
        await _run_scheduled_key_companies(schedule)
        return
    await _run_scheduled_sensing(schedule)


async def _run_scheduled_sensing(schedule: dict) -> None:
    """Execute a scheduled sensing pipeline run."""
    try:
        from core.sensing.pipeline import run_sensing_pipeline

        result = await run_sensing_pipeline(
            domain=schedule.get("domain", "Generative AI"),
            custom_requirements=schedule.get("custom_requirements", ""),
            must_include=schedule.get("must_include"),
            dont_include=schedule.get("dont_include"),
            lookback_days=schedule.get("lookback_days", 7),
            user_id=schedule.get("user_id"),
        )

        # Save report to user's sensing dir
        user_id = schedule.get("user_id")
        if user_id:
            tracking_id = str(uuid.uuid4())
            sensing_dir = f"data/{user_id}/sensing"
            os.makedirs(sensing_dir, exist_ok=True)

            # Serialize alerts
            alerts_data = (
                [a.model_dump() for a in result.alerts]
                if result.alerts
                else []
            )

            report_data = {
                "report": result.report.model_dump(),
                "meta": {
                    "tracking_id": tracking_id,
                    "domain": schedule.get("domain", ""),
                    "raw_article_count": result.raw_article_count,
                    "deduped_article_count": result.deduped_article_count,
                    "classified_article_count": result.classified_article_count,
                    "execution_time_seconds": result.execution_time_seconds,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "scheduled": True,
                    "schedule_id": schedule["id"],
                    "alerts": alerts_data,
                },
            }

            report_path = os.path.join(sensing_dir, f"report_{tracking_id}.json")
            async with aiofiles.open(report_path, "w", encoding="utf-8") as f:
                await f.write(json.dumps(report_data, ensure_ascii=False, indent=2))

            logger.info(
                f"Scheduled report saved: {report_path} "
                f"({result.classified_article_count} articles)"
            )

            # Send email digest if configured
            try:
                from core.sensing.email_digest import is_smtp_configured, send_report_email
                if is_smtp_configured() and schedule.get("email"):
                    # Include alert summary in email for critical/high alerts
                    critical_alerts = [
                        a for a in alerts_data
                        if a.get("severity") in ("critical", "high")
                    ]
                    await send_report_email(
                        to_email=schedule["email"],
                        report_title=result.report.report_title,
                        domain=schedule.get("domain", ""),
                        executive_summary=result.report.executive_summary,
                        trends_count=len(result.report.key_trends),
                        radar_count=len(result.report.radar_items),
                    )
                    if critical_alerts:
                        logger.info(
                            f"Scheduled run produced {len(critical_alerts)} "
                            f"critical/high alerts for {schedule.get('domain')}"
                        )
            except Exception as e:
                logger.warning(f"Email digest failed: {e}")

            # Emit socket event if available
            try:
                from app.socket_handler import sio
                await sio.emit(
                    f"{user_id}/sensing_progress",
                    {
                        "tracking_id": tracking_id,
                        "stage": "complete",
                        "progress": 100,
                        "message": f"Scheduled report ready for {schedule.get('domain', '')}",
                    },
                )
                # Emit alerts via separate channel
                if alerts_data:
                    await sio.emit(
                        f"{user_id}/sensing_alerts",
                        {
                            "tracking_id": tracking_id,
                            "alerts": alerts_data,
                        },
                    )
            except Exception:
                pass

    except Exception as e:
        logger.error(f"Scheduled run failed for {schedule.get('id')}: {e}")


async def _run_scheduled_key_companies(schedule: dict) -> None:
    """Execute a scheduled Key Companies briefing (#16)."""
    try:
        from core.sensing.key_companies import (
            run_key_companies,
            save_key_companies,
        )
        from core.sensing.watchlists import get_watchlist

        user_id = schedule.get("user_id")
        if not user_id:
            return

        watchlist_id = schedule.get("watchlist_id") or ""
        companies = schedule.get("companies") or []
        highlight_domain = schedule.get("highlight_domain") or ""
        period_days = int(schedule.get("period_days") or 7)

        # Prefer current watchlist state if a watchlist_id was supplied.
        if watchlist_id:
            wl = await get_watchlist(user_id, watchlist_id)
            if wl:
                companies = wl.get("companies") or companies
                highlight_domain = (
                    wl.get("highlight_domain") or highlight_domain
                )
                period_days = int(wl.get("period_days") or period_days)

        if not companies:
            logger.warning(
                f"KC schedule {schedule.get('id')}: no companies to brief"
            )
            return

        tracking_id = str(uuid.uuid4())
        report = await run_key_companies(
            user_id=user_id,
            companies=companies,
            highlight_domain=highlight_domain,
            period_days=period_days,
            tracking_id=tracking_id,
            watchlist_id=watchlist_id,
        )
        await save_key_companies(user_id, tracking_id, report)

        logger.info(
            f"Scheduled KC briefing saved: user={user_id} "
            f"tracking_id={tracking_id} watchlist={watchlist_id}"
        )

        # Email digest
        try:
            from core.sensing.email_digest import (
                is_smtp_configured,
                send_key_companies_digest,
            )

            if is_smtp_configured() and schedule.get("email"):
                await send_key_companies_digest(
                    to_email=schedule["email"],
                    period_start=getattr(report, "period_start", "") or "",
                    period_end=getattr(report, "period_end", "") or "",
                    companies=list(getattr(report, "companies_analyzed", []) or []),
                    cross_company_summary=getattr(
                        report, "cross_company_summary", ""
                    )
                    or "",
                    briefings=[
                        b.model_dump() if hasattr(b, "model_dump") else b
                        for b in (getattr(report, "briefings", []) or [])
                    ],
                )
        except Exception as e:
            logger.warning(f"KC digest email failed: {e}")

        # Socket notification
        try:
            from app.socket_handler import sio

            await sio.emit(
                f"{user_id}/sensing_progress",
                {
                    "tracking_id": tracking_id,
                    "kind": "key_companies",
                    "stage": "complete",
                    "progress": 100,
                    "message": (
                        f"Scheduled Key Companies briefing ready "
                        f"({len(companies)} companies)"
                    ),
                },
            )
        except Exception:
            pass

    except Exception as e:
        logger.error(
            f"Scheduled KC run failed for {schedule.get('id')}: {e}"
        )


def _compute_next_run(frequency: str, from_dt: datetime) -> datetime:
    """Compute next run time from a base datetime."""
    if frequency == "weekly":
        return from_dt + timedelta(weeks=1)
    elif frequency == "biweekly":
        return from_dt + timedelta(weeks=2)
    elif frequency == "monthly":
        return from_dt + timedelta(days=30)
    elif frequency == "daily":
        return from_dt + timedelta(days=1)
    return from_dt + timedelta(weeks=1)


async def add_schedule(data: dict) -> dict:
    """Add a new schedule. Returns the created schedule."""
    kind = (data.get("kind") or "sensing").lower()
    schedule = {
        "id": str(uuid.uuid4()),
        "user_id": data["user_id"],
        "kind": kind,
        "domain": data.get("domain", "Generative AI"),
        "frequency": data.get("frequency", "weekly"),
        "custom_requirements": data.get("custom_requirements", ""),
        "must_include": data.get("must_include"),
        "dont_include": data.get("dont_include"),
        "lookback_days": data.get("lookback_days", 7),
        "enabled": True,
        "email": data.get("email", ""),
        # Key Companies specific — ignored for kind="sensing".
        "watchlist_id": data.get("watchlist_id", ""),
        "companies": data.get("companies") or [],
        "highlight_domain": data.get("highlight_domain", ""),
        "period_days": int(data.get("period_days") or 7),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "next_run": _compute_next_run(
            data.get("frequency", "weekly"),
            datetime.now(timezone.utc),
        ).isoformat(),
        "last_run": None,
    }
    _schedules.append(schedule)
    await _save_schedules()
    logger.info(
        f"Schedule added: {schedule['id']} "
        f"(kind={kind}, freq={schedule['frequency']})"
    )
    return schedule


async def remove_schedule(schedule_id: str) -> bool:
    """Remove a schedule by ID. Returns True if found and removed."""
    global _schedules
    before = len(_schedules)
    _schedules = [s for s in _schedules if s["id"] != schedule_id]
    if len(_schedules) < before:
        await _save_schedules()
        return True
    return False


async def update_schedule(schedule_id: str, updates: dict) -> Optional[dict]:
    """Update a schedule's fields. Returns the updated schedule or None."""
    for schedule in _schedules:
        if schedule["id"] == schedule_id:
            for key in (
                "enabled",
                "frequency",
                "domain",
                "custom_requirements",
                "must_include",
                "dont_include",
                "lookback_days",
                "email",
                "watchlist_id",
                "companies",
                "highlight_domain",
                "period_days",
                "kind",
            ):
                if key in updates:
                    schedule[key] = updates[key]
            if "frequency" in updates:
                schedule["next_run"] = _compute_next_run(
                    updates["frequency"],
                    datetime.now(timezone.utc),
                ).isoformat()
            await _save_schedules()
            return schedule
    return None


async def list_schedules(user_id: str) -> list[dict]:
    """List all schedules for a user."""
    return [s for s in _schedules if s.get("user_id") == user_id]


async def _load_schedules() -> None:
    """Load schedules from disk."""
    global _schedules
    if not os.path.exists(SCHEDULE_FILE):
        _schedules = []
        return
    try:
        async with aiofiles.open(SCHEDULE_FILE, "r", encoding="utf-8") as f:
            _schedules = json.loads(await f.read())
    except Exception:
        _schedules = []


async def _save_schedules() -> None:
    """Persist schedules to disk."""
    os.makedirs(os.path.dirname(SCHEDULE_FILE) or ".", exist_ok=True)
    try:
        async with aiofiles.open(SCHEDULE_FILE, "w", encoding="utf-8") as f:
            await f.write(json.dumps(_schedules, ensure_ascii=False, indent=2))
    except Exception as e:
        logger.error(f"Failed to save schedules: {e}")
