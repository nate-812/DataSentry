from datetime import UTC, datetime

import pytest

from datasentry.domain import Operation, OperationStatus
from datasentry.errors import DataSentryError
from datasentry.runbooks import (
    OperationEvent,
    OperationEventType,
    OperationLock,
    Runbook,
    RunbookOperationService,
)

NOW = datetime(2026, 6, 28, 12, 0, tzinfo=UTC)


class FakeRunbookRepository:
    def __init__(self) -> None:
        self.runbooks: dict[str, Runbook] = {}
        self.operations: dict[str, Operation] = {}
        self.events_by_operation_id: dict[str, list[OperationEvent]] = {}
        self.locks: dict[str, OperationLock] = {}

    def save_runbook(self, runbook: Runbook) -> None:
        self.runbooks[runbook.name] = runbook.model_copy(deep=True)

    def save_operation(self, operation: Operation) -> None:
        self.operations[operation.id] = operation.model_copy(deep=True)

    def update_operation(self, operation: Operation) -> None:
        self.operations[operation.id] = operation.model_copy(deep=True)

    def get_operation(self, operation_id: str) -> Operation:
        return self.operations[operation_id].model_copy(deep=True)

    def save_operation_event(self, event: OperationEvent) -> None:
        self.events_by_operation_id.setdefault(event.operation_id, []).append(
            event.model_copy(deep=True),
        )

    def list_operation_events(self, operation_id: str) -> list[OperationEvent]:
        return [
            event.model_copy(deep=True)
            for event in self.events_by_operation_id.get(operation_id, [])
        ]

    def get_active_operation_by_idempotency_key(
        self,
        idempotency_key: str | None,
    ) -> Operation | None:
        if idempotency_key is None:
            return None
        terminal_statuses = {
            OperationStatus.SUCCEEDED,
            OperationStatus.FAILED,
            OperationStatus.REJECTED,
            OperationStatus.CANCELLED,
        }
        for operation in self.operations.values():
            if (
                operation.idempotency_key == idempotency_key
                and operation.status not in terminal_statuses
            ):
                return operation.model_copy(deep=True)
        return None

    def acquire_operation_lock(self, lock: OperationLock) -> None:
        active_lock = self.locks.get(lock.lock_key)
        if active_lock is not None and active_lock.released_at is None:
            raise DataSentryError(
                code="operation.lock_conflict",
                message="操作锁已被占用",
            )
        self.locks[lock.lock_key] = lock.model_copy(deep=True)

    def release_operation_lock(self, lock_key: str, *, released_at: datetime) -> None:
        lock = self.locks[lock_key]
        self.locks[lock_key] = lock.model_copy(update={"released_at": released_at})


def _service(repository: FakeRunbookRepository) -> RunbookOperationService:
    return RunbookOperationService(repository=repository, clock=lambda: NOW)


def _request(
    service: RunbookOperationService,
    runbook_name: str = "mock.restart_preview",
) -> Operation:
    return service.request(
        runbook_name,
        parameters={"target": "api", "reason": "演练"},
        requester="operator",
        incident_id=None,
    )


def _event_types(repository: FakeRunbookRepository, operation_id: str) -> list[str]:
    return [event.event_type.value for event in repository.list_operation_events(operation_id)]


def test_request_approve_execute_records_full_audit_flow() -> None:
    repository = FakeRunbookRepository()
    service = _service(repository)

    requested = _request(service)
    assert requested.status is OperationStatus.AWAITING_APPROVAL

    approved = service.approve(requested.id, approver="lead")
    assert approved.status is OperationStatus.APPROVED

    executed = service.execute(approved.id, actor="operator")
    assert executed.status is OperationStatus.SUCCEEDED
    assert executed.result is not None
    assert executed.result["execution"]["status"] == "succeeded"
    assert executed.result["verification"]["status"] == "succeeded"
    assert _event_types(repository, executed.id) == [
        OperationEventType.OPERATION_REQUESTED.value,
        OperationEventType.POLICY_EVALUATED.value,
        OperationEventType.APPROVAL_GRANTED.value,
        OperationEventType.EXECUTION_STARTED.value,
        OperationEventType.EXECUTOR_OUTPUT_RECORDED.value,
        OperationEventType.VERIFICATION_STARTED.value,
        OperationEventType.VERIFICATION_SUCCEEDED.value,
    ]


def test_request_reuses_active_operation_by_idempotency_key() -> None:
    repository = FakeRunbookRepository()
    service = _service(repository)

    first = _request(service)
    second = _request(service)

    assert second.id == first.id
    assert len(repository.operations) == 1
    assert _event_types(repository, first.id) == [
        OperationEventType.OPERATION_REQUESTED.value,
        OperationEventType.POLICY_EVALUATED.value,
        OperationEventType.IDEMPOTENCY_REUSED.value,
    ]


def test_forbidden_runbook_is_rejected_before_operation_creation() -> None:
    repository = FakeRunbookRepository()
    service = _service(repository)

    with pytest.raises(DataSentryError) as raised:
        _request(service, runbook_name="forbidden.shell_command")

    assert raised.value.code == "runbook.forbidden"
    assert repository.operations == {}


def test_execute_before_approve_raises_invalid_state() -> None:
    repository = FakeRunbookRepository()
    service = _service(repository)
    operation = _request(service)

    with pytest.raises(DataSentryError) as raised:
        service.execute(operation.id, actor="operator")

    assert raised.value.code == "operation.invalid_state"
    assert raised.value.details == {
        "operation_id": operation.id,
        "status": OperationStatus.AWAITING_APPROVAL.value,
    }
