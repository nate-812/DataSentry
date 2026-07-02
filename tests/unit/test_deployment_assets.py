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


def test_existing_m9_operations_docs_link_required_smoke_commands() -> None:
    guide_path = ROOT / "docs/operations/m9-production-deployment.md"
    checklist_path = ROOT / "docs/operations/production-exposure-checklist.md"
    if not guide_path.exists() or not checklist_path.exists():
        return

    guide = guide_path.read_text(encoding="utf-8")
    checklist = checklist_path.read_text(encoding="utf-8")

    assert "systemctl status datasentry-api" in guide
    assert "curl -fsS http://127.0.0.1:18000/api/health" in guide
    assert "datasentry monitoring deployment-check" in guide
    assert "datasentry monitoring alert-smoke" in guide
    assert "datasentry inspection run" in guide
    assert "127.0.0.1:18000" in guide
    assert "Flink Web" in checklist
    assert "Doris FE" in checklist
    assert "MySQL" in checklist
    assert "Redis" in checklist
    assert "Spring API" in checklist
    assert "AI Engine" in checklist
