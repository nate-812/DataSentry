"""与稳定知识文档一致的 StreamLake 显式血缘目录。"""

from datasentry.knowledge.lineage import LineageGraph
from datasentry.knowledge.models import LineageEdge, LineageNode, LineageNodeKind


def _node(
    node_id: str,
    kind: LineageNodeKind,
    component: str,
    label: str,
) -> LineageNode:
    return LineageNode(node_id=node_id, kind=kind, component=component, label=label)


def build_streamlake_lineage() -> LineageGraph:
    """构建 M1 可审查、可测试的稳定血缘图。"""
    nodes = (
        _node("binance.websocket", LineageNodeKind.EXTERNAL, "binance", "Binance WebSocket"),
        _node("collector", LineageNodeKind.SERVICE, "collector", "Collector"),
        _node(
            "kafka.binance.trade.raw",
            LineageNodeKind.TOPIC,
            "kafka",
            "binance.trade.raw",
        ),
        _node("flink.kline", LineageNodeKind.JOB, "flink", "KlineAggregationJob"),
        _node("flink.whale", LineageNodeKind.JOB, "flink", "WhaleCepJob"),
        _node("flink.risk", LineageNodeKind.JOB, "flink", "RiskControlJob"),
        _node(
            "mysql.whale_thresholds",
            LineageNodeKind.TABLE,
            "mysql",
            "whale_thresholds",
        ),
        _node("mysql.risk_rules", LineageNodeKind.TABLE, "mysql", "risk_rules"),
        _node("doris.kline_1min", LineageNodeKind.TABLE, "doris", "kline_1min"),
        _node("doris.whale_alert", LineageNodeKind.TABLE, "doris", "whale_alert"),
        _node(
            "kafka.streamlake.whale.alert",
            LineageNodeKind.TOPIC,
            "kafka",
            "streamlake.whale.alert",
        ),
        _node("doris.risk_trigger", LineageNodeKind.TABLE, "doris", "risk_trigger"),
        _node(
            "redis.risk.blacklist",
            LineageNodeKind.KEY_PATTERN,
            "redis",
            "risk:blacklist:{SYMBOL}",
        ),
        _node(
            "api.kline.latest",
            LineageNodeKind.API,
            "spring_api",
            "/api/kline/{symbol}",
        ),
    )
    edges = (
        LineageEdge(source_id="binance.websocket", target_id="collector", relation="feeds"),
        LineageEdge(
            source_id="collector",
            target_id="kafka.binance.trade.raw",
            relation="writes",
        ),
        LineageEdge(
            source_id="kafka.binance.trade.raw",
            target_id="flink.kline",
            relation="consumed_by",
        ),
        LineageEdge(
            source_id="kafka.binance.trade.raw",
            target_id="flink.whale",
            relation="consumed_by",
        ),
        LineageEdge(
            source_id="kafka.binance.trade.raw",
            target_id="flink.risk",
            relation="consumed_by",
        ),
        LineageEdge(
            source_id="mysql.whale_thresholds",
            target_id="flink.whale",
            relation="configures",
        ),
        LineageEdge(
            source_id="mysql.risk_rules",
            target_id="flink.risk",
            relation="configures",
        ),
        LineageEdge(source_id="flink.kline", target_id="doris.kline_1min", relation="writes"),
        LineageEdge(
            source_id="doris.kline_1min",
            target_id="api.kline.latest",
            relation="queried_by",
        ),
        LineageEdge(source_id="flink.whale", target_id="doris.whale_alert", relation="writes"),
        LineageEdge(
            source_id="flink.whale",
            target_id="kafka.streamlake.whale.alert",
            relation="writes",
        ),
        LineageEdge(source_id="flink.risk", target_id="doris.risk_trigger", relation="writes"),
        LineageEdge(
            source_id="flink.risk",
            target_id="redis.risk.blacklist",
            relation="writes",
        ),
    )
    return LineageGraph(nodes, edges)
