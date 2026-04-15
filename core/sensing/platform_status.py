"""
Platform Status — auto-generates a capabilities summary from the codebase.
"""

import os
import logging
from datetime import datetime, timezone
from typing import List

from pydantic import BaseModel, Field

logger = logging.getLogger("sensing.platform_status")


class SourceStatus(BaseModel):
    name: str
    file: str
    requires_api_key: bool
    api_key_env_var: str = ""


class PlatformStatus(BaseModel):
    generated_at: str
    data_sources: List[SourceStatus]
    pipeline_stages: List[str]
    post_processing_modules: List[str]
    frontend_views: List[str]
    export_formats: List[str]
    api_endpoint_count: int
    total_python_files: int
    total_lines_of_code: int


def generate_platform_status() -> PlatformStatus:
    """Generate platform status by inspecting the codebase."""

    # Data sources
    sources_dir = "core/sensing/sources"
    data_sources = []
    source_files = [
        f for f in os.listdir(sources_dir)
        if f.endswith(".py") and f != "__init__.py"
    ] if os.path.exists(sources_dir) else []

    # Map known sources to their API key requirements
    source_info = {
        "arxiv_search.py": ("arXiv", False, ""),
        "github_trending.py": ("GitHub trending", False, ""),
        "hackernews.py": ("Hacker News", False, ""),
        "google_patent_search.py": ("Google Patents (Tavily)", True, "TAVILY_API_KEY"),
        "reddit_search.py": ("Reddit", False, ""),
        "semantic_scholar.py": ("Semantic Scholar", False, ""),
        "youtube_videos.py": ("YouTube videos", True, "YOUTUBE_API_KEY"),
        "devto_search.py": ("DEV.to", False, ""),
    }

    for f in source_files:
        info = source_info.get(f, (f.replace("_", " ").replace(".py", "").title(), False, ""))
        data_sources.append(SourceStatus(
            name=info[0], file=f, requires_api_key=info[1], api_key_env_var=info[2],
        ))

    # Pipeline stages
    pipeline_stages = [
        "Domain Intelligence (LLM-generated feeds, queries, key people)",
        "Source Discovery (web-powered RSS feed discovery)",
        "Multi-source Ingest (parallel fetch from all sources)",
        "Deduplication (URL + fuzzy title matching)",
        "Full Text Extraction (trafilatura, throttled async)",
        "LLM Classification (batch → quadrant, ring, relevance)",
        "LLM Report Generation (4-phase: Core → Radar → Insights → Details)",
        "Relevance Verification (LLM post-filter for off-topic content)",
        "Movement Detection (ring comparison vs previous report)",
        "Signal Strength Scoring (source authority weighted)",
        "Technology Relationship Extraction (LLM clusters + edges)",
        "Weak Signal Detection (DVI framework with cross-run history)",
    ]

    post_processing = [
        "Technology lifecycle stage detection",
        "YouTube video enrichment (opt-in)",
        "Report confidence scoring",
    ]

    frontend_views = [
        "Interactive Technology Radar (SVG)",
        "Report Renderer (markdown sections)",
        "Report Comparison (side-by-side diff)",
        "Multi-Report Timeline (ring evolution)",
        "Relationship Graph (technology clusters)",
        "Collaboration (share, vote, comment)",
    ]

    export_formats = ["PDF", "PowerPoint (PPTX)", "Email Digest"]

    # Count endpoints
    routes_file = "app/routes/sensing.py"
    endpoint_count = 0
    if os.path.exists(routes_file):
        with open(routes_file) as f:
            endpoint_count = sum(
                1 for line in f
                if line.strip().startswith("@router.")
            )

    # Count Python files and LOC
    total_files = 0
    total_loc = 0
    for root, _, files in os.walk("core"):
        for f in files:
            if f.endswith(".py"):
                total_files += 1
                fpath = os.path.join(root, f)
                try:
                    with open(fpath) as fh:
                        total_loc += sum(1 for _ in fh)
                except OSError:
                    pass

    return PlatformStatus(
        generated_at=datetime.now(timezone.utc).isoformat(),
        data_sources=data_sources,
        pipeline_stages=pipeline_stages,
        post_processing_modules=post_processing,
        frontend_views=frontend_views,
        export_formats=export_formats,
        api_endpoint_count=endpoint_count,
        total_python_files=total_files,
        total_lines_of_code=total_loc,
    )
