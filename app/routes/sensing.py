"""
Tech Sensing API — on-demand tech sensing report generation.

Endpoints:
  POST   /sensing/generate              — kick off async report generation
  GET    /sensing/status/{tracking_id}  — poll for completion
  GET    /sensing/history               — list past reports
  DELETE /sensing/report/{report_id}    — delete a report
  GET    /sensing/compare               — compare two reports
"""

import asyncio
import json
import logging
import os
import traceback
import uuid
from datetime import datetime, timezone
from typing import List, Literal, Optional

import aiofiles
from fastapi import APIRouter, Body, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.socket_handler import sio
from core.llm.client import tracking_id_var
from core.utils.generation_status import (
    read_generation_status,
    write_failed_status,
    write_pending_status,
    write_result,
)

# Sensing pipeline can take 10-60+ min (RSS + DDG + LLM classify + LLM report).
# Override the global 8-min stale timeout for sensing status reads.
SENSING_STALE_TIMEOUT_MINUTES = 120

logger = logging.getLogger("sensing.routes")

router = APIRouter(prefix="/sensing", tags=["Tech Sensing"])


# --- Request/Response Models ---


class SensingGenerateRequest(BaseModel):
    domain: str = Field(default="Generative AI", description="Target domain / topic")
    custom_requirements: str = Field(
        default="",
        description="Additional user guidance for the report",
    )
    must_include: Optional[List[str]] = Field(
        default=None,
        description="Keywords to prioritize in article discovery and classification",
    )
    dont_include: Optional[List[str]] = Field(
        default=None,
        description="Keywords to exclude from article discovery and classification",
    )
    lookback_days: int = Field(
        default=7,
        description="Number of days to look back (7=last week, 30=last month)",
    )
    feed_urls: Optional[List[str]] = Field(
        default=None,
        description="Override default RSS feed URLs",
    )
    search_queries: Optional[List[str]] = Field(
        default=None,
        description="Override default search queries",
    )
    include_videos: bool = Field(
        default=False,
        description="Include YouTube video enrichment (requires YOUTUBE_API_KEY)",
    )


# --- Helpers ---


def _get_sensing_dir(user_id: str) -> str:
    """Storage path: data/{user_id}/sensing/"""
    return f"data/{user_id}/sensing"


# --- Generate ---


@router.post("/generate")
async def generate_sensing_report(
    request: Request,
    body: SensingGenerateRequest = Body(...),
):
    """Start async tech sensing report generation."""
    payload = request.state.user
    if not payload:
        raise HTTPException(status_code=401, detail="User not authenticated")

    user_id = payload.userId
    tracking_id = str(uuid.uuid4())
    sensing_dir = _get_sensing_dir(user_id)
    os.makedirs(sensing_dir, exist_ok=True)
    status_path = os.path.join(sensing_dir, f"status_{tracking_id}.json")
    # Write pending status with domain info so history can show in-progress jobs
    pending_data = {
        "_status": "pending",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "domain": body.domain,
        "tracking_id": tracking_id,
    }
    async with aiofiles.open(status_path, "w", encoding="utf-8") as f:
        await f.write(json.dumps(pending_data, ensure_ascii=False))

    async def _run():
        tracking_id_var.set(tracking_id)
        try:
            from core.sensing.pipeline import run_sensing_pipeline

            async def _progress_cb(stage, pct, msg):
                logger.info(f"[{tracking_id[:8]}] [{stage}] {pct}% — {msg}")
                await sio.emit(
                    f"{user_id}/sensing_progress",
                    {
                        "tracking_id": tracking_id,
                        "stage": stage,
                        "progress": pct,
                        "message": msg,
                    },
                )

            result = await run_sensing_pipeline(
                domain=body.domain,
                custom_requirements=body.custom_requirements,
                feed_urls=body.feed_urls,
                search_queries=body.search_queries,
                must_include=body.must_include,
                dont_include=body.dont_include,
                lookback_days=body.lookback_days,
                progress_callback=_progress_cb,
                user_id=user_id,
                include_videos=body.include_videos,
            )

            report_data = {
                "report": result.report.model_dump(),
                "meta": {
                    "tracking_id": tracking_id,
                    "domain": body.domain,
                    "raw_article_count": result.raw_article_count,
                    "deduped_article_count": result.deduped_article_count,
                    "classified_article_count": result.classified_article_count,
                    "execution_time_seconds": result.execution_time_seconds,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    # Preserve generation params for regeneration
                    "custom_requirements": body.custom_requirements,
                    "must_include": body.must_include,
                    "dont_include": body.dont_include,
                    "lookback_days": body.lookback_days,
                },
            }

            await write_result(status_path, report_data)

            # Also save a persistent copy
            report_path = os.path.join(
                sensing_dir, f"report_{tracking_id}.json"
            )
            async with aiofiles.open(report_path, "w", encoding="utf-8") as f:
                await f.write(
                    json.dumps(report_data, ensure_ascii=False, indent=2)
                )

            await sio.emit(
                f"{user_id}/sensing_progress",
                {
                    "tracking_id": tracking_id,
                    "stage": "complete",
                    "progress": 100,
                    "message": "Report ready",
                },
            )

        except Exception:
            error_details = traceback.format_exc()
            await write_failed_status(status_path, error_details)
            logger.error("Generation failed: %s", error_details)
            await sio.emit(
                f"{user_id}/sensing_progress",
                {
                    "tracking_id": tracking_id,
                    "stage": "error",
                    "progress": 0,
                    "message": "Report generation failed",
                },
            )

    asyncio.create_task(_run())

    return JSONResponse(
        content={
            "status": "pending",
            "tracking_id": tracking_id,
            "message": f"Generating Tech Sensing Report for '{body.domain}'",
        }
    )


# --- Generate Company-Scoped Report ---


class CompanyGenerateRequest(BaseModel):
    company_name: str = Field(description="Company name to focus on")
    domain: str = Field(default="", description="Optional domain / topic")
    lookback_days: int = Field(default=7, description="Lookback period in days")
    custom_requirements: str = Field(default="", description="Additional guidance")


@router.post("/generate-company")
async def generate_company_report(
    request: Request,
    body: CompanyGenerateRequest = Body(...),
):
    """Generate a company-focused sensing report using existing pipeline."""
    payload = request.state.user
    if not payload:
        raise HTTPException(status_code=401, detail="User not authenticated")

    user_id = payload.userId
    tracking_id = str(uuid.uuid4())
    sensing_dir = _get_sensing_dir(user_id)
    os.makedirs(sensing_dir, exist_ok=True)
    status_path = os.path.join(sensing_dir, f"status_{tracking_id}.json")

    # Resolve company aliases
    from core.sensing.aliases import load_aliases

    aliases_map = await load_aliases(user_id)
    company_terms = [body.company_name]
    for canonical, alias_list in aliases_map.items():
        if canonical.lower() == body.company_name.lower():
            company_terms.extend(alias_list)
            break

    # Domain defaults to company name if not specified
    domain = body.domain or body.company_name

    # Prepend company-focused instructions
    company_reqs = (
        f"This report should focus specifically on {body.company_name}. "
        f"Analyze their technology strategy, product launches, partnerships, "
        f"competitive positioning, and market moves. "
    )
    if body.custom_requirements:
        company_reqs += body.custom_requirements

    pending_data = {
        "_status": "pending",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "domain": domain,
        "tracking_id": tracking_id,
    }
    async with aiofiles.open(status_path, "w", encoding="utf-8") as f:
        await f.write(json.dumps(pending_data, ensure_ascii=False))

    async def _run():
        tracking_id_var.set(tracking_id)
        try:
            from core.sensing.pipeline import run_sensing_pipeline

            async def _progress_cb(stage, pct, msg):
                logger.info(f"[{tracking_id[:8]}] [{stage}] {pct}% — {msg}")
                await sio.emit(
                    f"{user_id}/sensing_progress",
                    {
                        "tracking_id": tracking_id,
                        "stage": stage,
                        "progress": pct,
                        "message": msg,
                    },
                )

            result = await run_sensing_pipeline(
                domain=domain,
                custom_requirements=company_reqs,
                must_include=company_terms,
                lookback_days=body.lookback_days,
                progress_callback=_progress_cb,
                user_id=user_id,
            )

            report_data = {
                "report": result.report.model_dump(),
                "meta": {
                    "tracking_id": tracking_id,
                    "domain": domain,
                    "company_focus": body.company_name,
                    "raw_article_count": result.raw_article_count,
                    "deduped_article_count": result.deduped_article_count,
                    "classified_article_count": result.classified_article_count,
                    "execution_time_seconds": result.execution_time_seconds,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "custom_requirements": company_reqs,
                    "must_include": company_terms,
                    "lookback_days": body.lookback_days,
                },
            }

            await write_result(status_path, report_data)

            report_path = os.path.join(
                sensing_dir, f"report_{tracking_id}.json"
            )
            async with aiofiles.open(report_path, "w", encoding="utf-8") as f:
                await f.write(
                    json.dumps(report_data, ensure_ascii=False, indent=2)
                )

            await sio.emit(
                f"{user_id}/sensing_progress",
                {
                    "tracking_id": tracking_id,
                    "stage": "complete",
                    "progress": 100,
                    "message": "Company report ready",
                },
            )

        except Exception:
            error_details = traceback.format_exc()
            await write_failed_status(status_path, error_details)
            await sio.emit(
                f"{user_id}/sensing_progress",
                {
                    "tracking_id": tracking_id,
                    "stage": "error",
                    "progress": 0,
                    "message": "Company report generation failed",
                },
            )

    asyncio.create_task(_run())

    return JSONResponse(
        content={
            "status": "pending",
            "tracking_id": tracking_id,
            "message": f"Generating company report for '{body.company_name}'",
        }
    )


# --- Generate from Document ---


