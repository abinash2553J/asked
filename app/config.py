import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


class Settings:
    def __init__(self) -> None:
        self.max_comments_default = int(os.getenv("MAX_COMMENTS_DEFAULT", "500"))
        self.max_comments_cap = int(os.getenv("MAX_COMMENTS_CAP", "2000"))
        self.request_timeout = float(os.getenv("REQUEST_TIMEOUT", "20"))
        self.fetch_budget = float(os.getenv("FETCH_BUDGET", "45"))
        self.min_group_size = int(os.getenv("MIN_GROUP_SIZE", "2"))

        # Support GEMINI_API_KEY or LLM_API_KEY
        gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
        llm_key = os.getenv("LLM_API_KEY", "").strip()
        self.llm_api_key = gemini_key or llm_key

        # Auto-detect Gemini endpoints if using a Gemini key or model
        is_gemini = bool(
            gemini_key
            or self.llm_api_key.startswith("AIza")
            or self.llm_api_key.startswith("AQ.")
            or "generativelanguage.googleapis.com" in os.getenv("LLM_BASE_URL", "")
            or "gemini" in os.getenv("LLM_MODEL", "").lower()
        )
        default_base_url = (
            "https://generativelanguage.googleapis.com/v1beta/openai"
            if is_gemini
            else "https://api.openai.com/v1"
        )
        default_model = "gemini-2.5-flash" if is_gemini else "gpt-4o-mini"

        self.llm_base_url = os.getenv("LLM_BASE_URL", default_base_url).rstrip("/")
        self.llm_model = os.getenv("LLM_MODEL", default_model)
        self.llm_top_k = int(os.getenv("LLM_TOP_K", "10"))

        # Official Google YouTube Data API v3 Key
        self.youtube_api_key = os.getenv("YOUTUBE_API_KEY", os.getenv("GOOGLE_API_KEY", "")).strip()

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
