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

    # INTERNAL API (default disabled — set USE_INTERNAL=true to enable)
    INTERNAL_BASE_URL: str = ""
    INTERNAL_CLIENT_KEY: str = ""
    INTERNAL_API_TOKEN: str = ""
    INTERNAL_USER_EMAIL: str = ""
    INTERNAL_MODEL_ID: str = ""
    USE_INTERNAL: bool = False

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
