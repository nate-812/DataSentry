"""巡检与实时观察模型。"""

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
from datasentry.domain.enums import InspectionStatus


class Inspection(DomainModel):
    id: str = Field(default_factory=new_id)
    question: str = Field(min_length=1)
    scope: list[str] = Field(default_factory=list)
    status: InspectionStatus = InspectionStatus.RUNNING
    summary: str | None = None
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime | None = None

    _normalize_started_at = field_validator("started_at")(require_aware_datetime)
    _normalize_finished_at = field_validator("finished_at")(normalize_optional_datetime)

    @model_validator(mode="after")
    def validate_completion(self) -> Self:
        if self.status is InspectionStatus.COMPLETED and self.finished_at is None:
            raise ValueError("已完成的巡检必须包含 finished_at")
        if self.finished_at is not None and self.finished_at < self.started_at:
            raise ValueError("finished_at 不能早于 started_at")
        return self


class Observation(DomainModel):
    id: str = Field(default_factory=new_id)
    inspection_id: str = Field(min_length=1)
    component: str = Field(min_length=1)
    metric_or_fact: str = Field(min_length=1)
    value: JsonValue
    source: str = Field(min_length=1)
    target: str | None = None
    observed_at: datetime = Field(default_factory=utc_now)

    _normalize_observed_at = field_validator("observed_at")(require_aware_datetime)
