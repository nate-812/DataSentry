"""Spring API 与 AI Engine 健康和只读探针。"""

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel, JsonValue, ValidationError

from datasentry.domain import Observation, ToolName
from datasentry.domain.common import utc_now
from datasentry.tools.errors import ToolError


class JsonHttpTransport(Protocol):
    def get_json(self, target: str, path: str) -> JsonValue:
        raise NotImplementedError  # pragma: no cover


class ApiHealthArguments(BaseModel):
    service: Literal["spring_api", "ai_engine"]


def _object(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise ToolError(
            code="tool.parse_failed",
            message="API 健康响应结构无效",
        )
    return value


def _probe_status(value: JsonValue) -> str:
    if isinstance(value, dict):
        return "ok" if value else "empty"
    if isinstance(value, list):
        return "ok" if value else "empty"
    raise ToolError(
        code="tool.parse_failed",
        message="API 只读探针响应结构无效",
    )


class ApiHealthTool:
    """执行固定健康端点和最小只读业务探针。"""

    name = ToolName.GET_API_HEALTH
    spring_kline_probe_path = "/api/kline/BTCUSDT?interval=1min&limit=1"

    def __init__(
        self,
        transport: JsonHttpTransport,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._transport = transport
        self._clock = clock

    def execute(
        self,
        *,
        inspection_id: str,
        target: str,
        arguments: Mapping[str, JsonValue],
    ) -> list[Observation]:
        try:
            service = ApiHealthArguments.model_validate(arguments).service
        except ValidationError as error:
            raise ToolError(
                code="tool.invalid_arguments",
                message="API 健康工具参数无效",
            ) from error
        if target != service:
            raise ToolError(
                code="tool.invalid_arguments",
                message="API 服务参数与目标不一致",
            )
        if service == "spring_api":
            return self._spring(inspection_id, target)
        return self._ai(inspection_id, target)

    def _spring(self, inspection_id: str, target: str) -> list[Observation]:
        health = _object(self._transport.get_json(target, "/actuator/health"))
        state = "RUNNING" if str(health.get("status", "")).upper() == "UP" else "FAILED"
        probe_status = _probe_status(self._transport.get_json(target, self.spring_kline_probe_path))
        return [
            self._observation(
                inspection_id,
                target,
                "service_state",
                {"state": state},
            ),
            self._observation(
                inspection_id,
                target,
                "api_read_probe",
                {"status": probe_status, "resource": "kline_latest"},
            ),
        ]

    def _ai(self, inspection_id: str, target: str) -> list[Observation]:
        health = _object(self._transport.get_json(target, "/health"))
        status = str(health.get("status", "unknown")).casefold()
        mode = "degraded" if status == "degraded" else "normal"
        state = "RUNNING" if status in {"ok", "up", "healthy", "degraded"} else "FAILED"
        observations = [
            self._observation(
                inspection_id,
                target,
                "service_state",
                {"state": state, "mode": mode},
            )
        ]
        dependencies = health.get("dependencies")
        if isinstance(dependencies, dict) and dependencies.get("milvus") == "unavailable":
            observations.append(
                self._observation(
                    inspection_id,
                    target,
                    "optional_dependency_state",
                    {
                        "dependency": "milvus",
                        "state": "UNAVAILABLE_ALLOWED",
                    },
                )
            )
        return observations

    def _observation(
        self,
        inspection_id: str,
        target: str,
        metric_or_fact: str,
        value: JsonValue,
    ) -> Observation:
        return Observation(
            inspection_id=inspection_id,
            component=target,
            metric_or_fact=metric_or_fact,
            value=value,
            source="http_health",
            target=target,
            observed_at=self._clock(),
        )
