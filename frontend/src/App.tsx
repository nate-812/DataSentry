import { useEffect, useMemo, useState } from "react";

import { api } from "./api/client";
import type { HealthResponse, OverviewResponse } from "./api/types";
import { Layout, type PageKey } from "./components/Layout";
import { ApprovalsPage } from "./pages/ApprovalsPage";
import { ChatPage } from "./pages/ChatPage";
import { EvidencePage } from "./pages/EvidencePage";
import { GrafanaPage } from "./pages/GrafanaPage";
import { IncidentsPage } from "./pages/IncidentsPage";
import { OverviewPage } from "./pages/OverviewPage";

export function App() {
  const [activePage, setActivePage] = useState<PageKey>("overview");
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [overview, setOverview] = useState<OverviewResponse | null>(null);
  const [apiStatus, setApiStatus] = useState("loading");

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const [healthResponse, overviewResponse] = await Promise.all([
          api.health(),
          api.overview()
        ]);
        if (!active) return;
        setHealth(healthResponse);
        setOverview(overviewResponse);
        setApiStatus(healthResponse.status);
      } catch {
        if (!active) return;
        setApiStatus("error");
      }
    }
    void load();
    return () => {
      active = false;
    };
  }, []);

  const content = useMemo(() => {
    switch (activePage) {
      case "chat":
        return <ChatPage />;
      case "incidents":
        return <IncidentsPage />;
      case "evidence":
        return <EvidencePage />;
      case "approvals":
        return <ApprovalsPage />;
      case "grafana":
        return <GrafanaPage url={overview?.grafana.url} />;
      case "overview":
      default:
        return <OverviewPage health={health} overview={overview} />;
    }
  }, [activePage, health, overview]);

  return (
    <Layout
      activePage={activePage}
      apiStatus={apiStatus}
      llmStatus={health?.llm.provider ?? "unknown"}
      onNavigate={setActivePage}
    >
      {content}
    </Layout>
  );
}
