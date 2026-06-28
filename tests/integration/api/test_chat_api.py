from fastapi.testclient import TestClient

from datasentry.api import create_app
from datasentry.config import Settings


def test_chat_session_lifecycle_with_mock_llm(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATASENTRY_DATABASE_PATH", str(tmp_path / "datasentry.db"))
    monkeypatch.setenv("DATASENTRY_TARGETS_FILE", "config/targets.example.toml")
    monkeypatch.setenv("DATASENTRY_LLM_PROVIDER", "mock")
    app = create_app(Settings())
    client = TestClient(app)

    session_response = client.post("/api/chat/sessions", json={"title": "Kline"})
    assert session_response.status_code == 201
    session_id = session_response.json()["id"]

    run_response = client.post(
        f"/api/chat/sessions/{session_id}/runs",
        json={"question": "为什么K线不更新"},
    )

    assert run_response.status_code == 200
    payload = run_response.json()
    assert payload["assistant_message"]["role"] == "assistant"
    assert payload["assistant_message"]["content"]
    assert payload["run"]["status"] in {"completed", "failed"}


def test_chat_run_events_are_returned_as_sse(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATASENTRY_DATABASE_PATH", str(tmp_path / "datasentry.db"))
    monkeypatch.setenv("DATASENTRY_TARGETS_FILE", "config/targets.example.toml")
    app = create_app(Settings())
    client = TestClient(app)
    session_id = client.post("/api/chat/sessions", json={"title": "Kline"}).json()["id"]
    run_id = client.post(
        f"/api/chat/sessions/{session_id}/runs",
        json={"question": "为什么K线不更新"},
    ).json()["run"]["id"]

    response = client.get(f"/api/chat/runs/{run_id}/events")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: accepted" in response.text


def test_chat_session_detail_returns_messages(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATASENTRY_DATABASE_PATH", str(tmp_path / "datasentry.db"))
    monkeypatch.setenv("DATASENTRY_TARGETS_FILE", "config/targets.example.toml")
    monkeypatch.setenv("DATASENTRY_LLM_PROVIDER", "mock")
    client = TestClient(create_app(Settings()))
    session_id = client.post("/api/chat/sessions", json={"title": "Kline"}).json()["id"]

    client.post(
        f"/api/chat/sessions/{session_id}/runs",
        json={"question": "为什么K线不更新"},
    )
    response = client.get(f"/api/chat/sessions/{session_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["session"]["id"] == session_id
    assert [message["role"] for message in payload["messages"]] == ["user", "assistant"]
