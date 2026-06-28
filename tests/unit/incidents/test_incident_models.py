"""M5 事件记忆领域模型测试。"""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from datasentry.domain.enums import IncidentStatus, Severity
from datasentry.incidents import (
    IncidentFingerprint,
    IncidentLink,
    IncidentLinkKind,
    IncidentRCAReport,
    IncidentTimelineEvent,
    IncidentTimelineEventType,
)


def test_timeline_event_summary_must_not_be_empty() -> None:
    with pytest.raises(ValidationError):
        IncidentTimelineEvent(
            incident_id="incident-1",
            event_type=IncidentTimelineEventType.ALERT_FIRED,
            summary="",
            source="alertmanager",
        )


def test_incident_link_preserves_kind_and_target_id() -> None:
    link = IncidentLink(
        incident_id="incident-1",
        kind=IncidentLinkKind.FINDING,
        target_id="finding-1",
        summary="关联诊断结论",
    )

    assert link.kind is IncidentLinkKind.FINDING
    assert link.target_id == "finding-1"


def test_incident_fingerprint_preserves_component_and_active_window() -> None:
    first_seen_at = datetime(2026, 6, 28, 1, 0, tzinfo=UTC)
    last_seen_at = first_seen_at + timedelta(minutes=5)

    fingerprint = IncidentFingerprint(
        incident_id="incident-1",
        component="flink",
        failure_type="checkpoint_failed",
        stable_labels_hash="hash-1",
        severity=Severity.CRITICAL,
        first_seen_at=first_seen_at,
        last_seen_at=last_seen_at,
    )

    assert fingerprint.component == "flink"
    assert fingerprint.first_seen_at == first_seen_at
    assert fingerprint.last_seen_at == last_seen_at


def test_incident_rca_report_preserves_markdown_version_and_structured_status() -> None:
    report = IncidentRCAReport(
        incident_id="incident-1",
        version=2,
        markdown="# 复盘\n\n根因已定位。",
        structured={
            "status": IncidentStatus.RESOLVED,
            "severity": Severity.CRITICAL,
        },
        generated_by="deterministic-rca",
    )

    assert report.markdown.startswith("# 复盘")
    assert report.version == 2
    assert report.structured["status"] == IncidentStatus.RESOLVED
    assert report.structured["severity"] == Severity.CRITICAL
