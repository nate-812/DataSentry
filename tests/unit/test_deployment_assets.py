from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read_text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def assert_contains_all(text: str, fragments: list[str]) -> None:
    missing = [fragment for fragment in fragments if fragment not in text]
    assert not missing


def test_datasentry_systemd_example_is_loopback_only_and_uses_env_file() -> None:
    service = read_text("deploy/systemd/datasentry-api.service.example")

    assert "User=datasentry" in service
    assert "Group=datasentry" in service
    assert "EnvironmentFile=/etc/datasentry/datasentry.env" in service
    assert "--host 127.0.0.1" in service
    assert "--port 18000" in service
    assert "0.0.0.0" not in service
    assert "DATASENTRY_DORIS_PASSWORD" not in service
    assert "DATASENTRY_MYSQL_PASSWORD" not in service
    assert "DATASENTRY_REDIS_PASSWORD" not in service


def test_datasentry_env_example_contains_only_safe_placeholders() -> None:
    env = read_text("config/datasentry.env.example")

    assert "DATASENTRY_ENVIRONMENT=production" in env
    assert "DATASENTRY_API_HOST=127.0.0.1" in env
    assert "DATASENTRY_API_PORT=18000" in env
    assert "DATASENTRY_DATABASE_PATH=/var/lib/datasentry/datasentry.db" in env
    assert "DATASENTRY_TARGETS_FILE=/etc/datasentry/targets.toml" in env
    assert "DATASENTRY_LLM_PROVIDER=mock" in env
    forbidden_fragments = [
        "password=",
        "token=",
        "secret=",
        "DATASENTRY_DORIS_PASSWORD=",
        "DATASENTRY_MYSQL_PASSWORD=",
        "DATASENTRY_REDIS_PASSWORD=",
        "DATASENTRY_LLM_API_KEY=",
    ]
    lower_env = env.lower()
    for fragment in forbidden_fragments:
        assert fragment.lower() not in lower_env


def test_m9_operations_docs_link_required_smoke_commands() -> None:
    guide = read_text("docs/operations/m9-production-deployment.md")
    checklist = read_text("docs/operations/production-exposure-checklist.md")

    required_paths = [
        "/etc/datasentry",
        "/etc/datasentry/datasentry.env",
        "/etc/datasentry/targets.toml",
        "/etc/datasentry/monitoring.toml",
        "/opt/datasentry-agent",
        "/var/lib/datasentry",
        "/var/lib/datasentry/datasentry.db",
        "/var/log/datasentry",
        ".venv/bin/uvicorn",
    ]
    assert_contains_all(guide, required_paths)

    required_safety_invariants = [
        "127.0.0.1:18000",
        "http://127.0.0.1:18000/api/alertmanager/webhook",
        "公网",
        "写入生产数据库",
        "真实 secret",
        "用户再次确认",
    ]
    assert_contains_all(guide, required_safety_invariants)
    forbidden_public_or_secret_examples = [
        "0.0.0.0:18000",
        "DATASENTRY_DORIS_PASSWORD=secret",
        "DATASENTRY_MYSQL_PASSWORD=password",
        "DATASENTRY_REDIS_PASSWORD=redis",
        "DATASENTRY_LLM_API_KEY=sk-",
    ]
    for fragment in forbidden_public_or_secret_examples:
        assert fragment not in guide
    assert not re.search(
        r"sudo\s+install\b[^\n]*config/datasentry\.env\.example[^\n]*/etc/datasentry/datasentry\.env",
        guide,
    )
    assert "test ! -e /etc/datasentry/datasentry.env" in guide
    assert "test ! -e /etc/datasentry/monitoring.toml" in guide
    assert "config/monitoring.example.toml" in guide

    required_setup_commands = [
        "getent group datasentry",
        "id datasentry",
        "sudo groupadd --system datasentry",
        "sudo useradd --system",
        "sudo install -d",
        "sudo chown",
        "sudo chmod",
        "git rev-parse --short HEAD",
        "test -x .venv/bin/uvicorn",
        "test -f /etc/datasentry/targets.toml",
        "test -f /etc/datasentry/monitoring.toml",
    ]
    assert_contains_all(guide, required_setup_commands)

    required_runtime_commands = [
        "git status --short --branch",
        "git diff --check",
        "systemctl status datasentry-api",
        "curl -fsS http://127.0.0.1:18000/api/health",
        "webhook_configs:",
        "datasentry ops preflight",
        "datasentry monitoring deployment-check",
        "datasentry monitoring alert-smoke",
        "datasentry inspection run",
        "ssh -L 18000:127.0.0.1:18000 data1",
        "sudo systemctl stop datasentry-api",
        "sudo systemctl disable datasentry-api",
    ]
    assert_contains_all(guide, required_runtime_commands)

    checklist_sections = ["监听地址", "账号权限", "secret 管理", "回归证据", "明确不在本轮处理"]
    assert_contains_all(checklist, [f"## {section}" for section in checklist_sections])

    exposed_components = [
        "DataSentry API",
        "Prometheus",
        "Grafana",
        "Alertmanager",
        "Flink Web",
        "Doris FE",
        "MySQL",
        "Redis",
        "Spring API",
        "AI Engine",
    ]
    assert_contains_all(checklist, exposed_components)

    checklist_invariants = [
        "不自动修改云安全组",
        "SSH 日常巡检",
        "SELECT",
        "SHOW",
        "DESCRIBE",
        "禁止 `KEYS`",
        "真实 secret",
        "configured/missing",
        "datasentry monitoring deployment-check",
        "datasentry monitoring alert-smoke",
        "真实 K 线只读巡检",
        "Doris root 改密",
        "云安全组变更",
        "生产写 Runbook 仍未开放",
    ]
    assert_contains_all(checklist, checklist_invariants)
