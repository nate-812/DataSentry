"""对话、诊断任务和 SSE 事件的领域快照模型。"""

from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import Field, JsonValue, field_validator, model_validator

from datasentry.domain.common import (
    DomainModel,
    new_id,
    normalize_optional_datetime,
    require_aware_datetime,
    utc_now,
)


class ChatRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ChatRunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ChatEventType(StrEnum):
    ACCEPTED = "accepted"
    KNOWLEDGE_LOADED = "knowledge_loaded"
    TOOLS_PLANNED = "tools_planned"
    TOOL_STARTED = "tool_started"
    TOOL_FINISHED = "tool_finished"
    RULES_COMPLETED = "rules_completed"
    LLM_STARTED = "llm_started"
    LLM_COMPLETED = "llm_completed"
    COMPLETED = "completed"
    FAILED = "failed"


class ChatSession(DomainModel):
    id: str = Field(default_factory=new_id)
    title: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    _normalize_created_at = field_validator("created_at")(require_aware_datetime)
    _normalize_updated_at = field_validator("updated_at")(require_aware_datetime)

    @model_validator(mode="after")
    def validate_times(self) -> Self:
        if self.updated_at < self.created_at:
            raise ValueError("updated_at 不能早于 created_at")
        return self


class ChatMessage(DomainModel):
    id: str = Field(default_factory=new_id)
    session_id: str = Field(min_length=1)
    role: ChatRole
    content: str = Field(min_length=1)
    inspection_id: str | None = None
    llm_status: str | None = None
    created_at: datetime = Field(default_factory=utc_now)

    _normalize_created_at = field_validator("created_at")(require_aware_datetime)


class ChatRun(DomainModel):
    class Event(DomainModel):
        id: str = Field(default_factory=new_id)
        run_id: str = Field(min_length=1)
        event_type: ChatEventType
        payload: dict[str, JsonValue] = Field(default_factory=dict)
        created_at: datetime = Field(default_factory=utc_now)

        _normalize_created_at = field_validator("created_at")(require_aware_datetime)

    id: str = Field(default_factory=new_id)
    session_id: str = Field(min_length=1)
    user_message_id: str = Field(min_length=1)
    status: ChatRunStatus = ChatRunStatus.RUNNING
    inspection_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime | None = None

    _normalize_created_at = field_validator("created_at")(require_aware_datetime)
    _normalize_finished_at = field_validator("finished_at")(normalize_optional_datetime)

    @model_validator(mode="after")
    def validate_run(self) -> Self:
        if self.status is ChatRunStatus.FAILED and (
            self.error_code is None or self.error_message is None
        ):
            raise ValueError("失败的聊天任务必须包含错误码和错误信息")
        if self.finished_at is not None and self.finished_at < self.created_at:
            raise ValueError("finished_at 不能早于 created_at")
        return self
