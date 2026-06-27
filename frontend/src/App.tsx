import { Activity, ExternalLink, MessageSquare, ShieldCheck } from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";

import { api } from "./api/client";
import type { ChatRunResponse, ChatSession, HealthResponse, OverviewResponse } from "./api/types";

type LoadState = "loading" | "ready" | "error";

export function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [overview, setOverview] = useState<OverviewResponse | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [session, setSession] = useState<ChatSession | null>(null);
  const [question, setQuestion] = useState("为什么K线不更新");
  const [runResult, setRunResult] = useState<ChatRunResponse | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [errorText, setErrorText] = useState<string | null>(null);

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
        setLoadState("ready");
      } catch {
        if (!active) return;
        setLoadState("error");
        setErrorText("无法连接 DataSentry API");
      }
    }
    void load();
    return () => {
      active = false;
    };
  }, []);

  const statusText = useMemo(() => {
    if (loadState === "loading") return "连接中";
    if (loadState === "error") return "不可用";
    return health?.status === "ok" ? "正常" : "未知";
  }, [health?.status, loadState]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = question.trim();
    if (!trimmed || isRunning) return;
    setIsRunning(true);
    setErrorText(null);
    try {
      const activeSession = session ?? (await api.createSession("Kline 诊断"));
      setSession(activeSession);
      const result = await api.runQuestion(activeSession.id, trimmed);
      setRunResult(result);
    } catch {
      setErrorText("诊断请求失败，请检查 API 服务状态");
    } finally {
      setIsRunning(false);
    }
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">DataSentry</p>
          <h1>运维 Command Center</h1>
        </div>
        <div className="status-pill">
          <Activity size={18} aria-hidden="true" />
          <span>{statusText}</span>
        </div>
      </header>

      <section className="summary-grid" aria-label="系统概览">
        <MetricCard
          icon={<ShieldCheck size={20} aria-hidden="true" />}
          label="API"
          value={health?.environment ?? "development"}
          detail={health?.database.configured ? "SQLite 已配置" : "数据库未配置"}
        />
        <MetricCard
          icon={<MessageSquare size={20} aria-hidden="true" />}
          label="LLM"
          value={health?.llm.provider ?? "disabled"}
          detail={health?.llm.configured ? "可用于摘要" : "降级模板可用"}
        />
        <MetricCard
          icon={<Activity size={20} aria-hidden="true" />}
          label="巡检"
          value={String(overview?.recent_inspections.length ?? 0)}
          detail="最近记录"
        />
        <MetricCard
          icon={<ExternalLink size={20} aria-hidden="true" />}
          label="Grafana"
          value={overview?.grafana.url ? "已配置" : "未配置"}
          detail={overview?.grafana.url ?? "等待接入"}
        />
      </section>

      <section className="workspace">
        <div className="panel chat-panel">
          <div className="panel-heading">
            <h2>对话诊断</h2>
            <span>{session ? "会话已创建" : "新会话"}</span>
          </div>
          <form className="question-form" onSubmit={handleSubmit}>
            <textarea
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="输入要诊断的问题"
              rows={5}
            />
            <button type="submit" disabled={isRunning || !question.trim()}>
              {isRunning ? "诊断中" : "开始诊断"}
            </button>
          </form>
          {errorText ? <p className="error-text">{errorText}</p> : null}
          {runResult ? (
            <article className="answer">
              <div className="answer-meta">
                <span>{runResult.run.status}</span>
                <span>{runResult.assistant_message.llm_status ?? "unknown"}</span>
              </div>
              <p>{runResult.assistant_message.content}</p>
            </article>
          ) : null}
        </div>

        <div className="panel queue-panel">
          <div className="panel-heading">
            <h2>工作队列</h2>
            <span>本地模拟</span>
          </div>
          <QueueRow label="Incident" value={overview?.incidents.length ?? 0} />
          <QueueRow label="Operation" value={overview?.operations.length ?? 0} />
          <QueueRow label="Recent Inspection" value={overview?.recent_inspections.length ?? 0} />
        </div>
      </section>
    </main>
  );
}

function MetricCard({
  icon,
  label,
  value,
  detail
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <article className="metric-card">
      <div className="metric-icon">{icon}</div>
      <div>
        <p>{label}</p>
        <strong>{value}</strong>
        <span>{detail}</span>
      </div>
    </article>
  );
}

function QueueRow({ label, value }: { label: string; value: number }) {
  return (
    <div className="queue-row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
