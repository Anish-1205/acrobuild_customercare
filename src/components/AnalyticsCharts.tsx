import type { CountRow, TrendPoint } from "../lib/analyticsPresentation";

type AnalyticsDistributionCardProps = {
  copy: string;
  emptyCopy: string;
  rows: CountRow[];
  title: string;
};

type AnalyticsBarGraphCardProps = {
  accent: string;
  copy: string;
  emptyCopy: string;
  points: TrendPoint[];
  title: string;
};

function buildChartRows(rows: CountRow[], maxSegments = 5) {
  if (rows.length <= maxSegments) {
    return rows;
  }

  const visibleRows = rows.slice(0, maxSegments - 1);
  const otherValue = rows.slice(maxSegments - 1).reduce((sum, row) => sum + row.value, 0);

  return [
    ...visibleRows,
    {
      color: "#cbd5e1",
      label: "Other",
      value: otherValue
    }
  ];
}

function buildDonutBackground(rows: CountRow[]) {
  const total = rows.reduce((sum, row) => sum + row.value, 0);

  if (!total) {
    return "conic-gradient(#e2e8f0 0turn 1turn)";
  }

  let cursor = 0;

  return `conic-gradient(${rows
    .map((row) => {
      const start = (cursor / total) * 100;
      cursor += row.value;
      const end = (cursor / total) * 100;

      return `${row.color} ${start}% ${end}%`;
    })
    .join(", ")})`;
}

function formatPercent(value: number, total: number) {
  if (!total) {
    return 0;
  }

  return Math.round((value / total) * 100);
}

export function AnalyticsDistributionCard(props: AnalyticsDistributionCardProps) {
  const chartRows = buildChartRows(props.rows);
  const total = props.rows.reduce((sum, row) => sum + row.value, 0);
  const leadingRow = props.rows[0];

  return (
    <section className="plain-card analytics-surface analytics-chart-card">
      <div className="section-title">{props.title}</div>
      <div className="section-copy">{props.copy}</div>

      {!props.rows.length ? (
        <div className="empty-card">{props.emptyCopy}</div>
      ) : (
        <div className="analytics-distribution-shell">
          <div className="analytics-pie-column">
            <div className="analytics-pie-frame">
              <div
                className="analytics-pie-chart"
                style={{ background: buildDonutBackground(chartRows) }}
              />
            </div>
            <div className="analytics-pie-caption">
              <strong>{total} tickets</strong>
              <span>
                {leadingRow?.label} leads with {formatPercent(leadingRow?.value ?? 0, total)}%
              </span>
            </div>
          </div>

          <div className="analytics-distribution-list">
            {chartRows.map((row) => {
              const percent = formatPercent(row.value, total);

              return (
                <div className="analytics-distribution-item" key={row.label}>
                  <div className="analytics-distribution-head">
                    <span className="analytics-distribution-label">
                      <span className="badge-dot" style={{ backgroundColor: row.color }} />
                      {row.label}
                    </span>
                    <span className="analytics-distribution-value">
                      {row.value} <small>{percent}%</small>
                    </span>
                  </div>
                  <div className="analytics-distribution-track">
                    <span
                      className="analytics-distribution-fill"
                      style={{
                        background: `linear-gradient(90deg, ${row.color} 0%, ${row.color}cc 100%)`,
                        width: `${Math.max(percent, 8)}%`
                      }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </section>
  );
}

export function AnalyticsBarGraphCard(props: AnalyticsBarGraphCardProps) {
  if (!props.points.length) {
    return (
      <section className="plain-card analytics-surface analytics-chart-card">
        <div className="section-title">{props.title}</div>
        <div className="section-copy">{props.copy}</div>
        <div className="empty-card">{props.emptyCopy}</div>
      </section>
    );
  }

  const maxValue = Math.max(...props.points.map((point) => point.value), 1);
  const peakPoint = props.points.reduce((peak, point) => (point.value > peak.value ? point : peak), props.points[0]);
  const latestPoint = props.points[props.points.length - 1];

  return (
    <section className="plain-card analytics-surface analytics-chart-card analytics-bar-card">
      <div className="section-title">{props.title}</div>
      <div className="section-copy">{props.copy}</div>

      <div className="analytics-bar-shell">
        <div className="analytics-bar-summary">
          <div className="analytics-bar-stat">
            <span>Peak day</span>
            <strong>{peakPoint.value}</strong>
            <small>{peakPoint.label}</small>
          </div>
          <div className="analytics-bar-stat">
            <span>Latest</span>
            <strong>{latestPoint.value}</strong>
            <small>{latestPoint.label}</small>
          </div>
        </div>

        <div className="analytics-bar-plot">
          <div className="analytics-bar-chart">
            {props.points.map((point) => {
              const height = `${Math.max(point.value ? 18 : 8, Math.round((point.value / maxValue) * 100))}%`;

              return (
                <div className="analytics-bar-column" key={point.label}>
                  <span className="analytics-bar-value">{point.value}</span>
                  <div className="analytics-bar-track">
                    <span
                      className="analytics-bar-fill"
                      style={{
                        background: `linear-gradient(180deg, ${props.accent} 0%, ${props.accent}cc 100%)`,
                        height
                      }}
                    />
                  </div>
                  <span className="analytics-bar-label">{point.label}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
}
