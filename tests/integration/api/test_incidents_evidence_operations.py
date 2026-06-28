from datetime import UTC, datetime

from fastapi.testclient import TestClient

from datasentry.api import create_app
from datasentry.api.dependencies import get_incident_service
from datasentry.config import Settings
from datasentry.domain import (
    Evidence,
    EvidenceStatus,
    Finding,
    Incident,
    Inspection,
    InspectionStatus,
    Observation,
    Severity,
)
from datasentry.incidents import (
    IncidentService,
    IncidentTimelineEvent,
    IncidentTimelineEventType,
)
from datasentry.storage import SQLiteRepository

NOW = datetime(2026, 6, 27, 8, 0, tzinfo=UTC)


def test_evidence_route_returns_inspection_aggregate(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "datasentry.db"
    monkeypatch.setenv("DATASENTRY_DATABASE_PATH", str(database_path))
    inspection = Inspection(
        id="11111111-1111-4111-8111-111111111111",
        question="为什么K线不更新",
        scope=["simulation"],
        status=InspectionStatus.COMPLETED,
        summary="Kline delayed",
        started_at=NOW,
        finished_at=NOW,
    )
    observation = Observation(
        id="22222222-2222-4222-8222-222222222222",
        inspection_id=inspection.id,
        component="flink",
        metric_or_fact="checkpoint_status",
        value={"status": "ok"},
        source="test",
        target="flink",
        observed_at=NOW,
    )
    finding = Finding(
        id="33333333-3333-4333-8333-333333333333",
        inspection_id=inspection.id,
        severity=Severity.WARNING,
        status=EvidenceStatus.CONFIRMED,
        claim="Kline 数据停止推进",
        evidence=[
            Evidence(
                claim="Doris 新鲜度滞后",
                status=EvidenceStatus.CONFIRMED,
                source="test",
                target="doris",
                observed_at=NOW,
                summary="业务时间未推进",
            )
        ],
        impact="页面可能显示旧数据",
        recommendation="检查 Flink Job",
        created_at=NOW,
    )
    with SQLiteRepository(database_path) as repository:
        repository.save_inspection(inspection)
        repository.add_observation(observation)
        repository.add_finding(finding)

    response = TestClient(create_app(Settings())).get(f"/api/evidence/inspections/{inspection.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["inspection"]["id"] == inspection.id
    assert payload["observations"][0]["component"] == "flink"
    assert payload["findings"][0]["claim"] == "Kline 数据停止推进"


def test_operations_simulation_approve_and_reject(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATASENTRY_DATABASE_PATH", str(tmp_path / "datasentry.db"))
    client = TestClient(create_app(Settings()))

    created = client.post(
        "/api/operations/simulations",
        json={"name": "simulate_restart_preview", "requester": "operator"},
    )
    assert created.status_code == 201
    operation_id = created.json()["id"]

    approved = client.post(
        f"/api/operations/{operation_id}/approve",
        json={"approver": "operator"},
    )

    assert approved.status_code == 200
    assert approved.json()["status"] == "succeeded"

    rejected_created = client.post(
        "/api/operations/simulations",
        json={"name": "simulate_cache_refresh", "requester": "operator"},
    )
    rejected_id = rejected_created.json()["id"]
    rejected = client.post(
        f"/api/operations/{rejected_id}/reject",
        json={"approver": "operator"},
    )

    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"


def test_operations_reject_non_simulation_name(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATASENTRY_DATABASE_PATH", str(tmp_path / "datasentry.db"))
    client = TestClient(create_app(Settings()))

    response = client.post(
        "/api/operations/simulations",
        json={"name": "restart_flink", "requester": "operator"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "operation.not_simulation"


class NoopDiagnosisRunner:
    def run(self, question: str):  # pragma: no cover - RCA route does not call diagnostics
        raise AssertionError(f"不应执行诊断：{question}")


def test_incident_detail_timeline_rca_and_export_routes(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "datasentry.db"
    monkeypatch.setenv("DATASENTRY_DATABASE_PATH", str(database_path))
    incident = Incident(
        id="99999999-9999-4999-8999-999999999999",
        title="K线数据不更新",
        symptom="页面显示旧 Kline",
        severity=Severity.WARNING,
        opened_at=NOW,
        updated_at=NOW,
    )
    event = IncidentTimelineEvent(
        incident_id=incident.id,
        event_type=IncidentTimelineEventType.ALERT_FIRED,
        summary="收到 KlineFreshnessStale 告警",
        source="alertmanager",
        occurred_at=NOW,
    )
    with SQLiteRepository(database_path) as repository:
        repository.save_incident(incident)
        repository.save_timeline_event(event)

    app = create_app(Settings())

    def incident_service():
        with SQLiteRepository(database_path) as repository:
            yield IncidentService(repository=repository, diagnosis_runner=NoopDiagnosisRunner())

    app.dependency_overrides[get_incident_service] = incident_service
    client = TestClient(app)

    detail = client.get(f"/api/incidents/{incident.id}")
    timeline = client.get(f"/api/incidents/{incident.id}/timeline")
    rca = client.post(f"/api/incidents/{incident.id}/rca")
    exported = client.get(f"/api/incidents/{incident.id}/export")

    assert detail.status_code == 200
    assert detail.json()["incident"]["id"] == incident.id
    assert timeline.status_code == 200
    assert timeline.json()[0]["summary"] == "收到 KlineFreshnessStale 告警"
    assert rca.status_code == 200
    assert "历史事件仅用于经验参考" in rca.json()["markdown"]
    assert exported.status_code == 200
    assert "text/markdown" in exported.headers["content-type"]
