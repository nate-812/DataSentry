import { Search } from "lucide-react";
import { FormEvent, useState } from "react";

import { api } from "../api/client";
import type { EvidenceResponse } from "../api/types";
import { EvidenceList } from "../components/EvidenceList";

export function EvidencePage() {
  const [inspectionId, setInspectionId] = useState("");
  const [evidence, setEvidence] = useState<EvidenceResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!inspectionId.trim()) return;
    try {
      setEvidence(await api.evidence(inspectionId.trim()));
      setError(null);
    } catch {
      setError("未找到巡检证据");
      setEvidence(null);
    }
  }

  return (
    <div className="page-grid">
      <section className="panel span-2">
        <div className="panel-heading">
          <h2>证据查询</h2>
        </div>
        <form className="inline-form" onSubmit={submit}>
          <input
            value={inspectionId}
            onChange={(event) => setInspectionId(event.target.value)}
            placeholder="Inspection ID"
          />
          <button type="submit" title="查询证据">
            <Search size={16} aria-hidden="true" />
            查询
          </button>
        </form>
        {error ? <p className="error-text">{error}</p> : null}
      </section>
      <section className="panel span-2">
        <div className="panel-heading">
          <h2>Finding</h2>
          <span>{evidence?.findings.length ?? 0}</span>
        </div>
        <EvidenceList items={evidence?.findings ?? []} />
      </section>
    </div>
  );
}
