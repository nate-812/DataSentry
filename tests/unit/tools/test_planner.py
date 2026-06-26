from datetime import UTC, datetime

from datasentry.diagnosis.service import PreparedDiagnosis
from datasentry.domain import Inspection, ToolName
from datasentry.knowledge import (
    KnowledgeReference,
    LineageNode,
    LineageNodeKind,
    QuestionType,
    RouteMatch,
)
from datasentry.tools.planner import ReadOnlyInspectionPlanner

NOW = datetime(2026, 6, 25, 12, 0, tzinfo=UTC)


def _prepared() -> PreparedDiagnosis:
    node_ids = (
        "collector",
        "kafka.binance.trade.raw",
        "flink.kline",
        "doris.kline_1min",
        "api.kline.latest",
    )
    return PreparedDiagnosis(
        inspection=Inspection(
            id="inspection-1",
            question="为什么K线不更新",
            scope=["data_stale"],
            started_at=NOW,
        ),
        route=RouteMatch(
            question_type=QuestionType.DATA_STALE,
            required_topic_ids=("03", "04"),
            matched_keywords=("不更新",),
        ),
        knowledge=[
            KnowledgeReference(
                topic_id="03",
                path="03-jobs-and-lineage.md",
                title="任务、Topic与数据血缘",
                historical=False,
            )
        ],
        lineage_checkpoints=[
            LineageNode(
                node_id=node_id,
                kind=LineageNodeKind.SERVICE,
                component=node_id.split(".", 1)[0],
                label=node_id,
            )
            for node_id in node_ids
        ],
    )


def test_planner_builds_kline_readonly_calls_in_diagnostic_order() -> None:
    calls = ReadOnlyInspectionPlanner().plan(_prepared())

    assert [call.name for call in calls] == [
        ToolName.GET_HOST_STATUS,
        ToolName.GET_SERVICE_STATUS,
        ToolName.GET_FLINK_JOBS,
        ToolName.GET_FLINK_JOB,
        ToolName.GET_FLINK_CHECKPOINTS,
        ToolName.GET_FLINK_BACKPRESSURE,
        ToolName.GET_KAFKA_TOPIC,
        ToolName.GET_DORIS_TABLE_FRESHNESS,
        ToolName.GET_API_HEALTH,
    ]
    assert calls[1].arguments == {"service": "collector"}
    assert calls[6].arguments == {"topic": "binance.trade.raw"}


def test_planner_builds_component_status_calls_without_lineage() -> None:
    prepared = _prepared().model_copy(
        update={
            "inspection": _prepared().inspection.model_copy(
                update={"question": "Collector是不是挂了"}
            ),
            "lineage_checkpoints": [],
        }
    )

    calls = ReadOnlyInspectionPlanner().plan(prepared)

    assert [call.name for call in calls] == [
        ToolName.GET_HOST_STATUS,
        ToolName.GET_SERVICE_STATUS,
    ]
    assert calls[1].arguments == {"service": "collector"}


def test_planner_builds_risk_redis_sample_from_lineage() -> None:
    prepared = _prepared().model_copy(
        update={
            "lineage_checkpoints": [
                LineageNode(
                    node_id="flink.risk",
                    kind=LineageNodeKind.JOB,
                    component="flink",
                    label="RiskControlJob",
                ),
                LineageNode(
                    node_id="redis.risk.blacklist",
                    kind=LineageNodeKind.KEY_PATTERN,
                    component="redis",
                    label="risk:blacklist:{SYMBOL}",
                ),
            ]
        }
    )

    calls = ReadOnlyInspectionPlanner().plan(prepared)

    assert calls[-1].name is ToolName.GET_REDIS_KEY_SAMPLE
    assert calls[-1].arguments["pattern"] == "risk:blacklist:*"
