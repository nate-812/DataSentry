from pathlib import Path

from datasentry.knowledge import KnowledgeIndex, build_streamlake_lineage

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_repository_knowledge_index_is_valid() -> None:
    index = KnowledgeIndex.load(REPOSITORY_ROOT / "knowledge")

    assert set(index.topic_ids()) == {f"{number:02d}" for number in range(1, 10)}
    assert index.topic("07").historical is True
    assert "Collector" in index.load_topic_text("03")
    assert "任意Shell" in index.load_topic_text("09").replace(" ", "")


def test_repository_routes_reference_existing_topics() -> None:
    index = KnowledgeIndex.load(REPOSITORY_ROOT / "knowledge")

    for route in index.routes():
        for topic_id in route.required_topic_ids + route.optional_topic_ids:
            assert index.topic(topic_id).path.is_file()


def test_streamlake_catalog_contains_documented_primary_assets() -> None:
    graph = build_streamlake_lineage()
    documented = (REPOSITORY_ROOT / "knowledge/03-jobs-and-lineage.md").read_text(encoding="utf-8")

    for name in (
        "binance.trade.raw",
        "KlineAggregationJob",
        "WhaleCepJob",
        "RiskControlJob",
        "kline_1min",
        "whale_alert",
        "risk_trigger",
        "risk:blacklist:{SYMBOL}",
    ):
        assert name in documented
    assert graph.node("flink.kline").label == "KlineAggregationJob"
