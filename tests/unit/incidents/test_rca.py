from datetime import UTC, datetime

from datasentry.domain import Incident, Severity
from datasentry.incidents import (
    IncidentTimelineEvent,
    IncidentTimelineEventType,
    build_rca_report,
)

NOW = datetime(2026, 6, 28, 11, 0, tzinfo=UTC)


def test_build_rca_report_contains_boundary_statement_and_timeline() -> None:
    incident = Incident(
        id="incident-1",
        title="K线数据不更新",
        symptom="页面显示旧 Kline",
        severity=Severity.WARNING,
        root_cause="Flink Kline Job 延迟",
        opened_at=NOW,
        updated_at=NOW,
    )
    timeline = [
        IncidentTimelineEvent(
            incident_id=incident.id,
            event_type=IncidentTimelineEventType.ALERT_FIRED,
            summary="收到 KlineFreshnessStale 告警",
            source="alertmanager",
            occurred_at=NOW,
        )
    ]

    report = build_rca_report(
        incident=incident,
        timeline=timeline,
        evidence_summaries=["Doris kline_1min 业务时间滞后"],
        similar_summaries=["2026-06-20 曾出现 Flink lag"],
        unknowns=["需要人工确认 API 缓存"],
        next_version=1,
    )

    assert report.version == 1
    assert "历史事件仅用于经验参考，当前状态必须以本次只读巡检证据为准。" in report.markdown
    assert "收到 KlineFreshnessStale 告警" in report.markdown
    assert report.structured["unknowns"] == ["需要人工确认 API 缓存"]
