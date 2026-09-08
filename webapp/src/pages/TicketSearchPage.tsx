import { Link } from "react-router-dom";
import {
  startTransition,
  useDeferredValue,
  useEffect,
  useState
} from "react";
import {
  closeAdminTicket,
  getAdminTicketDetail,
  getAdminTickets,
  updateAdminTicketStatus
} from "../lib/api";
import {
  formatTicketTimestamp,
  getPriorityColor,
  getStatusColor,
  sortTicketsByRecent
} from "../lib/ticketPresentation";
import type { Ticket, TicketDetailResponse } from "../types";

type SearchMode =
  | "All Fields"
  | "Ticket ID"
  | "Customer Email"
  | "Issue"
  | "Agent";

type ViewMode = "Cards" | "Table";

type SearchFilters = {
  agent: string;
  issueType: string;
  priority: string;
  status: string;
};

const searchModes: SearchMode[] = [
  "All Fields",
  "Ticket ID",
  "Customer Email",
  "Issue",
  "Agent"
];

const defaultFilters: SearchFilters = {
  agent: "All",
  issueType: "All",
  priority: "All",
  status: "All"
};

function buildOptions(tickets: Ticket[], key: keyof Ticket) {
  return [
    "All",
    ...Array.from(
      new Set(
        tickets
          .map((ticket) => String(ticket[key] || "").trim())
          .filter(Boolean)
      )
    ).sort((left, right) => left.localeCompare(right))
  ];
}

function matchesSearchMode(ticket: Ticket, query: string, mode: SearchMode) {
  const normalizedQuery = query.trim().toLowerCase();

  if (!normalizedQuery) {
    return true;
  }

  if (mode === "Ticket ID") {
    return ticket.ticket_id.toLowerCase().includes(normalizedQuery);
  }

  if (mode === "Customer Email") {
    return ticket.customer_email.toLowerCase().includes(normalizedQuery);
  }

  if (mode === "Issue") {
    return ticket.issue.toLowerCase().includes(normalizedQuery);
  }

  if (mode === "Agent") {
    return ticket.assigned_agent.toLowerCase().includes(normalizedQuery);
  }

  return [
    ticket.ticket_id,
    ticket.customer_email,
    ticket.issue,
    ticket.assigned_agent
  ]
    .join(" ")
    .toLowerCase()
    .includes(normalizedQuery);
}

function escapeCsv(value: string) {
  return `"${value.replace(/"/g, "\"\"")}"`;
}

function escapeHtml(value: string) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function downloadFile(
  filename: string,
  content: string,
  mimeType: string
) {
  const blob = new Blob([content], { type: mimeType });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");

  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}

function exportTicketsAsCsv(tickets: Ticket[]) {
  const rows = [
    [
      "Ticket ID",
      "Customer Email",
      "Issue Type",
      "Priority",
      "Status",
      "Assigned Agent",
      "Queue",
      "Issue",
      "Created At",
      "Updated At"
    ],
    ...tickets.map((ticket) => [
      ticket.ticket_id,
      ticket.customer_email,
      ticket.issue_type,
      ticket.priority,
      ticket.status,
      ticket.assigned_agent,
      ticket.queue_name,
      ticket.issue,
      ticket.created_at,
      ticket.updated_at
    ])
  ];

  const csvText = rows
    .map((row) => row.map((cell) => escapeCsv(String(cell ?? ""))).join(","))
    .join("\n");

  downloadFile(
    `ticket-search-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")}.csv`,
    csvText,
    "text/csv;charset=utf-8;"
  );
}

