"""M5 事件记忆领域模型。"""

from datetime import datetime
from enum import StrEnum
from typing import Any, Self

from pydantic import Field, field_validator, model_validator

from datasentry.domain.common import (
    DomainModel,
    new_id,
    require_aware_datetime,
    utc_now,
)
from datasentry.domain.enums import IncidentStatus, Severity
from datasentry.domain.incident import Incident


class IncidentLinkKind(StrEnum):
    INSPECTION = "inspection"
    FINDING = "finding"
    OPERATION = "operation"
    ALERT = "alert"
    CHAT_RUN = "chat_run"
    RCA_REPORT = "rca_report"


class IncidentTimelineEventType(StrEnum):
    ALERT_FIRED = "alert_fired"
    ALERT_RESOLVED = "alert_resolved"
    DIAGNOSIS_STARTED = "diagnosis_started"
    DIAGNOSIS_COMPLETED = "diagnosis_completed"
    DIAGNOSIS_FAILED = "diagnosis_failed"
    FINDING_ADDED = "finding_added"
    OPERATION_LINKED = "operation_linked"
    STATUS_CHANGED = "status_changed"
    VERIFICATION_COMPLETED = "verification_completed"
    RCA_GENERATED = "rca_generated"
    MANUAL_NOTE_ADDED = "manual_note_added"


class IncidentAction(StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    RESOLVED_SIGNAL_RECORDED = "resolved_signal_recorded"
    DIAGNOSIS_FAILED = "diagnosis_failed"
    IGNORED = "ignored"


class IncidentLink(DomainModel):
    id: str = Field(default_factory=new_id)
    incident_id: str = Field(min_length=1)
    kind: IncidentLinkKind
    target_id: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=utc_now)

    _normalize_created_at = field_validator("created_at")(require_aware_datetime)


class IncidentTimelineEvent(DomainModel):
    id: str = Field(default_factory=new_id)
    incident_id: str = Field(min_length=1)
    event_type: IncidentTimelineEventType
    summary: str = Field(min_length=1)
    source: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=utc_now)

    _normalize_occurred_at = field_validator("occurred_at")(require_aware_datetime)


class IncidentFingerprint(DomainModel):
    id: str = Field(default_factory=new_id)
    incident_id: str = Field(min_length=1)
    component: str = Field(min_length=1)
    failure_type: str = Field(min_length=1)
    stable_labels_hash: str = Field(min_length=1)
    severity: Severity
    first_seen_at: datetime = Field(default_factory=utc_now)
    last_seen_at: datetime = Field(default_factory=utc_now)

    _normalize_first_seen_at = field_validator("first_seen_at")(require_aware_datetime)
    _normalize_last_seen_at = field_validator("last_seen_at")(require_aware_datetime)

    @model_validator(mode="after")
    def validate_active_window(self) -> Self:
        if self.last_seen_at < self.first_seen_at:
            raise ValueError("last_seen_at 不能早于 first_seen_at")
        return self


class IncidentRCAReport(DomainModel):
    id: str = Field(default_factory=new_id)
    incident_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    markdown: str = Field(min_length=1)
    structured: dict[str, Any] = Field(default_factory=dict)
    generated_by: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=utc_now)

    _normalize_created_at = field_validator("created_at")(require_aware_datetime)


class IncidentDetail(DomainModel):
    incident: Incident
    links: list[IncidentLink] = Field(default_factory=list)
    timeline: list[IncidentTimelineEvent] = Field(default_factory=list)
    fingerprints: list[IncidentFingerprint] = Field(default_factory=list)
    latest_rca: IncidentRCAReport | None = None


class IncidentUpsertResult(DomainModel):
    accepted: bool = True
    incident_id: str = Field(min_length=1)
    action: IncidentAction
    status: IncidentStatus
    deduplication_key: str = Field(min_length=1)
    diagnosis_question: str = Field(min_length=1)
