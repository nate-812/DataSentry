import pytest

from datasentry.errors import LineageError
from datasentry.knowledge import LineageEdge, LineageGraph, build_streamlake_lineage


def test_kline_check_path_is_ordered() -> None:
    graph = build_streamlake_lineage()

    path = graph.shortest_path("collector", "api.kline.latest")

    assert [node.node_id for node in path] == [
        "collector",
        "kafka.binance.trade.raw",
        "flink.kline",
        "doris.kline_1min",
        "api.kline.latest",
    ]


@pytest.mark.parametrize(
    ("target", "expected_tail"),
    [
        ("doris.whale_alert", ["flink.whale", "doris.whale_alert"]),
        (
            "kafka.streamlake.whale.alert",
            ["flink.whale", "kafka.streamlake.whale.alert"],
        ),
        ("doris.risk_trigger", ["flink.risk", "doris.risk_trigger"]),
        ("redis.risk.blacklist", ["flink.risk", "redis.risk.blacklist"]),
    ],
)
def test_trade_lineage_reaches_expected_sink(
    target: str,
    expected_tail: list[str],
) -> None:
    path = build_streamlake_lineage().shortest_path("collector", target)
    assert [node.node_id for node in path][-2:] == expected_tail


def test_graph_rejects_edge_with_unknown_node() -> None:
    with pytest.raises(LineageError) as raised:
        LineageGraph(
            nodes=(),
            edges=(LineageEdge(source_id="a", target_id="b", relation="writes"),),
        )

    assert raised.value.code == "lineage.unknown_node"


def test_missing_path_returns_safe_error() -> None:
    graph = build_streamlake_lineage()

    with pytest.raises(LineageError) as raised:
        graph.shortest_path("mysql.whale_thresholds", "redis.risk.blacklist")

    assert raised.value.code == "lineage.path_not_found"
