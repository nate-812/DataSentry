"""Runbook 执行策略。"""

from datasentry.domain.enums import OperationRisk
from datasentry.errors import DataSentryError
from datasentry.runbooks.models import ExecutionMode, Runbook


class RunbookPolicy:
    """校验 Runbook 请求是否符合 M6 第一版执行边界。"""

    def assert_request_allowed(self, runbook: Runbook) -> None:
        if (
            runbook.risk is OperationRisk.FORBIDDEN
            or runbook.execution_mode is ExecutionMode.FORBIDDEN
        ):
            raise DataSentryError(
                code="runbook.forbidden",
                message="Runbook 被策略禁止执行",
            )
        if not runbook.enabled:
            raise DataSentryError(
                code="runbook.disabled",
                message="Runbook 已禁用",
            )
        if runbook.execution_mode is not ExecutionMode.MOCK:
            raise DataSentryError(
                code="runbook.execution_mode_not_allowed",
                message="M6 第一版只允许 mock 执行模式",
            )
