from pydantic import BaseModel

from core.config import settings


class GPULLMConfig(BaseModel):
    model: str
    port: int


# SETTINGS
SWITCHES = {
    "FALLBACK_TO_GEMINI": False,
    "FALLBACK_TO_OPENAI": False,
    "DISABLE_THINKING": True,
    "TECH_SENSING": True,
    # INTERNAL LLM API (opt-in). Activated only when settings.USE_INTERNAL=true
    # AND the INTERNAL_* credentials are populated. See core/llm/client.py.
    "USE_INTERNAL": settings.USE_INTERNAL,
    # RATE_LIMIT_INTERNAL controls whether we sleep between INTERNAL calls
    # (3 calls / 60s sliding window). It does NOT control fallback.
    "RATE_LIMIT_INTERNAL": True,
    # INTERNAL_NO_FALLBACK: when True, an INTERNAL failure raises immediately
    # instead of falling through to GPU/Gemini/OpenAI. Debug aid only — leave
    # False in production so the existing fallback chain protects requests.
    "INTERNAL_NO_FALLBACK": settings.INTERNAL_NO_FALLBACK,
}

PORT1 = 11434
PORT2 = 11435

# Model token limits
MODEL_CONTEXT_TOKENS = settings.MODEL_CONTEXT_TOKENS
MODEL_OUTPUT_TOKENS = settings.MODEL_OUTPUT_TOKENS
MODEL_OUTPUT_RESERVE = settings.MODEL_OUTPUT_RESERVE

MAIN_MODEL = settings.MAIN_MODEL

# Tech Sensing LLM configurations
GPU_SENSING_CLASSIFY_LLM = GPULLMConfig(model=MAIN_MODEL, port=PORT1)
GPU_SENSING_REPORT_LLM = GPULLMConfig(model=MAIN_MODEL, port=PORT1)
GPU_SENSING_COMPANY_ANALYSIS_LLM = GPULLMConfig(model=MAIN_MODEL, port=PORT1)

# Leading Indicator Radar (LIR) LLM configurations
GPU_LIR_EXTRACT_LLM = GPULLMConfig(model=MAIN_MODEL, port=PORT1)
GPU_LIR_CANON_LLM = GPULLMConfig(model=MAIN_MODEL, port=PORT1)

# Fallback LLM models
FALLBACK_GEMINI_MODEL = "gemini-2.5-flash"
FALLBACK_OPENAI_MODEL = "gpt-4o-mini"


# ───────────────────────────────────────────────────────────────────
# Feature flags for the 33-feature Company Analysis + Key Companies
# improvement plan. Each flag defaults to False so the existing
# behavior is preserved; flip on selectively via env or settings.
# ───────────────────────────────────────────────────────────────────
import os as _os


def _env_flag(name: str, default: bool = False) -> bool:
    val = _os.getenv(name, "").strip().lower()
    if not val:
        return default
    return val in ("1", "true", "yes", "on")


