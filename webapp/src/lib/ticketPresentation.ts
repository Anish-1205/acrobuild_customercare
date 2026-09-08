import type { Ticket } from "../types";

const activeStatuses = new Set([
  "Open",
  "In Progress",
  "Waiting on Customer"
]);

const priorityOrder: Record<string, number> = {
  High: 0,
  Medium: 1,
  Low: 2
};

const statusOrder: Record<string, number> = {
  Open: 0,
  "In Progress": 1,
  "Waiting on Customer": 2,
  Resolved: 3,
  Closed: 4
};

export function formatTicketTimestamp(
  value: string,
  mode: "date" | "full" = "full"
) {
  if (!value) {
    return mode === "date" ? "Unknown date" : "Just now";
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return value;
  }

  if (mode === "date") {
    return new Intl.DateTimeFormat("en-AU", {
      day: "2-digit",
      month: "short",
      year: "numeric"
    }).format(date);
  }

  return new Intl.DateTimeFormat("en-AU", {
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    month: "short",
    year: "numeric"
  }).format(date);
}

export function getPriorityColor(priority: string) {
  const normalized = priority.trim().toLowerCase();

  if (normalized === "high") {
    return "#ef4444";
  }

  if (normalized === "medium") {
    return "#f59e0b";
  }

  return "#38bdf8";
}

export function getStatusColor(status: string) {
  const normalized = status.trim().toLowerCase();

  if (normalized === "resolved") {
    return "#22c55e";
  }

  if (normalized === "in progress") {
    return "#f59e0b";
  }

  if (normalized === "waiting on customer") {
    return "#8b5cf6";
  }

  if (normalized === "closed") {
    return "#64748b";
  }

  return "#38bdf8";
}

export function isActiveTicketStatus(status: string) {
  return activeStatuses.has(status);
}

export function buildTicketSearchBlob(ticket: Ticket) {
  return [
    ticket.ticket_id,
    ticket.customer_email,
    ticket.issue,
    ticket.issue_type,
    ticket.intent_tag,
    ticket.queue_name,
    ticket.status,
    ticket.assigned_agent,
    ticket.brand_tag
  ]
    .join(" ")
    .toLowerCase();
}

export function sortTicketsByRecent(left: Ticket, right: Ticket) {
  return right.updated_at.localeCompare(left.updated_at);
}

export function sortTicketsForQueue(left: Ticket, right: Ticket) {
  const leftStatus = statusOrder[left.status] ?? 9;
  const rightStatus = statusOrder[right.status] ?? 9;

  if (leftStatus !== rightStatus) {
    return leftStatus - rightStatus;
  }

  const leftPriority = priorityOrder[left.priority] ?? 9;
  const rightPriority = priorityOrder[right.priority] ?? 9;

  if (leftPriority !== rightPriority) {
    return leftPriority - rightPriority;
  }

  return right.updated_at.localeCompare(left.updated_at);
}
