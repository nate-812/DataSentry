"""Mock Runbook 操作后验证器。"""

from collections.abc import Callable
from datetime import datetime

from datasentry.domain import Operation
from datasentry.domain.common import utc_now
from datasentry.runbooks.idempotency import require_target
from datasentry.runbooks.models import Runbook, RunbookVerificationResult


class MockOperationVerifier:
    """只返回确定性结果的本地 mock 操作后验证器。"""

    def __init__(self, clock: Callable[[], datetime] = utc_now) -> None:
        self._clock = clock

    def verify(self, runbook: Runbook, operation: Operation) -> RunbookVerificationResult:
        verified_at = self._clock()
        target = require_target(operation.parameters)
        postcheck_summary = str(runbook.postcheck.get("summary", "执行后状态已通过 mock 验证"))
        return RunbookVerificationResult(
            status="succeeded",
            summary=f"模拟验证 {runbook.title} 已通过：{postcheck_summary}",
            details={
                "target": target,
                "runbook": runbook.name,
                "operation_id": operation.id,
                "verification_source": "mock_postcheck",
                "postcheck_summary": postcheck_summary,
            },
            verified_at=verified_at,
        )
