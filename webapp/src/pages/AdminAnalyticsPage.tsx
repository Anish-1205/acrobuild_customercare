import { useDeferredValue, useEffect, useState } from "react";
import {
  AnalyticsBarGraphCard,
  AnalyticsDistributionCard,
} from "../components/AnalyticsCharts";
import { WorkspaceStatePanel } from "../components/WorkspaceStatePanel";
import { getAdminTickets } from "../lib/api";
import {
  buildOptions,
  createCountRows,
  createTicketTrendPoints
} from "../lib/analyticsPresentation";
import {
  buildTicketSearchBlob,
  formatTicketTimestamp,
  getPriorityColor,
  getStatusColor,
  isActiveTicketStatus,
  sortTicketsByRecent
} from "../lib/ticketPresentation";
import type { Ticket } from "../types";

type FilterState = {
  priority: string;
  queue: string;
  search: string;
  status: string;
};

const defaultFilters: FilterState = {
  priority: "All",
  queue: "All",
  search: "",
  status: "All"
};

type AdminAnalyticsPageProps = {
  embedded?: boolean;
};

export function AdminAnalyticsPage({ embedded = false }: AdminAnalyticsPageProps) {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [filters, setFilters] = useState<FilterState>(defaultFilters);
  const [isLoading, setIsLoading] = useState(true);
  const [isWorking, setIsWorking] = useState(false);
  const [error, setError] = useState("");
  const deferredSearch = useDeferredValue(filters.search);

  async function loadTickets() {
    const response = await getAdminTickets();
    setTickets([...response.tickets].sort(sortTicketsByRecent));
  }

  useEffect(() => {
    let cancelled = false;

    async function hydrate() {
      try {
        setIsLoading(true);
        setError("");
        const response = await getAdminTickets();

        if (!cancelled) {
          setTickets([...response.tickets].sort(sortTicketsByRecent));
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : "Unable to load analytics.");
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    }

    void hydrate();

    return () => {
      cancelled = true;
    };
  }, []);

  const filteredTickets = tickets.filter((ticket) => {
    if (deferredSearch.trim() && !buildTicketSearchBlob(ticket).includes(deferredSearch.trim().toLowerCase())) {
      return false;
    }

    if (filters.status !== "All" && ticket.status !== filters.status) {
      return false;
    }

    if (filters.priority !== "All" && ticket.priority !== filters.priority) {
      return false;
    }

    if (filters.queue !== "All" && ticket.queue_name !== filters.queue) {
      return false;
    }

    return true;
  });

  const totalTickets = filteredTickets.length;
  const activeQueueCount = filteredTickets.filter((ticket) => isActiveTicketStatus(ticket.status)).length;
  const highPriorityCount = filteredTickets.filter((ticket) => ticket.priority === "High").length;
  const waitingOnCustomerCount = filteredTickets.filter((ticket) => ticket.status === "Waiting on Customer").length;
  const trendPoints = createTicketTrendPoints(filteredTickets, "updated_at");
  const queueRows = createCountRows(filteredTickets, (ticket) => ticket.queue_name, () => "#14b8a6").slice(0, 6);
  const statusRows = createCountRows(filteredTickets, (ticket) => ticket.status, getStatusColor);
  const agentRows = createCountRows(filteredTickets, (ticket) => ticket.assigned_agent, () => "#38bdf8").slice(0, 5);
  const recentTickets = [...filteredTickets].sort(sortTicketsByRecent).slice(0, 8);
  const priorityTickets = [...filteredTickets]
    .filter((ticket) => ticket.priority === "High" || ticket.status === "Waiting on Customer")
    .sort(sortTicketsByRecent)
    .slice(0, 5);
  const availableOptions = {
    priorities: buildOptions(tickets, "priority"),
    queues: buildOptions(tickets, "queue_name"),
    statuses: buildOptions(tickets, "status")
  };

  async function handleRefresh() {
    try {
      setIsWorking(true);
      setError("");
      await loadTickets();
    } catch (refreshError) {
      setError(refreshError instanceof Error ? refreshError.message : "Unable to refresh analytics.");
    } finally {
      setIsWorking(false);
    }
  }

  return (
    <div className="stack-page">
      {!embedded ? (
        <section className="hero-card compact">
          <div className="hero-kicker">Operations Dashboard</div>
          <h2>Analytics</h2>
          <p>Focus on queue health, ticket pressure, and the highest-priority work without the old cluttered side panels.</p>
        </section>
      ) : null}

      {error ? <div className="banner-error">{error}</div> : null}

      {isLoading ? (
        <WorkspaceStatePanel
          description="We are pulling the latest ticket volume, queue movement, and priority signals for the team."
          eyebrow="Analytics workspace"
          metrics={[
            {
              accent: "cyan",
              label: "Status mix",
              note: "Refreshing active queue distribution",
              value: "..."
            },
            {
              accent: "teal",
              label: "Agent load",
              note: "Checking current ownership balance",
              value: "..."
            },
            {
              accent: "amber",
              label: "Trend line",
              note: "Preparing the latest seven-day movement",
              value: "..."
            }
          ]}
          stateLabel="Syncing queue signals"
          title="Loading analytics workspace"
        />
      ) : !tickets.length ? (
        <WorkspaceStatePanel
          description="Once tickets start coming in, this page will show queue pressure, trend lines, and workload balance."
          eyebrow="Analytics workspace"
          metrics={[
            {
              accent: "cyan",
              label: "Tracked queues",
              note: "Ready to split volume by support lane",
              value: "0"
            },
            {
              accent: "violet",
              label: "Agent coverage",
              note: "Workload cards appear with the first assignment",
              value: "0"
            },
            {
              accent: "amber",
              label: "Priority watch",
              note: "High-priority alerts will appear here",
              value: "0"
            }
          ]}
          stateLabel="Waiting for first ticket activity"
          title="No tickets are available yet"
          variant="empty"
        />
      ) : (
        <div className="analytics-modern-shell">
          <section className="plain-card analytics-toolbar-card">
            <div className="workspace-detail-topbar">
              <div>
                <div className="workspace-detail-kicker">Queue analytics</div>
                <div className="section-title">Live queue overview</div>
                <div className="section-copy">Filter the queue by status, priority, or team and keep the page focused on the current workload.</div>
              </div>

              <div className="workspace-detail-actions">
                <button className="ghost-button" disabled={isWorking} onClick={() => void handleRefresh()} type="button">
                  Refresh
                </button>
                <button className="ghost-button" onClick={() => setFilters(defaultFilters)} type="button">
                  Clear filters
                </button>
              </div>
            </div>

            <div className="analytics-toolbar-grid">
              <label className="field-block">
                <span>Search tickets</span>
                <input
                  className="field-input"
                  onChange={(event) =>
                    setFilters((current) => ({
                      ...current,
                      search: event.target.value
                    }))
                  }
                  placeholder="Ticket, issue, customer, queue"
                  value={filters.search}
                />
              </label>

              <label className="field-block">
                <span>Status</span>
                <select
                  className="field-input"
                  onChange={(event) =>
                    setFilters((current) => ({
                      ...current,
                      status: event.target.value
                    }))
                  }
                  value={filters.status}
                >
                  {availableOptions.statuses.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
              </label>

              <label className="field-block">
                <span>Priority</span>
                <select
                  className="field-input"
                  onChange={(event) =>
                    setFilters((current) => ({
                      ...current,
                      priority: event.target.value
                    }))
                  }
                  value={filters.priority}
                >
                  {availableOptions.priorities.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
              </label>

              <label className="field-block">
                <span>Queue</span>
                <select
                  className="field-input"
                  onChange={(event) =>
                    setFilters((current) => ({
                      ...current,
                      queue: event.target.value
                    }))
                  }
                  value={filters.queue}
                >
                  {availableOptions.queues.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </section>

          <section className="overview-grid dashboard-kpi-grid">
            <article className="metric-card metric-accent-cyan">
              <div className="metric-label">Total tickets</div>
              <div className="metric-value">{totalTickets}</div>
              <p>Tickets in the current analytics slice.</p>
            </article>
            <article className="metric-card metric-accent-amber">
              <div className="metric-label">Active queue</div>
              <div className="metric-value">{activeQueueCount}</div>
              <p>Open, in progress, or waiting on customer.</p>
            </article>
            <article className="metric-card metric-accent-red">
              <div className="metric-label">High priority</div>
              <div className="metric-value">{highPriorityCount}</div>
              <p>Tickets that need the fastest action.</p>
            </article>
            <article className="metric-card metric-accent-violet">
              <div className="metric-label">Waiting on customer</div>
              <div className="metric-value">{waitingOnCustomerCount}</div>
              <p>Threads blocked until the shopper replies.</p>
            </article>
          </section>

          <div className="analytics-card-grid analytics-visual-grid">
            <AnalyticsDistributionCard
              copy="How the filtered tickets are spread across statuses."
              emptyCopy="No status data is available for the current filters."
              rows={statusRows}
              title="Status Mix"
            />
            <AnalyticsBarGraphCard
              accent="#14b8a6"
              copy="A seven-day bar graph of queue movement inside the current analytics filters."
              emptyCopy="No ticket activity is available for the current filters."
              points={trendPoints}
              title="7-day Queue Movement"
            />
            <AnalyticsDistributionCard
              copy="How the filtered tickets are spread across queues."
              emptyCopy="No queues matched the current filters."
              rows={queueRows}
              title="Queue Mix"
            />
            <AnalyticsDistributionCard
              copy="Current ticket ownership across support agents."
              emptyCopy="No agent assignments matched the current filters."
              rows={agentRows}
              title="Agent Workload"
            />
          </div>

          <div className="analytics-queue-grid">
            <section className="plain-card analytics-surface">
              <div className="section-title">Recent tickets</div>
              <div className="section-copy">Newest tickets in the current analytics view.</div>

              <div className="analytics-ticket-table">
                {recentTickets.map((ticket) => (
                  <article className="analytics-ticket-row" key={ticket.ticket_id}>
                    <div>
                      <strong>{ticket.ticket_id}</strong>
                      <div className="mini-copy">{ticket.customer_email}</div>
                    </div>
                    <div>{ticket.queue_name}</div>
                    <div>
                      <span className="badge-chip dark">
                        <span className="badge-dot" style={{ backgroundColor: getPriorityColor(ticket.priority) }} />
                        {ticket.priority}
                      </span>
                    </div>
                    <div className="mini-copy">{formatTicketTimestamp(ticket.updated_at)}</div>
                  </article>
                ))}
              </div>
            </section>

            <section className="plain-card analytics-surface">
              <div className="section-title">Needs attention</div>
              <div className="section-copy">High-priority or waiting tickets that should stay visible.</div>

              <div className="analytics-escalation-list">
                {priorityTickets.length ? (
                  priorityTickets.map((ticket) => (
                    <article className="analytics-escalation-card" key={ticket.ticket_id}>
                      <div className="workspace-record-title-row">
                        <strong>{ticket.ticket_id}</strong>
                        <span className="badge-chip dark">
                          <span className="badge-dot" style={{ backgroundColor: getStatusColor(ticket.status) }} />
                          {ticket.status}
                        </span>
                      </div>
                      <div className="workspace-record-copy">{ticket.issue}</div>
                      <div className="badge-row compact workspace-record-tag-row">
                        <span className="badge-chip dark">{ticket.queue_name}</span>
                        <span className="badge-chip dark">{ticket.assigned_agent}</span>
                      </div>
                    </article>
                  ))
                ) : (
                  <div className="empty-card">No urgent tickets matched the current filters.</div>
                )}
              </div>
            </section>
          </div>
        </div>
      )}
    </div>
  );
}
