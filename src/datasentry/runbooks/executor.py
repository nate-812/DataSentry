"""Mock Runbook 执行器。"""

from collections.abc import Callable
from datetime import datetime

from datasentry.domain import Operation
from datasentry.domain.common import utc_now
from datasentry.runbooks.idempotency import require_target
from datasentry.runbooks.models import Runbook, RunbookExecutionResult


class MockRunbookExecutor:
    """只返回确定性结果的本地 mock 执行器。"""

    def __init__(self, clock: Callable[[], datetime] = utc_now) -> None:
        self._clock = clock

    def execute(self, runbook: Runbook, operation: Operation) -> RunbookExecutionResult:
        started_at = self._clock()
        finished_at = self._clock()
        target = require_target(operation.parameters)
        return RunbookExecutionResult(
            status="succeeded",
            summary=f"模拟执行 {runbook.title} 已完成",
            details={
                "target": target,
                "runbook": runbook.name,
                "operation_id": operation.id,
                "execution_source": "mock_executor",
            },
            started_at=started_at,
            finished_at=finished_at,
        )
