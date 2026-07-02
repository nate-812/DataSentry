from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read_text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


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

    assert "# M9 生产化部署运维手册" in guide
    assert "DataSentry API 作为 `data1` 本机 loopback 服务运行" in guide
    assert "云端只运行明确 Git 版本" in guide
    assert "http://127.0.0.1:18000/api/alertmanager/webhook" in guide
    assert "直接暴露 DataSentry API、Grafana、Prometheus、Alertmanager" in guide
    assert "写入生产数据库、执行任意 Shell、自动重启、自动补数" in guide
    assert "/etc/datasentry/datasentry.env" in guide
    assert "/etc/datasentry/targets.toml" in guide
    assert "git status --short --branch" in guide
    assert "git rev-parse --short HEAD" in guide
    assert "git diff --check" in guide
    assert (
        "sudo install -o root -g root -m 0644 "
        "deploy/systemd/datasentry-api.service.example "
        "/etc/systemd/system/datasentry-api.service"
        in guide
    )
    assert (
        "sudo install -o root -g datasentry -m 0640 "
        "config/datasentry.env.example /etc/datasentry/datasentry.env"
        in guide
    )
    assert "systemctl status datasentry-api" in guide
    assert "curl -fsS http://127.0.0.1:18000/api/health" in guide
    assert "webhook_configs:" in guide
    assert "- url: http://127.0.0.1:18000/api/alertmanager/webhook" in guide
    assert "datasentry ops preflight --targets-file /etc/datasentry/targets.toml" in guide
    assert "datasentry monitoring deployment-check" in guide
    assert "datasentry monitoring alert-smoke" in guide
    assert "datasentry inspection run" in guide
    assert "127.0.0.1:18000" in guide
    assert "Incident id、Inspection id、整体状态和失败项" in guide
    assert "ssh -L 18000:127.0.0.1:18000 data1" in guide
    assert "sudo systemctl stop datasentry-api" in guide
    assert "sudo systemctl disable datasentry-api" in guide
    assert "保留 `/var/lib/datasentry/datasentry.db`" in guide

    assert "# 生产暴露面收口 Checklist" in checklist
    assert "不自动修改云安全组、主机防火墙或业务配置" in checklist
    assert "DataSentry API" in checklist
    assert "Prometheus" in checklist
    assert "Grafana" in checklist
    assert "Alertmanager" in checklist
    assert "Flink Web" in checklist
    assert "Doris FE" in checklist
    assert "MySQL" in checklist
    assert "Redis" in checklist
    assert "Spring API" in checklist
    assert "AI Engine" in checklist
    assert "SSH 日常巡检使用无 sudo、无写权限的只读账号" in checklist
    assert "Doris/MySQL 诊断账号仅允许 `SELECT`、`SHOW` 和 `DESCRIBE`" in checklist
    assert "Redis ACL 仅允许计划内只读命令，禁止 `KEYS`" in checklist
    assert "真实 secret 只存在于云端受限文件或进程环境" in checklist
    assert "`datasentry ops preflight` 只展示变量名和 configured/missing 状态" in checklist
    assert "systemctl status datasentry-api" in checklist
    assert "curl -fsS http://127.0.0.1:18000/api/health" in checklist
    assert "datasentry monitoring deployment-check" in checklist
    assert "datasentry monitoring alert-smoke" in checklist
    assert "真实 K 线只读巡检" in checklist
    assert "Doris root 改密已单独排期" in checklist
    assert "云安全组变更已单独审批" in checklist
    assert "生产写 Runbook 仍未开放" in checklist
