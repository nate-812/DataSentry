"""M7 有限自治领域模型。"""

from datetime import datetime
from enum import StrEnum
from typing import Self, cast

from pydantic import Field, JsonValue, field_validator, model_validator

from datasentry.domain.common import (
    DomainModel,
    new_id,
    normalize_optional_datetime,
    require_aware_datetime,
    utc_now,
)
from datasentry.domain.enums import OperationRisk
from datasentry.redaction import redact_value


class CircuitBreakerState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class AutonomyDecisionStatus(StrEnum):
    ALLOWED = "allowed"
    SHADOWED = "shadowed"
    BLOCKED = "blocked"
    ESCALATED = "escalated"


class MaintenanceWindow(DomainModel):
    weekdays: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4])
    start_minute_utc: int = Field(default=60, ge=0, le=1439)
    end_minute_utc: int = Field(default=600, ge=1, le=1440)

    @field_validator("weekdays")
    @classmethod
    def validate_weekdays(cls, value: list[int]) -> list[int]:
        unique_weekdays = sorted(set(value))
        if not unique_weekdays:
            raise ValueError("维护窗口必须至少包含一天")
        if any(weekday < 0 or weekday > 6 for weekday in unique_weekdays):
            raise ValueError("维护窗口星期必须在 0 到 6 之间")
        return unique_weekdays

    @model_validator(mode="after")
    def validate_window_range(self) -> Self:
        if self.end_minute_utc <= self.start_minute_utc:
            raise ValueError("维护窗口结束分钟必须大于开始分钟")
        return self

    def matches(self, now: datetime) -> bool:
        normalized_now = require_aware_datetime(now)
        minute_of_day = normalized_now.hour * 60 + normalized_now.minute
        return normalized_now.weekday() in self.weekdays and (
            self.start_minute_utc <= minute_of_day < self.end_minute_utc
        )


class RateLimitRule(DomainModel):
    scope: str = Field(pattern=r"^(per_runbook|per_target|per_incident)$")
    window_seconds: int = Field(default=3600, gt=0)
    limit: int = 3

    @field_validator("limit")
    @classmethod
    def validate_limit(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("速率限制次数必须大于 0")
        return value


class AutonomyPolicy(DomainModel):
    runbook_name: str = Field(min_length=1)
    enabled: bool = False
    shadow_mode: bool = True
    allowed_risks: list[OperationRisk] = Field(
        default_factory=lambda: [OperationRisk.L0, OperationRisk.L1],
    )
    maintenance_windows: list[MaintenanceWindow] = Field(
        default_factory=lambda: [MaintenanceWindow()],
    )
    rate_limits: list[RateLimitRule] = Field(
        default_factory=lambda: [
            RateLimitRule(scope="per_runbook", window_seconds=3600, limit=3),
            RateLimitRule(scope="per_target", window_seconds=3600, limit=1),
            RateLimitRule(scope="per_incident", window_seconds=3600, limit=1),
        ],
    )
    min_success_rate: float = Field(default=0.95, ge=0, le=1)
    min_success_samples: int = Field(default=5, ge=0)
    failure_threshold: int = Field(default=2, gt=0)
    circuit_breaker_state: CircuitBreakerState = CircuitBreakerState.CLOSED
    updated_at: datetime = Field(default_factory=utc_now)

    _normalize_updated_at = field_validator("updated_at")(require_aware_datetime)


class AutonomyDecision(DomainModel):
    status: AutonomyDecisionStatus
    reason_code: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    runbook_name: str = Field(min_length=1)
    target: str | None = None
    incident_id: str | None = None
    operation_id: str | None = None
    window_matched: bool = False
    payload: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("payload")
    @classmethod
    def redact_payload(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        return cast("dict[str, JsonValue]", redact_value(value))


class AutonomyRunRecord(DomainModel):
    id: str = Field(default_factory=new_id)
    runbook_name: str = Field(min_length=1)
    target: str = Field(min_length=1)
    incident_id: str | None = None
    operation_id: str | None = None
    decision_status: AutonomyDecisionStatus
    reason_code: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime | None = None
    succeeded: bool | None = None
    payload: dict[str, JsonValue] = Field(default_factory=dict)

    _normalize_created_at = field_validator("created_at")(require_aware_datetime)
    _normalize_finished_at = field_validator("finished_at")(normalize_optional_datetime)

    @field_validator("payload")
    @classmethod
    def redact_payload(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        return cast("dict[str, JsonValue]", redact_value(value))

    @model_validator(mode="after")
    def validate_allowed_operation_link(self) -> Self:
        if self.decision_status is AutonomyDecisionStatus.ALLOWED and self.operation_id is None:
            raise ValueError("allowed 决策必须关联 Operation")
        return self
