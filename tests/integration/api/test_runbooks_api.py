from fastapi.testclient import TestClient

from datasentry.api import create_app
from datasentry.config import Settings


def test_runbook_operation_full_api_flow(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATASENTRY_DATABASE_PATH", str(tmp_path / "datasentry.db"))
    client = TestClient(create_app(Settings()))

    runbooks = client.get("/api/runbooks")
    assert runbooks.status_code == 200
    assert runbooks.json()[0]["name"] == "mock.restart_preview"

    created = client.post(
        "/api/operations",
        json={
            "runbook_name": "mock.restart_preview",
            "parameters": {"target": "api", "reason": "演练"},
            "requester": "operator",
        },
    )
    assert created.status_code == 201
    operation_id = created.json()["id"]
    assert created.json()["status"] == "awaiting_approval"

    approved = client.post(
        f"/api/operations/{operation_id}/approve",
        json={"approver": "operator"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    executed = client.post(
        f"/api/operations/{operation_id}/execute",
        json={"actor": "operator"},
    )
    assert executed.status_code == 200
    assert executed.json()["status"] == "succeeded"

    events = client.get(f"/api/operations/{operation_id}/events")
    assert events.status_code == 200
    assert events.json()[-1]["event_type"] == "verification_succeeded"


def test_forbidden_runbook_api_rejects_request(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATASENTRY_DATABASE_PATH", str(tmp_path / "datasentry.db"))
    client = TestClient(create_app(Settings()))

    response = client.post(
        "/api/operations",
        json={
            "runbook_name": "forbidden.shell_command",
            "parameters": {"target": "api", "command": "rm -rf /"},
            "requester": "operator",
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == "runbook.forbidden"


def test_runbook_operation_rejects_missing_required_parameter(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATASENTRY_DATABASE_PATH", str(tmp_path / "datasentry.db"))
    client = TestClient(create_app(Settings()))

    response = client.post(
        "/api/operations",
        json={
            "runbook_name": "mock.restart_preview",
            "parameters": {"target": "api"},
            "requester": "operator",
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == "runbook.invalid_parameters"
    assert response.json()["details"] == {"parameter": "reason"}


def test_runbook_operation_rejects_invalid_required_string_parameter(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DATASENTRY_DATABASE_PATH", str(tmp_path / "datasentry.db"))
    client = TestClient(create_app(Settings()))

    response = client.post(
        "/api/operations",
        json={
            "runbook_name": "mock.restart_preview",
            "parameters": {"target": "api", "reason": 123},
            "requester": "operator",
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == "runbook.invalid_parameters"
    assert response.json()["details"] == {"parameter": "reason"}


def test_operation_events_require_existing_operation(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATASENTRY_DATABASE_PATH", str(tmp_path / "datasentry.db"))
    client = TestClient(create_app(Settings()))

    response = client.get("/api/operations/missing-operation/events")

    assert response.status_code == 404
    assert response.json()["code"] == "storage.operation_not_found"