function exportTicketsAsExcelTable(tickets: Ticket[]) {
  const headers = [
    "Ticket ID",
    "Customer Email",
    "Issue Type",
    "Priority",
    "Status",
    "Assigned Agent",
    "Queue",
    "Issue",
    "Created At",
    "Updated At"
  ];

  const rows = tickets.map((ticket) => [
    ticket.ticket_id,
    ticket.customer_email,
    ticket.issue_type,
    ticket.priority,
    ticket.status,
    ticket.assigned_agent,
    ticket.queue_name,
    ticket.issue,
    ticket.created_at,
    ticket.updated_at
  ]);

  const html = `
    <html xmlns:o="urn:schemas-microsoft-com:office:office"
          xmlns:x="urn:schemas-microsoft-com:office:excel"
          xmlns="http://www.w3.org/TR/REC-html40">
      <head>
        <meta charset="utf-8" />
      </head>
      <body>
        <table>
          <thead>
            <tr>${headers.map((header) => `<th>${escapeHtml(header)}</th>`).join("")}</tr>
          </thead>
          <tbody>
            ${rows
              .map(
                (row) =>
                  `<tr>${row
                    .map((cell) => `<td>${escapeHtml(String(cell ?? ""))}</td>`)
                    .join("")}</tr>`
              )
              .join("")}
          </tbody>
        </table>
      </body>
    </html>
  `;

  downloadFile(
    `ticket-search-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")}.xls`,
    html,
    "application/vnd.ms-excel"
  );
}

type TicketSearchPageProps = {
  embedded?: boolean;
};

