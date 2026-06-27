from pathlib import Path

import pytest

from datasentry.config import Settings


def test_settings_use_safe_local_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.environment == "development"
    assert settings.database_path == Path("var/datasentry.db")
    assert settings.targets_file == Path("config/targets.toml")
    assert settings.log_level == "INFO"
    assert settings.log_format == "json"


def test_settings_read_datasentry_prefixed_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATASENTRY_DATABASE_PATH", "/tmp/custom.db")
    monkeypatch.setenv("DATASENTRY_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("DATASENTRY_TARGETS_FILE", "/tmp/targets.toml")

    settings = Settings(_env_file=None)

    assert settings.database_path == Path("/tmp/custom.db")
    assert settings.log_level == "DEBUG"
    assert settings.targets_file == Path("/tmp/targets.toml")


def test_m4_llm_settings_default_to_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATASENTRY_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("DATASENTRY_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("DATASENTRY_LLM_MODEL", raising=False)
    monkeypatch.delenv("DATASENTRY_LLM_API_KEY", raising=False)
    monkeypatch.delenv("DATASENTRY_LLM_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("DATASENTRY_API_CORS_ORIGINS", raising=False)

    settings = Settings(_env_file=None)

    assert settings.llm_provider == "disabled"
    assert settings.llm_api_key is None
    assert settings.api_cors_origins == ["http://localhost:5173"]


def test_m4_llm_settings_load_openai_compatible(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATASENTRY_LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("DATASENTRY_LLM_BASE_URL", "https://llm.example.test/v1")
    monkeypatch.setenv("DATASENTRY_LLM_MODEL", "ops-model")
    monkeypatch.setenv("DATASENTRY_LLM_API_KEY", "secret-key")
    monkeypatch.setenv("DATASENTRY_LLM_TIMEOUT_SECONDS", "7")

    settings = Settings(_env_file=None)

    assert settings.llm_provider == "openai_compatible"
    assert str(settings.llm_base_url) == "https://llm.example.test/v1"
    assert settings.llm_model == "ops-model"
    assert settings.llm_api_key == "secret-key"
    assert settings.llm_timeout_seconds == 7
    assert "secret-key" not in repr(settings)


def test_m4_api_settings_parse_cors_and_grafana_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "DATASENTRY_API_CORS_ORIGINS",
        '["http://localhost:5173","https://ops.example.test"]',
    )
    monkeypatch.setenv("DATASENTRY_GRAFANA_URL", "https://grafana.example.test/")

    settings = Settings(_env_file=None)

    assert settings.api_cors_origins == [
        "http://localhost:5173",
        "https://ops.example.test",
    ]
    assert str(settings.grafana_url) == "https://grafana.example.test/"
