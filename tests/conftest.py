import pytest
from app.config import Settings
from app import main


@pytest.fixture(autouse=True)
def no_llm_in_tests(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("YOUTUBE_API_KEY", "")
    monkeypatch.setenv("GOOGLE_API_KEY", "")
    test_settings = Settings()
    monkeypatch.setattr("app.main.get_settings", lambda: test_settings)
    monkeypatch.setattr("app.config.get_settings", lambda: test_settings)
