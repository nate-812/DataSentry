from datetime import UTC, datetime, timedelta

from datasentry.diagnosis import RuleContext, evidence_from_observation
from datasentry.domain import EvidenceStatus, Observation
from datasentry.knowledge import QuestionType

NOW = datetime(2026, 6, 25, 12, 0, tzinfo=UTC)


def _observation(
    component: str,
    metric_or_fact: str,
    value: object,
    observed_at: datetime,
    *,
    source: str = "simulation_fixture",
) -> Observation:
    return Observation(
        inspection_id="fixture",
        component=component,
        metric_or_fact=metric_or_fact,
        value=value,
        source=source,
        target="local",
        observed_at=observed_at,
    )


def test_rule_context_finds_latest_matching_observation() -> None:
    older = _observation("flink", "job_state", {"state": "RUNNING"}, NOW)
    newer = _observation(
        "flink",
        "job_state",
        {"state": "MISSING"},
        NOW + timedelta(minutes=1),
    )
    context = RuleContext(
        inspection_id="inspection",
        question_type=QuestionType.DATA_STALE,
        observations=(older, newer),
        lineage_checkpoints=(),
        created_at=NOW,
    )

    assert context.find("flink", "job_state") == newer


def test_observation_evidence_keeps_runtime_provenance() -> None:
    item = _observation("kafka", "topic_advancing", True, NOW)

    evidence = evidence_from_observation(item, claim="Kafka 原始 Topic 仍在推进")

    assert evidence.status is EvidenceStatus.CONFIRMED
    assert evidence.source == item.source
    assert evidence.target == item.target
    assert evidence.observed_at == item.observed_at


def test_historical_observation_cannot_be_promoted_to_confirmed_evidence() -> None:
    item = _observation(
        "flink",
        "job_state",
        {"state": "RUNNING"},
        NOW,
        source="knowledge:07-runtime-baseline-2026-06-25.md",
    )

    evidence = evidence_from_observation(item, claim="历史快照中的 Job 状态")

    assert evidence.status is EvidenceStatus.HISTORICAL
