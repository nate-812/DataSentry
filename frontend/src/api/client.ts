import type {
  ChatSessionDetail,
  ChatRunResponse,
  ChatSession,
  EvidenceResponse,
  HealthResponse,
  Incident,
  IncidentDetail,
  IncidentRCAReport,
  Operation,
  OverviewResponse
} from "./types";

export const API_BASE = import.meta.env.VITE_DATASENTRY_API_BASE ?? "http://127.0.0.1:8000";

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init
  });
  if (!response.ok) {
    throw new Error(`DataSentry API error ${response.status}`);
  }
  return (await response.json()) as T;
}

async function requestText(path: string): Promise<string> {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) {
    throw new Error(`DataSentry API error ${response.status}`);
  }
  return await response.text();
}

export const api = {
  health: () => requestJson<HealthResponse>("/api/health"),
  overview: () => requestJson<OverviewResponse>("/api/overview"),
  incidents: () => requestJson<Incident[]>("/api/incidents"),
  incident: (incidentId: string) => requestJson<IncidentDetail>(`/api/incidents/${incidentId}`),
  incidentSimilar: (incidentId: string) =>
    requestJson<Incident[]>(`/api/incidents/${incidentId}/similar`),
  generateIncidentRca: (incidentId: string) =>
    requestJson<IncidentRCAReport>(`/api/incidents/${incidentId}/rca`, { method: "POST" }),
  exportIncident: (incidentId: string) => requestText(`/api/incidents/${incidentId}/export`),
  operations: () => requestJson<Operation[]>("/api/operations"),
  evidence: (inspectionId: string) =>
    requestJson<EvidenceResponse>(`/api/evidence/inspections/${inspectionId}`),
  createSession: (title: string) =>
    requestJson<ChatSession>("/api/chat/sessions", {
      method: "POST",
      body: JSON.stringify({ title })
    }),
  session: (sessionId: string) =>
    requestJson<ChatSessionDetail>(`/api/chat/sessions/${sessionId}`),
  runQuestion: (sessionId: string, question: string) =>
    requestJson<ChatRunResponse>(`/api/chat/sessions/${sessionId}/runs`, {
      method: "POST",
      body: JSON.stringify({ question })
    }),
  runEvents: (runId: string) => requestText(`/api/chat/runs/${runId}/events`),
  createSimulation: (name: string, requester: string) =>
    requestJson<Operation>("/api/operations/simulations", {
      method: "POST",
      body: JSON.stringify({ name, requester })
    }),
  approveOperation: (operationId: string, approver: string) =>
    requestJson<Operation>(`/api/operations/${operationId}/approve`, {
      method: "POST",
      body: JSON.stringify({ approver })
    }),
  rejectOperation: (operationId: string, approver: string) =>
    requestJson<Operation>(`/api/operations/${operationId}/reject`, {
      method: "POST",
      body: JSON.stringify({ approver })
    })
};
