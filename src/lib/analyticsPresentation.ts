import type { Ticket } from "../types";

export type CountRow = {
  color: string;
  label: string;
  value: number;
};

export type TrendPoint = {
  label: string;
  value: number;
};

function formatDateKey(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");

  return `${year}-${month}-${day}`;
}

export function buildOptions(tickets: Ticket[], key: keyof Ticket) {
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

export function createCountRows(
  tickets: Ticket[],
  getLabel: (ticket: Ticket) => string,
  getColor: (label: string) => string
) {
  const counts = new Map<string, number>();

  for (const ticket of tickets) {
    const label = getLabel(ticket).trim() || "Unknown";
    counts.set(label, (counts.get(label) ?? 0) + 1);
  }

  return [...counts.entries()]
    .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))
    .map(([label, value]) => ({
      color: getColor(label),
      label,
      value
    }));
}

export function createTicketTrendPoints(
  tickets: Ticket[],
  dateField: "created_at" | "updated_at",
  days = 7
) {
  const endDate = new Date();
  endDate.setHours(0, 0, 0, 0);

  const dayFormatter = new Intl.DateTimeFormat("en-AU", {
    day: "2-digit",
    month: "short"
  });

  const points = Array.from({ length: days }, (_, index) => {
    const date = new Date(endDate);
    date.setDate(endDate.getDate() - (days - index - 1));

    return {
      key: formatDateKey(date),
      label: dayFormatter.format(date),
      value: 0
    };
  });

  const counts = new Map(points.map((point) => [point.key, 0]));

  for (const ticket of tickets) {
    const source = ticket[dateField];

    if (!source) {
      continue;
    }

    const date = new Date(source);

    if (Number.isNaN(date.getTime())) {
      continue;
    }

    const key = formatDateKey(date);

    if (!counts.has(key)) {
      continue;
    }

    counts.set(key, (counts.get(key) ?? 0) + 1);
  }

  return points.map((point) => ({
    label: point.label,
    value: counts.get(point.key) ?? 0
  }));
}
