from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError

from datasentry.domain import Incident, IncidentStatus, Severity


def test_resolved_incident_requires_resolved_at(observed_at: datetime) -> None:
    with pytest.raises(ValidationError):
        Incident(
            title="Kline delayed",
            symptom="Doris freshness is behind",
            status=IncidentStatus.RESOLVED,
            severity=Severity.WARNING,
            opened_at=observed_at,
            updated_at=observed_at,
        )


def test_incident_rejects_update_before_open(observed_at: datetime) -> None:
    with pytest.raises(ValidationError):
        Incident(
            title="Kline delayed",
            symptom="Doris freshness is behind",
            severity=Severity.WARNING,
            opened_at=observed_at,
            updated_at=observed_at - timedelta(seconds=1),
        )
