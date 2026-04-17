"""Linear issue creation from sensing updates (#24).

Uses Linear GraphQL API with a Personal API key.
Per-user credentials stored via ``integrations.py``::

    {
        "api_key": "lin_api_...",
        "team_id": "xxxxxxxx-xxxx-..."
    }
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("sensing.linear_export")

LINEAR_API = "https://api.linear.app/graphql"
LINEAR_LABEL_NAME = "Auto-Sensing"


def _headers(api_key: str) -> Dict[str, str]:
    return {
        "Authorization": api_key,
        "Content-Type": "application/json",
    }


async def verify_linear(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Probe Linear /graphql with a viewer query."""
    api_key = cfg.get("api_key") or ""
    if not api_key:
        raise ValueError("api_key is required")

    query = "query { viewer { id name email } }"
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            LINEAR_API,
            headers=_headers(api_key),
            json={"query": query},
        )
        r.raise_for_status()
        data = r.json()
        if "errors" in data:
            raise ValueError(data["errors"])
        return data.get("data", {}).get("viewer", {})


async def _get_or_create_label(api_key: str, team_id: str) -> Optional[str]:
    """Find or create the Auto-Sensing label. Returns label ID."""
    # Search existing labels.
    query = """
    query($teamId: String!) {
        issueLabels(filter: { team: { id: { eq: $teamId } }, name: { eq: "Auto-Sensing" } }) {
            nodes { id name }
        }
    }
    """
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            LINEAR_API,
            headers=_headers(api_key),
            json={"query": query, "variables": {"teamId": team_id}},
        )
        r.raise_for_status()
        nodes = (
            r.json().get("data", {}).get("issueLabels", {}).get("nodes", [])
        )
        if nodes:
            return nodes[0]["id"]

        # Create label.
        create = """
        mutation($teamId: String!, $name: String!) {
            issueLabelCreate(input: { teamId: $teamId, name: $name, color: "#6366f1" }) {
                issueLabel { id }
                success
            }
        }
        """
        r2 = await client.post(
            LINEAR_API,
            headers=_headers(api_key),
            json={
                "query": create,
                "variables": {"teamId": team_id, "name": LINEAR_LABEL_NAME},
            },
        )
        r2.raise_for_status()
        result = r2.json().get("data", {}).get("issueLabelCreate", {})
        return (result.get("issueLabel") or {}).get("id")


async def create_linear_issue(
    cfg: Dict[str, Any],
    *,
    title: str,
    description: str,
    priority: int = 0,
) -> Dict[str, Any]:
    """Create a single Linear issue. Returns ``{id, identifier, url}``."""
    api_key = cfg.get("api_key") or ""
    team_id = cfg.get("team_id") or ""
    if not api_key or not team_id:
        raise ValueError("Linear config requires api_key and team_id")

    label_id = await _get_or_create_label(api_key, team_id)

    mutation = """
    mutation($teamId: String!, $title: String!, $description: String!, $priority: Int, $labelIds: [String!]) {
        issueCreate(input: {
            teamId: $teamId,
            title: $title,
            description: $description,
            priority: $priority,
            labelIds: $labelIds
        }) {
            issue { id identifier url title }
            success
        }
    }
    """
    variables: Dict[str, Any] = {
        "teamId": team_id,
        "title": title[:255],
        "description": description[:10000],
        "priority": priority,
    }
    if label_id:
        variables["labelIds"] = [label_id]

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            LINEAR_API,
            headers=_headers(api_key),
            json={"query": mutation, "variables": variables},
        )
        r.raise_for_status()
        data = r.json()
        if "errors" in data:
            logger.error(f"[linear] create issue errors: {data['errors']}")
            raise ValueError(str(data["errors"]))
        result = data.get("data", {}).get("issueCreate", {})
        if not result.get("success"):
            raise RuntimeError("Linear issueCreate returned success=false")
        return result.get("issue", {})


def format_update_description(
    update: Dict[str, Any], *, company: str = ""
) -> str:
    """Build a Markdown description from a sensing update dict."""
    parts: List[str] = []
    if company:
        parts.append(f"**Company:** {company}")
    if update.get("category"):
        parts.append(f"**Category:** {update['category']}")
    if update.get("date"):
        parts.append(f"**Date:** {update['date']}")
    if update.get("summary"):
        parts.append(f"\n{update['summary']}")
    if update.get("source_url"):
        parts.append(f"\n[Source]({update['source_url']})")
    if update.get("domain"):
        parts.append(f"**Domain:** {update['domain']}")
    parts.append("\n---\n_Created automatically by Tech Sensing._")
    return "\n".join(parts)
