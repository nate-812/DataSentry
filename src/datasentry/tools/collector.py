"""顺序执行只读工具计划，并将局部失败转换为未知项。"""

from typing import Protocol

from datasentry.domain import Observation, ToolStatus
from datasentry.domain.common import DomainModel
from datasentry.tools.models import ToolCall, ToolOutcome


class Gateway(Protocol):
    def execute(self, inspection_id: str, call: ToolCall) -> ToolOutcome:
        raise NotImplementedError  # pragma: no cover


class CollectionResult(DomainModel):
    outcomes: list[ToolOutcome]
    observations: list[Observation]
    unknowns: list[str]


class InspectionCollector:
    """保持低并发，按计划顺序调用网关。"""

    def __init__(self, gateway: Gateway) -> None:
        self._gateway = gateway

    def collect(
        self,
        inspection_id: str,
        calls: tuple[ToolCall, ...],
    ) -> CollectionResult:
        outcomes: list[ToolOutcome] = []
        observations: list[Observation] = []
        unknowns: list[str] = []
        for call in calls:
            outcome = self._gateway.execute(inspection_id, call)
            outcomes.append(outcome)
            observations.extend(outcome.observations)
            if outcome.status is ToolStatus.FAILED:
                assert outcome.failure is not None
                unknowns.append(
                    f"工具 {call.name.value} 查询 {call.target} 失败({outcome.failure.code})"
                )
        return CollectionResult(
            outcomes=outcomes,
            observations=observations,
            unknowns=unknowns,
        )
