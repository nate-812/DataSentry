from datetime import UTC, datetime

from datasentry.diagnosis import (
    ComponentDownRule,
    ConfigurationMismatchRule,
    FlinkBackpressureRule,
    KlineStalledAtFlinkRule,
    RuleContext,
)
from datasentry.domain import EvidenceStatus, Observation, Severity
from datasentry.knowledge import QuestionType

NOW = datetime(2026, 6, 25, 12, 0, tzinfo=UTC)


def _observation(
    component: str,
    metric_or_fact: str,
    value: object,
    *,
    target: str = "local",
    source: str = "simulation_fixture",
) -> Observation:
    return Observation(
        inspection_id="fixture",
        component=component,
        metric_or_fact=metric_or_fact,
        value=value,
        source=source,
        target=target,
        observed_at=NOW,
    )


def _context(
    *observations: Observation,
    question_type: QuestionType,
) -> RuleContext:
    return RuleContext(
        inspection_id="inspection",
        question_type=question_type,
        observations=observations,
        lineage_checkpoints=(),
        created_at=NOW,
    )


def test_kline_rule_locates_break_at_flink() -> None:
    context = _context(
        _observation("kafka", "topic_advancing", True, target="binance.trade.raw"),
        _observation("flink", "kline_job_state", {"state": "MISSING"}),
        _observation("doris", "kline_freshness_seconds", 900, target="kline_1min"),
        question_type=QuestionType.DATA_STALE,
    )

    finding = KlineStalledAtFlinkRule().evaluate(context)

    assert finding is not None
    assert finding.status is EvidenceStatus.INFERRED
    assert finding.severity is Severity.CRITICAL
    assert finding.claim == "K线链路停在 Flink 计算层"
    assert len(finding.evidence) == 3


def test_component_down_rule_reports_confirmed_absence() -> None:
    context = _context(
        _observation(
            "collector",
            "service_state",
            {"state": "NOT_RUNNING"},
            target="data1",
        ),
        question_type=QuestionType.COMPONENT_DOWN,
    )

    finding = ComponentDownRule().evaluate(context)

    assert finding is not None
    assert finding.status is EvidenceStatus.CONFIRMED
    assert finding.claim == "Collector 当前未运行"


def test_backpressure_rule_requires_high_pressure_and_checkpoint_failures() -> None:
    context = _context(
        _observation("flink", "backpressure_level", "high"),
        _observation("flink", "checkpoint_consecutive_failures", 3),
        question_type=QuestionType.LATENCY_BACKPRESSURE,
    )

    finding = FlinkBackpressureRule().evaluate(context)

    assert finding is not None
    assert finding.status is EvidenceStatus.INFERRED
    assert finding.severity is Severity.WARNING


def test_configuration_rule_reports_effective_source_mismatch() -> None:
    context = _context(
        _observation(
            "flink",
            "configuration_resolution",
            {
                "key": "WHALE_THRESHOLD",
                "expected_source": "mysql",
                "effective_source": "default",
            },
        ),
        question_type=QuestionType.CONFIGURATION,
    )

    finding = ConfigurationMismatchRule().evaluate(context)

    assert finding is not None
    assert finding.status is EvidenceStatus.CONFIRMED
    assert finding.claim == "配置 WHALE_THRESHOLD 的生效来源与预期不一致"


def test_kline_rule_returns_unknown_when_required_observation_is_missing() -> None:
    context = _context(
        _observation("kafka", "topic_advancing", True),
        question_type=QuestionType.DATA_STALE,
    )

    finding = KlineStalledAtFlinkRule().evaluate(context)

    assert finding is not None
    assert finding.status is EvidenceStatus.UNKNOWN
    assert finding.unknowns == [
        "Kline Job 当前状态未知",
        "Doris kline_1min 数据新鲜度未知",
    ]


def test_component_down_rule_keeps_historical_finding_status() -> None:
    context = _context(
        _observation(
            "collector",
            "service_state",
            {"state": "NOT_RUNNING"},
            source="knowledge:07-runtime-baseline-2026-06-25.md",
        ),
        question_type=QuestionType.COMPONENT_DOWN,
    )

    finding = ComponentDownRule().evaluate(context)

    assert finding is not None
    assert finding.status is EvidenceStatus.HISTORICAL
    assert finding.evidence[0].status is EvidenceStatus.HISTORICAL


def test_kline_rule_does_not_infer_current_failure_from_historical_inputs() -> None:
    source = "knowledge:07-runtime-baseline-2026-06-25.md"
    context = _context(
        _observation("kafka", "topic_advancing", True, source=source),
        _observation(
            "flink",
            "kline_job_state",
            {"state": "MISSING"},
            source=source,
        ),
        _observation("doris", "kline_freshness_seconds", 900, source=source),
        question_type=QuestionType.DATA_STALE,
    )

    finding = KlineStalledAtFlinkRule().evaluate(context)

    assert finding is not None
    assert finding.status is EvidenceStatus.HISTORICAL
