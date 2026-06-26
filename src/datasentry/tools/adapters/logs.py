"""配置目录限定的最近日志读取和脱敏。"""

import re
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Protocol, cast

from pydantic import BaseModel, Field, JsonValue, ValidationError

from datasentry.domain import Observation, ToolName
from datasentry.domain.common import utc_now
from datasentry.tools.errors import ToolError
from datasentry.tools.redaction import redact_text
from datasentry.tools.targets import LogSource
from datasentry.tools.transports.ssh import SshCommandId

ANSI_PATTERN = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
CONTROL_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class TextSshTransport(Protocol):
    def execute(
        self,
        target: str,
        command_id: SshCommandId,
        arguments: tuple[str, ...] = (),
    ) -> str:
        raise NotImplementedError  # pragma: no cover


class LogArguments(BaseModel):
    minutes: int = Field(default=30, ge=1, le=30)
    lines: int = Field(default=200, ge=1, le=200)


class RecentLogsTool:
    name = ToolName.GET_RECENT_LOGS

    def __init__(
        self,
        transport: TextSshTransport,
        *,
        sources: Mapping[str, LogSource],
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._transport = transport
        self._sources = dict(sources)
        self._clock = clock

    def execute(
        self,
        *,
        inspection_id: str,
        target: str,
        arguments: Mapping[str, JsonValue],
    ) -> list[Observation]:
        try:
            parsed = LogArguments.model_validate(arguments)
        except ValidationError as error:
            raise ToolError(
                code="tool.invalid_arguments",
                message="日志查询范围无效",
            ) from error
        source = self._sources.get(target)
        if source is None:
            raise ToolError(
                code="tool.configuration",
                message="组件日志源未配置",
            )
        command_arguments: tuple[str, ...]
        if source.kind == "journal":
            assert source.unit is not None
            command_id = SshCommandId.RECENT_JOURNAL
            command_arguments = (
                source.unit,
                str(parsed.minutes),
                str(parsed.lines),
            )
        else:
            assert source.path is not None
            command_id = SshCommandId.RECENT_FILE
            command_arguments = (str(source.path), str(parsed.lines))
        output = self._transport.execute(
            source.host,
            command_id,
            command_arguments,
        )
        sanitized = CONTROL_PATTERN.sub("", ANSI_PATTERN.sub("", output))
        lines = [redact_text(line) for line in sanitized.splitlines()[-parsed.lines :]]
        return [
            Observation(
                inspection_id=inspection_id,
                component=target,
                metric_or_fact="recent_logs",
                value={
                    "lines": cast(JsonValue, lines),
                    "line_count": len(lines),
                    "window_minutes": parsed.minutes,
                    "truncated": False,
                },
                source="ssh_limited_logs",
                target=target,
                observed_at=self._clock(),
            )
        ]
