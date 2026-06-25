from pathlib import Path

import pytest

from datasentry.errors import ConfigurationError
from datasentry.tools.targets import EnvironmentSecretResolver, TargetCatalog


def _write_targets(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "targets.toml"
    path.write_text(content, encoding="utf-8")
    return path


def _valid_targets() -> str:
    return """
[limits]
connect_timeout_seconds = 3
read_timeout_seconds = 5
max_output_bytes = 65536
max_log_lines = 200
max_log_minutes = 30
retry_attempts = 1

[hosts.data1]
address = "192.0.2.10"

[ssh.data1]
host = "data1"
port = 22
username = "datasentry-readonly"
password_env = "TEST_SSH_PASSWORD"
known_hosts = "/tmp/test-known-hosts"

[http.flink]
base_url = "http://192.0.2.10:8081"

[mysql.doris]
host = "data1"
port = 9030
database = "streamlake"
username = "datasentry_readonly"
password_env = "TEST_DORIS_PASSWORD"
timezone = "UTC"

[redis.redis]
host = "data1"
port = 6379
database = 0
username = "datasentry_readonly"
password_env = "TEST_REDIS_PASSWORD"

[logs.spring_api]
host = "data1"
kind = "file"
path = "/opt/StreamLake-Binance/api-server/logs/app.log"
"""


def test_target_catalog_loads_aliases_without_resolving_secrets(
    tmp_path: Path,
) -> None:
    catalog = TargetCatalog.load(_write_targets(tmp_path, _valid_targets()))

    assert catalog.host("data1").address == "192.0.2.10"
    assert catalog.ssh_target("data1").password_env == "TEST_SSH_PASSWORD"
    assert "secret-value" not in catalog.model_dump_json()


@pytest.mark.parametrize(
    ("replacement", "code"),
    [
        (
            'base_url = "http://user:password@192.0.2.10:8081"',
            "configuration.target_invalid",
        ),
        ('known_hosts = ""', "configuration.target_invalid"),
        ('password_env = "bad-env-name"', "configuration.target_invalid"),
        ('path = "../../etc/passwd"', "configuration.target_invalid"),
    ],
)
def test_target_catalog_rejects_unsafe_values(
    tmp_path: Path,
    replacement: str,
    code: str,
) -> None:
    if replacement.startswith("base_url"):
        content = _valid_targets().replace(
            'base_url = "http://192.0.2.10:8081"',
            replacement,
        )
    elif replacement.startswith("known_hosts"):
        content = _valid_targets().replace(
            'known_hosts = "/tmp/test-known-hosts"',
            replacement,
        )
    elif replacement.startswith("password_env"):
        content = _valid_targets().replace(
            'password_env = "TEST_DORIS_PASSWORD"',
            replacement,
        )
    else:
        content = _valid_targets().replace(
            'path = "/opt/StreamLake-Binance/api-server/logs/app.log"',
            replacement,
        )

    with pytest.raises(ConfigurationError) as raised:
        TargetCatalog.load(_write_targets(tmp_path, content))

    assert raised.value.code == code


def test_target_catalog_rejects_unknown_host_reference(tmp_path: Path) -> None:
    content = _valid_targets().replace('host = "data1"', 'host = "missing"', 1)

    with pytest.raises(ConfigurationError) as raised:
        TargetCatalog.load(_write_targets(tmp_path, content))

    assert raised.value.code == "configuration.target_reference_missing"


def test_secret_resolver_reports_missing_environment_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TEST_DORIS_PASSWORD", raising=False)

    with pytest.raises(ConfigurationError) as raised:
        EnvironmentSecretResolver().require("TEST_DORIS_PASSWORD")

    assert raised.value.code == "configuration.secret_missing"
    assert raised.value.details == {"environment_variable": "TEST_DORIS_PASSWORD"}


def test_secret_resolver_reads_value_without_exposing_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_DORIS_PASSWORD", "secret-value")

    assert EnvironmentSecretResolver().require("TEST_DORIS_PASSWORD") == "secret-value"


def test_target_catalog_reports_missing_alias(tmp_path: Path) -> None:
    catalog = TargetCatalog.load(_write_targets(tmp_path, _valid_targets()))

    with pytest.raises(ConfigurationError) as raised:
        catalog.host("missing")

    assert raised.value.code == "configuration.target_missing"