SENSING_FEATURES = {
    # Phase 2 — evidence-breadth providers
    "rss_provider": _env_flag("SENSING_FEATURE_RSS", False),
    "github_provider": _env_flag("SENSING_FEATURE_GITHUB", False),
    "arxiv_provider": _env_flag("SENSING_FEATURE_ARXIV", False),
    "press_wire_provider": _env_flag("SENSING_FEATURE_PRESS_WIRE", False),
    "youtube_provider": _env_flag("SENSING_FEATURE_YOUTUBE", False),
    "edgar_provider": _env_flag("SENSING_FEATURE_EDGAR", False),
    "patents_provider": _env_flag("SENSING_FEATURE_PATENTS", False),
    # Phase 1 — trust / UX
    "source_evidence": _env_flag("SENSING_FEATURE_SOURCE_EVIDENCE", True),
    "single_source_downgrade": _env_flag("SENSING_FEATURE_SS_DOWNGRADE", True),
    "sentiment": _env_flag("SENSING_FEATURE_SENTIMENT", True),
    "telemetry": _env_flag("SENSING_FEATURE_TELEMETRY", True),
    "byo_urls": _env_flag("SENSING_FEATURE_BYO_URLS", True),
    "aliases": _env_flag("SENSING_FEATURE_ALIASES", True),
    "exclusions": _env_flag("SENSING_FEATURE_EXCLUSIONS", True),
    # Phase 3 — output richness
    "momentum": _env_flag("SENSING_FEATURE_MOMENTUM", True),
    "overlap_matrix": _env_flag("SENSING_FEATURE_OVERLAP", True),
    "strategic_themes": _env_flag("SENSING_FEATURE_THEMES", False),
    "timeline": _env_flag("SENSING_FEATURE_TIMELINE", True),
    "cross_domain_rollup": _env_flag("SENSING_FEATURE_CROSS_DOMAIN", True),
    "investment_aggregator": _env_flag("SENSING_FEATURE_INVESTMENT", True),
    # Phase 4 — persistence
    "watchlists": _env_flag("SENSING_FEATURE_WATCHLISTS", True),
    "scheduled_digest": _env_flag("SENSING_FEATURE_SCHEDULED_DIGEST", False),
    "diff": _env_flag("SENSING_FEATURE_DIFF", True),
    "similar_companies": _env_flag("SENSING_FEATURE_SIMILAR", True),
    # Phase 5 — exports
    "kc_pdf_pptx": _env_flag("SENSING_FEATURE_KC_PDF_PPTX", True),
    "csv_xlsx": _env_flag("SENSING_FEATURE_CSV_XLSX", True),
    "markdown_notion": _env_flag("SENSING_FEATURE_MD_NOTION", True),
    "jira_linear": _env_flag("SENSING_FEATURE_JIRA", False),
    # Phase 6 — heavy compute
    "follow_up": _env_flag("SENSING_FEATURE_FOLLOW_UP", True),
    "contradictions": _env_flag("SENSING_FEATURE_CONTRADICTIONS", False),
    "hallucination_probe": _env_flag("SENSING_FEATURE_HALLUCINATION", False),
    "hiring_signals": _env_flag("SENSING_FEATURE_HIRING", False),
    "opportunity_threat": _env_flag("SENSING_FEATURE_OPP_THREAT", True),
    # Leading Indicator Radar (LIR)
    "lir_enabled": _env_flag("SENSING_FEATURE_LIR", True),
    "lir_arxiv": _env_flag("SENSING_FEATURE_LIR_ARXIV", True),
    "lir_github": _env_flag("SENSING_FEATURE_LIR_GITHUB", True),
    "lir_hackernews": _env_flag("SENSING_FEATURE_LIR_HN", True),
    "lir_reddit": _env_flag("SENSING_FEATURE_LIR_REDDIT", True),
    "lir_semantic_scholar": _env_flag("SENSING_FEATURE_LIR_SEMSCHOLAR", True),
    "lir_huggingface": _env_flag("SENSING_FEATURE_LIR_HF", True),
    "lir_pypi_npm": _env_flag("SENSING_FEATURE_LIR_PYPI", True),
    "lir_vendor_changelogs": _env_flag("SENSING_FEATURE_LIR_VENDOR", True),
    "lir_standards": _env_flag("SENSING_FEATURE_LIR_STANDARDS", True),
    "lir_patents": _env_flag("SENSING_FEATURE_LIR_PATENTS", False),
    "lir_openalex": _env_flag("SENSING_FEATURE_LIR_OPENALEX", True),
    "lir_google_trends": _env_flag("SENSING_FEATURE_LIR_GTRENDS", False),
    "lir_stackexchange": _env_flag("SENSING_FEATURE_LIR_STACKEX", True),
    "lir_job_postings": _env_flag("SENSING_FEATURE_LIR_JOBS", True),
}


def sensing_feature(name: str) -> bool:
    """Lookup helper — returns False for unknown flags."""
    return bool(SENSING_FEATURES.get(name, False))
