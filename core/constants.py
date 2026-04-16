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

# Fallback LLM models
FALLBACK_GEMINI_MODEL = "gemini-2.5-flash"
FALLBACK_OPENAI_MODEL = "gpt-4o-mini"
