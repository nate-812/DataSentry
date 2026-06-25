from datetime import UTC, datetime
from pathlib import Path

import pytest

from datasentry.tools.adapters.logs import RecentLogsTool
from datasentry.tools.errors import ToolError
from datasentry.tools.targets import LogSource
from datasentry.tools.transports.ssh import SshCommandId

NOW = datetime(2026, 6, 25, 12, 0, tzinfo=UTC)


class FixtureTransport:
    def execute(
        self,
        target: str,
        command_id: SshCommandId,
        arguments: tuple[str, ...] = (),
    ) -> str:
        del target
        assert command_id is SshCommandId.RECENT_FILE
        assert arguments[1] == "200"
        return (
            "INFO request completed\n"
            "ERROR password=super-secret Authorization: Bearer token-value\n"
            "\x1b[31mcolored\x1b[0m\n"
        )


def test_recent_logs_uses_configured_source_and_redacts_output() -> None:
    tool = RecentLogsTool(
        FixtureTransport(),
        sources={
            "spring_api": LogSource(
                host="data1",
                kind="file",
                path=Path("/opt/StreamLake-Binance/api-server/logs/app.log"),
            )
        },
        clock=lambda: NOW,
    )

    observations = tool.execute(
        inspection_id="inspection-1",
        target="spring_api",
        arguments={"minutes": 30, "lines": 200},
    )

    value = observations[0].value
    assert isinstance(value, dict)
    text = "\n".join(value["lines"])
    assert "super-secret" not in text
    assert "token-value" not in text
    assert "\x1b" not in text


def test_recent_logs_rejects_limit_above_policy() -> None:
    tool = RecentLogsTool(FixtureTransport(), sources={}, clock=lambda: NOW)

    with pytest.raises(ToolError) as raised:
        tool.execute(
            inspection_id="inspection-1",
            target="spring_api",
            arguments={"minutes": 31, "lines": 201},
        )

    assert raised.value.code == "tool.invalid_arguments"
