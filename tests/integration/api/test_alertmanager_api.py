import json
from pathlib import Path

from fastapi.testclient import TestClient

from datasentry.api import create_app
from datasentry.config import Settings


def test_alertmanager_webhook_parses_payload(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATASENTRY_DATABASE_PATH", str(tmp_path / "datasentry.db"))
    payload = json.loads(
        Path("tests/fixtures/alertmanager/kline_freshness_firing.json").read_text(
            encoding="utf-8",
        )
    )
    client = TestClient(create_app(Settings()))

    response = client.post("/api/alertmanager/webhook", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "accepted"
    assert body["alert_count"] >= 1
    assert body["group_key"] == payload["groupKey"]
