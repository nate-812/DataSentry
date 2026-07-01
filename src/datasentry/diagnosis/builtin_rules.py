"""M1 首批确定性诊断规则。"""

from typing import ClassVar

from pydantic import JsonValue

from datasentry.diagnosis.rules import RuleContext, evidence_from_observation
from datasentry.domain import Evidence, EvidenceStatus, Finding, Severity
from datasentry.knowledge import QuestionType


def _object(value: JsonValue) -> dict[str, JsonValue] | None:
    if isinstance(value, dict):
        return value
    return None


def _unknown_evidence(context: RuleContext, claim: str) -> Evidence:
    return Evidence(
        claim=claim,
        status=EvidenceStatus.UNKNOWN,
        source="datasentry_diagnosis",
        target=None,
        observed_at=context.created_at,
        summary="当前 Observation 不足以确认该事实",
    )


def _finding_status(
    evidence: list[Evidence],
    *,
    current_status: EvidenceStatus,
) -> EvidenceStatus:
    historical_count = sum(item.status is EvidenceStatus.HISTORICAL for item in evidence)
    if historical_count == len(evidence):
        return EvidenceStatus.HISTORICAL
    if historical_count:
        return EvidenceStatus.UNKNOWN
    return current_status


class KlineStalledAtFlinkRule:
    """识别 Kafka 推进但 Kline Job 缺失的链路中断。"""

    rule_id = "data.kline_stalled_at_flink"
    supported_question_types = frozenset({QuestionType.DATA_STALE})

    def evaluate(self, context: RuleContext) -> Finding | None:
        if context.question_type not in self.supported_question_types:
            return None
        kafka = context.find("kafka", "topic_advancing")
        flink = context.find("flink", "kline_job_state")
        doris = context.find("doris", "kline_freshness_seconds")
        unknowns: list[str] = []
        if flink is None:
            unknowns.append("Kline Job 当前状态未知")
        if doris is None:
            unknowns.append("Doris kline_1min 数据新鲜度未知")
        if unknowns:
            evidence = (
                [
                    evidence_from_observation(
                        kafka,
                        claim="Kafka 原始 Topic 当前仍在推进",
                    )
                ]
                if kafka is not None
                else [_unknown_evidence(context, "Kafka 原始 Topic 推进状态未知")]
            )
            return Finding(
                inspection_id=context.inspection_id,
                severity=Severity.WARNING,
                status=EvidenceStatus.UNKNOWN,
                claim="K线链路中断位置尚未确认",
                evidence=evidence,
                impact="无法确定 K 线不更新发生在哪一层",
                recommendation="补充查询 Kline Job 状态和 Doris 数据新鲜度",
                unknowns=unknowns,
                created_at=context.created_at,
            )
        assert flink is not None
        assert doris is not None
        flink_value = _object(flink.value)
        state = None if flink_value is None else flink_value.get("state")
        freshness = doris.value
        if (
            kafka is not None
            and kafka.value is True
            and state in {"MISSING", "FAILED", "CANCELED"}
            and isinstance(freshness, (int, float))
            and not isinstance(freshness, bool)
            and freshness >= 300
        ):
            evidence = [
                evidence_from_observation(kafka, claim="Kafka 原始 Topic 当前仍在推进"),
                evidence_from_observation(flink, claim="Kline Job 当前未正常运行"),
                evidence_from_observation(
                    doris,
                    claim="Doris kline_1min 数据新鲜度已落后",
                ),
            ]
            status = _finding_status(
                evidence,
                current_status=EvidenceStatus.INFERRED,
            )
            return Finding(
                inspection_id=context.inspection_id,
                severity=Severity.CRITICAL,
                status=status,
                claim=(
                    "历史快照显示 K线链路曾停在 Flink 计算层"
                    if status is EvidenceStatus.HISTORICAL
                    else "K线链路停在 Flink 计算层"
                ),
                evidence=evidence,
                impact="新的交易数据无法形成 K 线结果并供 API 查询",
                recommendation="读取有限 JobManager 日志，确认无重复 Job 后再申请恢复",
                unknowns=["Kline Job 上次退出原因尚未确认"],
                created_at=context.created_at,
            )
        if (
            state == "RUNNING"
            and isinstance(freshness, (int, float))
            and not isinstance(freshness, bool)
            and freshness < 300
        ):
            evidence = []
            if kafka is not None and kafka.value is True:
                evidence.append(
                    evidence_from_observation(kafka, claim="Kafka 原始 Topic 当前仍在推进")
                )
            evidence.extend(
                [
                    evidence_from_observation(flink, claim="Kline Job 当前正常运行"),
                    evidence_from_observation(
                        doris,
                        claim="Doris kline_1min 数据新鲜度正常",
                    ),
                ]
            )
            status = _finding_status(
                evidence,
                current_status=EvidenceStatus.CONFIRMED,
            )
            return Finding(
                inspection_id=context.inspection_id,
                severity=Severity.INFO,
                status=status,
                claim=(
                    "历史快照显示 K线主链路曾正常推进"
                    if status is EvidenceStatus.HISTORICAL
                    else "K线主链路当前正在推进"
                ),
                evidence=evidence,
                impact="当前证据未显示 K线主链路存在数据不更新",
                recommendation="若用户仍看到页面不更新，继续检查 API 缓存、前端轮询和查询参数",
                unknowns=[],
                created_at=context.created_at,
            )
        return None


