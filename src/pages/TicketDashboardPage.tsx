import {
  useDeferredValue,
  useEffect,
  useState
} from "react";
import {
  AnalyticsBarGraphCard,
  AnalyticsDistributionCard,
} from "../components/AnalyticsCharts";
import { WorkspaceStatePanel } from "../components/WorkspaceStatePanel";
import {
  getAdminTickets
} from "../lib/api";
import {
  buildOptions,
  createCountRows,
  createTicketTrendPoints
} from "../lib/analyticsPresentation";
import {
  buildTicketSearchBlob,
  getStatusColor,
  isActiveTicketStatus,
  sortTicketsByRecent
} from "../lib/ticketPresentation";
import type { Ticket } from "../types";

type DashboardFilters = {
  agent: string;
  priority: string;
  queue: string;
  search: string;
  status: string;
};

const defaultFilters: DashboardFilters = {
  agent: "All",
  priority: "All",
  queue: "All",
  search: "",
  status: "All"
};

type TicketDashboardPageProps = {
  embedded?: boolean;
};

export function TicketDashboardPage({ embedded = false }: TicketDashboardPageProps) {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [filters, setFilters] = useState<DashboardFilters>(defaultFilters);
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

        if (cancelled) {
          return;
        }

        const nextTickets = [...response.tickets].sort(sortTicketsByRecent);
        setTickets(nextTickets);
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : "Unable to load the ticket dashboard.");
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

  const visibleTickets = tickets.filter((ticket) => {
    if (deferredSearch.trim() && !buildTicketSearchBlob(ticket).includes(deferredSearch.trim().toLowerCase())) {
      return false;
    }

    if (filters.status !== "All" && ticket.status !== filters.status) {
      return false;
    }

    if (filters.priority !== "All" && ticket.priority !== filters.priority) {
      return false;
    }

    if (filters.agent !== "All" && ticket.assigned_agent !== filters.agent) {
      return false;
    }

    if (filters.queue !== "All" && ticket.queue_name !== filters.queue) {
      return false;
    }

    return true;
  });

  const activeCount = visibleTickets.filter((ticket) => isActiveTicketStatus(ticket.status)).length;
  const highPriorityCount = visibleTickets.filter((ticket) => ticket.priority === "High").length;
  const waitingOnCustomerCount = visibleTickets.filter(
    (ticket) => ticket.status === "Waiting on Customer"
  ).length;
  const closedCount = visibleTickets.filter((ticket) => ticket.status === "Closed").length;
  const trendPoints = createTicketTrendPoints(visibleTickets, "updated_at");
  const agentRows = createCountRows(
    visibleTickets,
    (ticket) => ticket.assigned_agent,
    () => "#38bdf8"
  ).slice(0, 6);
  const statusRows = createCountRows(visibleTickets, (ticket) => ticket.status, getStatusColor);
  const queueRows = createCountRows(
    visibleTickets,
    (ticket) => ticket.queue_name,
    () => "#14b8a6"
  ).slice(0, 6);
  const filterOptions = {
    agents: buildOptions(tickets, "assigned_agent"),
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
      setError(refreshError instanceof Error ? refreshError.message : "Unable to refresh dashboard data.");
    } finally {
      setIsWorking(false);
    }
  }

  return (
    <div className="stack-page">
      {!embedded ? (
        <section className="hero-card compact">
          <div className="hero-kicker">Operations Workspace</div>
          <h2>Ticket Dashboard</h2>
          <p>Keep the dashboard light and focused on the key queue signals instead of showing extra filter sections.</p>
        </section>
      ) : null}

      {error ? <div className="banner-error">{error}</div> : null}

      {isLoading ? (
        <WorkspaceStatePanel
          description="We are loading the latest ticket mix, agent coverage, and movement across the support queues."
          eyebrow="Dashboard workspace"
          metrics={[
            {
              accent: "cyan",
              label: "Ticket mix",
              note: "Preparing the live queue snapshot",
              value: "..."
            },
            {
              accent: "violet",
              label: "Ownership",
              note: "Refreshing agent coverage and handoffs",
              value: "..."
            },
            {
              accent: "amber",
              label: "Velocity",
              note: "Rebuilding the seven-day movement cards",
              value: "..."
            }
          ]}
          stateLabel="Building dashboard snapshot"
          title="Loading ticket dashboard"
        />
      ) : !tickets.length ? (
        <WorkspaceStatePanel
          description="As soon as tickets are created, this dashboard will surface queue mix, ownership, and ticket movement."
          eyebrow="Dashboard workspace"
          metrics={[
            {
              accent: "cyan",
              label: "Visible tickets",
              note: "The board is ready to track the first queue",
              value: "0"
            },
            {
              accent: "teal",
              label: "Active queue",
              note: "Open and in-progress work will appear here",
              value: "0"
            },
            {
              accent: "amber",
              label: "Agent workload",
              note: "Ownership cards will appear once tickets are assigned",
              value: "0"
            }
          ]}
          stateLabel="Waiting for first ticket activity"
          title="No tickets are available yet"
          variant="empty"
        />
      ) : (
        <div className="analytics-modern-shell">
          <section className="overview-grid dashboard-kpi-grid">
            <article className="metric-card metric-accent-cyan">
              <div className="metric-label">Tickets in view</div>
              <div className="metric-value">{visibleTickets.length}</div>
              <p>All tickets matching the current dashboard filters.</p>
            </article>
            <article className="metric-card metric-accent-amber">
              <div className="metric-label">Active queue</div>
              <div className="metric-value">{activeCount}</div>
              <p>Open, in-progress, or waiting on customer.</p>
            </article>
            <article className="metric-card metric-accent-red">
              <div className="metric-label">High priority</div>
              <div className="metric-value">{highPriorityCount}</div>
              <p>Tickets that need the fastest operational response.</p>
            </article>
            <article className="metric-card metric-accent-violet">
              <div className="metric-label">Closed</div>
              <div className="metric-value">{closedCount}</div>
              <p>Resolved work already moved out of the active queue.</p>
            </article>
          </section>

          <section className="plain-card analytics-toolbar-card dashboard-toolbar-card">
            <div className="workspace-detail-topbar">
              <div>
                <div className="workspace-detail-kicker">Dashboard summary</div>
                <div className="section-title">Queue snapshot</div>
                <div className="section-copy">This page stays focused on live counts, movement, and workload balance without extra decoration.</div>
              </div>

              <div className="workspace-detail-actions">
                <button className="ghost-button" disabled={isWorking} onClick={() => void handleRefresh()} type="button">
                  Refresh
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
                  {filterOptions.statuses.map((value) => (
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
                  {filterOptions.priorities.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
              </label>

              <label className="field-block">
                <span>Agent</span>
                <select
                  className="field-input"
                  onChange={(event) =>
                    setFilters((current) => ({
                      ...current,
                      agent: event.target.value
                    }))
                  }
                  value={filters.agent}
                >
                  {filterOptions.agents.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </section>

          <div className="analytics-card-grid analytics-visual-grid">
            <AnalyticsDistributionCard
              copy="Status share across the filtered dashboard view."
              emptyCopy="No status data is available for the current dashboard filters."
              rows={statusRows}
              title="Status Mix"
            />
            <AnalyticsBarGraphCard
              accent="#38bdf8"
              copy="A seven-day bar graph of ticket activity inside the current dashboard filter set."
              emptyCopy="No ticket activity is available for the current dashboard filters."
              points={trendPoints}
              title="7-day Ticket Movement"
            />
            <AnalyticsDistributionCard
              copy="Current ticket ownership across the filtered ticket set."
              emptyCopy="No agent assignments matched the current dashboard filters."
              rows={agentRows}
              title="Agent Workload"
            />
            <AnalyticsDistributionCard
              copy="Queue ownership across the filtered ticket set."
              emptyCopy="No queues matched the current dashboard filters."
              rows={queueRows}
              title="Queue Mix"
            />
          </div>

          <section className="plain-card analytics-toolbar-card dashboard-spotlight-card">
            <div className="workspace-detail-topbar">
              <div>
                <div className="workspace-detail-kicker">Live attention line</div>
                <div className="section-title">Operational focus</div>
                <div className="section-copy">Track how much of the visible queue still needs action and how much is blocked on customer response.</div>
              </div>
            </div>

            <div className="dashboard-focus-grid">
              <article className="dashboard-focus-card accent-cyan">
                <span>Active work</span>
                <strong>{activeCount}</strong>
                <small>Tickets that still require team action</small>
              </article>
              <article className="dashboard-focus-card accent-amber">
                <span>Waiting on customer</span>
                <strong>{waitingOnCustomerCount}</strong>
                <small>Threads paused until the shopper replies</small>
              </article>
              <article className="dashboard-focus-card accent-violet">
                <span>Queues covered</span>
                <strong>{queueRows.length}</strong>
                <small>Support lanes represented in the current slice</small>
              </article>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
