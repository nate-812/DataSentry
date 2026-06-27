import { ExternalLink } from "lucide-react";

export function GrafanaPage({ url }: { url: string | null | undefined }) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>Grafana</h2>
        {url ? <span>已配置</span> : <span>未配置</span>}
      </div>
      {url ? (
        <>
          <a className="link-button" href={url} target="_blank" rel="noreferrer" title="打开 Grafana">
            <ExternalLink size={16} aria-hidden="true" />
            打开 Grafana
          </a>
          <iframe title="Grafana dashboard" className="grafana-frame" src={url} />
        </>
      ) : (
        <p className="muted">设置 DATASENTRY_GRAFANA_URL 后可从这里打开看板。</p>
      )}
    </section>
  );
}
