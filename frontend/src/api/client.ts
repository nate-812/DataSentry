import type {
  ChatRunResponse,
  ChatSession,
  HealthResponse,
  OverviewResponse
} from "./types";

const API_BASE = import.meta.env.VITE_DATASENTRY_API_BASE ?? "http://127.0.0.1:8000";

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

export const api = {
  health: () => requestJson<HealthResponse>("/api/health"),
  overview: () => requestJson<OverviewResponse>("/api/overview"),
  createSession: (title: string) =>
    requestJson<ChatSession>("/api/chat/sessions", {
      method: "POST",
      body: JSON.stringify({ title })
    }),
  runQuestion: (sessionId: string, question: string) =>
    requestJson<ChatRunResponse>(`/api/chat/sessions/${sessionId}/runs`, {
      method: "POST",
      body: JSON.stringify({ question })
    })
};
