"""Notion exporter for Company Analysis + Key Companies reports (#23).

Uses Notion's official REST API (https://developers.notion.com/). The
user provides:

  - ``token``: a Notion integration secret (``secret_...``), created at
    https://www.notion.so/my-integrations.
  - ``parent_page_id``: any page the integration has been shared with;
    we create the export as a subpage.

Notion's rich-text block size limits (2000 chars per text block) are
handled by chunking.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("sensing.notion_export")


NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
MAX_TEXT_LEN = 1900  # Notion hard-caps at 2000; leave a margin.


# ──────────────────────────── block helpers ─────────────────────────


def _rt(text: str, *, bold: bool = False, italic: bool = False) -> Dict[str, Any]:
    return {
        "type": "text",
        "text": {"content": text[:MAX_TEXT_LEN]},
        "annotations": {
            "bold": bold,
            "italic": italic,
            "strikethrough": False,
            "underline": False,
            "code": False,
            "color": "default",
        },
    }


def _heading(text: str, level: int = 2) -> Dict[str, Any]:
    level = max(1, min(level, 3))
    key = f"heading_{level}"
    return {
        "object": "block",
        "type": key,
        key: {"rich_text": [_rt(text)]},
    }


def _paragraph(text: str, *, bold: bool = False) -> List[Dict[str, Any]]:
    # Chunk long text across multiple paragraph blocks.
    chunks = [text[i : i + MAX_TEXT_LEN] for i in range(0, len(text), MAX_TEXT_LEN)] or [""]
    return [
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": [_rt(c, bold=bold)]},
        }
        for c in chunks
    ]


def _bullet(text: str) -> Dict[str, Any]:
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": [_rt(text[:MAX_TEXT_LEN])]},
    }


def _numbered(text: str) -> Dict[str, Any]:
    return {
        "object": "block",
        "type": "numbered_list_item",
        "numbered_list_item": {"rich_text": [_rt(text[:MAX_TEXT_LEN])]},
    }


def _quote(text: str) -> Dict[str, Any]:
    return {
        "object": "block",
        "type": "quote",
        "quote": {"rich_text": [_rt(text[:MAX_TEXT_LEN])]},
    }


def _divider() -> Dict[str, Any]:
    return {"object": "block", "type": "divider", "divider": {}}


def _callout(text: str, emoji: str = "✨") -> Dict[str, Any]:
    return {
        "object": "block",
        "type": "callout",
        "callout": {
            "rich_text": [_rt(text[:MAX_TEXT_LEN])],
            "icon": {"type": "emoji", "emoji": emoji},
        },
    }


# ──────────────────────── report → blocks ───────────────────────────


def _key_companies_blocks(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    blocks: List[Dict[str, Any]] = []

    companies = report.get("companies_analyzed", []) or []
    period = f"{report.get('period_start','')} → {report.get('period_end','')}"
    blocks.append(
        _callout(
            f"Weekly briefing · {period} · {len(companies)} companies",
            emoji="📊",
        )
    )

    if report.get("highlight_domain"):
        blocks.extend(_paragraph(f"Highlight domain: {report['highlight_domain']}"))

    ds = report.get("diff_summary") or None
    if ds:
        blocks.append(_heading("Changes since last briefing", level=2))
        blocks.append(_bullet(f"NEW updates: {ds.get('new_count', 0)}"))
        blocks.append(_bullet(f"ONGOING updates: {ds.get('ongoing_count', 0)}"))
        for r in ds.get("resolved_topics", []) or []:
            blocks.append(_bullet(f"Closed: {r.get('company','')} — {r.get('headline','')}"))

    if report.get("cross_company_summary"):
        blocks.append(_heading("Cross-company summary", level=2))
        blocks.append(_quote(report["cross_company_summary"]))

    rollup = report.get("domain_rollup") or []
    if rollup:
        blocks.append(_heading("Domain rollup", level=2))
        for d in rollup:
            blocks.append(
                _bullet(
                    f"{d.get('domain','?')} — {d.get('update_count', 0)} updates across "
                    f"{d.get('company_count', 0)} companies"
                )
            )

    for b in report.get("briefings", []) or []:
        blocks.append(_divider())
        blocks.append(_heading(b.get("company", "?"), level=2))

        mom = b.get("momentum") or {}
        if isinstance(mom, dict) and "score" in mom:
            score = round(mom.get("score") or 0)
            band = "High" if score >= 70 else ("Moderate" if score >= 40 else "Quiet")
            drivers = ", ".join(mom.get("top_drivers") or [])
            blocks.extend(
                _paragraph(
                    f"Momentum: {score} ({band})" + (f" · {drivers}" if drivers else "")
                )
            )

        if b.get("overall_summary"):
            blocks.extend(_paragraph(b["overall_summary"]))

        for u in b.get("updates", []) or []:
            tag = u.get("category", "Other")
            date = u.get("date", "")
            diff = (u.get("diff") or {}).get("status", "")
            bits = [x for x in [tag, date, diff] if x]
            prefix = f"[{' · '.join(bits)}] " if bits else ""
            blocks.append(_bullet(f"{prefix}{u.get('headline','')}"))
            if u.get("summary"):
                blocks.extend(_paragraph(u["summary"]))
            if u.get("source_url"):
                blocks.extend(_paragraph(u["source_url"]))

    return blocks


def _company_analysis_blocks(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    blocks: List[Dict[str, Any]] = []

    companies = report.get("companies_analyzed", []) or []
    techs = report.get("technologies_analyzed", []) or []
    blocks.append(
        _callout(
            f"Company analysis · {len(companies)} companies × {len(techs)} technologies",
            emoji="🏢",
        )
    )

    if report.get("executive_summary"):
        blocks.append(_heading("Executive summary", level=2))
        blocks.append(_quote(report["executive_summary"]))

    ot = report.get("opportunity_threat") or None
    if ot:
        blocks.append(_heading("Opportunity / threat", level=2))
        for label, key, emoji in [
            ("Opportunities", "opportunities", "🎯"),
            ("Threats", "threats", "⚠️"),
            ("Recommended actions", "recommended_actions", "✅"),
        ]:
            items = ot.get(key) or []
            if items:
                blocks.extend(_paragraph(label, bold=True))
                for i in items:
                    blocks.append(_bullet(f"{emoji} {i}"))

    themes = report.get("strategic_themes") or []
    if themes:
        blocks.append(_heading("Strategic themes", level=2))
        for t in themes:
            blocks.append(_bullet(f"{t.get('theme','')} — {t.get('rationale','')}"))

    matrix = report.get("comparative_matrix") or []
    if matrix:
        blocks.append(_heading("Comparative matrix", level=2))
        for m in matrix:
            blocks.append(
                _bullet(
                    f"{m.get('technology','?')} → leader: {m.get('leader','?')}. "
                    f"{m.get('rationale','')}"
                )
            )

    profiles = report.get("company_profiles") or []
    for p in profiles:
        blocks.append(_divider())
        blocks.append(_heading(p.get("company", "?"), level=2))
        if p.get("overall_summary"):
            blocks.extend(_paragraph(p["overall_summary"]))
        for strength in p.get("strengths") or []:
            blocks.append(_bullet(f"Strength: {strength}"))
        for gap in p.get("gaps") or []:
            blocks.append(_bullet(f"Gap: {gap}"))
        for f in p.get("technology_findings") or []:
            blocks.append(_heading(f.get("technology", "?"), level=3))
            if f.get("summary"):
                blocks.extend(_paragraph(f["summary"]))
            conf = round((f.get("confidence") or 0) * 100)
            blocks.extend(
                _paragraph(f"Confidence: {conf}% · Stance: {f.get('stance','')}")
            )
            for url in f.get("source_urls") or []:
                blocks.extend(_paragraph(url))

    return blocks


# ──────────────────────────── HTTP client ───────────────────────────


def _headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


async def verify_token(token: str) -> Dict[str, Any]:
    """Quick sanity check: hit /users/me with the provided token.

    Returns the integration's "bot user" payload, or raises.
    """
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(f"{NOTION_API}/users/me", headers=_headers(token))
        r.raise_for_status()
        return r.json()


async def _create_page(
    token: str, parent_page_id: str, title: str, children: List[Dict[str, Any]]
) -> Dict[str, Any]:
    # Notion caps children at 100 per create call; we create the page
    # then append the rest.
    first_chunk = children[:100]
    rest = children[100:]

    payload = {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "properties": {
            "title": {"title": [_rt(title)]},
        },
        "children": first_chunk,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{NOTION_API}/pages", headers=_headers(token), json=payload
        )
        if r.status_code >= 400:
            logger.error(f"[notion] create page failed: {r.status_code} {r.text}")
            r.raise_for_status()
        page = r.json()
        page_id = page.get("id")

        # Append remaining blocks 100 at a time.
        while rest and page_id:
            chunk = rest[:100]
            rest = rest[100:]
            r2 = await client.patch(
                f"{NOTION_API}/blocks/{page_id}/children",
                headers=_headers(token),
                json={"children": chunk},
            )
            if r2.status_code >= 400:
                logger.error(
                    f"[notion] append children failed: {r2.status_code} {r2.text}"
                )
                r2.raise_for_status()

        return page


async def export_key_companies_to_notion(
    *, token: str, parent_page_id: str, report: Dict[str, Any]
) -> Dict[str, Any]:
    """Create a Notion subpage with the full Key Companies briefing.

    Returns the Notion ``page`` object (includes ``url``).
    """
    title = (
        f"Key Companies — {report.get('period_start','')}"
        f" → {report.get('period_end','')}"
    )
    blocks = _key_companies_blocks(report)
    return await _create_page(token, parent_page_id, title, blocks)


async def export_company_analysis_to_notion(
    *, token: str, parent_page_id: str, report: Dict[str, Any]
) -> Dict[str, Any]:
    """Create a Notion subpage with the full Company Analysis report."""
    n_co = len(report.get("companies_analyzed") or [])
    n_tech = len(report.get("technologies_analyzed") or [])
    title = f"Company Analysis — {n_co} companies × {n_tech} technologies"
    blocks = _company_analysis_blocks(report)
    return await _create_page(token, parent_page_id, title, blocks)
