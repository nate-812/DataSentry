from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError

from datasentry.domain import Operation, OperationRisk, OperationStatus


def test_forbidden_operation_cannot_be_approved(observed_at: datetime) -> None:
    with pytest.raises(ValidationError):
        Operation(
            name="arbitrary_shell",
            version="1",
            risk=OperationRisk.FORBIDDEN,
            status=OperationStatus.APPROVED,
            requester="operator",
            approver="reviewer",
            requested_at=observed_at,
            approved_at=observed_at,
        )


def test_approved_at_requires_approver(observed_at: datetime) -> None:
    with pytest.raises(ValidationError):
        Operation(
            name="refresh_diagnosis",
            version="1",
            risk=OperationRisk.L1,
            status=OperationStatus.APPROVED,
            requester="operator",
            requested_at=observed_at,
            approved_at=observed_at,
        )


def test_operation_rejects_invalid_time_order(observed_at: datetime) -> None:
    with pytest.raises(ValidationError):
        Operation(
            name="refresh_diagnosis",
            version="1",
            risk=OperationRisk.L1,
            status=OperationStatus.SUCCEEDED,
            requester="operator",
            approver="reviewer",
            requested_at=observed_at,
            approved_at=observed_at + timedelta(seconds=2),
            executed_at=observed_at + timedelta(seconds=1),
            verified_at=observed_at + timedelta(seconds=3),
        )
