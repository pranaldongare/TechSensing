from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv()


class Settings(BaseSettings):
    SECRET_KEY: str
    MODE: str = "development"
    API_KEY_1: str = ""
    API_KEY_2: str = ""
    API_KEY_3: str = ""
    API_KEY_4: str = ""
    API_KEY_5: str = ""
    API_KEY_6: str = ""
    OPENAI_API: str = ""
    QUERY_URL: str = "http://localhost:11434"
    VISION_URL: str = "http://localhost:11435"
    MAIN_MODEL: str = "qwen3:14b"
    LOCAL_BASE_URL: str = "http://localhost"

    # Local LLM (Ollama) primary path. Set USE_LOCAL_LLM=false to skip Ollama
    # entirely and use the cloud fallback chain (OpenAI/Gemini) directly.
    USE_LOCAL_LLM: bool = True

    # INTERNAL API (default disabled — set USE_INTERNAL=true to enable)
    INTERNAL_BASE_URL: str = ""
    INTERNAL_CLIENT_KEY: str = ""
    INTERNAL_API_TOKEN: str = ""
    INTERNAL_USER_EMAIL: str = ""
    INTERNAL_MODEL_ID: str = ""
    USE_INTERNAL: bool = False
    # Max output tokens for INTERNAL API calls. Default 8000 matches PRISM.
    INTERNAL_MAX_NEW_TOKENS: int = 8000
    # Debug aid: when True, an INTERNAL failure raises immediately instead of
    # falling through to GPU/Gemini/OpenAI. Useful for surfacing the actual
    # INTERNAL error during debugging. Leave False in production.
    INTERNAL_NO_FALLBACK: bool = False
    # Hybrid mode: when True (and USE_INTERNAL=true), the article classifier
    # specifically routes to the local GPU LLM while every OTHER LLM call
    # (report generation, deep dives, novelty, key companies, LIR, ...)
    # still goes through INTERNAL. Use this when the INTERNAL content filter
    # keeps blocking the classifier prompt (FR-201) but works fine for the
    # rest of the pipeline. INTERNAL_NO_FALLBACK is ignored for the
    # classifier when this is on.
    INTERNAL_BYPASS_CLASSIFIER: bool = False

    # YouTube Data API v3 (for tech sensing video enrichment)
    YOUTUBE_API_KEY: str = ""

    # Model token configuration
    MODEL_CONTEXT_TOKENS: int = 32000
    MODEL_OUTPUT_TOKENS: int = 16000
    MODEL_OUTPUT_RESERVE: int = 4000

    class Config:
        env_file = ".env"
        extra = "allow"


settings = Settings()
