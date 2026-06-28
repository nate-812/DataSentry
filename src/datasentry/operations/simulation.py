"""本地模拟审批流，不执行生产 Runbook。"""

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from datasentry.domain import Operation, OperationStatus
from datasentry.domain.common import utc_now
from datasentry.errors import DataSentryError


class OperationRepository(Protocol):
    def get_operation(self, operation_id: str) -> Operation:
        raise NotImplementedError  # pragma: no cover

    def update_operation(self, operation: Operation) -> None:
        raise NotImplementedError  # pragma: no cover


class SimulationOperationService:
    """只推进本地模拟 Operation 状态，不连接生产组件。"""

    def __init__(
        self,
        *,
        repository: OperationRepository,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._repository = repository
        self._clock = clock

    def approve(self, operation_id: str, *, approver: str) -> Operation:
        operation = self._get_simulation_operation(operation_id)
        now = self._clock()
        updated = operation.model_copy(
            update={
                "status": OperationStatus.SUCCEEDED,
                "approver": approver,
                "approved_at": now,
                "executed_at": now,
                "verified_at": now,
                "result": {"simulation": True, "status": "succeeded"},
            },
        )
        self._repository.update_operation(updated)
        return updated

    def reject(self, operation_id: str, *, approver: str) -> Operation:
        operation = self._get_simulation_operation(operation_id)
        now = self._clock()
        updated = operation.model_copy(
            update={
                "status": OperationStatus.REJECTED,
                "approver": approver,
                "approved_at": now,
                "result": {"simulation": True, "status": "rejected"},
            },
        )
        self._repository.update_operation(updated)
        return updated

    def _get_simulation_operation(self, operation_id: str) -> Operation:
        operation = self._repository.get_operation(operation_id)
        if not operation.name.startswith("simulate_"):
            raise DataSentryError(
                code="operation.not_simulation",
                message="M4 只允许处理本地模拟审批操作",
            )
        return operation
