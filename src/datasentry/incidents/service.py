"""Incident 记忆编排服务。"""

from typing import Protocol, cast

from datasentry.domain import EvidenceStatus, Finding, Incident, IncidentStatus, Severity
from datasentry.domain.common import utc_now
from datasentry.incidents.fingerprints import build_alert_fingerprint
from datasentry.incidents.lifecycle import next_status_for_alert, next_status_for_diagnosis_failure
from datasentry.incidents.models import (
    IncidentAction,
    IncidentDetail,
    IncidentFingerprint,
    IncidentLink,
    IncidentLinkKind,
    IncidentRCAReport,
    IncidentTimelineEvent,
    IncidentTimelineEventType,
    IncidentUpsertResult,
)
from datasentry.incidents.rca import build_rca_report
from datasentry.notifications import AlertmanagerPayload
from datasentry.notifications.deduplication import build_alert_deduplication_key
from datasentry.notifications.service import map_alert_to_question
from datasentry.storage import Repository
from datasentry.tools import LiveInspectionResult
from datasentry.tools.redaction import redact_text, redact_value


class DiagnosisRunner(Protocol):
    """执行现场只读诊断的最小协议。"""

    def run(self, question: str) -> LiveInspectionResult:
        raise NotImplementedError  # pragma: no cover


