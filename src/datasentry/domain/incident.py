"""Incident lifecycle snapshot model."""

from datetime import datetime
from typing import Self

from pydantic import Field, field_validator, model_validator

from datasentry.domain.common import (
    DomainModel,
    new_id,
    normalize_optional_datetime,
    require_aware_datetime,
    utc_now,
)
from datasentry.domain.enums import IncidentStatus, Severity


class Incident(DomainModel):
    id: str = Field(default_factory=new_id)
    title: str = Field(min_length=1)
    symptom: str = Field(min_length=1)
    status: IncidentStatus = IncidentStatus.OPEN
    severity: Severity
    root_cause: str | None = None
    opened_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    resolved_at: datetime | None = None

    _normalize_opened_at = field_validator("opened_at")(require_aware_datetime)
    _normalize_updated_at = field_validator("updated_at")(require_aware_datetime)
    _normalize_resolved_at = field_validator("resolved_at")(normalize_optional_datetime)

    @model_validator(mode="after")
    def validate_lifecycle_times(self) -> Self:
        if self.updated_at < self.opened_at:
            raise ValueError("updated_at must not be before opened_at")
        if self.status is IncidentStatus.RESOLVED and self.resolved_at is None:
            raise ValueError("resolved incident requires resolved_at")
        if self.resolved_at is not None and self.resolved_at < self.opened_at:
            raise ValueError("resolved_at must not be before opened_at")
        return self
