"""真实只读采集与 M1 确定性诊断的组合服务。"""

from typing import Protocol

from datasentry.diagnosis import DiagnosisResult, DiagnosisService, PreparedDiagnosis
from datasentry.domain import ToolInvocation
from datasentry.domain.common import DomainModel
from datasentry.storage import Repository
from datasentry.tools.collector import CollectionResult
from datasentry.tools.models import ToolCall


class Planner(Protocol):
    def plan(self, prepared: PreparedDiagnosis) -> tuple[ToolCall, ...]:
        raise NotImplementedError  # pragma: no cover


class Collector(Protocol):
    def collect(
        self,
        inspection_id: str,
        calls: tuple[ToolCall, ...],
    ) -> CollectionResult:
        raise NotImplementedError  # pragma: no cover


class LiveInspectionResult(DomainModel):
    diagnosis: DiagnosisResult
    tool_invocations: list[ToolInvocation]


class LiveInspectionService:
    """准备巡检、采集真实 Observation 并完成诊断。"""

    def __init__(
        self,
        *,
        repository: Repository,
        diagnosis: DiagnosisService,
        planner: Planner,
        collector: Collector,
    ) -> None:
        self._repository = repository
        self._diagnosis = diagnosis
        self._planner = planner
        self._collector = collector

    def run(self, question: str) -> LiveInspectionResult:
        prepared = self._diagnosis.prepare(question)
        self._repository.start_inspection(prepared.inspection)
        try:
            calls = self._planner.plan(prepared)
            collection = self._collector.collect(prepared.inspection.id, calls)
            diagnosis = self._diagnosis.complete(
                prepared,
                collection.observations,
                collection_unknowns=tuple(collection.unknowns),
            )
            return LiveInspectionResult(
                diagnosis=diagnosis,
                tool_invocations=self._repository.list_tool_invocations(prepared.inspection.id),
            )
        except Exception:
            self._diagnosis.fail(prepared.inspection)
            raise
