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
