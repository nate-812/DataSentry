import {
  Activity,
  BarChart3,
  ClipboardCheck,
  DatabaseZap,
  FileWarning,
  MessageSquare
} from "lucide-react";
import type { ReactNode } from "react";

import { StatusBadge } from "./StatusBadge";

export type PageKey = "overview" | "chat" | "incidents" | "evidence" | "approvals" | "grafana";

const navItems: Array<{ key: PageKey; label: string; icon: ReactNode }> = [
  { key: "overview", label: "概览", icon: <Activity size={18} aria-hidden="true" /> },
  { key: "chat", label: "对话", icon: <MessageSquare size={18} aria-hidden="true" /> },
  { key: "incidents", label: "Incident", icon: <FileWarning size={18} aria-hidden="true" /> },
  { key: "evidence", label: "证据", icon: <DatabaseZap size={18} aria-hidden="true" /> },
  { key: "approvals", label: "审批", icon: <ClipboardCheck size={18} aria-hidden="true" /> },
  { key: "grafana", label: "Grafana", icon: <BarChart3 size={18} aria-hidden="true" /> }
];

export function Layout({
  activePage,
  apiStatus,
  llmStatus,
  onNavigate,
  children
}: {
  activePage: PageKey;
  apiStatus: string;
  llmStatus: string;
  onNavigate: (page: PageKey) => void;
  children: ReactNode;
}) {
  return (
    <main className="console-shell">
      <aside className="nav-rail" aria-label="主导航">
        <div className="brand-block">
          <span>DS</span>
          <strong>DataSentry</strong>
        </div>
        <nav>
          {navItems.map((item) => (
            <button
              className={activePage === item.key ? "nav-button active" : "nav-button"}
              key={item.key}
              onClick={() => onNavigate(item.key)}
              title={item.label}
              type="button"
            >
              {item.icon}
              <span>{item.label}</span>
            </button>
          ))}
        </nav>
      </aside>
      <section className="console-main">
        <header className="status-strip">
          <div>
            <p className="eyebrow">Command Center</p>
            <h1>StreamLake 诊断控制台</h1>
          </div>
          <div className="status-group">
            <StatusBadge label={`API ${apiStatus}`} tone={apiStatus === "ok" ? "ok" : "warning"} />
            <StatusBadge label={`LLM ${llmStatus}`} tone="ok" />
          </div>
        </header>
        {children}
      </section>
    </main>
  );
}
