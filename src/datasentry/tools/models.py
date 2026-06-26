"""白名单工具调用、失败和返回值模型。"""

from datetime import datetime
from typing import Self

from pydantic import Field, JsonValue, field_validator, model_validator

from datasentry.domain import Observation, ToolName, ToolStatus
from datasentry.domain.common import DomainModel, new_id, require_aware_datetime, utc_now


class ToolRetryPolicy(DomainModel):
    """单个工具允许的有限重试策略。"""

    attempts: int = Field(default=1, ge=0, le=1)


class ToolCall(DomainModel):
    """上层编排器可以提交的封闭工具调用。"""

    id: str = Field(default_factory=new_id)
    name: ToolName
    target: str = Field(min_length=1)
    arguments: dict[str, JsonValue] = Field(default_factory=dict)


class ToolFailure(DomainModel):
    """稳定且不包含底层秘密的工具失败。"""

    code: str = Field(pattern=r"^tool\.[a-z0-9_.]+$")
    message: str = Field(min_length=1)
    retryable: bool = False


class ToolOutcome(DomainModel):
    """一次工具调用的标准化输出。"""

    call: ToolCall
    status: ToolStatus
    observations: list[Observation] = Field(default_factory=list)
    failure: ToolFailure | None = None
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime = Field(default_factory=utc_now)

    _normalize_started_at = field_validator("started_at")(require_aware_datetime)
    _normalize_finished_at = field_validator("finished_at")(require_aware_datetime)

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        if self.finished_at < self.started_at:
            raise ValueError("finished_at 不能早于 started_at")
        if self.status is ToolStatus.SUCCEEDED and self.failure is not None:
            raise ValueError("成功结果不能包含失败信息")
        if self.status is ToolStatus.FAILED and self.failure is None:
            raise ValueError("失败结果必须包含失败信息")
        return self
