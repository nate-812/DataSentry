"""应用 Service 使用的存储抽象。"""

from dataclasses import dataclass
from typing import Protocol

from datasentry.chat import ChatMessage, ChatRun, ChatSession
from datasentry.domain import (
    Finding,
    Incident,
    Inspection,
    Observation,
    Operation,
    ToolInvocation,
)
from datasentry.domain.enums import IncidentStatus, OperationStatus


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

    def list_inspections(self, limit: int = 20) -> list[InspectionAggregate]:
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

    def list_incidents(
        self,
        *,
        status: IncidentStatus | None = None,
        limit: int = 20,
    ) -> list[Incident]:
        raise NotImplementedError  # pragma: no cover

    def save_operation(self, operation: Operation) -> None:
        raise NotImplementedError  # pragma: no cover

    def update_operation(self, operation: Operation) -> None:
        raise NotImplementedError  # pragma: no cover

    def get_operation(self, operation_id: str) -> Operation:
        raise NotImplementedError  # pragma: no cover

    def list_operations(
        self,
        *,
        status: OperationStatus | None = None,
        limit: int = 20,
    ) -> list[Operation]:
        raise NotImplementedError  # pragma: no cover

    def save_chat_session(self, session: ChatSession) -> None:
        raise NotImplementedError  # pragma: no cover

    def get_chat_session(self, session_id: str) -> ChatSession:
        raise NotImplementedError  # pragma: no cover

    def list_chat_sessions(self, limit: int = 20) -> list[ChatSession]:
        raise NotImplementedError  # pragma: no cover

    def save_chat_message(self, message: ChatMessage) -> None:
        raise NotImplementedError  # pragma: no cover

    def list_chat_messages(self, session_id: str, limit: int = 20) -> list[ChatMessage]:
        raise NotImplementedError  # pragma: no cover

    def save_chat_run(self, run: ChatRun) -> None:
        raise NotImplementedError  # pragma: no cover

    def update_chat_run(self, run: ChatRun) -> None:
        raise NotImplementedError  # pragma: no cover

    def get_chat_run(self, run_id: str) -> ChatRun:
        raise NotImplementedError  # pragma: no cover

    def save_chat_run_event(self, event: ChatRun.Event) -> None:
        raise NotImplementedError  # pragma: no cover

    def list_chat_run_events(self, run_id: str, limit: int = 100) -> list[ChatRun.Event]:
        raise NotImplementedError  # pragma: no cover

    def close(self) -> None:
        raise NotImplementedError  # pragma: no cover
