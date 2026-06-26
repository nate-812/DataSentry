"""根据已确定的血缘路径构造固定只读工具调用。"""

from datasentry.diagnosis import PreparedDiagnosis
from datasentry.domain import ToolName
from datasentry.tools.models import ToolCall

JOB_NODES = {
    "flink.kline": "kline",
    "flink.whale": "whale",
    "flink.risk": "risk",
}
COMPONENT_SERVICES = (
    (("collector",), "collector"),
    (("kafka",), "kafka"),
    (("flink",), "flink_jobmanager"),
    (("doris",), "doris_fe"),
    (("redis",), "redis"),
    (("mysql",), "mysql"),
    (("spring", "api"), "spring_api"),
    (("ai",), "ai_engine"),
)


class ReadOnlyInspectionPlanner:
    """将 Kline 主链路映射为确定性只读检查顺序。"""

    def plan(self, prepared: PreparedDiagnosis) -> tuple[ToolCall, ...]:
        node_ids = {node.node_id for node in prepared.lineage_checkpoints}
        calls: list[ToolCall] = []
        if "collector" in node_ids:
            calls.extend(
                (
                    ToolCall(name=ToolName.GET_HOST_STATUS, target="data1"),
                    ToolCall(
                        name=ToolName.GET_SERVICE_STATUS,
                        target="data1",
                        arguments={"service": "collector"},
                    ),
                )
            )
        for node_id, job in JOB_NODES.items():
            if node_id not in node_ids:
                continue
            calls.extend(
                (
                    ToolCall(name=ToolName.GET_FLINK_JOBS, target="flink"),
                    ToolCall(
                        name=ToolName.GET_FLINK_JOB,
                        target="flink",
                        arguments={"job": job},
                    ),
                    ToolCall(
                        name=ToolName.GET_FLINK_CHECKPOINTS,
                        target="flink",
                        arguments={"job": job},
                    ),
                    ToolCall(
                        name=ToolName.GET_FLINK_BACKPRESSURE,
                        target="flink",
                        arguments={"job": job},
                    ),
                )
            )
        if "kafka.binance.trade.raw" in node_ids:
            calls.append(
                ToolCall(
                    name=ToolName.GET_KAFKA_TOPIC,
                    target="data1",
                    arguments={"topic": "binance.trade.raw"},
                )
            )
        if "doris.kline_1min" in node_ids:
            calls.append(
                ToolCall(
                    name=ToolName.GET_DORIS_TABLE_FRESHNESS,
                    target="doris",
                    arguments={"table": "kline_1min"},
                )
            )
        if "doris.whale_alert" in node_ids:
            calls.append(
                ToolCall(
                    name=ToolName.GET_DORIS_TABLE_FRESHNESS,
                    target="doris",
                    arguments={"table": "whale_alert"},
                )
            )
        if "doris.risk_trigger" in node_ids:
            calls.append(
                ToolCall(
                    name=ToolName.GET_DORIS_TABLE_FRESHNESS,
                    target="doris",
                    arguments={"table": "risk_trigger"},
                )
            )
        if "redis.risk.blacklist" in node_ids:
            calls.append(
                ToolCall(
                    name=ToolName.GET_REDIS_KEY_SAMPLE,
                    target="redis",
                    arguments={"pattern": "risk:blacklist:*", "limit": 20},
                )
            )
        if "api.kline.latest" in node_ids:
            calls.append(
                ToolCall(
                    name=ToolName.GET_API_HEALTH,
                    target="spring_api",
                    arguments={"service": "spring_api"},
                )
            )
        if not calls:
            calls.extend(self._component_calls(prepared.inspection.question))
        return tuple(calls)

    @staticmethod
    def _component_calls(question: str) -> tuple[ToolCall, ...]:
        normalized = question.casefold()
        for keywords, service in COMPONENT_SERVICES:
            if not any(keyword in normalized for keyword in keywords):
                continue
            calls = [
                ToolCall(name=ToolName.GET_HOST_STATUS, target="data1"),
                ToolCall(
                    name=ToolName.GET_SERVICE_STATUS,
                    target="data1",
                    arguments={"service": service},
                ),
            ]
            if service in {"spring_api", "ai_engine"}:
                calls.append(
                    ToolCall(
                        name=ToolName.GET_API_HEALTH,
                        target=service,
                        arguments={"service": service},
                    )
                )
            return tuple(calls)
        return ()
