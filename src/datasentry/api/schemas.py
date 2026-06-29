"""M4 API 的公开请求和响应模型。"""

from pydantic import BaseModel, Field, JsonValue


class DatabaseHealth(BaseModel):
    configured: bool


class LLMHealth(BaseModel):
    provider: str
    configured: bool


class HealthResponse(BaseModel):
    status: str
    environment: str
    database: DatabaseHealth
    llm: LLMHealth


class GrafanaLink(BaseModel):
    url: str | None


class OverviewResponse(BaseModel):
    health: dict[str, object]
    recent_inspections: list[dict[str, object]]
    incidents: list[dict[str, object]]
    operations: list[dict[str, object]]
    grafana: GrafanaLink


class OperationSimulationRequest(BaseModel):
    name: str = Field(min_length=1)
    requester: str = Field(min_length=1)


class OperationActionRequest(BaseModel):
    approver: str = Field(min_length=1)


class OperationCreateRequest(BaseModel):
    runbook_name: str = Field(min_length=1)
    parameters: dict[str, JsonValue] = Field(default_factory=dict)
    requester: str = Field(min_length=1)
    incident_id: str | None = None


class OperationExecuteRequest(BaseModel):
    actor: str = Field(min_length=1)


class OperationCancelRequest(BaseModel):
    actor: str = Field(min_length=1)


class AutonomyCandidateRequest(BaseModel):
    runbook_name: str = Field(min_length=1)
    parameters: dict[str, JsonValue] = Field(default_factory=dict)
    incident_id: str | None = None


class AutonomyPolicyUpdateRequest(BaseModel):
    enabled: bool | None = None
    shadow_mode: bool | None = None


class ChatSessionCreateRequest(BaseModel):
    title: str = Field(min_length=1)


class ChatRunCreateRequest(BaseModel):
    question: str = Field(min_length=1)


class AlertmanagerIncidentResponse(BaseModel):
    accepted: bool
    incident_id: str
    action: str
    status: str
    deduplication_key: str
    diagnosis_question: str


class IncidentDetailResponse(BaseModel):
    incident: dict[str, object]
    links: list[dict[str, object]]
    timeline: list[dict[str, object]]
    fingerprints: list[dict[str, object]]
    latest_rca: dict[str, object] | None


class IncidentRCAResponse(BaseModel):
    id: str
    incident_id: str
    version: int
    markdown: str
    structured: dict[str, object]
    generated_by: str
    created_at: str
