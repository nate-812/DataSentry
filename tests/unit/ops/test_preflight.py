from pathlib import Path

import pytest

from datasentry.ops import build_ops_preflight_report
from datasentry.tools.targets import TargetCatalog


def _write_targets(tmp_path: Path) -> Path:
    path = tmp_path / "targets.toml"
    path.write_text(
        """
[hosts.data1]
address = "192.0.2.10"

[ssh.data1]
host = "data1"
port = 22
username = "datasentry-readonly"
password_env = "DATASENTRY_SSH_PASSWORD"
known_hosts = "/tmp/test-known-hosts"
kafka_bootstrap = "data1:9092"

[mysql.doris]
host = "data1"
port = 9030
database = "streamlake"
username = "datasentry_readonly"
password_env = "DATASENTRY_DORIS_PASSWORD"

[mysql.mysql]
host = "data1"
port = 3306
database = "risk_control"
username = "datasentry_readonly"
password_env = "DATASENTRY_MYSQL_PASSWORD"

[mysql.doris_passwordless]
host = "data1"
port = 9030
database = "streamlake"
username = "root"

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


def test_preflight_reports_secret_presence_without_exposing_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATASENTRY_DORIS_PASSWORD", "doris-secret-value")
    monkeypatch.delenv("DATASENTRY_MYSQL_PASSWORD", raising=False)
    catalog = TargetCatalog.load(_write_targets(tmp_path))

    report = build_ops_preflight_report(
        targets=catalog,
        targets_file=tmp_path / "targets.toml",
    )

    payload = report.model_dump(mode="json")
    assert payload["targets_file"] == str(tmp_path / "targets.toml")
    assert payload["secrets"] == [
        {
            "component": "ssh",
            "target": "data1",
            "environment_variable": "DATASENTRY_SSH_PASSWORD",
            "status": "missing",
            "required": True,
            "cloud_variable": None,
            "message": "本地进程缺少 DATASENTRY_SSH_PASSWORD，该目标在触网前会返回配置缺失。",
        },
        {
            "component": "mysql",
            "target": "doris",
            "environment_variable": "DATASENTRY_DORIS_PASSWORD",
            "status": "configured",
            "required": True,
            "cloud_variable": "DORIS_PASSWORD",
            "message": "DATASENTRY_DORIS_PASSWORD 已在当前进程环境中设置。",
        },
        {
            "component": "mysql",
            "target": "mysql",
            "environment_variable": "DATASENTRY_MYSQL_PASSWORD",
            "status": "missing",
            "required": True,
            "cloud_variable": "MYSQL_PASSWORD",
            "message": "本地进程缺少 DATASENTRY_MYSQL_PASSWORD，该目标在触网前会返回配置缺失。",
        },
        {
            "component": "redis",
            "target": "redis",
            "environment_variable": "DATASENTRY_REDIS_PASSWORD",
            "status": "missing",
            "required": True,
            "cloud_variable": "REDIS_PASSWORD",
            "message": "本地进程缺少 DATASENTRY_REDIS_PASSWORD，该目标在触网前会返回配置缺失。",
        },
    ]
    assert payload["passwordless_targets"] == [
        {
            "component": "mysql",
            "target": "doris_passwordless",
            "message": "该数据库目标未声明 password_env，将使用空密码发起只读连接。",
        }
    ]
    assert "doris-secret-value" not in report.model_dump_json()
