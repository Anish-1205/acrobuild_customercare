import type { ReactNode } from "react";

type WorkspaceStateMetric = {
  accent?: "amber" | "cyan" | "teal" | "violet";
  label: string;
  note: string;
  value: ReactNode;
};

type WorkspaceStatePanelProps = {
  description: string;
  eyebrow: string;
  metrics: WorkspaceStateMetric[];
  stateLabel: string;
  title: string;
  variant?: "empty" | "loading";
};

export function WorkspaceStatePanel({
  description,
  eyebrow,
  metrics,
  stateLabel,
  title,
  variant = "loading"
}: WorkspaceStatePanelProps) {
  return (
    <section className={`workspace-state-panel ${variant === "empty" ? "is-empty" : "is-loading"}`}>
      <div className="workspace-state-copy">
        <div className="workspace-state-eyebrow">{eyebrow}</div>
        <h3>{title}</h3>
        <p>{description}</p>
      </div>

      <div className="workspace-state-metric-grid">
        {metrics.map((metric) => (
          <article
            className={`workspace-state-metric${metric.accent ? ` accent-${metric.accent}` : ""}`}
            key={metric.label}
          >
            <span>{metric.label}</span>
            <strong>{metric.value}</strong>
            <small>{metric.note}</small>
          </article>
        ))}
      </div>

      <div className="workspace-state-footer">
        <div className="workspace-state-pill">{stateLabel}</div>
        <div className="workspace-state-signal" aria-hidden="true">
          <span className="signal-bar short" />
          <span className="signal-bar tall" />
          <span className="signal-bar medium" />
          <span className="signal-bar short" />
        </div>
      </div>
    </section>
  );
}
