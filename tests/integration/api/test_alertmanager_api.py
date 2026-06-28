import json
from pathlib import Path

from fastapi.testclient import TestClient

from datasentry.api import create_app
from datasentry.api.dependencies import get_incident_service
from datasentry.config import Settings
from datasentry.domain import IncidentStatus
from datasentry.incidents import IncidentAction, IncidentUpsertResult


class FakeIncidentService:
    def handle_alertmanager_payload(self, payload) -> IncidentUpsertResult:
        return IncidentUpsertResult(
            incident_id="incident-api-1",
            action=IncidentAction.CREATED,
            status=IncidentStatus.INVESTIGATING,
            deduplication_key="dedup-key-1",
            diagnosis_question="为什么 K线数据不更新",
        )


def test_alertmanager_webhook_parses_payload(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATASENTRY_DATABASE_PATH", str(tmp_path / "datasentry.db"))
    payload = json.loads(
        Path("tests/fixtures/alertmanager/kline_freshness_firing.json").read_text(
            encoding="utf-8",
        )
    )
    app = create_app(Settings())
    app.dependency_overrides[get_incident_service] = lambda: FakeIncidentService()
    client = TestClient(app)

    response = client.post("/api/alertmanager/webhook", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] is True
    assert body["incident_id"] == "incident-api-1"
    assert body["action"] == "created"
    assert body["status"] == "investigating"
    assert body["diagnosis_question"] == "为什么 K线数据不更新"
