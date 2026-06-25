from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from datasentry.domain import ToolInvocation, ToolName, ToolStatus

NOW = datetime(2026, 6, 25, 12, 0, tzinfo=UTC)


def test_tool_invocation_accepts_completed_audit() -> None:
    invocation = ToolInvocation(
        inspection_id="inspection-1",
        tool_name=ToolName.GET_FLINK_JOBS,
        target="flink",
        parameters={"job": "kline"},
        status=ToolStatus.SUCCEEDED,
        observation_count=1,
        started_at=NOW,
        finished_at=NOW + timedelta(milliseconds=25),
        duration_ms=25,
    )

    assert invocation.tool_name is ToolName.GET_FLINK_JOBS
    assert invocation.error_code is None


def test_tool_invocation_rejects_finished_time_before_started() -> None:
    with pytest.raises(ValidationError):
        ToolInvocation(
            inspection_id="inspection-1",
            tool_name=ToolName.GET_FLINK_JOBS,
            target="flink",
            parameters={},
            status=ToolStatus.SUCCEEDED,
            observation_count=1,
            started_at=NOW,
            finished_at=NOW - timedelta(seconds=1),
            duration_ms=0,
        )


def test_failed_tool_invocation_requires_error_code_and_message() -> None:
    with pytest.raises(ValidationError):
        ToolInvocation(
            inspection_id="inspection-1",
            tool_name=ToolName.GET_FLINK_JOBS,
            target="flink",
            parameters={},
            status=ToolStatus.FAILED,
            observation_count=0,
            started_at=NOW,
            finished_at=NOW,
            duration_ms=0,
        )


def test_successful_tool_invocation_rejects_error_details() -> None:
    with pytest.raises(ValidationError):
        ToolInvocation(
            inspection_id="inspection-1",
            tool_name=ToolName.GET_FLINK_JOBS,
            target="flink",
            parameters={},
            status=ToolStatus.SUCCEEDED,
            observation_count=0,
            error_code="tool.timeout",
            error_message="读取超时",
            started_at=NOW,
            finished_at=NOW,
            duration_ms=0,
        )
