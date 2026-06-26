"""知识、血缘、规则和 Repository 的本地诊断编排。"""

from collections.abc import Callable, Sequence
from contextlib import suppress
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from datasentry.diagnosis.rules import DiagnosisRule, RuleContext
from datasentry.domain import (
    Evidence,
    EvidenceStatus,
    Finding,
    Inspection,
    InspectionStatus,
    Observation,
    Severity,
)
from datasentry.domain.common import utc_now
from datasentry.knowledge import (
    KnowledgeIndex,
    KnowledgeReference,
    KnowledgeRouter,
    LineageGraph,
    LineageNode,
    RouteMatch,
)
from datasentry.storage import InspectionAggregate, Repository


class DiagnosisResult(BaseModel):
    """一次知识驱动诊断的可序列化结果。"""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    route: RouteMatch
    knowledge: list[KnowledgeReference]
    lineage_checkpoints: list[LineageNode]
    aggregate: InspectionAggregate


class PreparedDiagnosis(BaseModel):
    """已完成知识与血缘准备、尚未采集现场 Observation 的巡检。"""

    model_config = ConfigDict(frozen=True)

    inspection: Inspection
    route: RouteMatch
    knowledge: list[KnowledgeReference]
    lineage_checkpoints: list[LineageNode]


class DiagnosisService:
    """执行不依赖网络和 LLM 的确定性诊断。"""

    def __init__(
        self,
        repository: Repository,
        knowledge_index: KnowledgeIndex,
        router: KnowledgeRouter,
        lineage_graph: LineageGraph,
        rules: Sequence[DiagnosisRule],
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._repository = repository
        self._knowledge_index = knowledge_index
        self._router = router
        self._lineage_graph = lineage_graph
        self._rules = tuple(rules)
        self._clock = clock

    def diagnose(
        self,
        question: str,
        observations: list[Observation],
        collection_unknowns: tuple[str, ...] = (),
    ) -> DiagnosisResult:
        """路由问题、执行规则并保存巡检聚合。"""
        prepared = self.prepare(question)
        self._repository.start_inspection(prepared.inspection)
        try:
            return self.complete(
                prepared,
                observations,
                collection_unknowns=collection_unknowns,
            )
        except Exception:
            self.fail(prepared.inspection)
            raise

    def prepare(self, question: str) -> PreparedDiagnosis:
        """完成问题路由、知识加载和血缘选择，不访问生产工具。"""
        route = self._router.route(question)
        knowledge = [self._knowledge_reference(topic_id) for topic_id in route.required_topic_ids]
        checkpoints = self._lineage_checkpoints(question)
        started_at = self._clock()
        inspection = Inspection(
            question=question,
            scope=[
                route.question_type.value,
                *(f"knowledge:{item.topic_id}" for item in knowledge),
                *(f"lineage:{item.node_id}" for item in checkpoints),
            ],
            status=InspectionStatus.RUNNING,
            started_at=started_at,
        )
        return PreparedDiagnosis(
            inspection=inspection,
            route=route,
            knowledge=knowledge,
            lineage_checkpoints=list(checkpoints),
        )

    def complete(
        self,
        prepared: PreparedDiagnosis,
        observations: list[Observation],
        *,
        collection_unknowns: tuple[str, ...] = (),
    ) -> DiagnosisResult:
        """执行规则并原子完成已启动的巡检。"""
        inspection = prepared.inspection
        rebound = [
            item.model_copy(update={"inspection_id": inspection.id}) for item in observations
        ]
        context = RuleContext(
            inspection_id=inspection.id,
            question_type=prepared.route.question_type,
            observations=tuple(rebound),
            lineage_checkpoints=tuple(prepared.lineage_checkpoints),
            created_at=inspection.started_at,
        )
        findings = [
            finding
            for rule in self._rules
            if prepared.route.question_type in rule.supported_question_types
            if (finding := rule.evaluate(context)) is not None
        ]
        if not findings:
            findings = [self._unknown_finding(context)]
        findings = self._append_unknowns(findings, collection_unknowns)
        completed = inspection.model_copy(
            update={
                "status": InspectionStatus.COMPLETED,
                "summary": findings[0].claim,
                "finished_at": self._clock(),
            }
        )
        aggregate = self._repository.complete_inspection(
            completed,
            rebound,
            findings,
        )
        return DiagnosisResult(
            route=prepared.route,
            knowledge=prepared.knowledge,
            lineage_checkpoints=prepared.lineage_checkpoints,
            aggregate=aggregate,
        )

    def fail(self, inspection: Inspection) -> None:
        """尽力将已启动巡检标记为失败。"""
        failed = inspection.model_copy(
            update={
                "status": InspectionStatus.FAILED,
                "summary": "诊断未能完成",
                "finished_at": self._clock(),
            }
        )
        with suppress(Exception):
            self._repository.fail_inspection(failed)

    def _knowledge_reference(self, topic_id: str) -> KnowledgeReference:
        topic = self._knowledge_index.topic(topic_id)
        self._knowledge_index.load_topic_text(topic_id)
        return KnowledgeReference(
            topic_id=topic.topic_id,
            path=topic.path.name,
            title=topic.title,
            historical=topic.historical,
        )

    def _lineage_checkpoints(self, question: str) -> tuple[LineageNode, ...]:
        normalized = question.casefold()
        if "k线" in normalized or "kline" in normalized:
            return self._lineage_graph.shortest_path("collector", "api.kline.latest")
        if "巨鲸" in normalized or "whale" in normalized:
            return self._lineage_graph.shortest_path("collector", "doris.whale_alert")
        if "风控" in normalized or "risk" in normalized:
            return self._lineage_graph.shortest_path("collector", "redis.risk.blacklist")
        return ()

    @staticmethod
    def _unknown_finding(context: RuleContext) -> Finding:
        claim = "当前 Observation 不足以形成确定性结论"
        evidence = Evidence(
            claim=claim,
            status=EvidenceStatus.UNKNOWN,
            source="datasentry_diagnosis",
            target=None,
            observed_at=context.created_at,
            summary="没有规则满足全部前置证据",
        )
        return Finding(
            inspection_id=context.inspection_id,
            severity=Severity.INFO,
            status=EvidenceStatus.UNKNOWN,
            claim=claim,
            evidence=[evidence],
            impact="当前无法确定故障位置或影响范围",
            recommendation="补充对应组件的实时只读 Observation",
            unknowns=["现场状态证据不足"],
            created_at=context.created_at,
        )

    @staticmethod
    def _append_unknowns(
        findings: list[Finding],
        collection_unknowns: tuple[str, ...],
    ) -> list[Finding]:
        if not collection_unknowns:
            return findings
        return [
            finding.model_copy(
                update={"unknowns": list(dict.fromkeys((*finding.unknowns, *collection_unknowns)))}
            )
            for finding in findings
        ]
