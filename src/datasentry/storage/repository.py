"""应用 Service 使用的存储抽象。"""

from dataclasses import dataclass
from typing import Protocol

from datasentry.domain import (
    Finding,
    Incident,
    Inspection,
    Observation,
    Operation,
    ToolInvocation,
)


@dataclass(frozen=True, slots=True)
class InspectionAggregate:
    inspection: Inspection
    observations: list[Observation]
    findings: list[Finding]


class Repository(Protocol):
    def start_inspection(self, inspection: Inspection) -> None:
        raise NotImplementedError  # pragma: no cover

    def complete_inspection(
        self,
        inspection: Inspection,
        observations: list[Observation],
        findings: list[Finding],
    ) -> InspectionAggregate:
        raise NotImplementedError  # pragma: no cover

    def fail_inspection(self, inspection: Inspection) -> None:
        raise NotImplementedError  # pragma: no cover

    def save_inspection(self, inspection: Inspection) -> None:
        raise NotImplementedError  # pragma: no cover

    def add_observation(self, observation: Observation) -> None:
        raise NotImplementedError  # pragma: no cover

    def add_finding(self, finding: Finding) -> None:
        raise NotImplementedError  # pragma: no cover

    def get_inspection(self, inspection_id: str) -> InspectionAggregate:
        raise NotImplementedError  # pragma: no cover

    def save_tool_invocation(self, invocation: ToolInvocation) -> None:
        raise NotImplementedError  # pragma: no cover

    def list_tool_invocations(self, inspection_id: str) -> list[ToolInvocation]:
        raise NotImplementedError  # pragma: no cover

    def save_incident(self, incident: Incident) -> None:
        raise NotImplementedError  # pragma: no cover

    def update_incident(self, incident: Incident) -> None:
        raise NotImplementedError  # pragma: no cover

    def get_incident(self, incident_id: str) -> Incident:
        raise NotImplementedError  # pragma: no cover

    def save_operation(self, operation: Operation) -> None:
        raise NotImplementedError  # pragma: no cover

    def update_operation(self, operation: Operation) -> None:
        raise NotImplementedError  # pragma: no cover

    def get_operation(self, operation_id: str) -> Operation:
        raise NotImplementedError  # pragma: no cover

    def close(self) -> None:
        raise NotImplementedError  # pragma: no cover