class IncidentService:
    """处理告警建档、时间线、历史记忆和 RCA。"""

    def __init__(self, *, repository: Repository, diagnosis_runner: DiagnosisRunner) -> None:
        self._repository = repository
        self._diagnosis_runner = diagnosis_runner

    def handle_alertmanager_payload(self, payload: AlertmanagerPayload) -> IncidentUpsertResult:
        labels = self._labels(payload)
        question = map_alert_to_question(payload)
        deduplication_key = build_alert_deduplication_key(payload)
        probe = build_alert_fingerprint(incident_id="pending", labels=labels)
        incident_id = self._repository.find_active_incident_by_fingerprint(probe)
        action = IncidentAction.UPDATED if incident_id is not None else IncidentAction.CREATED
        incident = (
            self._repository.get_incident(incident_id)
            if incident_id is not None
            else self._create_incident(payload, labels, probe)
        )
        status = next_status_for_alert(incident.status, alert_status=payload.status)
        incident = incident.model_copy(
            update={
                "status": status,
                "severity": self._max_severity(incident.severity, probe.severity),
                "updated_at": utc_now(),
            }
        )
        self._repository.update_incident(incident)
        fingerprint = probe.model_copy(update={"incident_id": incident.id})
        self._repository.save_incident_fingerprint(fingerprint)
        self._repository.save_incident_link(
            IncidentLink(
                incident_id=incident.id,
                kind=IncidentLinkKind.ALERT,
                target_id=deduplication_key,
                summary="Alertmanager 告警",
            )
        )
        self._append_event(
            incident.id,
            event_type=(
                IncidentTimelineEventType.ALERT_RESOLVED
                if payload.status == "resolved"
                else IncidentTimelineEventType.ALERT_FIRED
            ),
            summary=f"Alertmanager {payload.status}: {labels.get('alertname', 'unknown')}",
            payload={"status": payload.status, "labels": labels},
        )
        if payload.status == "resolved":
            return IncidentUpsertResult(
                incident_id=incident.id,
                action=IncidentAction.RESOLVED_SIGNAL_RECORDED,
                status=status,
                deduplication_key=deduplication_key,
                diagnosis_question=question,
            )

        try:
            result = self._diagnosis_runner.run(question)
        except Exception as error:
            blocked = incident.model_copy(
                update={
                    "status": next_status_for_diagnosis_failure(status),
                    "updated_at": utc_now(),
                }
            )
            self._repository.update_incident(blocked)
            self._append_event(
                incident.id,
                event_type=IncidentTimelineEventType.DIAGNOSIS_FAILED,
                summary=f"诊断执行失败：{redact_text(str(error))}",
                payload={"error": redact_text(str(error))},
            )
            return IncidentUpsertResult(
                incident_id=incident.id,
                action=IncidentAction.DIAGNOSIS_FAILED,
                status=blocked.status,
                deduplication_key=deduplication_key,
                diagnosis_question=question,
            )

        self._link_diagnosis(incident, result)
        refreshed = self._repository.get_incident(incident.id)
        return IncidentUpsertResult(
            incident_id=incident.id,
            action=action,
            status=refreshed.status,
            deduplication_key=deduplication_key,
            diagnosis_question=question,
        )

    def get_detail(self, incident_id: str) -> IncidentDetail:
        return IncidentDetail(
            incident=self._repository.get_incident(incident_id),
            links=self._repository.list_incident_links(incident_id),
            timeline=self._repository.list_timeline_events(incident_id),
            fingerprints=self._repository.list_incident_fingerprints(incident_id),
            latest_rca=self._repository.get_latest_rca_report(incident_id),
        )

    def find_similar(self, incident_id: str, *, limit: int = 5) -> list[Incident]:
        fingerprints = self._repository.list_incident_fingerprints(incident_id)
        if not fingerprints:
            return []
        return [
            incident
            for incident in self._repository.search_similar_incidents(
                fingerprints[0],
                limit=limit + 1,
            )
            if incident.id != incident_id
        ][:limit]

    def generate_rca(self, incident_id: str) -> IncidentRCAReport:
        detail = self.get_detail(incident_id)
        existing = self._repository.list_rca_reports(incident_id)
        similar = self.find_similar(incident_id)
        report = build_rca_report(
            incident=detail.incident,
            timeline=detail.timeline,
            evidence_summaries=[
                link.summary
                for link in detail.links
                if link.kind in {IncidentLinkKind.FINDING, IncidentLinkKind.INSPECTION}
            ],
            similar_summaries=[f"{item.updated_at.isoformat()} {item.title}" for item in similar],
            unknowns=[],
            next_version=len(existing) + 1,
        )
        self._repository.save_rca_report(report)
        self._repository.save_incident_link(
            IncidentLink(
                incident_id=incident_id,
                kind=IncidentLinkKind.RCA_REPORT,
                target_id=report.id,
                summary=f"生成 RCA 草稿 v{report.version}",
            )
        )
        self._append_event(
            incident_id,
            event_type=IncidentTimelineEventType.RCA_GENERATED,
            summary=f"生成 RCA 草稿 v{report.version}",
            payload={"rca_report_id": report.id, "version": report.version},
        )
        return report

    def _create_incident(
        self,
        payload: AlertmanagerPayload,
        labels: dict[str, str],
        fingerprint: IncidentFingerprint,
    ) -> Incident:
        alertname = labels.get("alertname", "StreamLakeAlert")
        component = fingerprint.component
        incident = Incident(
            title=f"{alertname} on {component}",
            symptom=(
                payload.primary_alert.annotations.get("summary")
                or payload.common_annotations.get("summary")
                or f"{alertname} 告警触发"
            ),
            status=IncidentStatus.OPEN,
            severity=fingerprint.severity,
        )
        self._repository.save_incident(incident)
        return incident

    def _link_diagnosis(self, incident: Incident, result: LiveInspectionResult) -> None:
        aggregate = result.diagnosis.aggregate
        self._repository.save_incident_link(
            IncidentLink(
                incident_id=incident.id,
                kind=IncidentLinkKind.INSPECTION,
                target_id=aggregate.inspection.id,
                summary=aggregate.inspection.summary or "诊断巡检完成",
            )
        )
        findings = list(aggregate.findings)
        for finding in findings:
            self._repository.save_incident_link(
                IncidentLink(
                    incident_id=incident.id,
                    kind=IncidentLinkKind.FINDING,
                    target_id=finding.id,
                    summary=finding.claim,
                )
            )
            self._append_event(
                incident.id,
                event_type=IncidentTimelineEventType.FINDING_ADDED,
                summary=finding.claim,
                payload={"finding_id": finding.id, "status": finding.status.value},
            )
        root_cause = self._root_cause(findings)
        updated = incident.model_copy(
            update={
                "root_cause": root_cause or incident.root_cause,
                "updated_at": utc_now(),
            }
        )
        self._repository.update_incident(updated)
        self._append_event(
            incident.id,
            event_type=IncidentTimelineEventType.DIAGNOSIS_COMPLETED,
            summary=aggregate.inspection.summary or "诊断完成",
            payload={"inspection_id": aggregate.inspection.id},
        )

    def _append_event(
        self,
        incident_id: str,
        *,
        event_type: IncidentTimelineEventType,
        summary: str,
        payload: dict[str, object],
    ) -> None:
        self._repository.save_timeline_event(
            IncidentTimelineEvent(
                incident_id=incident_id,
                event_type=event_type,
                summary=redact_text(summary),
                source="datasentry_incident_service",
                payload=cast(dict[str, object], redact_value(payload)),
            )
        )

    @staticmethod
    def _labels(payload: AlertmanagerPayload) -> dict[str, str]:
        return payload.common_labels | payload.group_labels | payload.primary_alert.labels

    @staticmethod
    def _max_severity(left: Severity, right: Severity) -> Severity:
        order = {
            Severity.INFO: 0,
            Severity.WARNING: 1,
            Severity.CRITICAL: 2,
        }
        return left if order[left] >= order[right] else right

    @staticmethod
    def _root_cause(findings: list[Finding]) -> str | None:
        for finding in findings:
            if finding.status is EvidenceStatus.CONFIRMED:
                return finding.claim
        return None
