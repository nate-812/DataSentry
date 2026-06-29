"""Runbook 操作服务。"""

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Protocol, cast

from pydantic import JsonValue

from datasentry.domain import Operation, OperationStatus
from datasentry.domain.common import utc_now
from datasentry.errors import DataSentryError
from datasentry.runbooks.catalog import BuiltInRunbookCatalog
from datasentry.runbooks.executor import MockRunbookExecutor
from datasentry.runbooks.idempotency import (
    render_idempotency_key,
    render_lock_key,
    require_target,
)
from datasentry.runbooks.models import (
    OperationEvent,
    OperationEventType,
    OperationLock,
    Runbook,
    RunbookExecutionResult,
    RunbookVerificationResult,
)
from datasentry.runbooks.policy import RunbookPolicy
from datasentry.runbooks.verifier import MockOperationVerifier


class RunbookRepository(Protocol):
    def save_runbook(self, runbook: Runbook) -> None:
        raise NotImplementedError  # pragma: no cover

    def save_operation(self, operation: Operation) -> None:
        raise NotImplementedError  # pragma: no cover

    def update_operation(self, operation: Operation) -> None:
        raise NotImplementedError  # pragma: no cover

    def get_operation(self, operation_id: str) -> Operation:
        raise NotImplementedError  # pragma: no cover

    def save_operation_event(self, event: OperationEvent) -> None:
        raise NotImplementedError  # pragma: no cover

    def list_operation_events(self, operation_id: str) -> list[OperationEvent]:
        raise NotImplementedError  # pragma: no cover

    def get_active_operation_by_idempotency_key(
        self,
        idempotency_key: str | None,
    ) -> Operation | None:
        raise NotImplementedError  # pragma: no cover

    def acquire_operation_lock(self, lock: OperationLock) -> None:
        raise NotImplementedError  # pragma: no cover

    def release_operation_lock(self, lock_key: str, *, released_at: datetime) -> None:
        raise NotImplementedError  # pragma: no cover


class RunbookCatalog(Protocol):
    def get(self, name: str) -> Runbook:
        raise NotImplementedError  # pragma: no cover


class RunbookExecutor(Protocol):
    def execute(self, runbook: Runbook, operation: Operation) -> RunbookExecutionResult:
        raise NotImplementedError  # pragma: no cover


class OperationVerifier(Protocol):
    def verify(self, runbook: Runbook, operation: Operation) -> RunbookVerificationResult:
        raise NotImplementedError  # pragma: no cover


