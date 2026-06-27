export type HealthResponse = {
  status: string;
  environment: string;
  database: { configured: boolean };
  llm: { provider: string; configured: boolean };
};

export type OverviewResponse = {
  health: { status: string };
  recent_inspections: unknown[];
  incidents: unknown[];
  operations: unknown[];
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
