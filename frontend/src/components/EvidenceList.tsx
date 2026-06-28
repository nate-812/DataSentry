export function EvidenceList({ items }: { items: Array<Record<string, unknown>> }) {
  if (items.length === 0) {
    return <p className="muted">暂无证据记录</p>;
  }
  return (
    <div className="evidence-list">
      {items.map((item, index) => (
        <pre key={index}>{JSON.stringify(item, null, 2)}</pre>
      ))}
    </div>
  );
}
