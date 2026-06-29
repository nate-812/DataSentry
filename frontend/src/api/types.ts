export type HealthResponse = {
  status: string;
  environment: string;
  database: { configured: boolean };
  llm: { provider: string; configured: boolean };
};

export type OverviewResponse = {
  health: { status: string };
  recent_inspections: InspectionSummary[];
  incidents: Incident[];
  operations: Operation[];
  grafana: { url: string | null };
};

export type ChatSession = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
};

export type ChatRunResponse = {
  run: { id: string; status: string; inspection_id: string | null };
  assistant_message: {
    id: string;
    role: "assistant";
    content: string;
    inspection_id: string | null;
    llm_status: string | null;
  };
};

export type ChatSessionDetail = {
  session: ChatSession;
  messages: ChatMessage[];
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  inspection_id: string | null;
  llm_status: string | null;
  created_at: string;
};

export type InspectionSummary = {
  inspection: {
    id: string;
    question: string;
    status: string;
    summary: string | null;
    started_at: string;
    finished_at: string | null;
  };
  observation_count: number;
  finding_count: number;
};

export type EvidenceResponse = {
  inspection: InspectionSummary["inspection"];
  observations: Array<Record<string, unknown>>;
  findings: Array<Record<string, unknown>>;
  tool_invocations: Array<Record<string, unknown>>;
};

export type Incident = {
  id: string;
  title: string;
  symptom: string;
  status: string;
  severity: string;
  root_cause: string | null;
  opened_at: string;
  updated_at: string;
  resolved_at: string | null;
};

export type IncidentLink = {
  id: string;
  incident_id: string;
  kind: string;
  target_id: string;
  summary: string;
  created_at: string;
};

export type IncidentTimelineEvent = {
  id: string;
  incident_id: string;
  event_type: string;
  summary: string;
  source: string;
  payload: Record<string, unknown>;
  occurred_at: string;
};

export type IncidentFingerprint = {
  id: string;
  incident_id: string;
  component: string;
  failure_type: string;
  stable_labels_hash: string;
  severity: string;
  first_seen_at: string;
  last_seen_at: string;
};

export type IncidentRCAReport = {
  id: string;
  incident_id: string;
  version: number;
  markdown: string;
  structured: Record<string, unknown>;
  generated_by: string;
  created_at: string;
};

export type IncidentDetail = {
  incident: Incident;
  links: IncidentLink[];
  timeline: IncidentTimelineEvent[];
  fingerprints: IncidentFingerprint[];
  latest_rca: IncidentRCAReport | null;
};

export type Operation = {
  id: string;
  incident_id: string | null;
  name: string;
  version: string;
  idempotency_key: string | null;
  parameters: Record<string, unknown>;
  risk: string;
  status: string;
  requester: string;
  approver: string | null;
  requested_at: string;
  approved_at: string | null;
  executed_at: string | null;
  verified_at: string | null;
  result: Record<string, unknown> | null;
};

export type Runbook = {
  name: string;
  version: string;
  title: string;
  description: string;
  risk: string;
  execution_mode: string;
  parameter_schema: Record<string, unknown>;
  precheck: Record<string, unknown>;
  postcheck: Record<string, unknown>;
  lock_key_template: string;
  idempotency_key_template: string;
  enabled: boolean;
  audit_notes: string | null;
};

export type OperationEvent = {
  id: string;
  operation_id: string;
  event_type: string;
  summary: string;
  actor: string;
  payload: Record<string, unknown>;
  created_at: string;
};

export type OperationCreatePayload = {
  runbook_name: string;
  parameters: Record<string, unknown>;
  requester: string;
  incident_id?: string | null;
};

export type AutonomyPolicy = {
  runbook_name: string;
  enabled: boolean;
  shadow_mode: boolean;
  circuit_breaker_state: "closed" | "open" | "half_open";
  min_success_rate: number;
  min_success_samples: number;
  failure_threshold: number;
};

export type AutonomyDecision = {
  status: "allowed" | "shadowed" | "blocked" | "escalated";
  reason_code: string;
  reason: string;
  runbook_name: string;
  target: string | null;
  incident_id: string | null;
  operation_id: string | null;
  window_matched: boolean;
};

export type AutonomyRunRecord = {
  id: string;
  runbook_name: string;
  target: string;
  incident_id: string | null;
  operation_id: string | null;
  decision_status: "allowed" | "shadowed" | "blocked" | "escalated";
  reason_code: string;
  reason: string;
  created_at: string;
  finished_at: string | null;
  succeeded: boolean | null;
};
