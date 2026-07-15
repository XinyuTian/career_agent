import pytest

from career_agent.config import DB_PATH, load_settings


@pytest.fixture(autouse=True)
def disable_dotenv(monkeypatch):
    monkeypatch.setattr("career_agent.config.load_dotenv", lambda: None)


def test_db_path_is_under_data(tmp_path, monkeypatch):
    assert DB_PATH.name == "career.db"
    assert DB_PATH.parent.name == "data"


def test_prefers_ai_builder_token(monkeypatch):
    monkeypatch.setenv("AI_BUILDER_TOKEN", "token-from-token")
    monkeypatch.setenv("AI_BUILDER_API_KEY", "token-from-key")
    settings = load_settings()
    assert settings.api_key == "token-from-token"


def test_falls_back_to_api_key(monkeypatch):
    monkeypatch.delenv("AI_BUILDER_TOKEN", raising=False)
    monkeypatch.setenv("AI_BUILDER_API_KEY", "token-from-key")
    settings = load_settings()
    assert settings.api_key == "token-from-key"