export function TicketSearchPage({ embedded = false }: TicketSearchPageProps) {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [detail, setDetail] = useState<TicketDetailResponse | null>(null);
  const [selectedTicketId, setSelectedTicketId] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [searchMode, setSearchMode] = useState<SearchMode>("All Fields");
  const [viewMode, setViewMode] = useState<ViewMode>("Cards");
  const [filters, setFilters] = useState<SearchFilters>(defaultFilters);
  const [isLoading, setIsLoading] = useState(true);
  const [isWorking, setIsWorking] = useState(false);
  const [error, setError] = useState("");
  const deferredSearch = useDeferredValue(searchQuery);

  async function loadTickets(preferredTicketId?: string) {
    const response = await getAdminTickets();
    const nextTickets = [...response.tickets].sort(sortTicketsByRecent);
    const nextSelectedTicketId =
      preferredTicketId && nextTickets.some((ticket) => ticket.ticket_id === preferredTicketId)
        ? preferredTicketId
        : nextTickets[0]?.ticket_id ?? "";

    setTickets(nextTickets);
    setSelectedTicketId(nextSelectedTicketId);
  }

  async function loadDetail(ticketId: string) {
    if (!ticketId) {
      setDetail(null);
      return;
    }

    const response = await getAdminTicketDetail(ticketId);
    setDetail(response);
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
        setSelectedTicketId(nextTickets[0]?.ticket_id ?? "");
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : "Unable to load ticket search.");
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

  useEffect(() => {
    let cancelled = false;

    async function hydrateDetail() {
      if (!selectedTicketId) {
        setDetail(null);
        return;
      }

      try {
        setError("");
        const response = await getAdminTicketDetail(selectedTicketId);

        if (!cancelled) {
          setDetail(response);
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : "Unable to load ticket details.");
        }
      }
    }

    void hydrateDetail();

    return () => {
      cancelled = true;
    };
  }, [selectedTicketId]);

  const filteredTickets = tickets.filter((ticket) => {
    if (!matchesSearchMode(ticket, deferredSearch, searchMode)) {
      return false;
    }

    if (filters.status !== "All" && ticket.status !== filters.status) {
      return false;
    }

    if (filters.priority !== "All" && ticket.priority !== filters.priority) {
      return false;
    }

    if (filters.issueType !== "All" && ticket.issue_type !== filters.issueType) {
      return false;
    }

    if (filters.agent !== "All" && ticket.assigned_agent !== filters.agent) {
      return false;
    }

    return true;
  });

  useEffect(() => {
    if (!filteredTickets.length) {
      if (selectedTicketId) {
        setSelectedTicketId("");
      }
      return;
    }

    if (!filteredTickets.some((ticket) => ticket.ticket_id === selectedTicketId)) {
      setSelectedTicketId(filteredTickets[0].ticket_id);
    }
  }, [filteredTickets, selectedTicketId]);

  const selectedTicket =
    detail?.ticket ??
    tickets.find((ticket) => ticket.ticket_id === selectedTicketId) ??
    null;
  const filterOptions = {
    agents: buildOptions(tickets, "assigned_agent"),
    issueTypes: buildOptions(tickets, "issue_type"),
    priorities: buildOptions(tickets, "priority"),
    statuses: buildOptions(tickets, "status")
  };

  async function handleRefresh() {
    try {
      setIsWorking(true);
      setError("");
      await loadTickets(selectedTicketId);

      if (selectedTicketId) {
        await loadDetail(selectedTicketId);
      }
    } catch (refreshError) {
      setError(refreshError instanceof Error ? refreshError.message : "Unable to refresh ticket search.");
    } finally {
      setIsWorking(false);
    }
  }

  async function handleStatusChange(status: string) {
    if (!selectedTicket) {
      return;
    }

    try {
      setIsWorking(true);
      setError("");
      await updateAdminTicketStatus(selectedTicket.ticket_id, status);
      await loadTickets(selectedTicket.ticket_id);
      await loadDetail(selectedTicket.ticket_id);
    } catch (statusError) {
      setError(statusError instanceof Error ? statusError.message : "Unable to update ticket status.");
    } finally {
      setIsWorking(false);
    }
  }

  async function handleCloseTicket() {
    if (!selectedTicket) {
      return;
    }

    try {
      setIsWorking(true);
      setError("");
      await closeAdminTicket(selectedTicket.ticket_id);
      await loadTickets(selectedTicket.ticket_id);
      await loadDetail(selectedTicket.ticket_id);
    } catch (closeError) {
      setError(closeError instanceof Error ? closeError.message : "Unable to close this ticket.");
    } finally {
      setIsWorking(false);
    }
  }

  return (
    <div className="stack-page">
      {!embedded ? (
        <section className="hero-card compact">
          <div className="hero-kicker">Discovery Workspace</div>
          <h2>Ticket Search</h2>
          <p>
            Search by ID, customer, issue, or agent, then inspect a ticket without
            jumping out of the React control room.
          </p>
        </section>
      ) : null}

      {error ? <div className="banner-error">{error}</div> : null}

      {isLoading ? (
        <div className="empty-card tall">Loading ticket search.</div>
      ) : (
        <div className="ticket-search-layout">
          <section className="ticket-search-main">
            <section className="plain-card ticket-search-panel">
              <div className="section-head">
                <div>
                  <div className="section-kicker">Search & Filter</div>
                  <div className="section-title">Find Tickets Fast</div>
                </div>
                <div className="toolbar-row wrap">
                  <button
                    className="ghost-button"
                    disabled={isWorking}
                    onClick={() => void handleRefresh()}
                    type="button"
                  >
                    Refresh Results
                  </button>
                  <button
                    className="ghost-button"
                    onClick={() => {
                      setSearchQuery("");
                      setSearchMode("All Fields");
                      setFilters(defaultFilters);
                    }}
                    type="button"
                  >
                    Clear Filters
                  </button>
                </div>
              </div>

              <div className="ticket-search-toolbar">
                <label className="field-block">
                  <span>Search query</span>
                  <input
                    className="field-input"
                    onChange={(event) => setSearchQuery(event.target.value)}
                    placeholder="Ticket ID, customer email, refund, agent name"
                    value={searchQuery}
                  />
                </label>

                <label className="field-block">
                  <span>Search in</span>
                  <select
                    className="field-input"
                    onChange={(event) => setSearchMode(event.target.value as SearchMode)}
                    value={searchMode}
                  >
                    {searchModes.map((mode) => (
                      <option key={mode} value={mode}>
                        {mode}
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              <div className="ticket-search-filter-grid">
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
                  <span>Issue type</span>
                  <select
                    className="field-input"
                    onChange={(event) =>
                      setFilters((current) => ({
                        ...current,
                        issueType: event.target.value
                      }))
                    }
                    value={filters.issueType}
                  >
                    {filterOptions.issueTypes.map((value) => (
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

              <div className="ticket-search-summary">
                <div className="ticket-search-count">
                  {filteredTickets.length} ticket{filteredTickets.length === 1 ? "" : "s"} matched
                </div>

                <div className="ticket-search-actions">
                  <div className="view-toggle-group">
                    {(["Cards", "Table"] as ViewMode[]).map((mode) => (
                      <button
                        className={`view-toggle-button${viewMode === mode ? " active" : ""}`}
                        key={mode}
                        onClick={() => setViewMode(mode)}
                        type="button"
                      >
                        {mode}
                      </button>
                    ))}
                  </div>

                  <button
                    className="ghost-button small"
                    disabled={!filteredTickets.length}
                    onClick={() => exportTicketsAsCsv(filteredTickets)}
                    type="button"
                  >
                    Export CSV
                  </button>
                  <button
                    className="ghost-button small"
                    disabled={!filteredTickets.length}
                    onClick={() => exportTicketsAsExcelTable(filteredTickets)}
                    type="button"
                  >
                    Export Excel
                  </button>
                </div>
              </div>
            </section>

            <section className="plain-card ticket-search-results">
              {viewMode === "Cards" ? (
                <div className="search-card-list">
                  {filteredTickets.map((ticket) => (
                    <button
                      className={`search-result-card${ticket.ticket_id === selectedTicketId ? " active" : ""}`}
                      key={ticket.ticket_id}
                      onClick={() =>
                        startTransition(() => {
                          setSelectedTicketId(ticket.ticket_id);
                        })
                      }
                      type="button"
                    >
                      <div className="search-result-top">
                        <div className="search-result-title">
                          <span
                            className="badge-dot"
                            style={{ backgroundColor: getPriorityColor(ticket.priority) }}
                          />
                          {ticket.ticket_id}
                        </div>
                        <span className="soft-pill">
                          <span
                            className="badge-dot"
                            style={{ backgroundColor: getStatusColor(ticket.status) }}
                          />
                          {ticket.status}
                        </span>
                      </div>

                      <div className="search-result-issue">{ticket.issue.slice(0, 120)}</div>

                      <div className="search-result-meta">
                        <span>{ticket.issue_type}</span>
                        <span>{ticket.assigned_agent}</span>
                        <span>{ticket.customer_email}</span>
                      </div>
                    </button>
                  ))}

                  {!filteredTickets.length ? (
                    <div className="empty-card">
                      No tickets matched your current search criteria.
                    </div>
                  ) : null}
                </div>
              ) : (
                <div className="table-shell">
                  <div className="table-head ticket-search-table-grid">
                    <div>Ticket</div>
                    <div>Type</div>
                    <div>Priority</div>
                    <div>Status</div>
                    <div>Agent</div>
                    <div>Email</div>
                    <div>Issue</div>
                  </div>

                  {filteredTickets.map((ticket) => (
                    <button
                      className={`table-row ticket-search-table-grid ticket-table-row${ticket.ticket_id === selectedTicketId ? " active" : ""}`}
                      key={ticket.ticket_id}
                      onClick={() =>
                        startTransition(() => {
                          setSelectedTicketId(ticket.ticket_id);
                        })
                      }
                      type="button"
                    >
                      <div>{ticket.ticket_id}</div>
                      <div>{ticket.issue_type}</div>
                      <div>
                        <span className="soft-pill">
                          <span
                            className="badge-dot"
                            style={{ backgroundColor: getPriorityColor(ticket.priority) }}
                          />
                          {ticket.priority}
                        </span>
                      </div>
                      <div>
                        <span className="soft-pill">
                          <span
                            className="badge-dot"
                            style={{ backgroundColor: getStatusColor(ticket.status) }}
                          />
                          {ticket.status}
                        </span>
                      </div>
                      <div>{ticket.assigned_agent}</div>
                      <div>{ticket.customer_email}</div>
                      <div>{ticket.issue.slice(0, 92)}</div>
                    </button>
                  ))}

                  {!filteredTickets.length ? (
                    <div className="empty-card">
                      No tickets matched your current search criteria.
                    </div>
                  ) : null}
                </div>
              )}
            </section>
          </section>

          <aside className="ticket-search-side">
            {!selectedTicket || !detail ? (
              <div className="empty-card tall">Select a ticket to inspect its full context.</div>
            ) : (
              <div className="inspector-card ticket-search-inspector">
                <div className="inspector-hero">
                  <div className="hero-kicker">Ticket Inspector</div>
                  <h3>{selectedTicket.ticket_id}</h3>
                  <p>
                    {selectedTicket.issue_type} / {selectedTicket.queue_name}
                  </p>
                </div>

                <div className="badge-row compact">
                  <span className="badge-chip dark">
                    <span
                      className="badge-dot"
                      style={{ backgroundColor: getPriorityColor(selectedTicket.priority) }}
                    />
                    {selectedTicket.priority} Priority
                  </span>
                  <span className="badge-chip dark">
                    <span
                      className="badge-dot"
                      style={{ backgroundColor: getStatusColor(selectedTicket.status) }}
                    />
                    {selectedTicket.status}
                  </span>
                  <span className="badge-chip dark">
                    <span
                      className="badge-dot"
                      style={{ backgroundColor: "#14b8a6" }}
                    />
                    {selectedTicket.assigned_agent}
                  </span>
                </div>

                <div className="status-grid">
                  <button
                    className="status-button amber"
                    disabled={isWorking || selectedTicket.status === "In Progress"}
                    onClick={() => void handleStatusChange("In Progress")}
                    type="button"
                  >
                    In Progress
                  </button>
                  <button
                    className="status-button green"
                    disabled={isWorking || selectedTicket.status === "Resolved"}
                    onClick={() => void handleStatusChange("Resolved")}
                    type="button"
                  >
                    Resolve
                  </button>
                  <button
                    className="status-button blue"
                    disabled={isWorking || selectedTicket.status === "Open"}
                    onClick={() => void handleStatusChange("Open")}
                    type="button"
                  >
                    Reopen
                  </button>
                </div>

                <div className="detail-card">
                  <div className="detail-card-title">Issue Summary</div>
                  <div className="issue-preview">{selectedTicket.issue}</div>
                </div>

                <div className="detail-card">
                  <div className="detail-card-title">Ticket Details</div>
                  <dl className="detail-list">
                    <div><dt>Customer</dt><dd>{selectedTicket.customer_email}</dd></div>
                    <div><dt>Agent</dt><dd>{selectedTicket.assigned_agent}</dd></div>
                    <div><dt>Priority</dt><dd>{selectedTicket.priority}</dd></div>
                    <div><dt>Status</dt><dd>{selectedTicket.status}</dd></div>
                    <div><dt>Brand</dt><dd>{selectedTicket.brand_tag}</dd></div>
                    <div><dt>Coverage</dt><dd>{selectedTicket.business_hours_tag}</dd></div>
                    <div><dt>Updated</dt><dd>{formatTicketTimestamp(selectedTicket.updated_at)}</dd></div>
                  </dl>
                </div>

                <div className="detail-card">
                  <div className="detail-card-title">Latest Messages</div>
                  {detail.messages.length ? (
                    <div className="note-stack">
                      {detail.messages.slice(-4).reverse().map((message) => (
                        <article className="note-card" key={message.id}>
                          <div className="message-meta">
                            <span>
                              {message.sender.toLowerCase() === "customer" ? "Customer" : "Help Desk"}
                            </span>
                            <span>{formatTicketTimestamp(message.created_at)}</span>
                          </div>
                          <div className="message-text">
                            {message.message || "Attachment-only update"}
                          </div>
                        </article>
                      ))}
                    </div>
                  ) : (
                    <div className="empty-copy">No messages were found for this ticket yet.</div>
                  )}
                </div>

                <div className="action-row stack">
                  <button
                    className="ghost-button"
                    disabled={isWorking || selectedTicket.status === "Closed"}
                    onClick={() => void handleCloseTicket()}
                    type="button"
                  >
                    Close Ticket
                  </button>
                  <Link className="ghost-button button-link" to="/admin/inbox">
                    Open In Inbox
                  </Link>
                  <Link className="ghost-button button-link" to="/ticket-dashboard">
                    Open Dashboard
                  </Link>
                </div>
              </div>
            )}
          </aside>
        </div>
      )}
    </div>
  );
}
