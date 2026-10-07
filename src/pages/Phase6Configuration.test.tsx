import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { BusinessHoursPage } from "./BusinessHoursPage";
import { ChatWidgetPage } from "./ChatWidgetPage";
import { CSApiSettingsPage } from "./CSApiSettingsPage";
import { MacrosPage } from "./MacrosPage";
import { ManageTagsPage } from "./ManageTagsPage";
import { UsersPage } from "./UsersPage";

const api = vi.hoisted(() => ({
  archiveAdminMacro: vi.fn(),
  createAdminMacro: vi.fn(),
  createAdminTag: vi.fn(),
  createAdminUser: vi.fn(),
  deleteAdminMacro: vi.fn(),
  deleteAdminTag: vi.fn(),
  duplicateAdminMacro: vi.fn(),
  getAdminMacros: vi.fn(),
  getAdminTags: vi.fn(),
  getAdminUsers: vi.fn(),
  getBusinessHoursProfiles: vi.fn(),
  getCSApiSettings: vi.fn(),
  saveCSApiSettings: vi.fn(),
  updateAdminMacro: vi.fn(),
  updateAdminTag: vi.fn(),
  updateAdminUser: vi.fn(),
  updateBusinessHoursProfile: vi.fn()
}));

vi.mock("../lib/api", () => api);

const profile = {
  description: "Weekday coverage",
  id: 1,
  is_default: 1,
  name: "Default",
  ranges: [{ day_name: "Monday", end_time: "17:00", start_time: "09:00" }],
  summary: "Monday 09:00-17:00",
  timezone: "Asia/Kolkata"
};

const macro = {
  category: "General",
  id: 1,
  is_archived: 0,
  language: "English",
  name: "Acknowledgement",
  response_text: "Hello {{customer_first_name}}",
  set_status: "Open",
  subject_template: "Acknowledgement",
  tag_names: ["support"]
};

const tag = { color: "#0055ff", description: "Support", id: 1, name: "support", slug: "support", ticket_count: 2 };
const user = { email: "admin@example.test", id: 1, name: "Admin User", role: "admin", status: "Active", team: "Support" };

function renderInRouter(component: React.ReactNode) {
  return render(<MemoryRouter>{component}</MemoryRouter>);
}

describe("Phase 6C configuration and libraries", () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    api.getBusinessHoursProfiles.mockResolvedValue({ profiles: [profile] });
    api.updateBusinessHoursProfile.mockResolvedValue({ profile });
    api.getAdminMacros.mockResolvedValue({ macros: [macro] });
    api.getAdminTags.mockResolvedValue({ tags: [tag] });
    api.getAdminUsers.mockResolvedValue({ users: [user] });
    api.createAdminUser.mockResolvedValue({ user: { ...user, email: "new@example.test", id: 2, name: "New User", role: "agent" } });
    api.updateAdminUser.mockResolvedValue({ user });
    api.getCSApiSettings.mockResolvedValue({ api_key_configured: true, base_url: "https://example.test", company_id: "7" });
    api.saveCSApiSettings.mockResolvedValue({ api_key_configured: true, base_url: "https://example.test", company_id: "7" });
  });

  it("keeps Chat Box configuration browser-local and labels that boundary", () => {
    renderInRouter(<ChatWidgetPage embedded />);
    fireEvent.change(screen.getByLabelText("Chat title"), { target: { value: "Property care" } });

    expect(screen.getByRole("note")).toHaveTextContent(/local to this browser/i);
    expect(window.localStorage.getItem("supportConsole_widgetConfig")).toContain("Property care");
  });

  it("saves the selected Open Hours profile to its existing API", async () => {
    render(<BusinessHoursPage embedded />);
    fireEvent.click(await screen.findByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(api.updateBusinessHoursProfile).toHaveBeenCalledWith(expect.objectContaining({ id: 1, timezone: "Asia/Kolkata" })));
    expect(screen.getByRole("status")).toHaveTextContent("Business hours saved");
  });

  it("keeps Saved Replies filters and editor token text intact", async () => {
    render(<MacrosPage embedded />);
    expect(await screen.findByRole("heading", { name: "Saved Replies", level: 1 })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Search saved replies" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Manage" }));
    expect(screen.getByLabelText("Response template")).toHaveValue("Hello {{customer_first_name}}");
  });

  it("keeps tag deletion on the current tag API and retains ticket counts", async () => {
    render(<ManageTagsPage embedded />);
    expect(await screen.findByText("2 tickets")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(api.deleteAdminTag).toHaveBeenCalledWith(1));
  });

  it("creates a user record without claiming an email invitation was sent", async () => {
    render(<UsersPage embedded />);
    fireEvent.click(await screen.findByRole("button", { name: /Create user/ }));
    fireEvent.change(screen.getByLabelText("Full name"), { target: { value: "New User" } });
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "new@example.test" } });
    fireEvent.click(screen.getByRole("button", { name: "Create user" }));

    await waitFor(() => expect(api.createAdminUser).toHaveBeenCalledOnce());
    expect(screen.getByRole("status")).toHaveTextContent(/No invitation email was sent/i);
  });

  it("submits a blank configured API key to preserve the server-side secret", async () => {
    renderInRouter(<CSApiSettingsPage embedded />);
    expect(await screen.findByText(/A key is configured/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Save settings" }));

    await waitFor(() => expect(api.saveCSApiSettings).toHaveBeenCalledWith({ api_key: "", base_url: "https://example.test", company_id: 7 }));
    expect(screen.getByLabelText("API key")).toHaveValue("");
  });
});
