"""白名单只读工具的调用审计模型。"""

from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import Field, JsonValue, field_validator, model_validator

from datasentry.domain.common import DomainModel, new_id, require_aware_datetime


class ToolName(StrEnum):
    """M2 固定只读工具名称。"""

    GET_FLINK_JOBS = "get_flink_jobs"
    GET_FLINK_JOB = "get_flink_job"
    GET_FLINK_CHECKPOINTS = "get_flink_checkpoints"
    GET_FLINK_BACKPRESSURE = "get_flink_backpressure"
    GET_API_HEALTH = "get_api_health"
    GET_HOST_STATUS = "get_host_status"
    GET_SERVICE_STATUS = "get_service_status"
    GET_KAFKA_TOPICS = "get_kafka_topics"
    GET_KAFKA_TOPIC = "get_kafka_topic"
    GET_KAFKA_GROUP = "get_kafka_group"
    GET_DORIS_TABLE_FRESHNESS = "get_doris_table_freshness"
    GET_REDIS_KEY_SAMPLE = "get_redis_key_sample"
    GET_MYSQL_TABLE_SAMPLE = "get_mysql_table_sample"
    GET_RECENT_LOGS = "get_recent_logs"


class ToolStatus(StrEnum):
    """一次工具调用的最终状态。"""

    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ToolInvocation(DomainModel):
    """可安全持久化的单次工具调用审计。"""

    id: str = Field(default_factory=new_id)
    inspection_id: str = Field(min_length=1)
    tool_name: ToolName
    target: str = Field(min_length=1)
    parameters: dict[str, JsonValue] = Field(default_factory=dict)
    status: ToolStatus
    observation_count: int = Field(ge=0)
    error_code: str | None = None
    error_message: str | None = None
    started_at: datetime
    finished_at: datetime
    duration_ms: int = Field(ge=0)

    _normalize_started_at = field_validator("started_at")(require_aware_datetime)
    _normalize_finished_at = field_validator("finished_at")(require_aware_datetime)

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        if self.finished_at < self.started_at:
            raise ValueError("finished_at 不能早于 started_at")
        if self.status is ToolStatus.FAILED and (
            self.error_code is None or self.error_message is None
        ):
            raise ValueError("失败的工具调用必须包含错误码和错误摘要")
        if self.status is ToolStatus.SUCCEEDED and (
            self.error_code is not None or self.error_message is not None
        ):
            raise ValueError("成功的工具调用不能包含错误信息")
        return self
