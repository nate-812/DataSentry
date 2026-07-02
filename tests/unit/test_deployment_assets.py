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


def test_alertmanager_proxy_systemd_examples_are_bridge_only() -> None:
    socket = read_text("deploy/systemd/datasentry-alertmanager-proxy.socket.example")
    service = read_text("deploy/systemd/datasentry-alertmanager-proxy.service.example")

    assert "ListenStream=172.17.0.1:18000" in socket
    assert "Service=datasentry-alertmanager-proxy.service" in socket
    assert "ListenStream=0.0.0.0:18000" not in socket
    assert "ListenStream=*:18000" not in socket

    assert "User=datasentry" in service
    assert "Group=datasentry" in service
    assert "Requires=datasentry-api.service" in service
    assert "ExecStart=/lib/systemd/systemd-socket-proxyd 127.0.0.1:18000" in service
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
        "datasentry-alertmanager-proxy.socket",
        "datasentry-alertmanager-proxy.service",
        ".venv/bin/uvicorn",
    ]
    assert_contains_all(guide, required_paths)

    required_safety_invariants = [
        "127.0.0.1:18000",
        "172.17.0.1:18000",
        "http://host.docker.internal:18000/api/alertmanager/webhook",
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
        "systemctl status datasentry-alertmanager-proxy.socket",
        "curl -fsS http://172.17.0.1:18000/api/health",
        "webhook_configs:",
        "datasentry ops preflight",
        "datasentry monitoring deployment-check",
        "datasentry monitoring alert-smoke",
        "datasentry inspection run",
        "ssh -L 18000:127.0.0.1:18000 data1",
        "sudo systemctl stop datasentry-api",
        "sudo systemctl disable datasentry-api",
        "sudo systemctl stop datasentry-alertmanager-proxy.socket",
        "sudo systemctl disable datasentry-alertmanager-proxy.socket",
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
        "真实 Alertmanager API 投递",
        "真实 K 线只读巡检",
        "Doris root 改密",
        "云安全组变更",
        "生产写 Runbook 仍未开放",
    ]
    assert_contains_all(checklist, checklist_invariants)


def test_m9_exposure_maintenance_plan_covers_offline_preparation() -> None:
    plan = read_text("docs/operations/m9-exposure-maintenance-plan.md")
    readme = read_text("README.md")
    status = read_text("docs/PROJECT_STATUS.md")

    required_sections = [
        "## 使用场景",
        "## 本地准备",
        "## 维护窗口顺序",
        "## 组件收口清单",
        "## 回滚边界",
        "## 证据记录模板",
        "## 本地验证",
    ]
    assert_contains_all(plan, required_sections)

    required_cloud_startup_checks = [
        "datasentry-api",
        "datasentry-alertmanager-proxy.socket",
        "systemctl is-enabled",
        "systemctl is-active",
        "用户确认",
        "disable",
    ]
    assert_contains_all(plan, required_cloud_startup_checks)

    required_exposure_components = [
        "Flink Web",
        "Doris FE",
        "MySQL",
        "Redis",
        "Spring API",
        "AI Engine",
    ]
    assert_contains_all(plan, required_exposure_components)

    required_safety_rules = [
        "不开云端实例",
        "不执行 SSH",
        "不修改云安全组",
        "不打印真实 secret",
        "不开放生产写 Runbook",
        "Doris root 改密",
        "单独维护窗口",
    ]
    assert_contains_all(plan, required_safety_rules)

    required_regression_commands = [
        "datasentry monitoring deployment-check",
        "datasentry monitoring alert-smoke",
        "datasentry inspection run",
        "datasentry ops preflight",
        "curl -fsS http://127.0.0.1:18000/api/health",
        "curl -fsS http://172.17.0.1:18000/api/health",
    ]
    assert_contains_all(plan, required_regression_commands)

    assert "m9-exposure-maintenance-plan.md" in readme
    assert "M9 暴露面维护预案" in status


def test_m9_risk_backlog_tracks_local_and_cloud_followups() -> None:
    backlog = read_text("docs/operations/m9-risk-backlog.md")
    readme = read_text("README.md")
    status = read_text("docs/PROJECT_STATUS.md")

    required_sections = [
        "## 使用方式",
        "## 风险分级",
        "## 当前 Backlog",
        "## 不开云端时可推进",
        "## 开云端后的只读验证",
        "## 退出条件",
    ]
    assert_contains_all(backlog, required_sections)

    required_risks = [
        "get_kafka_topic",
        "tool.timeout",
        "Doris root 改密",
        "AI Engine",
        "systemd",
        "known_hosts",
        "datasentry_known_hosts",
        "ai-engine/docker-compose.yml",
        "ai-engine/nohup.out",
        "ai-engine/volumes/",
        "/root/bin",
        "Doris freshness",
        "RECOVER_YOUR_DATA_info",
    ]
    assert_contains_all(backlog, required_risks)

    required_fields = [
        "优先级",
        "当前证据",
        "本地准备",
        "云端只读验证",
        "升级条件",
        "关闭条件",
    ]
    assert_contains_all(backlog, required_fields)

    required_boundaries = [
        "不开云端实例",
        "不执行 SSH",
        "不打印真实 secret",
        "不自动修改生产配置",
        "不开放生产写 Runbook",
    ]
    assert_contains_all(backlog, required_boundaries)

    assert "m9-risk-backlog.md" in readme
    assert "M9 风险 backlog" in status


def test_root_bin_script_audit_records_automation_blockers() -> None:
    audit = read_text("docs/operations/root-bin-script-audit.md")
    backlog = read_text("docs/operations/m9-risk-backlog.md")
    readme = read_text("README.md")
    status = read_text("docs/PROJECT_STATUS.md")

    required_sections = [
        "## 审计范围",
        "## 总体结论",
        "## 高风险阻断项",
        "## 脚本逐项结论",
        "## 自动化准入结论",
        "## 后续整改顺序",
    ]
    assert_contains_all(audit, required_sections)

    required_scripts = [
        "init_data1.sh",
        "job.sh",
        "job.sh.bak-20260630-password-rotation",
        "kafka.sh",
        "spring.sh",
        "ai.sh",
        "doris.sh",
        "flink.sh",
        "xcall",
        "xsync",
    ]
    assert_contains_all(audit, required_scripts)

    required_blockers = [
        "root 无密 SSH",
        "root 权限运行应用",
        "缺乏幂等性",
        "现场编译",
        "0.0.0.0:8000",
        "/root/.streamlake-secrets",
        "不得进入 DataSentry 自动执行白名单",
        "不开放生产写 Runbook",
    ]
    assert_contains_all(audit, required_blockers)

    assert "已完成源码初审" in backlog
    assert "root-bin-script-audit.md" in readme
    assert "云端脚本审计" in status