@router.post("/generate-from-document")
async def generate_sensing_from_document(
    request: Request,
    file: UploadFile = File(...),
    domain: str = Form("Generative AI"),
    custom_requirements: str = Form(""),
    must_include: Optional[str] = Form(None),
    dont_include: Optional[str] = Form(None),
    lookback_days: int = Form(7),
    include_videos: bool = Form(False),
):
    """Start async tech sensing from an uploaded document instead of web
    sources."""
    payload = request.state.user
    if not payload:
        raise HTTPException(status_code=401, detail="User not authenticated")

    user_id = payload.userId
    tracking_id = str(uuid.uuid4())
    sensing_dir = _get_sensing_dir(user_id)
    os.makedirs(sensing_dir, exist_ok=True)
    status_path = os.path.join(sensing_dir, f"status_{tracking_id}.json")
    # Write pending status with domain info so history can show in-progress jobs
    pending_data = {
        "_status": "pending",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "domain": domain,
        "tracking_id": tracking_id,
    }
    async with aiofiles.open(status_path, "w", encoding="utf-8") as f:
        await f.write(json.dumps(pending_data, ensure_ascii=False))

    # Parse comma-separated keyword lists from form fields
    must_list = (
        [k.strip() for k in must_include.split(",") if k.strip()]
        if must_include
        else None
    )
    dont_list = (
        [k.strip() for k in dont_include.split(",") if k.strip()]
        if dont_include
        else None
    )

    # Save uploaded file temporarily
    upload_dir = os.path.join(sensing_dir, "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    safe_filename = file.filename or "document"
    file_path = os.path.join(upload_dir, f"{tracking_id}_{safe_filename}")
    async with aiofiles.open(file_path, "wb") as f:
        content = await file.read()
        await f.write(content)

    async def _run():
        tracking_id_var.set(tracking_id)
        try:
            from core.sensing.pipeline import run_sensing_pipeline_from_document

            async def _progress_cb(stage, pct, msg):
                logger.info(f"[{tracking_id[:8]}] [{stage}] {pct}% — {msg}")
                await sio.emit(
                    f"{user_id}/sensing_progress",
                    {
                        "tracking_id": tracking_id,
                        "stage": stage,
                        "progress": pct,
                        "message": msg,
                    },
                )

            result = await run_sensing_pipeline_from_document(
                file_path=file_path,
                file_name=safe_filename,
                domain=domain,
                custom_requirements=custom_requirements,
                must_include=must_list,
                dont_include=dont_list,
                lookback_days=lookback_days,
                include_videos=include_videos,
                progress_callback=_progress_cb,
                user_id=user_id,
            )

            report_data = {
                "report": result.report.model_dump(),
                "meta": {
                    "tracking_id": tracking_id,
                    "domain": domain,
                    "raw_article_count": result.raw_article_count,
                    "deduped_article_count": result.deduped_article_count,
                    "classified_article_count": result.classified_article_count,
                    "execution_time_seconds": result.execution_time_seconds,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "source_document": safe_filename,
                    "custom_requirements": custom_requirements,
                    "must_include": must_list,
                    "dont_include": dont_list,
                    "lookback_days": lookback_days,
                },
            }

            await write_result(status_path, report_data)

            # Save persistent copy
            report_path = os.path.join(
                sensing_dir, f"report_{tracking_id}.json"
            )
            async with aiofiles.open(report_path, "w", encoding="utf-8") as f:
                await f.write(
                    json.dumps(report_data, ensure_ascii=False, indent=2)
                )

            await sio.emit(
                f"{user_id}/sensing_progress",
                {
                    "tracking_id": tracking_id,
                    "stage": "complete",
                    "progress": 100,
                    "message": "Report ready",
                },
            )

        except Exception:
            error_details = traceback.format_exc()
            await write_failed_status(status_path, error_details)
            logger.error("Document generation failed: %s", error_details)
            await sio.emit(
                f"{user_id}/sensing_progress",
                {
                    "tracking_id": tracking_id,
                    "stage": "error",
                    "progress": 0,
                    "message": "Report generation failed",
                },
            )
        finally:
            # Clean up uploaded file
            try:
                os.remove(file_path)
            except Exception:
                pass

    asyncio.create_task(_run())

    return JSONResponse(
        content={
            "status": "pending",
            "tracking_id": tracking_id,
            "message": (
                f"Generating Tech Sensing Report from "
                f"'{safe_filename}' for '{domain}'"
            ),
        }
    )


# --- Status ---


@router.get("/status/{tracking_id}")
async def sensing_status(request: Request, tracking_id: str):
    """Poll for report generation status (with extended timeout for sensing)."""
    payload = request.state.user
    if not payload:
        raise HTTPException(status_code=401, detail="User not authenticated")

    user_id = payload.userId
    status_path = os.path.join(
        _get_sensing_dir(user_id), f"status_{tracking_id}.json"
    )

    gen_status = await _read_sensing_status(status_path)
    if gen_status is None:
        raise HTTPException(status_code=404, detail="Report not found")

    if gen_status["state"] == "pending":
        return JSONResponse(content={"status": "pending"})
    elif gen_status["state"] == "failed":
        return JSONResponse(
            content={"status": "failed", "error": gen_status.get("error", "")}
        )
    else:  # completed
        return JSONResponse(
            content={"status": "completed", "data": gen_status["data"]}
        )


async def _read_sensing_status(file_path: str) -> dict | None:
    """
    Custom status reader for sensing with a longer stale timeout (20 min).
    The global read_generation_status uses 8 min which is too short for
    the sensing pipeline (RSS + DDG + LLM classify batches + LLM report).
    """
    if not os.path.exists(file_path):
        return None

    try:
        async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
            content = await f.read()
    except Exception:
        return None

    if not content.strip():
        return {
            "state": "failed",
            "error": "Generation failed (empty status file). Please retry.",
        }

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return {"state": "failed", "error": "Corrupted status file. Please retry."}

    if not isinstance(data, dict):
        return {"state": "failed", "error": "Unexpected status file format."}

    status_field = data.get("_status")

    if status_field == "pending":
        started_at = data.get("started_at")
        if started_at:
            try:
                started = datetime.fromisoformat(started_at)
                elapsed = (datetime.now(timezone.utc) - started).total_seconds()
                if elapsed > SENSING_STALE_TIMEOUT_MINUTES * 60:
                    return {
                        "state": "failed",
                        "error": (
                            f"Generation timed out (no result after "
                            f"{SENSING_STALE_TIMEOUT_MINUTES} minutes). "
                            f"Please retry."
                        ),
                    }
            except (ValueError, TypeError):
                pass
        return {"state": "pending"}

    if status_field == "failed":
        return {"state": "failed", "error": data.get("error", "Unknown error")}

    # Completed (no _status key)
    return {"state": "completed", "data": data}


# --- Annotations ---


class AnnotationBody(BaseModel):
    key: str = Field(description="Annotation key: {tracking_id}:{item_type}:{item_key}")
    note: str = Field(description="The annotation text")
    item_type: str = Field(default="radar", description="Type of item being annotated")


@router.get("/annotations/{tracking_id}")
async def get_annotations(tracking_id: str, request: Request):
    """Get all annotations for a specific report."""
    payload = request.state.user
    if not payload:
        raise HTTPException(status_code=401, detail="User not authenticated")

    from core.sensing.annotations import load_annotations

    annotations = await load_annotations(payload.userId, tracking_id=tracking_id)
    return JSONResponse(content={"annotations": annotations})


@router.put("/annotations")
async def upsert_annotation(body: AnnotationBody, request: Request):
    """Create or update an annotation."""
    payload = request.state.user
    if not payload:
        raise HTTPException(status_code=401, detail="User not authenticated")

    from core.sensing.annotations import save_annotation

    annotations = await save_annotation(
        user_id=payload.userId,
        key=body.key,
        note=body.note,
        item_type=body.item_type,
    )
    return JSONResponse(content={"annotations": annotations})


@router.delete("/annotations")
async def remove_annotation(request: Request, key: str = ""):
    """Delete an annotation."""
    payload = request.state.user
    if not payload:
        raise HTTPException(status_code=401, detail="User not authenticated")

    if not key:
        raise HTTPException(status_code=400, detail="key parameter required")

    from core.sensing.annotations import delete_annotation

    annotations = await delete_annotation(user_id=payload.userId, key=key)
    return JSONResponse(content={"annotations": annotations})


# --- Search ---


@router.get("/search")
async def sensing_search(
    request: Request,
    q: str = "",
    domain: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 20,
):
    """Full-text search across stored sensing reports."""
    payload = request.state.user
    if not payload:
        raise HTTPException(status_code=401, detail="User not authenticated")

    if not q or len(q) < 2:
        return JSONResponse(content={"results": []})

    from core.sensing.report_search import search_reports

    results = await search_reports(
        user_id=payload.userId,
        query=q,
        domain=domain,
        date_from=date_from,
        date_to=date_to,
        max_results=min(limit, 50),
    )
    return JSONResponse(content={"results": results})


# --- History ---


@router.get("/history")
async def sensing_history(request: Request):
    """List past sensing reports for the current user."""
    payload = request.state.user
    if not payload:
        raise HTTPException(status_code=401, detail="User not authenticated")

    user_id = payload.userId
    sensing_dir = _get_sensing_dir(user_id)

    if not os.path.exists(sensing_dir):
        return JSONResponse(content={"reports": []})

    reports = []
    seen_ids = set()
    for fname in os.listdir(sensing_dir):
        if fname.startswith("report_") and fname.endswith(".json"):
            try:
                fpath = os.path.join(sensing_dir, fname)
                async with aiofiles.open(fpath, "r", encoding="utf-8") as f:
                    data = json.loads(await f.read())
                meta = data.get("meta", {})
                report = data.get("report", {})
                tid = meta.get("tracking_id")
                if tid:
                    seen_ids.add(tid)
                reports.append(
                    {
                        "tracking_id": tid,
                        "domain": meta.get("domain"),
                        "generated_at": meta.get("generated_at"),
                        "report_title": report.get("report_title", "Untitled"),
                        "total_articles": report.get(
                            "total_articles_analyzed", 0
                        ),
                        # Generation params for regeneration
                        "custom_requirements": meta.get("custom_requirements", ""),
                        "must_include": meta.get("must_include"),
                        "dont_include": meta.get("dont_include"),
                        "lookback_days": meta.get("lookback_days", 7),
                    }
                )
            except Exception:
                continue

    # Include in-progress (pending) reports from status files
    for fname in os.listdir(sensing_dir):
        if fname.startswith("status_") and fname.endswith(".json"):
            try:
                tid = fname.replace("status_", "").replace(".json", "")
                if tid in seen_ids:
                    continue  # Already have the completed report
                fpath = os.path.join(sensing_dir, fname)
                async with aiofiles.open(fpath, "r", encoding="utf-8") as f:
                    data = json.loads(await f.read())
                if data.get("_status") != "pending":
                    continue  # Only show actively generating jobs
                # Check if stale (past timeout)
                started_at = data.get("started_at")
                if started_at:
                    try:
                        started = datetime.fromisoformat(started_at)
                        elapsed = (datetime.now(timezone.utc) - started).total_seconds()
                        if elapsed > SENSING_STALE_TIMEOUT_MINUTES * 60:
                            continue  # Stale — don't show
                    except (ValueError, TypeError):
                        pass
                domain_name = data.get("domain", "Unknown")
                reports.append(
                    {
                        "tracking_id": tid,
                        "domain": domain_name,
                        "generated_at": data.get("started_at"),
                        "report_title": f"Generating: {domain_name}",
                        "total_articles": 0,
                        "status": "generating",
                    }
                )
            except Exception:
                continue

    reports.sort(key=lambda r: r.get("generated_at", ""), reverse=True)
    return JSONResponse(content={"reports": reports})


# --- Feeds ---


@router.get("/feeds")
async def sensing_feeds(request: Request, domain: str = "Generative AI"):
    """Return default RSS feeds and search queries for a domain."""
    from core.sensing.config import get_feeds_for_domain, get_search_queries_for_domain

    payload = request.state.user
    if not payload:
        raise HTTPException(status_code=401, detail="User not authenticated")

    feeds = get_feeds_for_domain(domain)
    queries = get_search_queries_for_domain(domain)
    return JSONResponse(content={"feeds": feeds, "queries": queries})


# --- Compare ---


@router.get("/compare")
async def sensing_compare(request: Request, a: str, b: str):
    """Compare two sensing reports by tracking ID."""
    from core.sensing.comparison import compare_reports

    payload = request.state.user
    if not payload:
        raise HTTPException(status_code=401, detail="User not authenticated")

    user_id = payload.userId
    sensing_dir = _get_sensing_dir(user_id)

    async def _load(tid: str) -> dict:
        fpath = os.path.join(sensing_dir, f"report_{tid}.json")
        if not os.path.exists(fpath):
            raise HTTPException(status_code=404, detail=f"Report {tid} not found")
        async with aiofiles.open(fpath, "r", encoding="utf-8") as f:
            return json.loads(await f.read())

    report_a = await _load(a)
    report_b = await _load(b)
    comparison = compare_reports(report_a, report_b)
    return JSONResponse(content=comparison.model_dump())


# --- Delete ---


@router.delete("/report/{report_id}")
async def delete_sensing_report(request: Request, report_id: str):
    """Delete a sensing report."""
    payload = request.state.user
    if not payload:
        raise HTTPException(status_code=401, detail="User not authenticated")

    user_id = payload.userId
    sensing_dir = _get_sensing_dir(user_id)

    for prefix in ("report_", "status_"):
        fpath = os.path.join(sensing_dir, f"{prefix}{report_id}.json")
        if os.path.exists(fpath):
            os.remove(fpath)

    return JSONResponse(content={"status": "deleted"})


# --- Topic Preferences ---


class TopicPrefUpdateRequest(BaseModel):
    domain: str
    technology_name: str
    interest: str = Field(description="One of: interested, not_interested, neutral")


@router.get("/topic-prefs")
async def get_topic_prefs(request: Request, domain: str = "Generative AI"):
    """Get topic preferences for a domain."""
    from core.sensing.topic_preferences import load_topic_preferences

    payload = request.state.user
    if not payload:
        raise HTTPException(status_code=401, detail="User not authenticated")

    prefs = await load_topic_preferences(payload.userId, domain)
    return JSONResponse(content=prefs.model_dump())


@router.put("/topic-prefs")
async def update_topic_pref(
    request: Request, body: TopicPrefUpdateRequest = Body(...)
):
    """Update a single topic's interest status."""
    from core.sensing.topic_preferences import mark_topic

    payload = request.state.user
    if not payload:
        raise HTTPException(status_code=401, detail="User not authenticated")

    if body.interest not in ("interested", "not_interested", "neutral"):
        raise HTTPException(
            status_code=400,
            detail="interest must be 'interested', 'not_interested', or 'neutral'",
        )

    prefs = await mark_topic(
        user_id=payload.userId,
        domain=body.domain,
        technology_name=body.technology_name,
        interest=body.interest,
    )
    return JSONResponse(content=prefs.model_dump())


# --- Schedules ---


class SensingScheduleRequest(BaseModel):
    domain: str = Field(default="Generative AI")
    frequency: str = Field(default="weekly", description="weekly|biweekly|monthly|daily")
    custom_requirements: str = Field(default="")
    must_include: Optional[List[str]] = None
    dont_include: Optional[List[str]] = None
    lookback_days: int = Field(default=7)


@router.post("/schedule")
async def create_schedule(request: Request, body: SensingScheduleRequest = Body(...)):
    """Create a new sensing report schedule."""
    from core.sensing.scheduler import add_schedule

    payload = request.state.user
    if not payload:
        raise HTTPException(status_code=401, detail="User not authenticated")

    schedule = await add_schedule({
        "user_id": payload.userId,
        "domain": body.domain,
        "frequency": body.frequency,
        "custom_requirements": body.custom_requirements,
        "must_include": body.must_include,
        "dont_include": body.dont_include,
        "lookback_days": body.lookback_days,
    })
    return JSONResponse(content=schedule)


@router.get("/schedules")
async def get_schedules(request: Request):
    """List user's sensing schedules."""
    from core.sensing.scheduler import list_schedules

    payload = request.state.user
    if not payload:
        raise HTTPException(status_code=401, detail="User not authenticated")

    schedules = await list_schedules(payload.userId)
    return JSONResponse(content={"schedules": schedules})


@router.put("/schedule/{schedule_id}")
async def update_schedule_endpoint(
    request: Request, schedule_id: str, body: dict = Body(...)
):
    """Update a schedule (enable/disable, change frequency, etc.)."""
    from core.sensing.scheduler import update_schedule

    payload = request.state.user
    if not payload:
        raise HTTPException(status_code=401, detail="User not authenticated")

    updated = await update_schedule(schedule_id, body)
    if not updated:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return JSONResponse(content=updated)


@router.delete("/schedule/{schedule_id}")
async def delete_schedule(request: Request, schedule_id: str):
    """Delete a sensing schedule."""
    from core.sensing.scheduler import remove_schedule

    payload = request.state.user
    if not payload:
        raise HTTPException(status_code=401, detail="User not authenticated")

    removed = await remove_schedule(schedule_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return JSONResponse(content={"status": "deleted"})


# --- Key Companies scheduled digests (#16) ---


class KeyCompaniesScheduleRequest(BaseModel):
    """Create a scheduled Key Companies briefing."""

    frequency: Literal["daily", "weekly", "biweekly", "monthly"] = "weekly"
    email: str = ""
    watchlist_id: str = ""
    companies: List[str] = Field(default_factory=list)
    highlight_domain: str = ""
    period_days: int = 7


@router.post("/key-companies/schedule")
async def create_key_companies_schedule(
    request: Request,
    body: KeyCompaniesScheduleRequest = Body(...),
):
    """Create a scheduled Key Companies briefing (#16)."""
    from core.sensing.scheduler import add_schedule

    payload = _require_user(request)

    if not body.watchlist_id and not body.companies:
        raise HTTPException(
            status_code=400,
            detail="Either watchlist_id or companies is required.",
        )

    schedule = await add_schedule(
        {
            "user_id": payload.userId,
            "kind": "key_companies",
            "frequency": body.frequency,
            "email": body.email,
            "watchlist_id": body.watchlist_id,
            "companies": body.companies,
            "highlight_domain": body.highlight_domain,
            "period_days": body.period_days,
        }
    )
    return JSONResponse(content=schedule)


# --- Timeline ---


@router.get("/timeline")
async def sensing_timeline(request: Request, domain: str = ""):
    """Build multi-report timeline for a domain."""
    from core.sensing.timeline import build_timeline

    payload = request.state.user
    if not payload:
        raise HTTPException(status_code=401, detail="User not authenticated")

    timeline = await build_timeline(
        user_id=payload.userId,
        domain=domain if domain else None,
    )
    return JSONResponse(content=timeline.model_dump())


# --- Org Context ---


class OrgContextRequest(BaseModel):
    tech_stack: List[str] = []
    industry: str = ""
    priorities: List[str] = []


@router.get("/org-context")
async def get_org_context(request: Request):
    """Get user's org tech context."""
    from core.sensing.org_context import load_org_context

    payload = request.state.user
    if not payload:
        raise HTTPException(status_code=401, detail="User not authenticated")

    context = await load_org_context(payload.userId)
    if not context:
        return JSONResponse(content={"tech_stack": [], "industry": "", "priorities": []})
    return JSONResponse(content=context.model_dump())


@router.put("/org-context")
async def update_org_context(
    request: Request, body: OrgContextRequest = Body(...)
):
    """Update user's org tech context."""
    from core.sensing.org_context import OrgTechContext, save_org_context

    payload = request.state.user
    if not payload:
        raise HTTPException(status_code=401, detail="User not authenticated")

    context = OrgTechContext(
        tech_stack=body.tech_stack,
        industry=body.industry,
        priorities=body.priorities,
    )
    await save_org_context(payload.userId, context)
    return JSONResponse(content=context.model_dump())


# --- One-Pager Export ---


class OnepagerRequest(BaseModel):
    tracking_id: str = Field(description="Report tracking ID to pull events from.")
    selected_indices: List[int] = Field(
        description="0-based indices into top_events (max 8)."
    )


@router.post("/onepager")
async def generate_onepager(
    request: Request,
    body: OnepagerRequest = Body(...),
):
    """Generate one-pager card data for selected top events via LLM."""
    from core.constants import GPU_SENSING_REPORT_LLM
    from core.llm.client import invoke_llm
    from core.llm.output_schemas.sensing_outputs import OnepagerOutput
    from core.llm.prompts.sensing_prompts import onepager_bullets_prompt

    payload = request.state.user
    if not payload:
        raise HTTPException(status_code=401, detail="User not authenticated")

    user_id = payload.userId
    sensing_dir = _get_sensing_dir(user_id)

    # Load the saved report
    report_path = os.path.join(sensing_dir, f"report_{body.tracking_id}.json")
    if not os.path.exists(report_path):
        raise HTTPException(status_code=404, detail="Report not found")

    async with aiofiles.open(report_path, "r", encoding="utf-8") as f:
        report_data = json.loads(await f.read())

    report = report_data.get("report", report_data)
    top_events = report.get("top_events", [])

    if not top_events:
        raise HTTPException(status_code=400, detail="Report has no top events")

    # Validate indices
    indices = [i for i in body.selected_indices if 0 <= i < len(top_events)]
    if not indices:
        raise HTTPException(status_code=400, detail="No valid event indices")
    indices = indices[:8]  # Cap at 8

    selected_events = [top_events[i] for i in indices]
    domain = report.get("domain", "Technology")
    date_range = report.get("date_range", "")

    # Build prompt and call LLM
    prompt = onepager_bullets_prompt(selected_events, domain)

    try:
        result = await invoke_llm(
            gpu_model=GPU_SENSING_REPORT_LLM.model,
            response_schema=OnepagerOutput,
            contents=prompt,
            port=GPU_SENSING_REPORT_LLM.port,
        )
        output = OnepagerOutput.model_validate(result)
    except Exception as e:
        logger.error("One-pager LLM call failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"One-pager generation failed: {e}",
        )

    return JSONResponse(
        content={
            "status": "ok",
            "cards": [c.model_dump() for c in output.cards],
            "domain": domain,
            "date_range": date_range,
        }
    )


# --- Deep Dive ---


class DeepDiveRequest(BaseModel):
    technology_name: str
    domain: str = Field(default="Generative AI")
    seed_question: str = ""
    seed_urls: List[str] = Field(default_factory=list)


@router.post("/deep-dive")
async def start_deep_dive(
    request: Request,
    body: DeepDiveRequest = Body(...),
):
    """Start async deep dive analysis on a technology."""
    payload = request.state.user
    if not payload:
        raise HTTPException(status_code=401, detail="User not authenticated")

    user_id = payload.userId
    tracking_id = str(uuid.uuid4())
    sensing_dir = _get_sensing_dir(user_id)
    os.makedirs(sensing_dir, exist_ok=True)
    status_path = os.path.join(sensing_dir, f"deepdive_status_{tracking_id}.json")
    await write_pending_status(status_path)

    async def _run():
        tracking_id_var.set(tracking_id)
        try:
            from core.sensing.deep_dive import run_deep_dive

            async def _progress_cb(stage, pct, msg):
                logger.info(f"[{tracking_id[:8]}] [deep_dive/{stage}] {pct}% — {msg}")
                await sio.emit(
                    f"{user_id}/sensing_progress",
                    {
                        "tracking_id": tracking_id,
                        "stage": stage,
                        "progress": pct,
                        "message": msg,
                    },
                )

            result = await run_deep_dive(
                technology_name=body.technology_name,
                domain=body.domain,
                user_id=user_id,
                progress_callback=_progress_cb,
                seed_question=body.seed_question,
                seed_urls=body.seed_urls or None,
            )

            report_data = result.model_dump()
            await write_result(status_path, report_data)

            # Save persistent copy with metadata for history listing
            persistent_data = {
                "report": report_data,
                "meta": {
                    "tracking_id": tracking_id,
                    "technology_name": body.technology_name,
                    "domain": body.domain,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                },
            }
            report_path = os.path.join(
                sensing_dir, f"deepdive_{tracking_id}.json"
            )
            async with aiofiles.open(report_path, "w", encoding="utf-8") as f:
                await f.write(
                    json.dumps(persistent_data, ensure_ascii=False, indent=2)
                )

            await sio.emit(
                f"{user_id}/sensing_progress",
                {
                    "tracking_id": tracking_id,
                    "stage": "complete",
                    "progress": 100,
                    "message": "Deep dive ready",
                },
            )

        except Exception:
            error_details = traceback.format_exc()
            await write_failed_status(status_path, error_details)
            await sio.emit(
                f"{user_id}/sensing_progress",
                {
                    "tracking_id": tracking_id,
                    "stage": "error",
                    "progress": 0,
                    "message": "Deep dive failed",
                },
            )

    asyncio.create_task(_run())

    return JSONResponse(
        content={
            "status": "pending",
            "tracking_id": tracking_id,
            "message": f"Deep dive starting for '{body.technology_name}'",
        }
    )


@router.get("/deep-dive/status/{tracking_id}")
async def deep_dive_status(request: Request, tracking_id: str):
    """Poll for deep dive status."""
    payload = request.state.user
    if not payload:
        raise HTTPException(status_code=401, detail="User not authenticated")

    user_id = payload.userId
    status_path = os.path.join(
        _get_sensing_dir(user_id), f"deepdive_status_{tracking_id}.json"
    )

    gen_status = await _read_sensing_status(status_path)
    if gen_status is None:
        raise HTTPException(status_code=404, detail="Deep dive not found")

    if gen_status["state"] == "pending":
        return JSONResponse(content={"status": "pending"})
    elif gen_status["state"] == "failed":
        return JSONResponse(
            content={"status": "failed", "error": gen_status.get("error", "")}
        )
    else:
        return JSONResponse(
            content={"status": "completed", "data": gen_status["data"]}
        )


# --- Deep Dive Follow-Up ---


# --- Deep Dive History & Load ---


@router.get("/deep-dive/history")
async def deep_dive_history(request: Request):
    """List past deep dive analyses for the current user."""
    payload = request.state.user
    if not payload:
        raise HTTPException(status_code=401, detail="User not authenticated")

    user_id = payload.userId
    sensing_dir = _get_sensing_dir(user_id)

    if not os.path.exists(sensing_dir):
        return JSONResponse(content={"deep_dives": []})

    deep_dives = []
    for fname in os.listdir(sensing_dir):
        # Match deepdive_{uuid}.json but NOT deepdive_status_* or deepdive_chat_*
        if not fname.startswith("deepdive_") or not fname.endswith(".json"):
            continue
        if fname.startswith("deepdive_status_") or fname.startswith("deepdive_chat_"):
            continue

        try:
            fpath = os.path.join(sensing_dir, fname)
            async with aiofiles.open(fpath, "r", encoding="utf-8") as f:
                data = json.loads(await f.read())

            # Handle both new format (with meta) and old format (flat report)
            if "meta" in data and isinstance(data.get("meta"), dict):
                meta = data["meta"]
                tracking_id = meta.get("tracking_id", "")
                technology_name = meta.get("technology_name", "")
                domain_val = meta.get("domain", "")
                generated_at = meta.get("generated_at", "")
            else:
                # Old format: flat DeepDiveReport — extract from filename and data
                tracking_id = fname.replace("deepdive_", "").replace(".json", "")
                technology_name = data.get("technology_name", "Unknown")
                domain_val = ""
                # Use file modification time as generated_at
                mtime = os.path.getmtime(fpath)
                generated_at = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()

            if not tracking_id:
                continue

            # Count conversation messages if chat file exists
            chat_path = os.path.join(sensing_dir, f"deepdive_chat_{tracking_id}.json")
            message_count = 0
            if os.path.exists(chat_path):
                try:
                    async with aiofiles.open(chat_path, "r", encoding="utf-8") as f:
                        chat_data = json.loads(await f.read())
                    if isinstance(chat_data, list):
                        message_count = len(chat_data)
                except Exception:
                    pass

            deep_dives.append({
                "tracking_id": tracking_id,
                "technology_name": technology_name,
                "domain": domain_val,
                "generated_at": generated_at,
                "message_count": message_count,
            })
        except Exception:
            continue

    deep_dives.sort(key=lambda d: d.get("generated_at", ""), reverse=True)
    return JSONResponse(content={"deep_dives": deep_dives})


@router.get("/deep-dive/{tracking_id}/full")
async def load_deep_dive(request: Request, tracking_id: str):
    """Load a specific deep dive report with its conversation history."""
    payload = request.state.user
    if not payload:
        raise HTTPException(status_code=401, detail="User not authenticated")

    user_id = payload.userId
    sensing_dir = _get_sensing_dir(user_id)
    deepdive_path = os.path.join(sensing_dir, f"deepdive_{tracking_id}.json")

    if not os.path.exists(deepdive_path):
        raise HTTPException(status_code=404, detail="Deep dive not found")

    try:
        async with aiofiles.open(deepdive_path, "r", encoding="utf-8") as f:
            data = json.loads(await f.read())
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to read deep dive")

    # Handle both new format (with meta) and old format (flat report)
    if "meta" in data and isinstance(data.get("meta"), dict):
        report = data["report"]
        meta = data["meta"]
    else:
        # Old format: flat DeepDiveReport
        report = data
        mtime = os.path.getmtime(deepdive_path)
        meta = {
            "tracking_id": tracking_id,
            "technology_name": data.get("technology_name", "Unknown"),
            "domain": "",
            "generated_at": datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat(),
        }

    # Load conversation history if exists
    chat_path = os.path.join(sensing_dir, f"deepdive_chat_{tracking_id}.json")
    conversation_history = []
    if os.path.exists(chat_path):
        try:
            async with aiofiles.open(chat_path, "r", encoding="utf-8") as f:
                conversation_history = json.loads(await f.read())
            if not isinstance(conversation_history, list):
                conversation_history = []
        except Exception:
            conversation_history = []

    return JSONResponse(content={
        "report": report,
        "conversation_history": conversation_history,
        "meta": meta,
    })


# --- Company Analysis ---


class CompanyAnalysisRequest(BaseModel):
    report_tracking_id: str = Field(
        default="",
        description=(
            "Tracking ID of the parent Tech Sensing report. "
            "Leave empty to run in standalone mode."
        ),
    )
    company_names: List[str] = Field(
        description="Company names to analyze (1-10)",
    )
    technology_names: List[str] = Field(
        default_factory=list,
        description=(
            "Technology/area names to analyze. In report-linked mode these "
            "are matched against radar items (or top items by signal "
            "strength when empty). In standalone mode this list is "
            "required and used verbatim."
        ),
    )
    domain: Optional[str] = Field(
        default=None,
        description=(
            "Domain label. Required for standalone mode; overrides the "
            "parent report's domain when provided in report-linked mode."
        ),
    )


@router.post("/company-analysis")
async def start_company_analysis(
    request: Request,
    body: CompanyAnalysisRequest = Body(...),
):
    """Start an async company analysis for a specific report."""
    payload = request.state.user
    if not payload:
        raise HTTPException(status_code=401, detail="User not authenticated")

    if not body.company_names or not any(c.strip() for c in body.company_names):
        raise HTTPException(
            status_code=400, detail="At least one company name is required"
        )

    # Standalone mode needs explicit technologies + domain
    if not body.report_tracking_id:
        if not body.technology_names or not any(
            t.strip() for t in body.technology_names
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Standalone analysis requires at least one technology "
                    "or area to analyze"
                ),
            )
        if not body.domain or not body.domain.strip():
            raise HTTPException(
                status_code=400,
                detail="Standalone analysis requires a domain",
            )

    user_id = payload.userId
    tracking_id = str(uuid.uuid4())
    sensing_dir = _get_sensing_dir(user_id)
    os.makedirs(sensing_dir, exist_ok=True)
    status_path = os.path.join(
        sensing_dir, f"company_analysis_status_{tracking_id}.json"
    )
    await write_pending_status(status_path)

    async def _run():
        tracking_id_var.set(tracking_id)
        try:
            from core.sensing.company_analysis import (
                run_company_analysis,
                save_company_analysis,
            )

            async def _progress_cb(stage, pct, msg):
                logger.info(f"[{tracking_id[:8]}] [company/{stage}] {pct}% — {msg}")
                await sio.emit(
                    f"{user_id}/sensing_progress",
                    {
                        "tracking_id": tracking_id,
                        "stage": stage,
                        "progress": pct,
                        "message": msg,
                    },
                )

            report = await run_company_analysis(
                user_id=user_id,
                company_names=body.company_names,
                technology_names=body.technology_names,
                report_tracking_id=body.report_tracking_id,
                domain=body.domain,
                progress_callback=_progress_cb,
                tracking_id=tracking_id,
            )

            await save_company_analysis(
                user_id=user_id,
                tracking_id=tracking_id,
                report=report,
                companies=report.companies_analyzed,
                technologies=report.technologies_analyzed,
            )

            payload_out = {
                "report": report.model_dump(),
                "meta": {
                    "tracking_id": tracking_id,
                    "report_tracking_id": body.report_tracking_id,
                    "domain": report.domain,
                    "companies": report.companies_analyzed,
                    "technologies": report.technologies_analyzed,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                },
            }
            await write_result(status_path, payload_out)

            await sio.emit(
                f"{user_id}/sensing_progress",
                {
                    "tracking_id": tracking_id,
                    "stage": "complete",
                    "progress": 100,
                    "message": "Company analysis ready",
                },
            )

        except Exception:
            error_details = traceback.format_exc()
            await write_failed_status(status_path, error_details)
            logger.error("Company analysis failed: %s", error_details)
            await sio.emit(
                f"{user_id}/sensing_progress",
                {
                    "tracking_id": tracking_id,
                    "stage": "error",
                    "progress": 0,
                    "message": "Company analysis failed",
                },
            )

    asyncio.create_task(_run())

    return JSONResponse(
        content={
            "status": "pending",
            "tracking_id": tracking_id,
            "message": "Company analysis starting",
        }
    )


@router.get("/company-analysis/status/{tracking_id}")
async def company_analysis_status(request: Request, tracking_id: str):
    """Poll for company analysis status."""
    payload = request.state.user
    if not payload:
        raise HTTPException(status_code=401, detail="User not authenticated")

    user_id = payload.userId
    status_path = os.path.join(
        _get_sensing_dir(user_id),
        f"company_analysis_status_{tracking_id}.json",
    )

    gen_status = await _read_sensing_status(status_path)
    if gen_status is None:
        raise HTTPException(status_code=404, detail="Company analysis not found")

    if gen_status["state"] == "pending":
        return JSONResponse(content={"status": "pending"})
    elif gen_status["state"] == "failed":
        return JSONResponse(
            content={"status": "failed", "error": gen_status.get("error", "")}
        )
    else:
        return JSONResponse(
            content={"status": "completed", "data": gen_status["data"]}
        )


@router.get("/company-analysis/history")
async def company_analysis_history(request: Request, report_tracking_id: Optional[str] = None):
    """List past company analyses, optionally filtered by parent report."""
    payload = request.state.user
    if not payload:
        raise HTTPException(status_code=401, detail="User not authenticated")

    user_id = payload.userId
    sensing_dir = _get_sensing_dir(user_id)

    if not os.path.exists(sensing_dir):
        return JSONResponse(content={"analyses": []})

    analyses = []
    for fname in os.listdir(sensing_dir):
        if not fname.startswith("company_analysis_") or not fname.endswith(".json"):
            continue
        if fname.startswith("company_analysis_status_"):
            continue

        try:
            fpath = os.path.join(sensing_dir, fname)
            async with aiofiles.open(fpath, "r", encoding="utf-8") as f:
                data = json.loads(await f.read())

            meta = data.get("meta", {}) if isinstance(data, dict) else {}
            tracking_id = meta.get("tracking_id") or fname.replace(
                "company_analysis_", ""
            ).replace(".json", "")
            parent_id = meta.get("report_tracking_id", "")

            if report_tracking_id and parent_id != report_tracking_id:
                continue

            analyses.append({
                "tracking_id": tracking_id,
                "report_tracking_id": parent_id,
                "domain": meta.get("domain", ""),
                "companies": meta.get("companies", []),
                "technologies": meta.get("technologies", []),
                "generated_at": meta.get("generated_at", ""),
            })
        except Exception:
            continue

    analyses.sort(key=lambda d: d.get("generated_at", ""), reverse=True)
    return JSONResponse(content={"analyses": analyses})


@router.get("/company-analysis/{tracking_id}/full")
async def load_company_analysis(request: Request, tracking_id: str):
    """Load a specific saved company analysis."""
    payload = request.state.user
    if not payload:
        raise HTTPException(status_code=401, detail="User not authenticated")

    user_id = payload.userId
    sensing_dir = _get_sensing_dir(user_id)
    path = os.path.join(sensing_dir, f"company_analysis_{tracking_id}.json")

    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Company analysis not found")

    try:
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            data = json.loads(await f.read())
    except Exception:
        raise HTTPException(
            status_code=500, detail="Failed to read company analysis"
        )

    return JSONResponse(content=data)


# --- Key Companies (weekly cross-domain briefings) ---


class KeyCompaniesRequest(BaseModel):
    company_names: List[str] = Field(
        description="Company names to include in the weekly briefing (1-12)."
    )
    highlight_domain: Optional[str] = Field(
        default="",
        description=(
            "Optional domain to emphasize (e.g., 'Generative AI'). When "
            "empty, the briefing is cross-domain."
        ),
    )
    period_days: Optional[int] = Field(
        default=7,
        description="Length of the briefing window in days (1-30).",
    )
    watchlist_id: Optional[str] = Field(
        default="",
        description=(
            "Optional watchlist id this run was kicked off from. Stored "
            "on the report so Phase 4 persistence features can tie runs "
            "back to the originating watchlist."
        ),
    )


@router.post("/key-companies")
async def start_key_companies(
    request: Request,
    body: KeyCompaniesRequest = Body(...),
):
    """Start an async Key Companies weekly briefing."""
    payload = request.state.user
    if not payload:
        raise HTTPException(status_code=401, detail="User not authenticated")

    if not body.company_names or not any(c.strip() for c in body.company_names):
        raise HTTPException(
            status_code=400, detail="At least one company name is required"
        )

    user_id = payload.userId
    tracking_id = str(uuid.uuid4())
    sensing_dir = _get_sensing_dir(user_id)
    os.makedirs(sensing_dir, exist_ok=True)
    status_path = os.path.join(
        sensing_dir, f"key_companies_status_{tracking_id}.json"
    )
    await write_pending_status(status_path)

    highlight_domain = (body.highlight_domain or "").strip()
    period_days = int(body.period_days or 7)

    async def _run():
        tracking_id_var.set(tracking_id)
        try:
            from core.sensing.key_companies import (
                run_key_companies,
                save_key_companies,
            )

            async def _progress_cb(stage, pct, msg):
                logger.info(f"[{tracking_id[:8]}] [key_companies/{stage}] {pct}% — {msg}")
                await sio.emit(
                    f"{user_id}/sensing_progress",
                    {
                        "tracking_id": tracking_id,
                        "stage": stage,
                        "progress": pct,
                        "message": msg,
                    },
                )

            report = await run_key_companies(
                user_id=user_id,
                company_names=body.company_names,
                highlight_domain=highlight_domain,
                period_days=period_days,
                progress_callback=_progress_cb,
                tracking_id=tracking_id,
                watchlist_id=(getattr(body, "watchlist_id", "") or ""),
            )

            await save_key_companies(
                user_id=user_id,
                tracking_id=tracking_id,
                report=report,
            )

            payload_out = {
                "report": report.model_dump(),
                "meta": {
                    "tracking_id": tracking_id,
                    "companies": report.companies_analyzed,
                    "highlight_domain": report.highlight_domain,
                    "period_days": report.period_days,
                    "period_start": report.period_start,
                    "period_end": report.period_end,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                },
            }
            await write_result(status_path, payload_out)

            await sio.emit(
                f"{user_id}/sensing_progress",
                {
                    "tracking_id": tracking_id,
                    "stage": "complete",
                    "progress": 100,
                    "message": "Key Companies briefing ready",
                },
            )
        except Exception:
            error_details = traceback.format_exc()
            await write_failed_status(status_path, error_details)
            logger.error("Key Companies failed: %s", error_details)
            await sio.emit(
                f"{user_id}/sensing_progress",
                {
                    "tracking_id": tracking_id,
                    "stage": "error",
                    "progress": 0,
                    "message": "Key Companies briefing failed",
                },
            )

    asyncio.create_task(_run())

    return JSONResponse(
        content={
            "status": "pending",
            "tracking_id": tracking_id,
            "message": "Key Companies briefing starting",
        }
    )


@router.get("/key-companies/status/{tracking_id}")
async def key_companies_status(request: Request, tracking_id: str):
    """Poll for Key Companies briefing status."""
    payload = request.state.user
    if not payload:
        raise HTTPException(status_code=401, detail="User not authenticated")

    user_id = payload.userId
    status_path = os.path.join(
        _get_sensing_dir(user_id),
        f"key_companies_status_{tracking_id}.json",
    )

    gen_status = await _read_sensing_status(status_path)
    if gen_status is None:
        raise HTTPException(status_code=404, detail="Key Companies briefing not found")

    if gen_status["state"] == "pending":
        return JSONResponse(content={"status": "pending"})
    elif gen_status["state"] == "failed":
        return JSONResponse(
            content={"status": "failed", "error": gen_status.get("error", "")}
        )
    else:
        return JSONResponse(
            content={"status": "completed", "data": gen_status["data"]}
        )


@router.get("/key-companies/history")
async def key_companies_history(request: Request):
    """List past Key Companies briefings for the current user."""
    payload = request.state.user
    if not payload:
        raise HTTPException(status_code=401, detail="User not authenticated")

    user_id = payload.userId
    sensing_dir = _get_sensing_dir(user_id)

    if not os.path.exists(sensing_dir):
        return JSONResponse(content={"briefings": []})

    briefings = []
    for fname in os.listdir(sensing_dir):
        if not fname.startswith("key_companies_") or not fname.endswith(".json"):
            continue
        if fname.startswith("key_companies_status_"):
            continue
        try:
            fpath = os.path.join(sensing_dir, fname)
            async with aiofiles.open(fpath, "r", encoding="utf-8") as f:
                data = json.loads(await f.read())
            meta = data.get("meta", {}) if isinstance(data, dict) else {}
            tracking_id = meta.get("tracking_id") or fname.replace(
                "key_companies_", ""
            ).replace(".json", "")
            briefings.append({
                "tracking_id": tracking_id,
                "companies": meta.get("companies", []),
                "highlight_domain": meta.get("highlight_domain", ""),
                "period_days": meta.get("period_days", 7),
                "period_start": meta.get("period_start", ""),
                "period_end": meta.get("period_end", ""),
                "generated_at": meta.get("generated_at", ""),
            })
        except Exception:
            continue

    briefings.sort(key=lambda d: d.get("generated_at", ""), reverse=True)
    return JSONResponse(content={"briefings": briefings})


@router.get("/key-companies/{tracking_id}/full")
async def load_key_companies(request: Request, tracking_id: str):
    """Load a specific saved Key Companies briefing."""
    payload = request.state.user
    if not payload:
        raise HTTPException(status_code=401, detail="User not authenticated")

    user_id = payload.userId
    sensing_dir = _get_sensing_dir(user_id)
    path = os.path.join(sensing_dir, f"key_companies_{tracking_id}.json")

    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Key Companies briefing not found")

    try:
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            data = json.loads(await f.read())
    except Exception:
        raise HTTPException(
            status_code=500, detail="Failed to read Key Companies briefing"
        )

    return JSONResponse(content=data)


# --- Collaboration ---


class VoteRequest(BaseModel):
    radar_item_name: str
    suggested_ring: str
    reasoning: str = ""


class CommentRequest(BaseModel):
    text: str
    radar_item_name: str = ""


@router.post("/share/{report_id}")
async def share_report(request: Request, report_id: str):
    """Create a shared report link."""
    from core.sensing.collaboration import create_shared_report

    payload = request.state.user
    if not payload:
        raise HTTPException(status_code=401, detail="User not authenticated")

    shared = await create_shared_report(
        report_tracking_id=report_id,
        owner_user_id=payload.userId,
    )
    return JSONResponse(content=shared.model_dump())


@router.get("/shared/{share_id}")
async def get_shared_report(request: Request, share_id: str):
    """Load a shared report (with the underlying report data)."""
    from core.sensing.collaboration import load_shared_report

    shared = await load_shared_report(share_id)
    if not shared:
        raise HTTPException(status_code=404, detail="Shared report not found")

    # Load the actual report data
    user_id = shared.owner_user_id
    sensing_dir = _get_sensing_dir(user_id)
    report_path = os.path.join(
        sensing_dir, f"report_{shared.report_tracking_id}.json"
    )

    report_data = None
    if os.path.exists(report_path):
        try:
            async with aiofiles.open(report_path, "r", encoding="utf-8") as f:
                report_data = json.loads(await f.read())
        except Exception:
            pass

    return JSONResponse(
        content={
            "shared": shared.model_dump(),
            "report": report_data,
        }
    )


@router.post("/shared/{share_id}/vote")
async def vote_on_shared(
    request: Request,
    share_id: str,
    body: VoteRequest = Body(...),
):
    """Add a ring vote to a shared report."""
    from core.sensing.collaboration import add_vote

    payload = request.state.user
    if not payload:
        raise HTTPException(status_code=401, detail="User not authenticated")

    vote = await add_vote(
        share_id=share_id,
        user_id=payload.userId,
        user_name=getattr(payload, 'name', payload.userId),
        radar_item_name=body.radar_item_name,
        suggested_ring=body.suggested_ring,
        reasoning=body.reasoning,
    )
    if not vote:
        raise HTTPException(status_code=404, detail="Shared report not found")
    return JSONResponse(content=vote.model_dump())


@router.post("/shared/{share_id}/comment")
async def comment_on_shared(
    request: Request,
    share_id: str,
    body: CommentRequest = Body(...),
):
    """Add a comment to a shared report."""
    from core.sensing.collaboration import add_comment

    payload = request.state.user
    if not payload:
        raise HTTPException(status_code=401, detail="User not authenticated")

    comment = await add_comment(
        share_id=share_id,
        user_id=payload.userId,
        user_name=getattr(payload, 'name', payload.userId),
        text=body.text,
        radar_item_name=body.radar_item_name,
    )
    if not comment:
        raise HTTPException(status_code=404, detail="Shared report not found")
    return JSONResponse(content=comment.model_dump())


@router.get("/shared/{share_id}/feedback")
async def get_shared_feedback(request: Request, share_id: str):
    """Get all votes and comments for a shared report."""
    from core.sensing.collaboration import get_feedback

    feedback = await get_feedback(share_id)
    if not feedback:
        raise HTTPException(status_code=404, detail="Shared report not found")
    return JSONResponse(content=feedback)


@router.get("/platform-status")
async def platform_status():
    """Auto-generated platform capabilities summary."""
    from core.sensing.platform_status import generate_platform_status

    status = generate_platform_status()
    return JSONResponse(content=status.model_dump())


@router.post("/source-feedback")
async def submit_source_feedback(
    request: Request,
    source_name: str = Body(...),
    vote: str = Body(...),  # "up" or "down"
):
    """Record user feedback on a source's quality."""
    from core.sensing.source_feedback import record_vote

    payload = request.state.user
    if not payload:
        raise HTTPException(status_code=401, detail="User not authenticated")
    if vote not in ("up", "down"):
        raise HTTPException(status_code=400, detail="vote must be 'up' or 'down'")

    feedback = await record_vote(payload.userId, source_name, vote)
    return JSONResponse(content={"status": "ok", "feedback": feedback})


@router.get("/source-feedback")
async def get_source_feedback(request: Request):
    """Get user's source quality feedback."""
    from core.sensing.source_feedback import load_source_feedback

    payload = request.state.user
    if not payload:
        raise HTTPException(status_code=401, detail="User not authenticated")

    feedback = await load_source_feedback(payload.userId)
    return JSONResponse(content=feedback)


@router.get("/dashboard")
async def sensing_dashboard(request: Request):
    """Cross-domain dashboard aggregating all tracked domains."""
    from core.sensing.dashboard import build_dashboard

    payload = request.state.user
    if not payload:
        raise HTTPException(status_code=401, detail="User not authenticated")

    dashboard = await build_dashboard(user_id=payload.userId)
    return JSONResponse(content=dashboard.model_dump())


@router.post("/query")
async def query_sensing_reports(
    request: Request,
    question: str = Body(...),
    domain: Optional[str] = Body(None),
):
    """Answer a natural language question using stored report data."""
    from core.sensing.query import query_reports

    payload = request.state.user
    if not payload:
        raise HTTPException(status_code=401, detail="User not authenticated")

    answer = await query_reports(
        user_id=payload.userId,
        question=question,
        domain=domain,
    )
    return JSONResponse(content=answer.model_dump())


# ───────────────────────────────────────────────────────────────
# Phase 1 — Quality & Trust: telemetry, aliases, exclusions,
# BYO URLs, watchlists
# ───────────────────────────────────────────────────────────────


def _require_user(request: Request):
    payload = request.state.user
    if not payload:
        raise HTTPException(status_code=401, detail="User not authenticated")
    return payload


@router.get("/telemetry/cost-summary")
async def get_cost_summary(
    request: Request,
    days: int = 30,
):
    """Aggregated cost/usage across all runs for the last N days."""
    from core.llm.telemetry import load_cost_summary

    payload = _require_user(request)
    data = await load_cost_summary(payload.userId, days=days)
    return JSONResponse(content=data)


@router.get("/telemetry/{tracking_id}")
async def get_run_telemetry(tracking_id: str, request: Request):
    """Cost/latency telemetry for one tracking_id (#28)."""
    from core.llm.telemetry import load_telemetry

    payload = _require_user(request)
    data = await load_telemetry(payload.userId, tracking_id)
    if data is None:
        return JSONResponse(content={"status": "not_found"}, status_code=404)
    return JSONResponse(content=data)


class AliasesBody(BaseModel):
    aliases: dict = Field(
        default_factory=dict,
        description="{canonical: [alias1, alias2, ...]}",
    )


@router.get("/config/aliases")
async def get_aliases(request: Request):
    """Return the current per-user alias map (#19)."""
    from core.sensing.aliases import load_aliases

    payload = _require_user(request)
    data = await load_aliases(payload.userId)
    return JSONResponse(content={"aliases": data})


@router.put("/config/aliases")
async def put_aliases(body: AliasesBody, request: Request):
    """Overwrite the per-user alias map (#19)."""
    from core.sensing.aliases import save_aliases

    payload = _require_user(request)
    await save_aliases(payload.userId, body.aliases or {})
    return JSONResponse(content={"status": "ok"})


class ExclusionsBody(BaseModel):
    exclusions: dict = Field(
        default_factory=dict,
        description="{global: [kw,...], per_company: {company: [kw,...]}}",
    )


@router.get("/config/exclusions")
async def get_exclusions(request: Request):
    """Return the current per-user exclusions (#20)."""
    from core.sensing.exclusions import load_exclusions

    payload = _require_user(request)
    data = await load_exclusions(payload.userId)
    return JSONResponse(content={"exclusions": data})


@router.put("/config/exclusions")
async def put_exclusions(body: ExclusionsBody, request: Request):
    """Overwrite the per-user exclusions (#20)."""
    from core.sensing.exclusions import save_exclusions

    payload = _require_user(request)
    await save_exclusions(payload.userId, body.exclusions or {})
    return JSONResponse(content={"status": "ok"})


class ByoUrlsBody(BaseModel):
    byo_urls: dict = Field(
        default_factory=dict,
        description="{company: [url, ...]}",
    )


@router.get("/config/byo-urls")
async def get_byo_urls(request: Request):
    """Return the current per-user BYO URL map (#18)."""
    from core.sensing.byo_urls import load_byo_urls

    payload = _require_user(request)
    data = await load_byo_urls(payload.userId)
    return JSONResponse(content={"byo_urls": data})


@router.put("/config/byo-urls")
async def put_byo_urls(body: ByoUrlsBody, request: Request):
    """Overwrite the per-user BYO URL map (#18)."""
    from core.sensing.byo_urls import save_byo_urls

    payload = _require_user(request)
    await save_byo_urls(payload.userId, body.byo_urls or {})
    return JSONResponse(content={"status": "ok"})


# ─── Watchlists (#15) ──────────────────────────────────────────


class WatchlistCreateBody(BaseModel):
    name: str = Field(..., min_length=1)
    companies: List[str] = Field(default_factory=list)
    highlight_domain: str = ""
    period_days: int = 7


class WatchlistUpdateBody(BaseModel):
    name: Optional[str] = None
    companies: Optional[List[str]] = None
    highlight_domain: Optional[str] = None
    period_days: Optional[int] = None


@router.get("/watchlists")
async def list_watchlists_route(request: Request):
    from core.sensing.watchlists import list_watchlists

    payload = _require_user(request)
    data = await list_watchlists(payload.userId)
    return JSONResponse(content={"watchlists": data})


@router.post("/watchlists")
async def create_watchlist_route(
    body: WatchlistCreateBody, request: Request
):
    from core.sensing.watchlists import create_watchlist

    payload = _require_user(request)
    wl = await create_watchlist(payload.userId, body.model_dump())
    return JSONResponse(content=wl)


@router.put("/watchlists/{watchlist_id}")
async def update_watchlist_route(
    watchlist_id: str, body: WatchlistUpdateBody, request: Request
):
    from core.sensing.watchlists import get_watchlist, update_watchlist

    payload = _require_user(request)
    # Merge partial update onto the current record so unset fields aren't
    # wiped by the sanitizer defaults.
    existing = await get_watchlist(payload.userId, watchlist_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    patch = body.model_dump(exclude_unset=True)
    merged = {**existing, **patch}
    updated = await update_watchlist(payload.userId, watchlist_id, merged)
    if updated is None:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    return JSONResponse(content=updated)


@router.delete("/watchlists/{watchlist_id}")
async def delete_watchlist_route(watchlist_id: str, request: Request):
    from core.sensing.watchlists import delete_watchlist

    payload = _require_user(request)
    ok = await delete_watchlist(payload.userId, watchlist_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    return JSONResponse(content={"status": "ok"})


# ──────────────────────────────────────────────────────────────
# Phase 3 — output richness endpoints (#14 timeline, #32 similar)
# ──────────────────────────────────────────────────────────────


@router.get("/company-timeline")
async def company_timeline_route(request: Request, companies: str = ""):
    """Return per-company timelines aggregated across saved runs (#14).

    ``companies`` is a comma-separated filter; empty = all companies.
    """
    from core.sensing.company_timeline import build_company_timeline

    payload = _require_user(request)
    filter_list = [c.strip() for c in companies.split(",") if c.strip()]
    timelines = await build_company_timeline(
        payload.userId, companies=filter_list or None
    )
    return JSONResponse(
        content={"timelines": [t.model_dump() for t in timelines]}
    )


class SimilarCompaniesBody(BaseModel):
    company: str
    domain: str = ""
    existing: List[str] = []
    max_suggestions: int = 5


@router.post("/similar-companies")
async def similar_companies_route(
    body: SimilarCompaniesBody, request: Request
):
    """On-demand peer-company expansion (#32)."""
    from core.constants import (
        GPU_SENSING_COMPANY_ANALYSIS_LLM as COMPANY_LLM,
    )
    from core.llm.client import invoke_llm
    from core.llm.prompts.analysis_prompts import (
        SimilarCompanies,
        similar_companies_prompt,
    )

    _require_user(request)
    if not body.company.strip():
        raise HTTPException(status_code=400, detail="company is required")

    prompt = similar_companies_prompt(
        seed_company=body.company.strip(),
        domain=body.domain.strip() or "Technology",
        existing_companies=body.existing,
        max_suggestions=max(1, min(body.max_suggestions, 10)),
    )
    try:
        result = await invoke_llm(
            gpu_model=COMPANY_LLM.model,
            response_schema=SimilarCompanies,
            contents=prompt,
            port=COMPANY_LLM.port,
        )
    except Exception as e:
        raise HTTPException(
            status_code=502, detail=f"similar-companies LLM call failed: {e}"
        )

    if not isinstance(result, SimilarCompanies):
        return JSONResponse(
            content={"companies": [], "rationale": ""}
        )
    return JSONResponse(content=result.model_dump())


# ──────────────────────────────────────────────────────────────
# Integrations config (Notion / Jira / Linear)  — #23 / #24
# ──────────────────────────────────────────────────────────────


class IntegrationConfigBody(BaseModel):
    provider: Literal["notion", "jira", "linear"]
    config: dict = Field(default_factory=dict)


@router.get("/integrations")
async def list_integrations_route(request: Request):
    """Return per-user integration configs with secrets redacted."""
    from core.sensing.integrations import load_integrations, redact

    payload = _require_user(request)
    data = await load_integrations(payload.userId)
    redacted = {k: redact(v) for k, v in data.items()}
    return JSONResponse(content={"integrations": redacted})


@router.put("/integrations")
async def set_integration_route(
    body: IntegrationConfigBody, request: Request
):
    """Upsert a single integration's config."""
    from core.sensing.integrations import set_integration, redact

    payload = _require_user(request)
    try:
        saved = await set_integration(payload.userId, body.provider, body.config)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return JSONResponse(content={"provider": body.provider, "config": redact(saved)})


@router.delete("/integrations/{provider}")
async def delete_integration_route(provider: str, request: Request):
    from core.sensing.integrations import delete_integration

    payload = _require_user(request)
    try:
        ok = await delete_integration(payload.userId, provider)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail="Not configured")
    return JSONResponse(content={"status": "ok"})


@router.post("/integrations/notion/verify")
async def verify_notion_route(request: Request):
    """Probe /users/me with the stored Notion token to confirm validity."""
    from core.sensing.integrations import get_integration
    from core.sensing.notion_export import verify_token

    payload = _require_user(request)
    cfg = await get_integration(payload.userId, "notion")
    token = (cfg or {}).get("token") or ""
    if not token:
        raise HTTPException(status_code=400, detail="Notion token not set")
    try:
        bot = await verify_token(token)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Notion auth failed: {e}")
    return JSONResponse(content={"status": "ok", "bot": bot})


# ──────────────────────────────────────────────────────────────
# Notion export endpoints (#23)
# ──────────────────────────────────────────────────────────────


class NotionExportBody(BaseModel):
    tracking_id: str
    parent_page_id: str = ""


async def _load_saved_report(
    user_id: str, kind: Literal["key_companies", "company_analysis"], tracking_id: str
) -> dict:
    filename = f"{kind}_{tracking_id}.json"
    path = os.path.join(_get_sensing_dir(user_id), filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"{kind} not found")
    async with aiofiles.open(path, "r", encoding="utf-8") as f:
        data = json.loads(await f.read())
    # Stored envelope is usually {report: ..., meta: ...}; unwrap if so.
    return data.get("report", data) if isinstance(data, dict) else data


@router.post("/export/notion/key-companies")
async def export_kc_to_notion(body: NotionExportBody, request: Request):
    from core.sensing.integrations import get_integration
    from core.sensing.notion_export import export_key_companies_to_notion

    payload = _require_user(request)
    cfg = await get_integration(payload.userId, "notion")
    token = (cfg or {}).get("token")
    parent = body.parent_page_id or (cfg or {}).get("default_parent_page_id")
    if not token or not parent:
        raise HTTPException(
            status_code=400,
            detail="Notion token + parent_page_id required",
        )
    report = await _load_saved_report(payload.userId, "key_companies", body.tracking_id)
    try:
        page = await export_key_companies_to_notion(
            token=token, parent_page_id=parent, report=report
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Notion export failed: {e}")
    return JSONResponse(content={"status": "ok", "page": page})


@router.post("/export/notion/company-analysis")
async def export_ca_to_notion(body: NotionExportBody, request: Request):
    from core.sensing.integrations import get_integration
    from core.sensing.notion_export import export_company_analysis_to_notion

    payload = _require_user(request)
    cfg = await get_integration(payload.userId, "notion")
    token = (cfg or {}).get("token")
    parent = body.parent_page_id or (cfg or {}).get("default_parent_page_id")
    if not token or not parent:
        raise HTTPException(
            status_code=400,
            detail="Notion token + parent_page_id required",
        )
    report = await _load_saved_report(
        payload.userId, "company_analysis", body.tracking_id
    )
    try:
        page = await export_company_analysis_to_notion(
            token=token, parent_page_id=parent, report=report
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Notion export failed: {e}")
    return JSONResponse(content={"status": "ok", "page": page})


# ──────────────────────────────────────────────────────────────
# Jira / Linear issue export endpoints (#24)
# ──────────────────────────────────────────────────────────────


class IssueExportItem(BaseModel):
    company: str = ""
    headline: str
    category: str = ""
    date: str = ""
    summary: str = ""
    source_url: str = ""
    domain: str = ""


class JiraExportBody(BaseModel):
    items: List[IssueExportItem]
    issue_type: str = "Task"


class LinearExportBody(BaseModel):
    items: List[IssueExportItem]
    priority: int = 0


@router.post("/integrations/jira/verify")
async def verify_jira_route(request: Request):
    from core.sensing.integrations import get_integration
    from core.sensing.jira_export import verify_jira

    payload = _require_user(request)
    cfg = await get_integration(payload.userId, "jira")
    if not cfg:
        raise HTTPException(status_code=400, detail="Jira not configured")
    try:
        user = await verify_jira(cfg)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Jira auth failed: {e}")
    return JSONResponse(content={"status": "ok", "user": user})


@router.post("/integrations/linear/verify")
async def verify_linear_route(request: Request):
    from core.sensing.integrations import get_integration
    from core.sensing.linear_export import verify_linear

    payload = _require_user(request)
    cfg = await get_integration(payload.userId, "linear")
    if not cfg:
        raise HTTPException(status_code=400, detail="Linear not configured")
    try:
        viewer = await verify_linear(cfg)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Linear auth failed: {e}")
    return JSONResponse(content={"status": "ok", "viewer": viewer})


@router.post("/export/jira")
async def export_to_jira(body: JiraExportBody, request: Request):
    """Create Jira issues for one or more sensing updates."""
    from core.sensing.integrations import get_integration
    from core.sensing.jira_export import create_jira_issue, format_update_description

    payload = _require_user(request)
    cfg = await get_integration(payload.userId, "jira")
    if not cfg or not cfg.get("api_token"):
        raise HTTPException(status_code=400, detail="Jira not configured")

    created = []
    errors = []
    for item in body.items:
        desc = format_update_description(
            item.model_dump(), company=item.company
        )
        try:
            issue = await create_jira_issue(
                cfg,
                summary=f"[Sensing] {item.headline}",
                description=desc,
                issue_type=body.issue_type,
                labels=["Auto-Sensing", item.category or "Uncategorized"],
            )
            created.append({"key": issue.get("key"), "id": issue.get("id")})
        except Exception as e:
            errors.append(f"{item.headline}: {e}")

    return JSONResponse(
        content={"created": created, "errors": errors},
        status_code=200 if not errors else 207,
    )


@router.post("/export/linear")
async def export_to_linear(body: LinearExportBody, request: Request):
    """Create Linear issues for one or more sensing updates."""
    from core.sensing.integrations import get_integration
    from core.sensing.linear_export import create_linear_issue, format_update_description

    payload = _require_user(request)
    cfg = await get_integration(payload.userId, "linear")
    if not cfg or not cfg.get("api_key"):
        raise HTTPException(status_code=400, detail="Linear not configured")

    created = []
    errors = []
    for item in body.items:
        desc = format_update_description(
            item.model_dump(), company=item.company
        )
        try:
            issue = await create_linear_issue(
                cfg,
                title=f"[Sensing] {item.headline}",
                description=desc,
                priority=body.priority,
            )
            created.append({
                "identifier": issue.get("identifier"),
                "url": issue.get("url"),
            })
        except Exception as e:
            errors.append(f"{item.headline}: {e}")

    return JSONResponse(
        content={"created": created, "errors": errors},
        status_code=200 if not errors else 207,
    )


# --- Model Releases (standalone) ---


class ModelReleasesRequest(BaseModel):
    lookback_days: int = Field(
        default=30,
        description="How many days to look back for model releases (1-90).",
        ge=1,
        le=90,
    )
    tracking_id: str = Field(
        default="",
        description="If provided, persist the refreshed releases back to this report.",
    )


@router.post("/model-releases")
async def get_latest_model_releases(
    request: Request,
    body: ModelReleasesRequest = Body(...),
):
    """Fetch latest model releases without running the full pipeline.

    Uses the 3-tier sourcing strategy:
      Tier 1: HuggingFace Hub API (open-weight models)
      Tier 2: Major AI lab blog RSS (proprietary models)
      Tier 3: DDG fallback (only if Tiers 1+2 yield <3 results)
    """
    payload = request.state.user
    if not payload:
        raise HTTPException(status_code=401, detail="User not authenticated")

    try:
        from core.sensing.sources.model_releases import get_model_releases

        releases = await get_model_releases(lookback_days=body.lookback_days)
        releases_dicts = [r.model_dump() for r in releases]

        # Persist to report if tracking_id provided
        if body.tracking_id:
            user_id = payload.userId
            sensing_dir = _get_sensing_dir(user_id)
            for fname in (
                f"status_{body.tracking_id}.json",
                f"report_{body.tracking_id}.json",
            ):
                fpath = os.path.join(sensing_dir, fname)
                if os.path.exists(fpath):
                    try:
                        async with aiofiles.open(fpath, "r", encoding="utf-8") as f:
                            report_data = json.loads(await f.read())
                        if "report" in report_data and isinstance(report_data["report"], dict):
                            report_data["report"]["model_releases"] = releases_dicts
                            async with aiofiles.open(fpath, "w", encoding="utf-8") as f:
                                await f.write(json.dumps(report_data, ensure_ascii=False, indent=2))
                    except Exception as e:
                        logger.warning(f"Failed to update model_releases in {fname}: {e}")

        return JSONResponse(
            content={
                "status": "ok",
                "lookback_days": body.lookback_days,
                "count": len(releases),
                "model_releases": releases_dicts,
            }
        )
    except Exception as e:
        logger.warning(f"Model releases standalone fetch failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Model releases fetch failed: {str(e)}",
        )


# --- AI Leaderboard ---


@router.post("/ai-leaderboard")
async def get_ai_leaderboard_data(request: Request):
    """Fetch AI model leaderboard data from Artificial Analysis API.

    Returns all models sorted by ranking metrics across categories:
    LLM Quality, LLM Speed, LLM Price, Image, Video, Speech.
    """
    payload = request.state.user
    if not payload:
        raise HTTPException(status_code=401, detail="User not authenticated")

    try:
        from core.sensing.sources.ai_leaderboard import get_ai_leaderboard

        leaderboard = await get_ai_leaderboard()
        return JSONResponse(content={
            "status": "ok",
            "categories": leaderboard,
        })
    except Exception as e:
        logger.warning(f"AI leaderboard fetch failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"AI leaderboard fetch failed: {str(e)}",
        )
