import json
from datetime import UTC, datetime
from pathlib import Path

from datasentry.diagnosis import DiagnosisResult
from datasentry.domain import (
    Evidence,
    EvidenceStatus,
    Finding,
    Inspection,
    InspectionStatus,
    Severity,
)
from datasentry.knowledge import QuestionType, RouteMatch
from datasentry.notifications import NotificationService, parse_alertmanager_payload
from datasentry.storage import InspectionAggregate
from datasentry.tools import LiveInspectionResult

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "alertmanager"
NOW = datetime(2026, 6, 26, 10, 5, tzinfo=UTC)


class StubDiagnosisRunner:
    def __init__(self) -> None:
        self.questions: list[str] = []

    def run(self, question: str) -> LiveInspectionResult:
        self.questions.append(question)
        inspection = Inspection(
            id="inspection-1",
            question=question,
            scope=["data_stale"],
            status=InspectionStatus.COMPLETED,
            summary="K线链路数据新鲜度异常",
            started_at=NOW,
            finished_at=NOW,
        )
        evidence = Evidence(
            claim="Doris kline_1min 最新业务时间超出阈值",
            status=EvidenceStatus.CONFIRMED,
            source="doris_sql",
            target="data1:9030",
            observed_at=NOW,
            summary="latest_event_time=2026-06-26T09:50:00Z",
        )
        finding = Finding(
            inspection_id=inspection.id,
            severity=Severity.CRITICAL,
            status=EvidenceStatus.CONFIRMED,
            claim="K线链路数据新鲜度异常",
            evidence=[evidence],
            impact="前端可能显示过期 K 线",
            recommendation="检查 Flink Kline Job 和 Doris 写入延迟",
            unknowns=["password=super-secret"],
            created_at=NOW,
        )
        return LiveInspectionResult(
            diagnosis=DiagnosisResult(
                route=RouteMatch(
                    question_type=QuestionType.DATA_STALE,
                    required_topic_ids=("03", "04"),
                    matched_keywords=("K线",),
                ),
                knowledge=[],
                lineage_checkpoints=[],
                aggregate=InspectionAggregate(
                    inspection=inspection,
                    observations=[],
                    findings=[finding],
                ),
            ),
            tool_invocations=[],
        )


class FailingDiagnosisRunner:
    def run(self, question: str) -> LiveInspectionResult:
        del question
        raise RuntimeError("password=super-secret")


def test_notification_service_maps_alert_to_question_and_message() -> None:
    payload = parse_alertmanager_payload(
        json.loads((FIXTURE_DIR / "kline_freshness_firing.json").read_text())
    )
    runner = StubDiagnosisRunner()
    service = NotificationService(diagnosis_runner=runner)

    result = service.build(payload)

    assert runner.questions == ["为什么 K线数据不更新"]
    assert result.content.diagnosis_question == "为什么 K线数据不更新"
    assert result.content.unknowns == ["password=[REDACTED]"]
    assert result.content.findings[0].unknowns == ["password=[REDACTED]"]
    assert "super-secret" not in result.content.unknowns[0]
    assert "super-secret" not in result.content.findings[0].unknowns[0]
    assert result.wecom_markdown["msgtype"] == "markdown"
    assert result.generic_webhook["finding_summaries"] == ["K线链路数据新鲜度异常"]
    assert result.generic_webhook["unknowns"] == ["password=[REDACTED]"]


def test_notification_service_keeps_alert_when_diagnosis_fails() -> None:
    payload = parse_alertmanager_payload(
        json.loads((FIXTURE_DIR / "kline_freshness_firing.json").read_text())
    )
    service = NotificationService(diagnosis_runner=FailingDiagnosisRunner())

    result = service.build(payload)

    assert result.content.findings == []
    assert result.content.unknowns == ["诊断执行失败：password=[REDACTED]"]
    assert "super-secret" not in result.content.unknowns[0]
    assert result.generic_webhook["diagnosis_status"] == "unknown"
    assert result.generic_webhook["unknowns"] == ["诊断执行失败：password=[REDACTED]"]
