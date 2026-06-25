"""Evidence and diagnostic finding models."""

from datetime import datetime

from pydantic import Field, field_validator

from datasentry.domain.common import DomainModel, new_id, require_aware_datetime, utc_now
from datasentry.domain.enums import EvidenceStatus, Severity


class Evidence(DomainModel):
    claim: str = Field(min_length=1)
    status: EvidenceStatus
    source: str = Field(min_length=1)
    target: str | None = None
    observed_at: datetime
    summary: str = Field(min_length=1)

    _normalize_observed_at = field_validator("observed_at")(require_aware_datetime)


class Finding(DomainModel):
    id: str = Field(default_factory=new_id)
    inspection_id: str = Field(min_length=1)
    severity: Severity
    status: EvidenceStatus
    claim: str = Field(min_length=1)
    evidence: list[Evidence] = Field(min_length=1)
    impact: str = Field(min_length=1)
    recommendation: str = Field(min_length=1)
    unknowns: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)

    _normalize_created_at = field_validator("created_at")(require_aware_datetime)
