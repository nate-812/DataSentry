from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import JsonValue

from datasentry.domain import (
    Inspection,
    Observation,
    ToolName,
    ToolStatus,
)
from datasentry.errors import ConfigurationError
from datasentry.storage import SQLiteRepository
from datasentry.tools.errors import ToolError
from datasentry.tools.gateway import ToolGateway
from datasentry.tools.models import ToolCall

NOW = datetime(2026, 6, 25, 12, 0, tzinfo=UTC)


class StubTool:
    name = ToolName.GET_API_HEALTH

    def execute(
        self,
        *,
        inspection_id: str,
        target: str,
        arguments: Mapping[str, JsonValue],
    ) -> list[Observation]:
        del arguments
        return [
            Observation(
                inspection_id=inspection_id,
                component="spring_api",
                metric_or_fact="service_state",
                value={"state": "RUNNING", "token": "do-not-store"},
                source="http_health",
                target=target,
                observed_at=NOW,
            )
        ]


class FailingTool:
    name = ToolName.GET_FLINK_JOBS

    def execute(
        self,
        *,
        inspection_id: str,
        target: str,
        arguments: Mapping[str, JsonValue],
    ) -> list[Observation]:
        del inspection_id, target, arguments
        raise ToolError(
            code="tool.timeout",
            message="目标读取超时",
            retryable=True,
        )


@pytest.fixture
def repository(tmp_path: Path) -> SQLiteRepository:
    with SQLiteRepository(tmp_path / "datasentry.db") as instance:
        instance.start_inspection(
            Inspection(
                id="inspection-1",
                question="测试工具网关",
                scope=["test"],
                started_at=NOW,
            )
        )
        yield instance


def _clock() -> datetime:
    _clock.current += timedelta(milliseconds=10)
    return _clock.current


_clock.current = NOW


def test_gateway_persists_redacted_success_audit_and_observations(
    repository: SQLiteRepository,
) -> None:
    _clock.current = NOW
    gateway = ToolGateway(repository, (StubTool(),), clock=_clock)

    outcome = gateway.execute(
        "inspection-1",
        ToolCall(
            name=ToolName.GET_API_HEALTH,
            target="spring_api",
            arguments={"token": "do-not-store", "service": "spring_api"},
        ),
    )

    assert outcome.status is ToolStatus.SUCCEEDED
    assert outcome.observations[0].value == {
        "state": "RUNNING",
        "token": "[REDACTED]",
    }
    invocation = repository.list_tool_invocations("inspection-1")[0]
    assert invocation.parameters["token"] == "[REDACTED]"
    assert invocation.observation_count == 1


def test_gateway_converts_tool_error_to_failed_outcome(
    repository: SQLiteRepository,
) -> None:
    _clock.current = NOW
    outcome = ToolGateway(repository, (FailingTool(),), clock=_clock).execute(
        "inspection-1",
        ToolCall(name=ToolName.GET_FLINK_JOBS, target="flink"),
    )

    assert outcome.status is ToolStatus.FAILED
    assert outcome.failure is not None
    assert outcome.failure.code == "tool.timeout"
    assert outcome.observations == []
    invocation = repository.list_tool_invocations("inspection-1")[0]
    assert invocation.error_code == "tool.timeout"


def test_gateway_rejects_duplicate_or_missing_tool_registration(
    repository: SQLiteRepository,
) -> None:
    with pytest.raises(ConfigurationError):
        ToolGateway(repository, (StubTool(), StubTool()))

    gateway = ToolGateway(repository, ())
    outcome = gateway.execute(
        "inspection-1",
        ToolCall(name=ToolName.GET_API_HEALTH, target="spring_api"),
    )

    assert outcome.status is ToolStatus.FAILED
    assert outcome.failure is not None
    assert outcome.failure.code == "tool.not_registered"
