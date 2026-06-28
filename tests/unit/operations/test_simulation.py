from datetime import UTC, datetime

import pytest

from datasentry.domain import Operation, OperationRisk, OperationStatus
from datasentry.errors import DataSentryError
from datasentry.operations import SimulationOperationService

NOW = datetime(2026, 6, 27, 8, 0, tzinfo=UTC)


class MemoryOperationRepository:
    def __init__(self, operation: Operation) -> None:
        self.operation = operation

    def get_operation(self, operation_id: str) -> Operation:
        assert operation_id == self.operation.id
        return self.operation

    def update_operation(self, operation: Operation) -> None:
        self.operation = operation


def _simulation_operation() -> Operation:
    return Operation(
        id="11111111-1111-4111-8111-111111111111",
        name="simulate_restart_preview",
        version="1",
        risk=OperationRisk.L1,
        requester="operator",
        requested_at=NOW,
    )


def test_approve_simulation_operation_succeeds() -> None:
    operation = _simulation_operation()
    repository = MemoryOperationRepository(operation)
    service = SimulationOperationService(repository=repository, clock=lambda: NOW)

    updated = service.approve(operation.id, approver="operator")

    assert updated.status is OperationStatus.SUCCEEDED
    assert updated.approver == "operator"
    assert updated.approved_at == NOW
    assert updated.executed_at == NOW
    assert updated.verified_at == NOW
    assert updated.result == {"simulation": True, "status": "succeeded"}
    assert repository.operation == updated


def test_reject_simulation_operation_records_rejection() -> None:
    operation = _simulation_operation()
    repository = MemoryOperationRepository(operation)
    service = SimulationOperationService(repository=repository, clock=lambda: NOW)

    updated = service.reject(operation.id, approver="operator")

    assert updated.status is OperationStatus.REJECTED
    assert updated.approver == "operator"
    assert updated.approved_at == NOW
    assert updated.executed_at is None
    assert updated.verified_at is None
    assert updated.result == {"simulation": True, "status": "rejected"}
    assert repository.operation == updated


def test_reject_non_simulation_operation_is_denied() -> None:
    operation = Operation(
        id="11111111-1111-4111-8111-111111111111",
        name="restart_flink",
        version="1",
        risk=OperationRisk.L2,
        requester="operator",
        requested_at=NOW,
    )
    service = SimulationOperationService(
        repository=MemoryOperationRepository(operation),
        clock=lambda: NOW,
    )

    with pytest.raises(DataSentryError) as raised:
        service.approve(operation.id, approver="operator")

    assert raised.value.code == "operation.not_simulation"
