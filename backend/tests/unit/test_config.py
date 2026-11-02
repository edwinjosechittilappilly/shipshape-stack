import pytest

from app.config import Settings


def test_defaults_match_the_runtime_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("DATABASE_URL", "APP_ENV", "LOG_LEVEL", "CORS_ORIGINS"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings()
    assert settings.database_url == "postgresql+psycopg://app:app@localhost:5432/app"
    assert settings.app_env == "local"
    assert settings.log_level == "INFO"


def test_cors_origins_is_a_comma_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://a.example, http://b.example ,,")
    assert Settings().cors_origins == ["http://a.example", "http://b.example"]


def test_log_level_is_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "debug")
    assert Settings().log_level == "DEBUG"


def test_unknown_app_env_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "prod")
    with pytest.raises(ValueError, match="app_env"):
        Settings()
