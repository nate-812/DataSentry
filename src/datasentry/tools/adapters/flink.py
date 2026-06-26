"""Flink REST 响应到标准 Observation 的确定性映射。"""

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Literal, Protocol, cast

from pydantic import BaseModel, JsonValue, ValidationError

from datasentry.domain import Observation, ToolName
from datasentry.domain.common import utc_now
from datasentry.tools.errors import ToolError

JOB_NAMES = {
    "kline": "streamlake-kline-aggregation",
    "whale": "streamlake-whale-cep",
    "risk": "streamlake-risk-control",
}
JOB_FACTS = {
    "kline": "kline_job_state",
    "whale": "whale_job_state",
    "risk": "risk_job_state",
}


class JsonHttpTransport(Protocol):
    def get_json(self, target: str, path: str) -> JsonValue:
        raise NotImplementedError  # pragma: no cover


class FlinkJobArguments(BaseModel):
    job: Literal["kline", "whale", "risk"]


def _object(value: JsonValue, context: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise ToolError(
            code="tool.parse_failed",
            message=f"Flink {context} 响应结构无效",
        )
    return value


def _array(value: JsonValue, context: str) -> list[JsonValue]:
    if not isinstance(value, list):
        raise ToolError(
            code="tool.parse_failed",
            message=f"Flink {context} 列表结构无效",
        )
    return value


def _milliseconds_to_datetime(value: JsonValue) -> datetime | None:
    if not isinstance(value, int) or isinstance(value, bool):
        return None
    return datetime.fromtimestamp(value / 1000, tz=UTC)


def _backpressure_level(value: dict[str, JsonValue]) -> JsonValue:
    return value.get("backpressure-level", value.get("backpressureLevel", "unknown"))


class _FlinkTool:
    def __init__(
        self,
        transport: JsonHttpTransport,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._transport = transport
        self._clock = clock

    def _jobs(self, target: str) -> list[dict[str, JsonValue]]:
        payload = _object(self._transport.get_json(target, "/jobs/overview"), "Job")
        return [_object(item, "Job") for item in _array(payload.get("jobs"), "Job")]

    def _job(self, target: str, arguments: Mapping[str, JsonValue]) -> tuple[str, str]:
        try:
            alias = FlinkJobArguments.model_validate(arguments).job
        except ValidationError as error:
            raise ToolError(
                code="tool.invalid_arguments",
                message="Flink Job 参数无效",
            ) from error
        expected_name = JOB_NAMES[alias]
        job = next(
            (item for item in self._jobs(target) if item.get("name") == expected_name),
            None,
        )
        if job is None or not isinstance(job.get("jid"), str):
            raise ToolError(
                code="tool.upstream_error",
                message="指定 Flink Job 当前不存在",
            )
        return alias, cast(str, job["jid"])

    def _observation(
        self,
        *,
        inspection_id: str,
        metric_or_fact: str,
        value: JsonValue,
        target: str,
    ) -> Observation:
        return Observation(
            inspection_id=inspection_id,
            component="flink",
            metric_or_fact=metric_or_fact,
            value=value,
            source="flink_rest",
            target=target,
            observed_at=self._clock(),
        )


class FlinkJobsTool(_FlinkTool):
    name = ToolName.GET_FLINK_JOBS

    def execute(
        self,
        *,
        inspection_id: str,
        target: str,
        arguments: Mapping[str, JsonValue],
    ) -> list[Observation]:
        if arguments:
            raise ToolError(
                code="tool.invalid_arguments",
                message="Flink Job 列表工具不接受参数",
            )
        jobs = self._jobs(target)
        by_name = {item.get("name"): item for item in jobs}
        observations: list[Observation] = []
        for alias, expected_name in JOB_NAMES.items():
            job = by_name.get(expected_name)
            value: JsonValue
            if job is None:
                value = {
                    "job_id": None,
                    "job_name": expected_name,
                    "state": "MISSING",
                }
            else:
                value = {
                    "job_id": job.get("jid"),
                    "job_name": expected_name,
                    "state": job.get("state", "UNKNOWN"),
                }
            observations.append(
                self._observation(
                    inspection_id=inspection_id,
                    metric_or_fact=JOB_FACTS[alias],
                    value=value,
                    target=target,
                )
            )
        return observations


class FlinkJobTool(_FlinkTool):
    name = ToolName.GET_FLINK_JOB

    def execute(
        self,
        *,
        inspection_id: str,
        target: str,
        arguments: Mapping[str, JsonValue],
    ) -> list[Observation]:
        alias, job_id = self._job(target, arguments)
        payload = _object(self._transport.get_json(target, f"/jobs/{job_id}"), "Job")
        vertices = _array(payload.get("vertices", []), "Vertex")[:20]
        return [
            self._observation(
                inspection_id=inspection_id,
                metric_or_fact=f"{alias}_job_details",
                value={
                    "job_id": job_id,
                    "name": payload.get("name"),
                    "state": payload.get("state"),
                    "vertices": vertices,
                },
                target=target,
            )
        ]


class FlinkCheckpointsTool(_FlinkTool):
    name = ToolName.GET_FLINK_CHECKPOINTS

    def execute(
        self,
        *,
        inspection_id: str,
        target: str,
        arguments: Mapping[str, JsonValue],
    ) -> list[Observation]:
        _, job_id = self._job(target, arguments)
        payload = _object(
            self._transport.get_json(target, f"/jobs/{job_id}/checkpoints"),
            "Checkpoint",
        )
        latest = _object(payload.get("latest", {}), "Checkpoint latest")
        completed = _object(latest.get("completed", {}), "Checkpoint completed")
        history = _array(payload.get("history", []), "Checkpoint history")
        consecutive_failures = 0
        for item in history:
            checkpoint = _object(item, "Checkpoint history")
            if checkpoint.get("status") != "FAILED":
                break
            consecutive_failures += 1
        values: tuple[tuple[str, JsonValue], ...] = (
            (
                "checkpoint_latest_completed_at",
                (
                    None
                    if (
                        completed_at := _milliseconds_to_datetime(
                            completed.get("latest_ack_timestamp")
                        )
                    )
                    is None
                    else completed_at.isoformat()
                ),
            ),
            (
                "checkpoint_latest_duration_ms",
                completed.get("end_to_end_duration"),
            ),
            ("checkpoint_latest_size_bytes", completed.get("state_size")),
            ("checkpoint_consecutive_failures", consecutive_failures),
        )
        return [
            self._observation(
                inspection_id=inspection_id,
                metric_or_fact=metric,
                value=value,
                target=target,
            )
            for metric, value in values
        ]


class FlinkBackpressureTool(_FlinkTool):
    name = ToolName.GET_FLINK_BACKPRESSURE

    def execute(
        self,
        *,
        inspection_id: str,
        target: str,
        arguments: Mapping[str, JsonValue],
    ) -> list[Observation]:
        _, job_id = self._job(target, arguments)
        details = _object(
            self._transport.get_json(target, f"/jobs/{job_id}"),
            "Job",
        )
        summaries: list[JsonValue] = []
        levels: list[str] = []
        for vertex_value in _array(details.get("vertices", []), "Vertex")[:20]:
            vertex = _object(vertex_value, "Vertex")
            vertex_id = vertex.get("id")
            if not isinstance(vertex_id, str):
                continue
            pressure = _object(
                self._transport.get_json(
                    target,
                    f"/jobs/{job_id}/vertices/{vertex_id}/backpressure",
                ),
                "Backpressure",
            )
            level = _backpressure_level(pressure)
            if isinstance(level, str):
                levels.append(level)
            summaries.append(
                {
                    "vertex_id": vertex_id,
                    "vertex_name": vertex.get("name"),
                    "level": level,
                    "subtasks": _array(pressure.get("subtasks", []), "Subtask")[:20],
                }
            )
        aggregate = (
            "high"
            if "high" in levels
            else "low"
            if levels and all(level == "low" for level in levels)
            else "ok"
            if levels and all(level == "ok" for level in levels)
            else "unknown"
        )
        return [
            self._observation(
                inspection_id=inspection_id,
                metric_or_fact="backpressure_level",
                value=aggregate,
                target=target,
            ),
            self._observation(
                inspection_id=inspection_id,
                metric_or_fact="backpressure_vertices",
                value=summaries,
                target=target,
            ),
        ]
