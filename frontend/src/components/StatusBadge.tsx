import { CheckCircle2, CircleAlert, Loader2 } from "lucide-react";

export type StatusTone = "ok" | "warning" | "loading";

export function StatusBadge({ label, tone }: { label: string; tone: StatusTone }) {
  const Icon = tone === "ok" ? CheckCircle2 : tone === "warning" ? CircleAlert : Loader2;
  return (
    <span className={`status-badge status-badge-${tone}`}>
      <Icon size={16} aria-hidden="true" />
      {label}
    </span>
  );
}
