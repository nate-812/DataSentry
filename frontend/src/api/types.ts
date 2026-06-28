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
  name: string;
  status: string;
  requester: string;
  approver: string | null;
  requested_at: string;
  result: Record<string, unknown> | null;
};
