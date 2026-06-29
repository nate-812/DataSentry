from datetime import UTC, datetime

import pytest

from datasentry.domain import Operation, OperationRisk, OperationStatus
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
        self.conflicting_operation: Operation | None = None
        self.fail_on_event_type: OperationEventType | None = None

    def save_runbook(self, runbook: Runbook) -> None:
        self.runbooks[runbook.name] = runbook.model_copy(deep=True)

    def save_operation(self, operation: Operation) -> None:
        if self.conflicting_operation is not None:
            conflicting_operation = self.conflicting_operation
            self.conflicting_operation = None
            self.operations[conflicting_operation.id] = conflicting_operation.model_copy(
                deep=True,
            )
            raise DataSentryError(
                code="storage.conflict",
                message="操作幂等键已存在",
            )
        self.operations[operation.id] = operation.model_copy(deep=True)

    def update_operation(self, operation: Operation) -> None:
        self.operations[operation.id] = operation.model_copy(deep=True)

    def get_operation(self, operation_id: str) -> Operation:
        return self.operations[operation_id].model_copy(deep=True)

    def save_operation_event(self, event: OperationEvent) -> None:
        if event.event_type is self.fail_on_event_type:
            raise DataSentryError(
                code="storage.write_failed",
                message="审计事件写入失败",
            )
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


def test_service_events_use_strictly_increasing_timestamps_with_constant_clock() -> None:
    repository = FakeRunbookRepository()
    service = _service(repository)

    requested = _request(service)
    approved = service.approve(requested.id, approver="lead")
    executed = service.execute(approved.id, actor="operator")

    events = repository.list_operation_events(executed.id)
    event_times = [event.created_at for event in events]
    assert event_times == sorted(event_times)
    assert len(set(event_times)) == len(event_times)
    sorted_event_types = [
        event.event_type.value for event in sorted(events, key=lambda item: item.created_at)
    ]
    assert sorted_event_types == [
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


def test_request_recovers_active_operation_after_idempotency_storage_conflict() -> None:
    repository = FakeRunbookRepository()
    repository.conflicting_operation = Operation(
        id="11111111-1111-4111-8111-111111111111",
        name="mock.restart_preview",
        version="1.0.0",
        idempotency_key="mock.restart_preview:1.0.0:api:none",
        parameters={"target": "api", "reason": "演练"},
        risk=OperationRisk.L1,
        status=OperationStatus.AWAITING_APPROVAL,
        requester="other-operator",
        requested_at=NOW,
    )
    service = _service(repository)

    operation = _request(service)

    assert operation.id == "11111111-1111-4111-8111-111111111111"
    assert _event_types(repository, operation.id) == [
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


def test_execute_propagates_success_audit_failure_without_marking_failed() -> None:
    repository = FakeRunbookRepository()
    repository.fail_on_event_type = OperationEventType.VERIFICATION_SUCCEEDED
    service = _service(repository)
    requested = _request(service)
    approved = service.approve(requested.id, approver="lead")

    with pytest.raises(DataSentryError) as raised:
        service.execute(approved.id, actor="operator")

    assert raised.value.code == "storage.write_failed"
    saved_operation = repository.get_operation(approved.id)
    assert saved_operation.status is OperationStatus.SUCCEEDED
    assert saved_operation.result is not None
    assert saved_operation.result["execution"]["status"] == "succeeded"
    assert repository.locks["runbook:mock.restart_preview:api"].released_at is not None
    assert OperationEventType.OPERATION_FAILED.value not in _event_types(
        repository,
        approved.id,
    )
