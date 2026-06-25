"""诊断规则的纯函数上下文和证据转换。"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from datasentry.domain import Evidence, EvidenceStatus, Finding, Observation
from datasentry.knowledge import LineageNode, QuestionType


@dataclass(frozen=True, slots=True)
class RuleContext:
    """一次规则求值所需的全部不可变输入。"""

    inspection_id: str
    question_type: QuestionType
    observations: tuple[Observation, ...]
    lineage_checkpoints: tuple[LineageNode, ...]
    created_at: datetime

    def find(self, component: str, metric_or_fact: str) -> Observation | None:
        """返回时间最新的匹配 Observation。"""
        matched = (
            item
            for item in self.observations
            if item.component == component and item.metric_or_fact == metric_or_fact
        )
        return max(matched, key=lambda item: item.observed_at, default=None)


class DiagnosisRule(Protocol):
    """确定性诊断规则接口。"""

    rule_id: str
    supported_question_types: frozenset[QuestionType]

    def evaluate(self, context: RuleContext) -> Finding | None:
        """根据标准 Observation 返回 Finding 或不命中。"""
        raise NotImplementedError


def evidence_from_observation(
    observation: Observation,
    *,
    claim: str,
    summary: str | None = None,
) -> Evidence:
    """保留 Observation 来源和时间，并隔离历史快照。"""
    status = (
        EvidenceStatus.HISTORICAL
        if observation.source.startswith("knowledge:")
        else EvidenceStatus.CONFIRMED
    )
    return Evidence(
        claim=claim,
        status=status,
        source=observation.source,
        target=observation.target,
        observed_at=observation.observed_at,
        summary=summary or claim,
    )
