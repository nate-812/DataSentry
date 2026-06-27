import { useEffect, useState } from "react";

import { api } from "../api/client";
import type { Incident } from "../api/types";

export function IncidentsPage() {
  const [incidents, setIncidents] = useState<Incident[]>([]);

  useEffect(() => {
    void api.incidents().then(setIncidents).catch(() => setIncidents([]));
  }, []);

  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>Incident</h2>
        <span>{incidents.length}</span>
      </div>
      <div className="table-list">
        {incidents.map((incident) => (
          <div className="table-row" key={incident.id}>
            <strong>{incident.title}</strong>
            <span>{incident.status}</span>
            <span>{incident.severity}</span>
          </div>
        ))}
        {incidents.length === 0 ? <p className="muted">暂无 Incident</p> : null}
      </div>
    </section>
  );
}
