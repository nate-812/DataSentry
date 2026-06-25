from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError

from datasentry.domain import Inspection, InspectionStatus, Observation


def test_completed_inspection_requires_finished_at(observed_at: datetime) -> None:
    with pytest.raises(ValidationError):
        Inspection(
            id="11111111-1111-4111-8111-111111111111",
            question="M0 inspection",
            scope=["simulation"],
            status=InspectionStatus.COMPLETED,
            started_at=observed_at,
        )


def test_inspection_rejects_finished_at_before_started_at(observed_at: datetime) -> None:
    with pytest.raises(ValidationError):
        Inspection(
            question="M0 inspection",
            status=InspectionStatus.COMPLETED,
            started_at=observed_at,
            finished_at=observed_at - timedelta(seconds=1),
        )


def test_observation_rejects_naive_datetime(inspection_id: str) -> None:
    with pytest.raises(ValidationError):
        Observation(
            inspection_id=inspection_id,
            component="flink",
            metric_or_fact="job_state",
            value={"state": "RUNNING"},
            source="simulation",
            observed_at=datetime(2026, 6, 25, 12, 0),
        )


def test_observation_json_dump_is_serializable(
    inspection_id: str,
    observed_at: datetime,
) -> None:
    observation = Observation(
        inspection_id=inspection_id,
        component="flink",
        metric_or_fact="job_state",
        value={"state": "RUNNING", "parallelism": 3},
        source="simulation",
        observed_at=observed_at,
    )

    assert observation.model_dump(mode="json")["observed_at"] == "2026-06-25T12:00:00Z"


def test_optional_datetime_accepts_explicit_none(observed_at: datetime) -> None:
    inspection = Inspection(
        question="M0 inspection",
        started_at=observed_at,
        finished_at=None,
    )

    assert inspection.finished_at is None
