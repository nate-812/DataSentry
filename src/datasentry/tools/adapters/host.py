"""三台主机资源和固定服务状态只读适配器。"""

import re
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Literal, Protocol, cast

from pydantic import BaseModel, JsonValue, ValidationError

from datasentry.domain import Observation, ToolName
from datasentry.domain.common import utc_now
from datasentry.tools.errors import ToolError
from datasentry.tools.transports.ssh import SshCommandId


class TextSshTransport(Protocol):
    def execute(
        self,
        target: str,
        command_id: SshCommandId,
        arguments: tuple[str, ...] = (),
    ) -> str:
        raise NotImplementedError  # pragma: no cover


class ServiceArguments(BaseModel):
    service: Literal[
        "kafka",
        "flink_jobmanager",
        "flink_taskmanager",
        "doris_fe",
        "doris_be",
        "mysql",
        "redis",
        "collector",
        "spring_api",
        "ai_engine",
    ]


def _uptime_seconds(value: str) -> int | None:
    days = re.search(r"(\d+)\s+day", value)
    hours = re.search(r"(\d+)\s+hour", value)
    minutes = re.search(r"(\d+)\s+minute", value)
    if not any((days, hours, minutes)):
        return None
    return (
        (0 if days is None else int(days.group(1)) * 86400)
        + (0 if hours is None else int(hours.group(1)) * 3600)
        + (0 if minutes is None else int(minutes.group(1)) * 60)
    )


def _table_rows(value: str, *, limit: int = 50) -> list[dict[str, JsonValue]]:
    rows: list[dict[str, JsonValue]] = []
    for line in value.splitlines():
        fields = line.split()
        if len(fields) != 6 or not fields[1].isdigit():
            continue
        rows.append(
            {
                "source": fields[0],
                "total": int(fields[1]),
                "used": int(fields[2]),
                "available": int(fields[3]),
                "used_percent": int(fields[4].rstrip("%")),
                "mount": fields[5],
            }
        )
    return sorted(
        rows,
        key=lambda item: int(str(item["used_percent"])),
        reverse=True,
    )[:limit]


class _HostTool:
    def __init__(
        self,
        transport: TextSshTransport,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._transport = transport
        self._clock = clock

    def _observation(
        self,
        inspection_id: str,
        target: str,
        metric_or_fact: str,
        value: JsonValue,
    ) -> Observation:
        return Observation(
            inspection_id=inspection_id,
            component="host",
            metric_or_fact=metric_or_fact,
            value=value,
            source="ssh_readonly",
            target=target,
            observed_at=self._clock(),
        )


class HostStatusTool(_HostTool):
    name = ToolName.GET_HOST_STATUS

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
                message="主机状态工具不接受参数",
            )
        uptime = self._transport.execute(target, SshCommandId.HOST_UPTIME)
        memory_line = next(
            (
                line
                for line in self._transport.execute(
                    target,
                    SshCommandId.HOST_MEMORY,
                ).splitlines()
                if line.startswith("Mem:")
            ),
            "",
        )
        memory_fields = memory_line.split()
        if len(memory_fields) < 7:
            raise ToolError(
                code="tool.parse_failed",
                message="主机内存输出无法解析",
            )
        memory: JsonValue = {
            "total_bytes": int(memory_fields[1]),
            "used_bytes": int(memory_fields[2]),
            "free_bytes": int(memory_fields[3]),
            "available_bytes": int(memory_fields[6]),
        }
        filesystems = _table_rows(self._transport.execute(target, SshCommandId.HOST_FILESYSTEM))
        inodes = _table_rows(self._transport.execute(target, SshCommandId.HOST_INODES))
        synchronized = (
            self._transport.execute(target, SshCommandId.HOST_TIME).strip().casefold() == "yes"
        )
        return [
            self._observation(
                inspection_id,
                target,
                "host_uptime_seconds",
                _uptime_seconds(uptime),
            ),
            self._observation(
                inspection_id,
                target,
                "host_memory",
                memory,
            ),
            self._observation(
                inspection_id,
                target,
                "host_filesystems",
                cast(JsonValue, filesystems),
            ),
            self._observation(
                inspection_id,
                target,
                "host_inodes",
                cast(JsonValue, inodes),
            ),
            self._observation(
                inspection_id,
                target,
                "host_time_synchronized",
                synchronized,
            ),
        ]


class ServiceStatusTool(_HostTool):
    name = ToolName.GET_SERVICE_STATUS

    def execute(
        self,
        *,
        inspection_id: str,
        target: str,
        arguments: Mapping[str, JsonValue],
    ) -> list[Observation]:
        try:
            service = ServiceArguments.model_validate(arguments).service
        except ValidationError as error:
            raise ToolError(
                code="tool.invalid_arguments",
                message="服务状态参数无效",
            ) from error
        output = self._transport.execute(
            target,
            SshCommandId.SERVICE_STATUS,
            (service,),
        ).strip()
        state = "RUNNING" if output in {"active", "running"} or output.isdigit() else "NOT_RUNNING"
        return [
            Observation(
                inspection_id=inspection_id,
                component=service,
                metric_or_fact="service_state",
                value={"state": state},
                source="ssh_readonly",
                target=target,
                observed_at=self._clock(),
            )
        ]