class ComponentDownRule:
    """将明确的组件未运行 Observation 转换为 Finding。"""

    rule_id = "component.not_running"
    supported_question_types = frozenset({QuestionType.COMPONENT_DOWN})
    _labels: ClassVar[dict[str, str]] = {
        "collector": "Collector",
        "kafka": "Kafka",
        "flink": "Flink",
        "doris": "Doris",
        "redis": "Redis",
        "mysql": "MySQL",
        "spring_api": "Spring API",
        "ai_engine": "AI Engine",
    }

    def evaluate(self, context: RuleContext) -> Finding | None:
        if context.question_type not in self.supported_question_types:
            return None
        candidates = [
            item for item in context.observations if item.metric_or_fact == "service_state"
        ]
        if not candidates:
            return None
        observation = max(candidates, key=lambda item: item.observed_at)
        value = _object(observation.value)
        state = None if value is None else value.get("state")
        if state not in {"NOT_RUNNING", "MISSING", "FAILED"}:
            return None
        label = self._labels.get(observation.component, observation.component)
        evidence = evidence_from_observation(
            observation,
            claim=f"{label} 当前未运行",
        )
        status = _finding_status(
            [evidence],
            current_status=EvidenceStatus.CONFIRMED,
        )
        claim = (
            f"历史快照显示 {label} 未运行"
            if status is EvidenceStatus.HISTORICAL
            else f"{label} 当前未运行"
        )
        return Finding(
            inspection_id=context.inspection_id,
            severity=Severity.CRITICAL,
            status=status,
            claim=claim,
            evidence=[evidence],
            impact=f"{label} 负责的链路能力当前不可用",
            recommendation="读取部署知识与有限日志，确认启动依据后再请求人工处理",
            unknowns=["组件退出原因尚未确认"],
            created_at=context.created_at,
        )


class FlinkBackpressureRule:
    """识别高反压与连续 Checkpoint 失败同时出现。"""

    rule_id = "flink.backpressure_with_checkpoint_failures"
    supported_question_types = frozenset({QuestionType.LATENCY_BACKPRESSURE})

    def evaluate(self, context: RuleContext) -> Finding | None:
        if context.question_type not in self.supported_question_types:
            return None
        pressure = context.find("flink", "backpressure_level")
        failures = context.find("flink", "checkpoint_consecutive_failures")
        if pressure is None or failures is None:
            return None
        failure_count = failures.value
        if (
            pressure.value == "high"
            and isinstance(failure_count, int)
            and not isinstance(failure_count, bool)
            and failure_count >= 3
        ):
            evidence = [
                evidence_from_observation(pressure, claim="Flink 当前反压等级为 high"),
                evidence_from_observation(
                    failures,
                    claim="Flink 已连续发生至少 3 次 Checkpoint 失败",
                ),
            ]
            return Finding(
                inspection_id=context.inspection_id,
                severity=Severity.WARNING,
                status=_finding_status(
                    evidence,
                    current_status=EvidenceStatus.INFERRED,
                ),
                claim="Flink 链路存在持续反压并伴随 Checkpoint 失败",
                evidence=evidence,
                impact="处理延迟可能继续扩大，故障恢复点也可能变旧",
                recommendation="继续检查 Source 吞吐、Vertex 忙碌度和 Sink 耗时",
                unknowns=["反压最早出现的 Vertex 尚未确认"],
                created_at=context.created_at,
            )
        return None


class ConfigurationMismatchRule:
    """识别配置生效来源与预期来源不一致。"""

    rule_id = "configuration.effective_value_mismatch"
    supported_question_types = frozenset({QuestionType.CONFIGURATION})

    def evaluate(self, context: RuleContext) -> Finding | None:
        if context.question_type not in self.supported_question_types:
            return None
        observation = context.find("flink", "configuration_resolution")
        if observation is None:
            return None
        value = _object(observation.value)
        if value is None:
            return None
        key = value.get("key")
        expected = value.get("expected_source")
        effective = value.get("effective_source")
        if (
            isinstance(key, str)
            and isinstance(expected, str)
            and isinstance(effective, str)
            and expected != effective
        ):
            claim = f"配置 {key} 的生效来源与预期不一致"
            evidence = evidence_from_observation(observation, claim=claim)
            return Finding(
                inspection_id=context.inspection_id,
                severity=Severity.WARNING,
                status=_finding_status(
                    [evidence],
                    current_status=EvidenceStatus.CONFIRMED,
                ),
                claim=claim,
                evidence=[evidence],
                impact="运行中的 Job 可能使用了非预期配置",
                recommendation="按环境变量、配置文件、代码默认值顺序核对生效来源",
                unknowns=["配置内容已脱敏，具体值需要在受限工具中复核"],
                created_at=context.created_at,
            )
        return None
