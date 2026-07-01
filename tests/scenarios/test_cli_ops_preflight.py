import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from datasentry.cli.app import app

runner = CliRunner()


def _write_targets(tmp_path: Path) -> Path:
    path = tmp_path / "targets.toml"
    path.write_text(
        """
[hosts.data1]
address = "192.0.2.10"

[mysql.doris]
host = "data1"
port = 9030
database = "streamlake"
username = "datasentry_readonly"
password_env = "DATASENTRY_DORIS_PASSWORD"

[redis.redis]
host = "data1"
port = 6379
database = 0
username = "datasentry_readonly"
password_env = "DATASENTRY_REDIS_PASSWORD"
""",
        encoding="utf-8",
    )
    return path


def test_ops_preflight_outputs_secret_status_without_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    targets = _write_targets(tmp_path)
    monkeypatch.setenv("DATASENTRY_DORIS_PASSWORD", "doris-secret-value")
    monkeypatch.delenv("DATASENTRY_REDIS_PASSWORD", raising=False)

    result = runner.invoke(
        app,
        [
            "ops",
            "preflight",
            "--targets-file",
            str(targets),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["targets_file"] == str(targets)
    assert payload["summary"] == {
        "configured": 1,
        "missing": 1,
        "total": 2,
    }
    assert payload["secrets"][0]["environment_variable"] == "DATASENTRY_DORIS_PASSWORD"
    assert payload["secrets"][0]["status"] == "configured"
    assert payload["secrets"][0]["cloud_variable"] == "DORIS_PASSWORD"
    assert payload["secrets"][1]["environment_variable"] == "DATASENTRY_REDIS_PASSWORD"
    assert payload["secrets"][1]["status"] == "missing"
    assert payload["secrets"][1]["cloud_variable"] == "REDIS_PASSWORD"
    assert "doris-secret-value" not in result.stdout
