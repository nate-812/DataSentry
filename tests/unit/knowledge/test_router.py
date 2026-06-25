from pathlib import Path

import pytest

from datasentry.errors import KnowledgeError
from datasentry.knowledge import KnowledgeIndex, KnowledgeRouter, QuestionType


@pytest.fixture
def knowledge_index() -> KnowledgeIndex:
    return KnowledgeIndex.load(Path(__file__).resolve().parents[3] / "knowledge")


@pytest.mark.parametrize(
    ("question", "question_type", "required"),
    [
        ("为什么K线不更新", QuestionType.DATA_STALE, ("03", "04")),
        ("Collector是不是挂了", QuestionType.COMPONENT_DOWN, ("02", "06")),
        (
            "Flink反压很高而且Checkpoint失败",
            QuestionType.LATENCY_BACKPRESSURE,
            ("03", "04"),
        ),
        ("Whale阈值配置为什么没生效", QuestionType.CONFIGURATION, ("04", "03")),
    ],
)
def test_router_selects_question_type_and_topics(
    knowledge_index: KnowledgeIndex,
    question: str,
    question_type: QuestionType,
    required: tuple[str, ...],
) -> None:
    match = KnowledgeRouter(knowledge_index).route(question)

    assert match.question_type is question_type
    assert match.required_topic_ids == required
    assert 1 <= len(match.required_topic_ids) <= 3


def test_router_prefers_configuration_over_generic_failure_word(
    knowledge_index: KnowledgeIndex,
) -> None:
    match = KnowledgeRouter(knowledge_index).route("配置错误导致Job不更新吗")
    assert match.question_type is QuestionType.CONFIGURATION


def test_router_adds_historical_topic_for_comparison(
    knowledge_index: KnowledgeIndex,
) -> None:
    match = KnowledgeRouter(knowledge_index).route("Kafka延迟是否比历史更高")
    assert match.required_topic_ids == ("03", "04", "07")


def test_router_rejects_unclassified_question(knowledge_index: KnowledgeIndex) -> None:
    with pytest.raises(KnowledgeError) as raised:
        KnowledgeRouter(knowledge_index).route("给我讲个故事")

    assert raised.value.code == "knowledge.question_unclassified"
