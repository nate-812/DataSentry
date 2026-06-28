import { Download, FileText, RefreshCw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { api } from "../api/client";
import type { Incident, IncidentDetail } from "../api/types";

export function IncidentsPage() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<IncidentDetail | null>(null);
  const [similar, setSimilar] = useState<Incident[]>([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [severityFilter, setSeverityFilter] = useState("");
  const [exportPreview, setExportPreview] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void api
      .incidents()
      .then((items) => {
        setIncidents(items);
        setSelectedId(items[0]?.id ?? null);
      })
      .catch(() => setIncidents([]));
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      setSimilar([]);
      return;
    }
    void Promise.all([api.incident(selectedId), api.incidentSimilar(selectedId)])
      .then(([incidentDetail, similarIncidents]) => {
        setDetail(incidentDetail);
        setSimilar(similarIncidents);
        setExportPreview("");
        setError(null);
      })
      .catch(() => {
        setDetail(null);
        setSimilar([]);
        setError("Incident 详情读取失败");
      });
  }, [selectedId]);

  const filtered = useMemo(
    () =>
      incidents.filter(
        (incident) =>
          (!statusFilter || incident.status === statusFilter) &&
          (!severityFilter || incident.severity === severityFilter)
      ),
    [incidents, severityFilter, statusFilter]
  );

  async function refreshRca() {
    if (!selectedId) return;
    const report = await api.generateIncidentRca(selectedId);
    const incidentDetail = await api.incident(selectedId);
    setDetail(incidentDetail);
    setExportPreview(report.markdown);
  }

  async function exportMarkdown() {
    if (!selectedId) return;
    setExportPreview(await api.exportIncident(selectedId));
  }

  return (
    <div className="incident-workspace">
      <section className="panel">
        <div className="panel-heading">
          <h2>Incident</h2>
          <span>{filtered.length}/{incidents.length}</span>
        </div>
        <div className="filter-row">
          <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
            <option value="">全部状态</option>
            <option value="open">open</option>
            <option value="investigating">investigating</option>
            <option value="blocked">blocked</option>
            <option value="verifying">verifying</option>
            <option value="resolved">resolved</option>
          </select>
          <select
            value={severityFilter}
            onChange={(event) => setSeverityFilter(event.target.value)}
          >
            <option value="">全部级别</option>
            <option value="info">info</option>
            <option value="warning">warning</option>
            <option value="critical">critical</option>
          </select>
        </div>
        <div className="table-list">
          {filtered.map((incident) => (
            <button
              className={`incident-row ${selectedId === incident.id ? "selected" : ""}`}
              key={incident.id}
              type="button"
              onClick={() => setSelectedId(incident.id)}
            >
              <strong>{incident.title}</strong>
              <span>{incident.status}</span>
              <span>{incident.severity}</span>
            </button>
          ))}
          {filtered.length === 0 ? <p className="muted">暂无 Incident</p> : null}
        </div>
      </section>
      <section className="panel">
        <div className="panel-heading">
          <h2>事件详情</h2>
          <span>{detail?.incident.updated_at ?? "未选择"}</span>
        </div>
        {error ? <p className="error-text">{error}</p> : null}
        {detail ? (
          <div className="incident-detail">
            <div className="metric-row">
              <div className="metric-cell">
                <span>状态</span>
                <strong>{detail.incident.status}</strong>
              </div>
              <div className="metric-cell">
                <span>级别</span>
                <strong>{detail.incident.severity}</strong>
              </div>
              <div className="metric-cell">
                <span>Fingerprint</span>
                <strong>{detail.fingerprints[0]?.component ?? "unknown"}</strong>
              </div>
            </div>
            <p>{detail.incident.symptom}</p>
            <p className="muted">{detail.incident.root_cause ?? "根因仍在确认中"}</p>
            <div className="button-row">
              <button type="button" onClick={refreshRca} title="生成 RCA">
                <RefreshCw size={16} aria-hidden="true" />
                生成 RCA
              </button>
              <button type="button" onClick={exportMarkdown} title="导出 Markdown">
                <Download size={16} aria-hidden="true" />
                导出
              </button>
            </div>
            <h2>时间线</h2>
            <ul className="event-list">
              {detail.timeline.map((event) => (
                <li key={event.id}>
                  <strong>{event.event_type}</strong>
                  <span>{event.occurred_at}</span>
                  <p>{event.summary}</p>
                </li>
              ))}
            </ul>
            <h2>关联证据</h2>
            <ul className="compact-list">
              {detail.links.map((link) => (
                <li key={link.id}>
                  <strong>{link.kind}</strong>
                  <p>{link.summary}</p>
                  <span className="muted">{link.target_id}</span>
                </li>
              ))}
              {detail.links.length === 0 ? <li className="muted">暂无关联证据</li> : null}
            </ul>
            <h2>相似历史</h2>
            <ul className="compact-list">
              {similar.map((incident) => (
                <li key={incident.id}>
                  <strong>{incident.title}</strong>
                  <p>{incident.status} / {incident.severity}</p>
                </li>
              ))}
              {similar.length === 0 ? <li className="muted">暂无相似历史</li> : null}
            </ul>
            <h2>RCA</h2>
            <pre className="markdown-preview">
              {exportPreview || detail.latest_rca?.markdown || "尚未生成 RCA 草稿"}
            </pre>
          </div>
        ) : (
          <p className="muted">选择一个 Incident 查看事件时间线和 RCA</p>
        )}
        <FileText className="panel-watermark" size={72} aria-hidden="true" />
      </section>
    </div>
  );
}
