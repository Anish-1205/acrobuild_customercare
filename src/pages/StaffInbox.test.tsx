import "@testing-library/jest-dom/vitest";
import { useState } from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { RoleId } from "../contexts/RoleContext";
import { AttachmentPreview } from "../components/AttachmentPreview";
import { AdminInboxPage, OwnerInboxWorkspacePage } from "./AdminInboxPage";
import { AgentInboxPage } from "./AgentInboxPage";

const api = vi.hoisted(() => ({
  closeAdminTicket: vi.fn(),
  createAdminTicketNote: vi.fn(),
  getAdminCustomerByEmail: vi.fn(),
  getAdminMacros: vi.fn(),
  getAdminRecommendedMacros: vi.fn(),
  getAdminTags: vi.fn(),
  getAdminTicketDetail: vi.fn(),
  getAdminTickets: vi.fn(),
  getOrdersByEmail: vi.fn(),
  markAdminTicketRead: vi.fn(),
  postAdminTicketReply: vi.fn(),
  updateAdminTicketAssignee: vi.fn(),
  updateAdminTicketStatus: vi.fn(),
  updateAdminTicketTags: vi.fn()
}));

vi.mock("../lib/api", () => api);

let currentRole: RoleId = "admin";
const setSearchSuggestions = vi.fn();
const setTicketSearchQuery = vi.fn();
const setVisibleTicketCount = vi.fn();

vi.mock("../contexts/RoleContext", () => ({
  useRole: () => ({ role: currentRole })
}));

vi.mock("../contexts/SearchContext", () => ({
  useSearch: () => ({
    ticketSearchQuery: "",
    setSearchSuggestions,
    setTicketSearchQuery,
    setVisibleTicketCount
  })
}));

const ticket = {
  assigned_agent: "Help Desk",
  assignment_method: "Auto-Routed",
  brand_tag: "AcroBuild",
  business_hours_tag: "Business Hours",
  created_at: "2026-10-07T08:00:00Z",
  customer_email: "customer@example.test",
  intent_tag: "General Inquiry",
  issue: "Need help with my request",
  issue_type: "General",
  priority: "Medium",
  queue_name: "General Queue",
  status: "Open",
  ticket_id: "AC-1001",
  unread_count: 1,
  updated_at: "2026-10-07T09:00:00Z"
};

const readTicket = { ...ticket, unread_count: 0 };
const detail = {
  messages: [
    {
      attachments: [],
      created_at: "2026-10-07T08:00:00Z",
      id: 1,
      message: "I need support.",
      sender: "customer",
      ticket_id: ticket.ticket_id
    }
  ],
  notes: [],
  tags: [],
  ticket
};

const macro = {
  category: "General",
  id: 1,
  name: "Acknowledgement",
  response_text: "Hello {{customer_first_name}}, we are reviewing your request.",
  tag_names: []
};

function renderInbox(kind: "admin" | "owner" | "agent") {
  currentRole = kind;
  const Component = kind === "agent" ? AgentInboxPage : kind === "owner" ? OwnerInboxWorkspacePage : AdminInboxPage;
  return render(
    <MemoryRouter initialEntries={[`/${kind}/inbox`]}>
      <Component />
    </MemoryRouter>
  );
}

function AttachmentPreviewHarness() {
  const [isOpen, setIsOpen] = useState(false);
  return (
    <>
      <button onClick={() => setIsOpen(true)} type="button">Open attachment</button>
      {isOpen ? (
        <AttachmentPreview
          alt="Mock attachment"
          onClose={() => setIsOpen(false)}
          src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw=="
        />
      ) : null}
    </>
  );
}

describe("Phase 6A staff inboxes", () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.clearAllMocks();
    api.getAdminTickets.mockResolvedValue({ tickets: [ticket] });
    api.getAdminTags.mockResolvedValue({ tags: [] });
    api.getAdminMacros.mockResolvedValue({ macros: [macro] });
    api.getAdminRecommendedMacros.mockResolvedValue({ macros: [macro] });
    api.getAdminTicketDetail.mockResolvedValue(detail);
    api.markAdminTicketRead.mockResolvedValue({ ticket: readTicket });
    api.getAdminCustomerByEmail.mockResolvedValue({ customer: { name: "Customer" }, orders: [] });
    api.getOrdersByEmail.mockResolvedValue({ orders: [] });
    api.postAdminTicketReply.mockResolvedValue({ ticket: readTicket });
  });

  it.each(["admin", "owner"] as const)("keeps assignment available to the %s manager inbox", async (role) => {
    const { container } = renderInbox(role);

    expect(container.firstElementChild).toHaveClass("staff-inbox", "staff-inbox-manager");
    expect(await screen.findByRole("heading", { name: "General AC-1001" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Assign to agent" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Reply message" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Internal note" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /AC-1001/i })).toHaveAttribute("aria-current", "true");
    expect(api.markAdminTicketRead).toHaveBeenCalledWith("AC-1001");
  });

  it("keeps the agent inbox restricted while preserving macro and keyboard reply behavior", async () => {
    const { container } = renderInbox("agent");

    expect(container.firstElementChild).toHaveClass("staff-inbox", "staff-inbox-agent");
    const reply = await screen.findByRole("textbox", { name: "Reply message" });
    expect(screen.queryByRole("combobox", { name: "Assign to agent" })).not.toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Select reply macro" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Acknowledgement" }));
    expect(reply).toHaveValue("Hello Customer, we are reviewing your request.");

    fireEvent.keyDown(reply, { key: "Enter", ctrlKey: true });
    await waitFor(() => expect(api.postAdminTicketReply).toHaveBeenCalledOnce());
    expect(api.updateAdminTicketAssignee).not.toHaveBeenCalled();
  });

  it("keeps attachment preview focus contained and returns it on Escape", () => {
    render(<AttachmentPreviewHarness />);
    const trigger = screen.getByRole("button", { name: "Open attachment" });

    trigger.focus();
    fireEvent.click(trigger);
    const close = screen.getByRole("button", { name: "Close image preview" });
    expect(close).toHaveFocus();

    fireEvent.keyDown(screen.getByRole("dialog", { name: "Attachment preview" }), { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "Attachment preview" })).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });
});
