from fastapi.testclient import TestClient

from datasentry.api import create_app
from datasentry.config import Settings


def test_health_does_not_expose_llm_api_key(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATASENTRY_DATABASE_PATH", str(tmp_path / "datasentry.db"))
    monkeypatch.setenv("DATASENTRY_LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("DATASENTRY_LLM_API_KEY", "secret-key")
    app = create_app(Settings())

    response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["llm"]["provider"] == "openai_compatible"
    assert payload["llm"]["configured"] is False
    assert "secret-key" not in response.text


def test_overview_returns_command_center_sections(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATASENTRY_DATABASE_PATH", str(tmp_path / "datasentry.db"))
    app = create_app(Settings())

    response = TestClient(app).get("/api/overview")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) >= {
        "health",
        "recent_inspections",
        "incidents",
        "operations",
        "grafana",
    }
    assert payload["health"]["status"] == "ok"
    assert payload["recent_inspections"] == []
    assert payload["incidents"] == []
    assert payload["operations"] == []