class RunbookOperationService:
    """编排 Runbook 请求、审批、执行、审计和操作后验证。"""

    def __init__(
        self,
        *,
        repository: RunbookRepository,
        catalog: RunbookCatalog | None = None,
        policy: RunbookPolicy | None = None,
        executor: RunbookExecutor | None = None,
        verifier: OperationVerifier | None = None,
        clock: Callable[[], datetime] = utc_now,
        lock_ttl: timedelta = timedelta(minutes=5),
    ) -> None:
        self._repository = repository
        self._catalog = catalog or BuiltInRunbookCatalog()
        self._policy = policy or RunbookPolicy()
        self._clock = clock
        self._executor = executor or MockRunbookExecutor(clock=clock)
        self._verifier = verifier or MockOperationVerifier(clock=clock)
        self._lock_ttl = lock_ttl
        self._last_event_at: datetime | None = None

    def request(
        self,
        runbook_name: str,
        parameters: dict[str, JsonValue],
        requester: str,
        incident_id: str | None = None,
    ) -> Operation:
        runbook = self._catalog.get(runbook_name)
        self._repository.save_runbook(runbook)
        self._policy.assert_request_allowed(runbook)
        idempotency_key = render_idempotency_key(runbook, parameters, incident_id)

        existing_operation = self._repository.get_active_operation_by_idempotency_key(
            idempotency_key,
        )
        if existing_operation is not None:
            self._save_idempotency_reused_event(
                existing_operation.id,
                requester,
                idempotency_key,
            )
            return existing_operation

        operation = Operation(
            incident_id=incident_id,
            name=runbook.name,
            version=runbook.version,
            idempotency_key=idempotency_key,
            parameters=parameters,
            risk=runbook.risk,
            status=OperationStatus.AWAITING_APPROVAL,
            requester=requester,
            requested_at=self._clock(),
        )
        try:
            self._repository.save_operation(operation)
        except DataSentryError as error:
            if error.code != "storage.conflict":
                raise
            existing_operation = self._repository.get_active_operation_by_idempotency_key(
                idempotency_key,
            )
            if existing_operation is None:
                raise
            self._save_idempotency_reused_event(
                existing_operation.id,
                requester,
                idempotency_key,
            )
            return existing_operation
        self._save_event(
            operation.id,
            OperationEventType.OPERATION_REQUESTED,
            actor=requester,
            summary="Runbook 操作已提交审批",
            payload={"runbook": runbook.name, "risk": runbook.risk.value},
        )
        self._save_event(
            operation.id,
            OperationEventType.POLICY_EVALUATED,
            actor=requester,
            summary="Runbook 策略校验已通过",
            payload={"result": "allowed", "execution_mode": runbook.execution_mode.value},
        )
        return operation

    def approve(self, operation_id: str, approver: str) -> Operation:
        operation = self._get_operation_in_state(
            operation_id,
            {OperationStatus.AWAITING_APPROVAL},
        )
        now = self._clock()
        updated = operation.model_copy(
            update={
                "status": OperationStatus.APPROVED,
                "approver": approver,
                "approved_at": now,
            },
        )
        self._repository.update_operation(updated)
        self._save_event(
            updated.id,
            OperationEventType.APPROVAL_GRANTED,
            actor=approver,
            summary="Runbook 操作已批准",
            payload={"status": updated.status.value},
        )
        return updated

    def reject(self, operation_id: str, approver: str) -> Operation:
        operation = self._get_operation_in_state(
            operation_id,
            {OperationStatus.REQUESTED, OperationStatus.AWAITING_APPROVAL},
        )
        now = self._clock()
        updated = operation.model_copy(
            update={
                "status": OperationStatus.REJECTED,
                "approver": approver,
                "approved_at": now,
                "result": {"status": "rejected"},
            },
        )
        self._repository.update_operation(updated)
        self._save_event(
            updated.id,
            OperationEventType.APPROVAL_REJECTED,
            actor=approver,
            summary="Runbook 操作已拒绝",
            payload={"status": updated.status.value},
        )
        return updated

    def cancel(self, operation_id: str, actor: str) -> Operation:
        operation = self._get_operation_in_state(
            operation_id,
            {OperationStatus.REQUESTED, OperationStatus.AWAITING_APPROVAL},
        )
        updated = operation.model_copy(
            update={
                "status": OperationStatus.CANCELLED,
                "result": {"status": "cancelled"},
            },
        )
        self._repository.update_operation(updated)
        self._save_event(
            updated.id,
            OperationEventType.OPERATION_CANCELLED,
            actor=actor,
            summary="Runbook 操作已取消",
            payload={"status": updated.status.value},
        )
        return updated

    def execute(self, operation_id: str, actor: str) -> Operation:
        operation = self._get_operation_in_state(operation_id, {OperationStatus.APPROVED})
        runbook = self._catalog.get(operation.name)
        lock_key = render_lock_key(runbook, operation.parameters)
        target = require_target(operation.parameters)
        acquired_at = self._clock()
        lock = OperationLock(
            lock_key=lock_key,
            operation_id=operation.id,
            runbook_name=runbook.name,
            target=target,
            acquired_at=acquired_at,
            expires_at=acquired_at + self._lock_ttl,
        )
        self._repository.acquire_operation_lock(lock)

        current_operation = operation
        try:
            current_operation = self._mark_running(operation, actor)
            try:
                execution = self._executor.execute(runbook, current_operation)
            except Exception as error:
                return self._mark_failed_from_error(current_operation, actor, error)
            self._save_event(
                current_operation.id,
                OperationEventType.EXECUTOR_OUTPUT_RECORDED,
                actor=actor,
                summary="Runbook 执行器输出已记录",
                payload={"status": execution.status, "summary": execution.summary},
            )

            current_operation = current_operation.model_copy(
                update={"status": OperationStatus.VERIFYING},
            )
            self._repository.update_operation(current_operation)
            self._save_event(
                current_operation.id,
                OperationEventType.VERIFICATION_STARTED,
                actor=actor,
                summary="Runbook 操作后验证已开始",
                payload={"status": current_operation.status.value},
            )

            try:
                verification = self._verifier.verify(runbook, current_operation)
            except Exception as error:
                return self._mark_failed_from_error(current_operation, actor, error)
            final_operation = self._complete_execution(
                current_operation,
                actor,
                execution,
                verification,
            )
            return final_operation
        finally:
            self._repository.release_operation_lock(lock_key, released_at=self._clock())

    def events(self, operation_id: str) -> list[OperationEvent]:
        return self._repository.list_operation_events(operation_id)

    def _mark_running(self, operation: Operation, actor: str) -> Operation:
        now = self._clock()
        updated = operation.model_copy(
            update={
                "status": OperationStatus.RUNNING,
                "executed_at": now,
            },
        )
        self._repository.update_operation(updated)
        self._save_event(
            updated.id,
            OperationEventType.EXECUTION_STARTED,
            actor=actor,
            summary="Runbook 执行已开始",
            payload={"status": updated.status.value},
        )
        return updated

    def _complete_execution(
        self,
        operation: Operation,
        actor: str,
        execution: RunbookExecutionResult,
        verification: RunbookVerificationResult,
    ) -> Operation:
        result = cast(
            "dict[str, JsonValue]",
            {
                "execution": execution.model_dump(mode="json"),
                "verification": verification.model_dump(mode="json"),
            },
        )
        if execution.status == "succeeded" and verification.status == "succeeded":
            updated = operation.model_copy(
                update={
                    "status": OperationStatus.SUCCEEDED,
                    "verified_at": verification.verified_at,
                    "result": result,
                },
            )
            event_type = OperationEventType.VERIFICATION_SUCCEEDED
            summary = "Runbook 操作后验证已通过"
        else:
            updated = operation.model_copy(
                update={
                    "status": OperationStatus.FAILED,
                    "verified_at": verification.verified_at,
                    "result": result,
                },
            )
            event_type = OperationEventType.VERIFICATION_FAILED
            summary = "Runbook 操作后验证未通过"

        self._repository.update_operation(updated)
        self._save_event(
            updated.id,
            event_type,
            actor=actor,
            summary=summary,
            payload={
                "execution_status": execution.status,
                "verification_status": verification.status,
                "status": updated.status.value,
            },
        )
        return updated

    def _mark_failed_from_error(
        self,
        operation: Operation,
        actor: str,
        error: Exception,
    ) -> Operation:
        safe_error = self._safe_error(error)
        updated = operation.model_copy(
            update={
                "status": OperationStatus.FAILED,
                "result": {"status": "failed", "error": safe_error},
            },
        )
        self._repository.update_operation(updated)
        self._save_event(
            updated.id,
            OperationEventType.OPERATION_FAILED,
            actor=actor,
            summary="Runbook 操作执行失败",
            payload=safe_error,
        )
        return updated

    def _save_event(
        self,
        operation_id: str,
        event_type: OperationEventType,
        *,
        actor: str,
        summary: str,
        payload: dict[str, JsonValue] | None = None,
    ) -> None:
        self._repository.save_operation_event(
            OperationEvent(
                operation_id=operation_id,
                event_type=event_type,
                summary=summary,
                actor=actor,
                payload=payload or {},
                created_at=self._event_timestamp(),
            ),
        )

    def _save_idempotency_reused_event(
        self,
        operation_id: str,
        actor: str,
        idempotency_key: str,
    ) -> None:
        self._save_event(
            operation_id,
            OperationEventType.IDEMPOTENCY_REUSED,
            actor=actor,
            summary="复用已有未完成 Runbook 操作",
            payload={"idempotency_key": idempotency_key},
        )

    def _event_timestamp(self) -> datetime:
        current_at = self._clock()
        if self._last_event_at is not None and current_at <= self._last_event_at:
            current_at = self._last_event_at + timedelta(microseconds=1)
        self._last_event_at = current_at
        return current_at

    def _get_operation_in_state(
        self,
        operation_id: str,
        allowed_statuses: set[OperationStatus],
    ) -> Operation:
        operation = self._repository.get_operation(operation_id)
        if operation.status not in allowed_statuses:
            raise DataSentryError(
                code="operation.invalid_state",
                message="Operation 当前状态不允许执行该动作",
                details={
                    "operation_id": operation.id,
                    "status": operation.status.value,
                },
            )
        return operation

    @staticmethod
    def _safe_error(error: Exception) -> dict[str, JsonValue]:
        if isinstance(error, DataSentryError):
            return {
                "code": error.code,
                "message": error.message,
            }
        return {
            "code": "operation.execution_failed",
            "message": "Runbook 操作执行失败",
        }
