from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest

from datasentry.diagnosis import (
    ComponentDownRule,
    ConfigurationMismatchRule,
    DiagnosisService,
    FlinkBackpressureRule,
    KlineStalledAtFlinkRule,
)
from datasentry.domain import EvidenceStatus, Observation
from datasentry.errors import KnowledgeError, StorageError
from datasentry.knowledge import (
    KnowledgeIndex,
    KnowledgeRouter,
    QuestionType,
    build_streamlake_lineage,
)
from datasentry.storage import Repository, SQLiteRepository

NOW = datetime(2026, 6, 25, 12, 0, tzinfo=UTC)
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def knowledge_index() -> KnowledgeIndex:
    return KnowledgeIndex.load(REPOSITORY_ROOT / "knowledge")


@pytest.fixture
def repository(tmp_path: Path) -> SQLiteRepository:
    with SQLiteRepository(tmp_path / "datasentry.db") as instance:
        yield instance


def _observations(inspection_id: str = "fixture") -> list[Observation]:
    return [
        Observation(
            inspection_id=inspection_id,
            component="kafka",
            metric_or_fact="topic_advancing",
            value=True,
            source="simulation_fixture",
            target="binance.trade.raw",
            observed_at=NOW,
        ),
        Observation(
            inspection_id=inspection_id,
            component="flink",
            metric_or_fact="kline_job_state",
            value={"state": "MISSING"},
            source="simulation_fixture",
            target="streamlake-kline-aggregation",
            observed_at=NOW,
        ),
        Observation(
            inspection_id=inspection_id,
            component="doris",
            metric_or_fact="kline_freshness_seconds",
            value=900,
            source="simulation_fixture",
            target="kline_1min",
            observed_at=NOW,
        ),
    ]


def _service(
    repository: Repository,
    knowledge_index: KnowledgeIndex,
) -> DiagnosisService:
    return DiagnosisService(
        repository=repository,
        knowledge_index=knowledge_index,
        router=KnowledgeRouter(knowledge_index),
        lineage_graph=build_streamlake_lineage(),
        rules=(
            KlineStalledAtFlinkRule(),
            ComponentDownRule(),
            FlinkBackpressureRule(),
            ConfigurationMismatchRule(),
        ),
        clock=lambda: NOW,
    )


def test_service_routes_loads_lineage_evaluates_and_persists(
    repository: SQLiteRepository,
    knowledge_index: KnowledgeIndex,
) -> None:
    service = _service(repository, knowledge_index)

    result = service.diagnose("为什么K线不更新", _observations())

    assert result.route.question_type is QuestionType.DATA_STALE
    assert [item.topic_id for item in result.knowledge] == ["03", "04"]
    assert [item.node_id for item in result.lineage_checkpoints] == [
        "collector",
        "kafka.binance.trade.raw",
        "flink.kline",
        "doris.kline_1min",
        "api.kline.latest",
    ]
    assert result.aggregate.findings[0].claim == "K线链路停在 Flink 计算层"
    assert repository.get_inspection(result.aggregate.inspection.id) == result.aggregate


def test_service_rebinds_input_observations_to_created_inspection(
    repository: SQLiteRepository,
    knowledge_index: KnowledgeIndex,
) -> None:
    result = _service(repository, knowledge_index).diagnose(
        "为什么K线不更新",
        _observations(),
    )
    inspection_id = result.aggregate.inspection.id

    assert {item.inspection_id for item in result.aggregate.observations} == {inspection_id}


def test_service_exposes_historical_topic_only_as_reference(
    repository: SQLiteRepository,
    knowledge_index: KnowledgeIndex,
) -> None:
    result = _service(repository, knowledge_index).diagnose(
        "Kafka延迟是否比历史更高",
        _observations(),
    )

    historical = [item for item in result.knowledge if item.historical]
    assert [item.topic_id for item in historical] == ["07"]
    assert all(
        evidence.status is not EvidenceStatus.CONFIRMED
        for finding in result.aggregate.findings
        for evidence in finding.evidence
        if evidence.source.startswith("knowledge:")
    )


def test_service_appends_collection_unknowns_to_findings(
    repository: SQLiteRepository,
    knowledge_index: KnowledgeIndex,
) -> None:
    result = _service(repository, knowledge_index).diagnose(
        "为什么K线不更新",
        _observations(),
        collection_unknowns=(
            "工具 get_kafka_topic 查询失败(tool.timeout)",
            "工具 get_kafka_topic 查询失败(tool.timeout)",
        ),
    )

    assert result.aggregate.findings[0].unknowns == [
        "Kline Job 上次退出原因尚未确认",
        "工具 get_kafka_topic 查询失败(tool.timeout)",
    ]


def test_service_does_not_persist_when_question_cannot_be_routed(
    knowledge_index: KnowledgeIndex,
) -> None:
    repository = Mock(spec=Repository)
    service = _service(repository, knowledge_index)

    with pytest.raises(KnowledgeError):
        service.diagnose("给我讲个故事", [])

    repository.start_inspection.assert_not_called()
    repository.complete_inspection.assert_not_called()
    repository.fail_inspection.assert_not_called()


def test_service_marks_started_inspection_failed_when_completion_fails(
    knowledge_index: KnowledgeIndex,
) -> None:
    repository = Mock(spec=Repository)
    repository.complete_inspection.side_effect = StorageError(
        code="storage.constraint",
        message="数据违反存储约束",
    )
    service = _service(repository, knowledge_index)

    with pytest.raises(StorageError):
        service.diagnose("为什么K线不更新", _observations())

    repository.start_inspection.assert_called_once()
    failed = repository.fail_inspection.call_args.args[0]
    assert failed.status.value == "failed"
    assert failed.summary == "诊断未能完成"
