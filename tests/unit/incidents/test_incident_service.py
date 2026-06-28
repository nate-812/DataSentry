import json
from pathlib import Path
from types import SimpleNamespace

from datasentry.domain import Evidence, EvidenceStatus, Finding, Inspection, Severity
from datasentry.incidents import IncidentAction, IncidentService
from datasentry.notifications import parse_alertmanager_payload
from datasentry.storage import InspectionAggregate, SQLiteRepository


class FakeDiagnosisRunner:
    def run(self, question: str) -> SimpleNamespace:
        inspection = Inspection(
            question=question,
            scope=["streamlake"],
            summary="Kline freshness stale",
        )
        finding = Finding(
            inspection_id=inspection.id,
            severity=Severity.WARNING,
            status=EvidenceStatus.CONFIRMED,
            claim="Kline 数据未持续推进",
            evidence=[
                Evidence(
                    claim="Doris 新鲜度滞后",
                    status=EvidenceStatus.CONFIRMED,
                    source="doris",
                    target="kline_1min",
                    observed_at=inspection.started_at,
                    summary="业务时间滞后",
                )
            ],
            impact="页面可能展示旧 Kline",
            recommendation="检查 Flink Kline Job",
            created_at=inspection.started_at,
        )
        aggregate = InspectionAggregate(
            inspection=inspection,
            observations=[],
            findings=[finding],
        )
        return SimpleNamespace(diagnosis=SimpleNamespace(aggregate=aggregate), tool_invocations=[])


def _payload():
    return parse_alertmanager_payload(
        json.loads(
            Path("tests/fixtures/alertmanager/kline_freshness_firing.json").read_text(
                encoding="utf-8",
            )
        )
    )


def test_service_creates_incident_from_alertmanager_payload(tmp_path: Path) -> None:
    payload = _payload()
    with SQLiteRepository(tmp_path / "datasentry.db") as repository:
        service = IncidentService(repository=repository, diagnosis_runner=FakeDiagnosisRunner())

        result = service.handle_alertmanager_payload(payload)

        assert result.action is IncidentAction.CREATED
        detail = service.get_detail(result.incident_id)
        assert detail.incident.title.startswith("KlineFreshnessStale")
        assert len(detail.timeline) >= 2
        assert detail.links


def test_service_merges_repeated_alert_into_same_incident(tmp_path: Path) -> None:
    payload = _payload()
    with SQLiteRepository(tmp_path / "datasentry.db") as repository:
        service = IncidentService(repository=repository, diagnosis_runner=FakeDiagnosisRunner())

        first = service.handle_alertmanager_payload(payload)
        second = service.handle_alertmanager_payload(payload)

        assert second.incident_id == first.incident_id
        assert second.action is IncidentAction.UPDATED
