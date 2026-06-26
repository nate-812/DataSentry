from datetime import UTC, datetime

from datasentry.domain import Observation, ToolName, ToolStatus
from datasentry.tools.collector import InspectionCollector
from datasentry.tools.models import ToolCall, ToolFailure, ToolOutcome

NOW = datetime(2026, 6, 25, 12, 0, tzinfo=UTC)


class FixtureGateway:
    def execute(self, inspection_id: str, call: ToolCall) -> ToolOutcome:
        if call.name is ToolName.GET_KAFKA_TOPIC:
            return ToolOutcome(
                call=call,
                status=ToolStatus.FAILED,
                failure=ToolFailure(
                    code="tool.timeout",
                    message="目标读取超时",
                    retryable=True,
                ),
                started_at=NOW,
                finished_at=NOW,
            )
        return ToolOutcome(
            call=call,
            status=ToolStatus.SUCCEEDED,
            observations=[
                Observation(
                    inspection_id=inspection_id,
                    component="flink",
                    metric_or_fact="kline_job_state",
                    value={"state": "RUNNING"},
                    source="fixture",
                    target="flink",
                    observed_at=NOW,
                )
            ],
            started_at=NOW,
            finished_at=NOW,
        )


def test_collector_continues_after_one_tool_failure() -> None:
    calls = (
        ToolCall(
            name=ToolName.GET_KAFKA_TOPIC,
            target="data1",
            arguments={"topic": "binance.trade.raw"},
        ),
        ToolCall(name=ToolName.GET_FLINK_JOBS, target="flink"),
    )

    result = InspectionCollector(FixtureGateway()).collect("inspection-1", calls)

    assert len(result.observations) == 1
    assert result.unknowns == ["工具 get_kafka_topic 查询 data1 失败(tool.timeout)"]
    assert [outcome.status for outcome in result.outcomes] == [
        ToolStatus.FAILED,
        ToolStatus.SUCCEEDED,
    ]
