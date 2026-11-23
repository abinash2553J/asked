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
        self.llm_api_key = os.getenv("LLM_API_KEY", "").strip()
        self.llm_base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.llm_model = os.getenv("LLM_MODEL", "gpt-4o-mini")
        self.llm_top_k = int(os.getenv("LLM_TOP_K", "10"))

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
