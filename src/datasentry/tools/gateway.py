"""白名单工具注册、执行、脱敏、失败归一化和审计。"""

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Protocol, cast

from pydantic import JsonValue

from datasentry.domain import Observation, ToolInvocation, ToolName, ToolStatus
from datasentry.domain.common import utc_now
from datasentry.errors import ConfigurationError
from datasentry.logging import get_logger
from datasentry.storage import Repository
from datasentry.tools.errors import ToolError
from datasentry.tools.models import ToolCall, ToolFailure, ToolOutcome
from datasentry.tools.redaction import redact_text, redact_value


class ReadOnlyTool(Protocol):
    """固定高层只读工具接口。"""

    name: ToolName

    def execute(
        self,
        *,
        inspection_id: str,
        target: str,
        arguments: Mapping[str, JsonValue],
    ) -> list[Observation]:
        raise NotImplementedError  # pragma: no cover


class ToolGateway:
    """统一执行固定工具，并保存已脱敏调用审计。"""

    def __init__(
        self,
        repository: Repository,
        tools: tuple[ReadOnlyTool, ...],
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._repository = repository
        self._clock = clock
        self._tools: dict[ToolName, ReadOnlyTool] = {}
        for tool in tools:
            if tool.name in self._tools:
                raise ConfigurationError(
                    code="configuration.duplicate_tool",
                    message="存在重复注册的白名单工具",
                    details={"tool_name": tool.name.value},
                )
            self._tools[tool.name] = tool

    def execute(self, inspection_id: str, call: ToolCall) -> ToolOutcome:
        """执行一个固定工具，预期失败不会中断巡检。"""
        started_at = self._clock()
        tool = self._tools.get(call.name)
        if tool is None:
            outcome = self._failed_outcome(
                call,
                started_at,
                ToolError(
                    code="tool.not_registered",
                    message="工具未注册",
                ),
            )
            self._audit(inspection_id, outcome)
            return outcome
        try:
            observations = tool.execute(
                inspection_id=inspection_id,
                target=call.target,
                arguments=call.arguments,
            )
            sanitized = [
                item.model_copy(update={"value": redact_value(item.value)}) for item in observations
            ]
            if any(item.inspection_id != inspection_id for item in sanitized):
                raise ToolError(
                    code="tool.internal_error",
                    message="工具返回了错误的巡检 ID",
                )
            outcome = ToolOutcome(
                call=call,
                status=ToolStatus.SUCCEEDED,
                observations=sanitized,
                started_at=started_at,
                finished_at=self._clock(),
            )
        except ToolError as error:
            outcome = self._failed_outcome(call, started_at, error)
        except Exception as error:
            get_logger(__name__).error(
                "tool.unexpected_error",
                tool_name=call.name.value,
                target=call.target,
                error_type=type(error).__name__,
            )
            outcome = self._failed_outcome(
                call,
                started_at,
                ToolError(
                    code="tool.internal_error",
                    message="工具发生未预期错误",
                ),
            )
        self._audit(inspection_id, outcome)
        return outcome

    def _failed_outcome(
        self,
        call: ToolCall,
        started_at: datetime,
        error: ToolError,
    ) -> ToolOutcome:
        return ToolOutcome(
            call=call,
            status=ToolStatus.FAILED,
            failure=ToolFailure(
                code=error.code,
                message=redact_text(error.message),
                retryable=error.retryable,
            ),
            started_at=started_at,
            finished_at=self._clock(),
        )

    def _audit(self, inspection_id: str, outcome: ToolOutcome) -> None:
        duration = outcome.finished_at - outcome.started_at
        failure = outcome.failure
        self._repository.save_tool_invocation(
            ToolInvocation(
                inspection_id=inspection_id,
                tool_name=outcome.call.name,
                target=outcome.call.target,
                parameters=cast(
                    dict[str, JsonValue],
                    redact_value(outcome.call.arguments),
                ),
                status=outcome.status,
                observation_count=len(outcome.observations),
                error_code=None if failure is None else failure.code,
                error_message=None if failure is None else failure.message,
                started_at=outcome.started_at,
                finished_at=outcome.finished_at,
                duration_ms=max(0, int(duration.total_seconds() * 1000)),
            )
        )
