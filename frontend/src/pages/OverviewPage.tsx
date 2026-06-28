import { ExternalLink } from "lucide-react";

import type { HealthResponse, OverviewResponse } from "../api/types";
import { StatusBadge } from "../components/StatusBadge";

export function OverviewPage({
  health,
  overview
}: {
  health: HealthResponse | null;
  overview: OverviewResponse | null;
}) {
  return (
    <div className="page-grid">
      <section className="panel span-2">
        <div className="panel-heading">
          <h2>运行状态</h2>
          <StatusBadge label={health?.status ?? "loading"} tone={health ? "ok" : "loading"} />
        </div>
        <div className="metric-row">
          <Metric label="环境" value={health?.environment ?? "-"} />
          <Metric label="LLM" value={health?.llm.provider ?? "-"} />
          <Metric label="数据库" value={health?.database.configured ? "已配置" : "未确认"} />
        </div>
      </section>

      <section className="panel">
        <div className="panel-heading">
          <h2>巡检</h2>
          <span>{overview?.recent_inspections.length ?? 0}</span>
        </div>
        <List values={overview?.recent_inspections.map((item) => item.inspection.question) ?? []} />
      </section>

      <section className="panel">
        <div className="panel-heading">
          <h2>Incident</h2>
          <span>{overview?.incidents.length ?? 0}</span>
        </div>
        <List values={overview?.incidents.map((item) => item.title) ?? []} />
      </section>

      <section className="panel">
        <div className="panel-heading">
          <h2>Operation</h2>
          <span>{overview?.operations.length ?? 0}</span>
        </div>
        <List values={overview?.operations.map((item) => `${item.name} · ${item.status}`) ?? []} />
      </section>

      <section className="panel">
        <div className="panel-heading">
          <h2>Grafana</h2>
          <ExternalLink size={18} aria-hidden="true" />
        </div>
        <p className="muted">{overview?.grafana.url ?? "未配置 Grafana URL"}</p>
      </section>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric-cell">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function List({ values }: { values: string[] }) {
  if (values.length === 0) return <p className="muted">暂无记录</p>;
  return (
    <ul className="compact-list">
      {values.slice(0, 6).map((value, index) => (
        <li key={`${value}-${index}`}>{value}</li>
      ))}
    </ul>
  );
}
