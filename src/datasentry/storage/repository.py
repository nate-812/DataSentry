"""应用 Service 使用的存储抽象。"""

from dataclasses import dataclass
from typing import Protocol

from datasentry.domain import Finding, Incident, Inspection, Observation, Operation


@dataclass(frozen=True, slots=True)
class InspectionAggregate:
    inspection: Inspection
    observations: list[Observation]
    findings: list[Finding]


class Repository(Protocol):
    def save_inspection(self, inspection: Inspection) -> None:
        raise NotImplementedError

    def add_observation(self, observation: Observation) -> None:
        raise NotImplementedError

    def add_finding(self, finding: Finding) -> None:
        raise NotImplementedError

    def get_inspection(self, inspection_id: str) -> InspectionAggregate:
        raise NotImplementedError

    def save_incident(self, incident: Incident) -> None:
        raise NotImplementedError

    def update_incident(self, incident: Incident) -> None:
        raise NotImplementedError

    def get_incident(self, incident_id: str) -> Incident:
        raise NotImplementedError

    def save_operation(self, operation: Operation) -> None:
        raise NotImplementedError

    def update_operation(self, operation: Operation) -> None:
        raise NotImplementedError

    def get_operation(self, operation_id: str) -> Operation:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError
