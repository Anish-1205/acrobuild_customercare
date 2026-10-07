import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { beginApiActivity, finishApiActivity, getApiActivity } from "../lib/apiActivity";
import { AdminAnalyticsPage } from "./AdminAnalyticsPage";
import { ApiActivityPage } from "./ApiActivityPage";
import { AutomationPage } from "./AutomationPage";

const api = vi.hoisted(() => ({
  confirmTicketAction: vi.fn(),
  getAdminTickets: vi.fn(),
  getAutomationDashboard: vi.fn(),
  proposeTicketAction: vi.fn()
}));

vi.mock("../lib/api", () => api);

const ticket = {
  assigned_agent: "Care Team",
  assignment_method: "Manual",
  brand_tag: "AcroBuild",
  business_hours_tag: "Business Hours",
  created_at: new Date().toISOString(),
  customer_email: "customer@example.test",
  intent_tag: "Support",
  issue: "Need an update",
  issue_type: "General",
  priority: "High",
  queue_name: "Support",
  status: "Open",
  ticket_id: "AC-6001",
  unread_count: 0,
  updated_at: new Date().toISOString()
};

describe("Phase 6D reporting, diagnostics, and automation", () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    api.getAdminTickets.mockResolvedValue({ tickets: [ticket] });
    api.getAutomationDashboard.mockResolvedValue({
      agents: [{ active_tickets: 2, available_capacity: 3, name: "Care Team", team: "Support" }],
      tickets: [{ age_hours: 5.5, assigned_agent: "Care Team", priority: "High", status: "Open", ticket_id: "AC-6001" }]
    });
    api.proposeTicketAction.mockResolvedValue({
      before: { assigned_agent: "Care Team", status: "Open" },
      change: { status: "Resolved" },
      expires_in: 600,
      kind: "status",
      proposal_id: "proposal-1",
      ticket_id: "AC-6001"
    });
    api.confirmTicketAction.mockResolvedValue({ completed: true });
  });

  it("keeps analytics derived from the loaded ticket list and exposes a textual chart description", async () => {
    render(<AdminAnalyticsPage embedded />);

    expect(await screen.findByRole("heading", { name: "Analytics", level: 1 })).toBeInTheDocument();
    expect(screen.getAllByText("1", { selector: ".metric-value" }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("img").some((chart) => chart.getAttribute("aria-label")?.includes(": 1"))).toBe(true);
  });

  it("redacts sensitive local trace fields before diagnostics can render them", () => {
    const activityId = beginApiActivity({
      endpoint: "/api/support/assist",
      method: "POST",
      request: { issue: "Show project options" },
      transport: "json"
    });
    finishApiActivity(activityId, {
      answer: "Available options returned.",
      data_api_calls: [{
        endpoint: "/api/cs/projects",
        error: "Bearer top-secret-token",
        params: { api_key: "top-secret-token", company_id: "1" },
        response_summary: { authorization: "top-secret-token", record_count: 2 }
      }]
    });

    const serialized = JSON.stringify(getApiActivity());
    expect(serialized).not.toContain("top-secret-token");
    expect(serialized).toContain("[REDACTED]");
  });

  it("keeps embedded diagnostics out of a nested main landmark and labels browser-local scope", () => {
    render(<MemoryRouter><ApiActivityPage basePath="/admin" /></MemoryRouter>);

    expect(screen.queryByRole("main")).not.toBeInTheDocument();
    expect(screen.getByText(/stored only in this browser/i)).toBeInTheDocument();
  });

  it("requires a proposal before the confirmation API can run", async () => {
    render(<AutomationPage />);

    fireEvent.click(await screen.findByRole("button", { name: "AC-6001" }));
    fireEvent.click(screen.getByRole("button", { name: "Preview resolution" }));
    await waitFor(() => expect(api.proposeTicketAction).toHaveBeenCalledWith("AC-6001", "status", "Resolved"));
    expect(api.confirmTicketAction).not.toHaveBeenCalled();
    expect(screen.getByText(/has not changed the ticket yet/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Confirm change" }));
    await waitFor(() => expect(api.confirmTicketAction).toHaveBeenCalledWith("proposal-1"));
  });
});
