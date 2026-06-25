"""Controlled operation request and outcome model."""

from datetime import datetime
from typing import Self

from pydantic import Field, JsonValue, field_validator, model_validator

from datasentry.domain.common import (
    DomainModel,
    new_id,
    normalize_optional_datetime,
    require_aware_datetime,
    utc_now,
)
from datasentry.domain.enums import OperationRisk, OperationStatus

ACTIVE_OR_SUCCESSFUL_STATUSES = frozenset(
    {
        OperationStatus.APPROVED,
        OperationStatus.RUNNING,
        OperationStatus.VERIFYING,
        OperationStatus.SUCCEEDED,
    }
)


class Operation(DomainModel):
    id: str = Field(default_factory=new_id)
    incident_id: str | None = None
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    parameters: dict[str, JsonValue] = Field(default_factory=dict)
    risk: OperationRisk
    status: OperationStatus = OperationStatus.REQUESTED
    requester: str = Field(min_length=1)
    approver: str | None = None
    result: dict[str, JsonValue] | None = None
    requested_at: datetime = Field(default_factory=utc_now)
    approved_at: datetime | None = None
    executed_at: datetime | None = None
    verified_at: datetime | None = None

    _normalize_requested_at = field_validator("requested_at")(require_aware_datetime)
    _normalize_approved_at = field_validator("approved_at")(normalize_optional_datetime)
    _normalize_executed_at = field_validator("executed_at")(normalize_optional_datetime)
    _normalize_verified_at = field_validator("verified_at")(normalize_optional_datetime)

    @model_validator(mode="after")
    def validate_operation(self) -> Self:
        if self.risk is OperationRisk.FORBIDDEN and self.status in ACTIVE_OR_SUCCESSFUL_STATUSES:
            raise ValueError("forbidden operation cannot be approved or executed")
        if self.approved_at is not None and self.approver is None:
            raise ValueError("approved_at requires approver")

        times = [
            value
            for value in (
                self.requested_at,
                self.approved_at,
                self.executed_at,
                self.verified_at,
            )
            if value is not None
        ]
        if times != sorted(times):
            raise ValueError("operation timestamps must be chronological")
        return self
