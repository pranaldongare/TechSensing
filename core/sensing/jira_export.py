"""Jira issue creation from sensing updates (#24).

Uses Jira Cloud REST API v3 with Basic-Auth (email + API token).
Per-user credentials are stored via ``integrations.py``::

    {
        "base_url": "https://acme.atlassian.net",
        "email": "me@acme.com",
        "api_token": "xxx",
        "project_key": "TECH"
    }

Each created issue gets an ``[Auto-Sensing]`` label so users can filter
or bulk-manage them.
"""

from __future__ import annotations

import base64
import logging
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("sensing.jira_export")

JIRA_LABEL = "Auto-Sensing"


def _auth_header(email: str, api_token: str) -> str:
    b64 = base64.b64encode(f"{email}:{api_token}".encode()).decode()
    return f"Basic {b64}"


async def verify_jira(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Quick probe of /rest/api/3/myself to verify credentials."""
    base = (cfg.get("base_url") or "").rstrip("/")
    email = cfg.get("email") or ""
    token = cfg.get("api_token") or ""
    if not base or not email or not token:
        raise ValueError("base_url, email, and api_token are required")

    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{base}/rest/api/3/myself",
            headers={
                "Authorization": _auth_header(email, token),
                "Accept": "application/json",
            },
        )
        r.raise_for_status()
        return r.json()


async def create_jira_issue(
    cfg: Dict[str, Any],
    *,
    summary: str,
    description: str,
    issue_type: str = "Task",
    labels: Optional[List[str]] = None,
    priority: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a single Jira issue.

    Returns the Jira ``issue`` JSON payload (``key``, ``id``, ``self``).
    """
    base = (cfg.get("base_url") or "").rstrip("/")
    email = cfg.get("email") or ""
    token = cfg.get("api_token") or ""
    project_key = cfg.get("project_key") or ""

    if not base or not email or not token or not project_key:
        raise ValueError(
            "Jira config requires base_url, email, api_token, project_key"
        )

    all_labels = list(set([JIRA_LABEL] + (labels or [])))

    fields: Dict[str, Any] = {
        "project": {"key": project_key},
        "summary": summary[:255],
        "description": {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": description[:32000]}],
                }
            ],
        },
        "issuetype": {"name": issue_type},
        "labels": all_labels,
    }
    if priority:
        fields["priority"] = {"name": priority}

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{base}/rest/api/3/issues",
            headers={
                "Authorization": _auth_header(email, token),
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json={"fields": fields},
        )
        if r.status_code >= 400:
            logger.error(f"[jira] create issue failed: {r.status_code} {r.text}")
            r.raise_for_status()
        return r.json()


def format_update_description(
    update: Dict[str, Any], *, company: str = ""
) -> str:
    """Build a readable description from a sensing update dict."""
    parts: List[str] = []
    if company:
        parts.append(f"Company: {company}")
    if update.get("category"):
        parts.append(f"Category: {update['category']}")
    if update.get("date"):
        parts.append(f"Date: {update['date']}")
    if update.get("summary"):
        parts.append(f"\n{update['summary']}")
    if update.get("source_url"):
        parts.append(f"\nSource: {update['source_url']}")
    if update.get("domain"):
        parts.append(f"Domain: {update['domain']}")
    parts.append("\n---\nCreated automatically by Tech Sensing.")
    return "\n".join(parts)
