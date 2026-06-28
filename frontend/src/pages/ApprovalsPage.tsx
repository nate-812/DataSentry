import { Check, Plus, X } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";

import { api } from "../api/client";
import type { Operation } from "../api/types";

export function ApprovalsPage() {
  const [operations, setOperations] = useState<Operation[]>([]);
  const [name, setName] = useState("simulate_restart_preview");
  const [requester, setRequester] = useState("operator");

  async function refresh() {
    setOperations(await api.operations().catch(() => []));
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await api.createSimulation(name.trim(), requester.trim());
    await refresh();
  }

  async function approve(id: string) {
    await api.approveOperation(id, requester || "operator");
    await refresh();
  }

  async function reject(id: string) {
    await api.rejectOperation(id, requester || "operator");
    await refresh();
  }

  return (
    <div className="page-grid">
      <section className="panel span-2">
        <div className="panel-heading">
          <h2>本地模拟审批</h2>
        </div>
        <form className="inline-form" onSubmit={create}>
          <input value={name} onChange={(event) => setName(event.target.value)} />
          <input value={requester} onChange={(event) => setRequester(event.target.value)} />
          <button type="submit" title="创建模拟操作">
            <Plus size={16} aria-hidden="true" />
            创建
          </button>
        </form>
      </section>
      <section className="panel span-2">
        <div className="panel-heading">
          <h2>Operation</h2>
          <span>{operations.length}</span>
        </div>
        <div className="table-list">
          {operations.map((operation) => (
            <div className="table-row action-row" key={operation.id}>
              <strong>{operation.name}</strong>
              <span>{operation.status}</span>
              <button type="button" title="批准模拟操作" onClick={() => approve(operation.id)}>
                <Check size={16} aria-hidden="true" />
              </button>
              <button type="button" title="拒绝模拟操作" onClick={() => reject(operation.id)}>
                <X size={16} aria-hidden="true" />
              </button>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
