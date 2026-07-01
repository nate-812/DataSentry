import { Ban, Check, Gauge, Play, Plus, RefreshCw, RotateCcw, X } from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";

import { api } from "../api/client";
import type {
  AutonomyDecision,
  AutonomyPolicy,
  AutonomyRunRecord,
  AutonomyStats,
  Operation,
  OperationEvent,
  Runbook
} from "../api/types";

export function ApprovalsPage() {
  const [runbooks, setRunbooks] = useState<Runbook[]>([]);
  const [operations, setOperations] = useState<Operation[]>([]);
  const [events, setEvents] = useState<OperationEvent[]>([]);
  const [autonomyPolicies, setAutonomyPolicies] = useState<AutonomyPolicy[]>([]);
  const [autonomyRuns, setAutonomyRuns] = useState<AutonomyRunRecord[]>([]);
  const [autonomyStats, setAutonomyStats] = useState<AutonomyStats[]>([]);
  const [autonomyDecision, setAutonomyDecision] = useState<AutonomyDecision | null>(null);
  const [runbookName, setRunbookName] = useState("");
  const [target, setTarget] = useState("api-server");
  const [reason, setReason] = useState("本地 M6 审批演练");
  const [incidentId, setIncidentId] = useState("");
  const [actor, setActor] = useState("operator");
  const [selectedOperationId, setSelectedOperationId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedRunbook = useMemo(
    () => runbooks.find((runbook) => runbook.name === runbookName) ?? null,
    [runbookName, runbooks]
  );
  const selectedOperation = useMemo(
    () => operations.find((operation) => operation.id === selectedOperationId) ?? null,
    [operations, selectedOperationId]
  );
  const statsByRunbook = useMemo(
    () => new Map(autonomyStats.map((stats) => [stats.runbook_name, stats])),
    [autonomyStats]
  );

  async function refreshOperations(nextSelectedId?: string | null) {
    const items = await api.operations();
    setOperations(items);
    setSelectedOperationId((current) => nextSelectedId ?? current ?? items[0]?.id ?? null);
  }

  async function refreshOperationEvents(operationId: string | null) {
    if (!operationId) {
      setEvents([]);
      return;
    }
    setEvents(await api.operationEvents(operationId));
  }

  async function refreshAutonomy() {
    const [policies, runs, stats] = await Promise.all([
      api.autonomyPolicies(),
      api.autonomyRuns(),
      api.autonomyStats()
    ]);
    setAutonomyPolicies(policies);
    setAutonomyRuns(runs);
    setAutonomyStats(stats);
  }

  async function refreshAll() {
    const [runbookItems, operationItems, policies, runs, stats] = await Promise.all([
      api.runbooks(),
      api.operations(),
      api.autonomyPolicies(),
      api.autonomyRuns(),
      api.autonomyStats()
    ]);
    setRunbooks(runbookItems);
    setOperations(operationItems);
    setAutonomyPolicies(policies);
    setAutonomyRuns(runs);
    setAutonomyStats(stats);
    setRunbookName((current) => current || runbookItems.find((item) => item.enabled)?.name || "");
    setSelectedOperationId((current) => current ?? operationItems[0]?.id ?? null);
  }

  useEffect(() => {
    void refreshAll().catch(() => setError("Runbook 控制台读取失败"));
  }, []);

  useEffect(() => {
    if (!selectedOperationId) {
      setEvents([]);
      return;
    }
    void api
      .operationEvents(selectedOperationId)
      .then((items) => {
        setEvents(items);
        setError(null);
      })
      .catch(() => {
        setEvents([]);
        setError("Operation 审计事件读取失败");
      });
  }, [selectedOperationId]);

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await runAction(async () => {
      const parameters: Record<string, unknown> = {
        target: target.trim(),
        reason: reason.trim()
      };
      const cleanIncidentId = incidentId.trim();
      const created = await api.createOperation({
        runbook_name: runbookName,
        parameters,
        requester: actor.trim() || "operator",
        incident_id: cleanIncidentId || null
      });
      await refreshOperations(created.id);
      await refreshOperationEvents(created.id);
    });
  }

  async function approve(operationId: string) {
    await runAction(async () => {
      const updated = await api.approveOperation(operationId, actor.trim() || "operator");
      await refreshOperations(updated.id);
      await refreshOperationEvents(updated.id);
    });
  }

  async function reject(operationId: string) {
    await runAction(async () => {
      const updated = await api.rejectOperation(operationId, actor.trim() || "operator");
      await refreshOperations(updated.id);
      await refreshOperationEvents(updated.id);
    });
  }

  async function execute(operationId: string) {
    await runAction(async () => {
      const updated = await api.executeOperation(operationId, actor.trim() || "operator");
      await refreshOperations(updated.id);
      await refreshOperationEvents(updated.id);
    });
  }

  async function cancel(operationId: string) {
    await runAction(async () => {
      const updated = await api.cancelOperation(operationId, actor.trim() || "operator");
      await refreshOperations(updated.id);
      await refreshOperationEvents(updated.id);
    });
  }

  async function updateAutonomyPolicy(
    runbookName: string,
    payload: { enabled?: boolean; shadow_mode?: boolean }
  ) {
    await runAction(async () => {
      await api.updateAutonomyPolicy(runbookName, payload);
      await refreshAutonomy();
    });
  }

  async function executeAutonomy(runbookName: string) {
    await runAction(async () => {
      const cleanIncidentId = incidentId.trim();
      const decision = await api.executeAutonomyCandidate({
        runbook_name: runbookName,
        parameters: {
          target: target.trim(),
          reason: reason.trim() || "本地 M7 自治演练"
        },
        incident_id: cleanIncidentId || null
      });
      setAutonomyDecision(decision);
      await refreshAutonomy();
      if (decision.operation_id) {
        await refreshOperations(decision.operation_id);
        await refreshOperationEvents(decision.operation_id);
      }
    });
  }

  async function halfOpenCircuitBreaker(runbookName: string) {
    await runAction(async () => {
      await api.halfOpenAutonomyCircuitBreaker(runbookName);
      await refreshAutonomy();
    });
  }

  async function resetCircuitBreaker(runbookName: string) {
    await runAction(async () => {
      await api.resetAutonomyCircuitBreaker(runbookName);
      await refreshAutonomy();
    });
  }

  async function runAction(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch {
      setError("Operation 动作执行失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="runbook-workspace">
      <section className="panel">
        <div className="panel-heading">
          <h2>Runbook</h2>
          <button type="button" title="刷新" onClick={() => void refreshAll()} disabled={busy}>
            <RefreshCw size={16} aria-hidden="true" />
          </button>
        </div>
        <form className="runbook-form" onSubmit={create}>
          <select value={runbookName} onChange={(event) => setRunbookName(event.target.value)}>
            {runbooks.map((runbook) => (
              <option value={runbook.name} key={runbook.name} disabled={!runbook.enabled}>
                {runbook.title}
              </option>
            ))}
          </select>
          <input
            aria-label="目标"
            value={target}
            onChange={(event) => setTarget(event.target.value)}
            placeholder="target"
          />
          <input
            aria-label="原因"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="reason"
          />
          <input
            aria-label="Incident ID"
            value={incidentId}
            onChange={(event) => setIncidentId(event.target.value)}
            placeholder="incident_id"
          />
          <input
            aria-label="操作者"
            value={actor}
            onChange={(event) => setActor(event.target.value)}
            placeholder="operator"
          />
          <button type="submit" title="创建 Operation" disabled={busy || !selectedRunbook?.enabled}>
            <Plus size={16} aria-hidden="true" />
            创建
          </button>
        </form>
        {selectedRunbook ? (
          <div className="runbook-summary">
            <strong>{selectedRunbook.name}</strong>
            <span>{selectedRunbook.risk} / {selectedRunbook.execution_mode}</span>
            <p>{selectedRunbook.description}</p>
          </div>
        ) : null}
        {error ? <p className="error-text">{error}</p> : null}
      </section>

      <section className="panel autonomy-panel">
        <div className="panel-heading">
          <h2>有限自治</h2>
          <button type="button" title="刷新自治" onClick={() => void refreshAutonomy()} disabled={busy}>
            <RefreshCw size={16} aria-hidden="true" />
          </button>
        </div>
        <div className="autonomy-grid">
          {autonomyPolicies.map((policy) => {
            const stats = statsByRunbook.get(policy.runbook_name);
            return (
              <article className="autonomy-row" key={policy.runbook_name}>
                <div>
                  <strong>{policy.runbook_name}</strong>
                  <span>{policy.circuit_breaker_state}</span>
                </div>
                <label>
                  <input
                    type="checkbox"
                    checked={policy.enabled}
                    onChange={(event) =>
                      void updateAutonomyPolicy(policy.runbook_name, {
                        enabled: event.target.checked
                      })
                    }
                  />
                  启用
                </label>
                <label>
                  <input
                    type="checkbox"
                    checked={policy.shadow_mode}
                    onChange={(event) =>
                      void updateAutonomyPolicy(policy.runbook_name, {
                        shadow_mode: event.target.checked
                      })
                    }
                  />
                  Shadow
                </label>
                <div className="autonomy-actions">
                  <button
                    type="button"
                    title="演练"
                    disabled={busy}
                    onClick={() => void executeAutonomy(policy.runbook_name)}
                  >
                    <Play size={16} aria-hidden="true" />
                  </button>
                  <button
                    type="button"
                    title="半开"
                    disabled={busy}
                    onClick={() => void halfOpenCircuitBreaker(policy.runbook_name)}
                  >
                    <Gauge size={16} aria-hidden="true" />
                  </button>
                  <button
                    type="button"
                    title="重置熔断"
                    disabled={busy}
                    onClick={() => void resetCircuitBreaker(policy.runbook_name)}
                  >
                    <RotateCcw size={16} aria-hidden="true" />
                  </button>
                </div>
                <div className="autonomy-stats">
                  <Metric label="成功率" value={formatRate(stats?.success_rate ?? null)} />
                  <Metric
                    label="样本"
                    value={`${stats?.allowed_runs ?? 0}/${policy.min_success_samples}`}
                  />
                  <Metric label="Shadow" value={String(stats?.shadowed_runs ?? 0)} />
                  <Metric label="升级" value={String(stats?.escalated_runs ?? 0)} />
                  <Metric
                    label="准入"
                    value={stats?.ready_for_autonomy ? "ready" : "collecting"}
                  />
                </div>
              </article>
            );
          })}
        </div>
        {autonomyDecision ? (
          <div className={`decision-banner decision-${autonomyDecision.status}`}>
            <strong>{autonomyDecision.status}</strong>
            <span>{autonomyDecision.reason}</span>
          </div>
        ) : null}
        <div className="decision-list">
          {autonomyRuns.slice(0, 5).map((run) => (
            <div className="decision-row" key={run.id}>
              <span>{run.decision_status}</span>
              <strong>{run.runbook_name}</strong>
              <small>{run.reason}</small>
            </div>
          ))}
          {autonomyRuns.length === 0 ? <p className="muted">暂无自治决策</p> : null}
        </div>
      </section>

      <section className="panel">
        <div className="panel-heading">
          <h2>Operation</h2>
          <span>{operations.length}</span>
        </div>
        <div className="operation-list">
          {operations.map((operation) => (
            <button
              className={`operation-row ${selectedOperationId === operation.id ? "selected" : ""}`}
              key={operation.id}
              type="button"
              onClick={() => setSelectedOperationId(operation.id)}
            >
              <strong>{operation.name}</strong>
              <span>{operation.status}</span>
              <span>{operation.risk}</span>
              <span>{formatTime(operation.requested_at)}</span>
            </button>
          ))}
          {operations.length === 0 ? <p className="muted">暂无 Operation</p> : null}
        </div>
      </section>

      <section className="panel span-2">
        <div className="panel-heading">
          <h2>执行链路</h2>
          <span>{selectedOperation?.id ?? "未选择"}</span>
        </div>
        {selectedOperation ? (
          <div className="runbook-detail">
            <div className="metric-row">
              <Metric label="状态" value={selectedOperation.status} />
              <Metric label="申请人" value={selectedOperation.requester} />
              <Metric label="批准人" value={selectedOperation.approver ?? "-"} />
            </div>
            <div className="button-row">
              <button
                type="button"
                title="批准"
                disabled={busy || selectedOperation.status !== "awaiting_approval"}
                onClick={() => void approve(selectedOperation.id)}
              >
                <Check size={16} aria-hidden="true" />
                批准
              </button>
              <button
                type="button"
                title="执行"
                disabled={busy || selectedOperation.status !== "approved"}
                onClick={() => void execute(selectedOperation.id)}
              >
                <Play size={16} aria-hidden="true" />
                执行
              </button>
              <button
                type="button"
                title="拒绝"
                disabled={busy || selectedOperation.status !== "awaiting_approval"}
                onClick={() => void reject(selectedOperation.id)}
              >
                <X size={16} aria-hidden="true" />
                拒绝
              </button>
              <button
                type="button"
                title="取消"
                disabled={busy || selectedOperation.status !== "awaiting_approval"}
                onClick={() => void cancel(selectedOperation.id)}
              >
                <Ban size={16} aria-hidden="true" />
                取消
              </button>
            </div>
            <pre className="operation-payload">
              {JSON.stringify(
                {
                  parameters: selectedOperation.parameters,
                  result: selectedOperation.result
                },
                null,
                2
              )}
            </pre>
            <h2>审计事件</h2>
            <ul className="event-list">
              {events.map((event) => (
                <li key={event.id}>
                  <strong>{event.event_type}</strong>
                  <span>{formatTime(event.created_at)} / {event.actor}</span>
                  <p>{event.summary}</p>
                </li>
              ))}
              {events.length === 0 ? <li className="muted">暂无审计事件</li> : null}
            </ul>
          </div>
        ) : (
          <p className="muted">暂无 Operation</p>
        )}
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

function formatTime(value: string | null) {
  if (!value) return "-";
  return new Date(value).toLocaleString();
}

function formatRate(value: number | null) {
  if (value === null) return "-";
  return `${Math.round(value * 100)}%`;
}
