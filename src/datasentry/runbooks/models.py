"""M6 Runbook 领域模型。"""

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


class ExecutionMode(StrEnum):
    MOCK = "mock"
    FORBIDDEN = "forbidden"


class OperationEventType(StrEnum):
    OPERATION_REQUESTED = "operation_requested"
    POLICY_EVALUATED = "policy_evaluated"
    IDEMPOTENCY_REUSED = "idempotency_reused"
    APPROVAL_GRANTED = "approval_granted"
    APPROVAL_REJECTED = "approval_rejected"
    EXECUTION_STARTED = "execution_started"
    EXECUTOR_OUTPUT_RECORDED = "executor_output_recorded"
    VERIFICATION_STARTED = "verification_started"
    VERIFICATION_SUCCEEDED = "verification_succeeded"
    VERIFICATION_FAILED = "verification_failed"
    OPERATION_FAILED = "operation_failed"
    OPERATION_CANCELLED = "operation_cancelled"


class Runbook(DomainModel):
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    risk: OperationRisk
    execution_mode: ExecutionMode
    parameter_schema: dict[str, JsonValue] = Field(default_factory=dict)
    precheck: dict[str, JsonValue] = Field(default_factory=dict)
    postcheck: dict[str, JsonValue] = Field(default_factory=dict)
    lock_key_template: str = Field(min_length=1)
    idempotency_key_template: str = Field(min_length=1)
    enabled: bool = True
    audit_notes: str | None = None

    @model_validator(mode="after")
    def validate_runbook_policy(self) -> Self:
        if (
            self.execution_mode is ExecutionMode.FORBIDDEN
            and self.risk is not OperationRisk.FORBIDDEN
        ):
            raise ValueError("forbidden 执行模式必须使用 forbidden 风险等级")
        return self


class OperationEvent(DomainModel):
    id: str = Field(default_factory=new_id)
    operation_id: str = Field(min_length=1)
    event_type: OperationEventType
    summary: str = Field(min_length=1)
    actor: str = Field(min_length=1)
    payload: dict[str, JsonValue] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)

    _normalize_created_at = field_validator("created_at")(require_aware_datetime)

    @field_validator("payload")
    @classmethod
    def redact_payload(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        return cast("dict[str, JsonValue]", redact_value(value))


class OperationLock(DomainModel):
    lock_key: str = Field(min_length=1)
    operation_id: str = Field(min_length=1)
    runbook_name: str = Field(min_length=1)
    target: str = Field(min_length=1)
    acquired_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime
    released_at: datetime | None = None

    _normalize_acquired_at = field_validator("acquired_at")(require_aware_datetime)
    _normalize_expires_at = field_validator("expires_at")(require_aware_datetime)
    _normalize_released_at = field_validator("released_at")(normalize_optional_datetime)

    @model_validator(mode="after")
    def validate_lock_window(self) -> Self:
        if self.expires_at <= self.acquired_at:
            raise ValueError("锁过期时间必须晚于获取时间")
        if self.released_at is not None and self.released_at < self.acquired_at:
            raise ValueError("锁释放时间不能早于获取时间")
        return self


class RunbookExecutionResult(DomainModel):
    status: str = Field(pattern=r"^(succeeded|failed)$")
    summary: str = Field(min_length=1)
    details: dict[str, JsonValue] = Field(default_factory=dict)
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime = Field(default_factory=utc_now)

    _normalize_started_at = field_validator("started_at")(require_aware_datetime)
    _normalize_finished_at = field_validator("finished_at")(require_aware_datetime)


class RunbookVerificationResult(DomainModel):
    status: str = Field(pattern=r"^(succeeded|failed)$")
    summary: str = Field(min_length=1)
    details: dict[str, JsonValue] = Field(default_factory=dict)
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime = Field(default_factory=utc_now)

    _normalize_started_at = field_validator("started_at")(require_aware_datetime)
    _normalize_finished_at = field_validator("finished_at")(require_aware_datetime)
