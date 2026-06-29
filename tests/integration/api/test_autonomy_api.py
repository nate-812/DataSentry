from fastapi.testclient import TestClient

from datasentry.api import create_app
from datasentry.autonomy import AutonomyPolicy, MaintenanceWindow
from datasentry.config import Settings
from datasentry.storage import SQLiteRepository


def _client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("DATASENTRY_DATABASE_PATH", str(tmp_path / "datasentry.db"))
    return TestClient(create_app(Settings()))


def _save_always_open_policy(database_path) -> None:
    with SQLiteRepository(database_path) as repository:
        repository.save_autonomy_policy(
            AutonomyPolicy(
                runbook_name="mock.restart_preview",
                enabled=True,
                shadow_mode=False,
                maintenance_windows=[
                    MaintenanceWindow(
                        weekdays=[0, 1, 2, 3, 4, 5, 6],
                        start_minute_utc=0,
                        end_minute_utc=1440,
                    ),
                ],
            ),
        )


def test_list_autonomy_policies_returns_default_shadow_policy(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    response = client.get("/api/autonomy/policies")

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["runbook_name"] == "mock.clear_cache_preview"
    assert payload[0]["enabled"] is False
    assert payload[0]["shadow_mode"] is True


def test_evaluate_autonomy_candidate_returns_disabled_decision(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/api/autonomy/evaluate",
        json={
            "runbook_name": "mock.restart_preview",
            "parameters": {"target": "api", "reason": "演练"},
            "incident_id": None,
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "blocked"
    assert response.json()["reason_code"] == "policy.disabled"


def test_execute_autonomy_candidate_does_not_create_operation_when_shadowed(
    tmp_path,
    monkeypatch,
) -> None:
    client = _client(tmp_path, monkeypatch)
    policy = client.patch(
        "/api/autonomy/policies/mock.restart_preview",
        json={"enabled": True, "shadow_mode": True},
    )
    assert policy.status_code == 200

    response = client.post(
        "/api/autonomy/execute",
        json={
            "runbook_name": "mock.restart_preview",
            "parameters": {"target": "api", "reason": "演练"},
            "incident_id": None,
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "shadowed"
    runs = client.get("/api/autonomy/runs").json()
    assert runs[0]["decision_status"] == "shadowed"
    assert runs[0]["operation_id"] is None


def test_execute_autonomy_candidate_creates_mock_operation_when_allowed(
    tmp_path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "datasentry.db"
    monkeypatch.setenv("DATASENTRY_DATABASE_PATH", str(database_path))
    _save_always_open_policy(database_path)
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/api/autonomy/execute",
        json={
            "runbook_name": "mock.restart_preview",
            "parameters": {"target": "api", "reason": "演练"},
            "incident_id": None,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "allowed"
    assert payload["operation_id"]
    runs = client.get("/api/autonomy/runs").json()
    assert runs[0]["decision_status"] == "allowed"
    assert runs[0]["operation_id"] == payload["operation_id"]
    assert runs[0]["succeeded"] is True
