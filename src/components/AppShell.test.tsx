import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { RoleId } from "../contexts/RoleContext";
import { AppShell } from "./AppShell";

const logout = vi.fn();
const setTicketSearchQuery = vi.fn();
let currentRole: RoleId = "admin";

vi.mock("../contexts/RoleContext", () => ({
  useRole: () => ({
    currentUser: { email: `${currentRole}@acrobuild.com`, name: `${currentRole} user`, role: currentRole },
    logout,
    role: currentRole
  })
}));

vi.mock("../contexts/SearchContext", () => ({
  useSearch: () => ({
    searchSuggestions: [
      {
        id: "ticket-1",
        kind: "ticket",
        primary: "AC-1001",
        secondary: "Customer request",
        searchText: "ac-1001 customer request",
        value: "AC-1001"
      }
    ],
    ticketSearchQuery: "ac",
    setTicketSearchQuery,
    visibleTicketCount: 1
  })
}));

function renderShell(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route element={<AppShell />} path="/">
          <Route element={<div>Workspace content</div>} path="admin/workspace" />
          <Route element={<div>Workspace content</div>} path="agent/inbox" />
        </Route>
        <Route element={<div>Login</div>} path="/login" />
      </Routes>
    </MemoryRouter>
  );
}

describe("AppShell", () => {
  afterEach(cleanup);

  beforeEach(() => {
    currentRole = "admin";
    logout.mockReset();
    setTicketSearchQuery.mockReset();
  });

  it("renders the shared admin navigation with the URL-selected item active", () => {
    const { container } = renderShell("/admin/workspace?panel=analytics");

    expect(screen.getByRole("navigation", { name: "Staff navigation" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Analytics" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "API activity" })).toHaveAttribute("href", "/admin/workspace?panel=api-activity");
    expect(screen.queryByRole("link", { name: "Safety Rules" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Collapse navigation" }));
    expect(container.firstElementChild).toHaveClass("staff-navigation-collapsed");
  });

  it("keeps ticket search keyboard selection and logout behavior", async () => {
    renderShell("/admin/workspace");
    const search = screen.getByRole("combobox", { name: "Search tickets" });

    fireEvent.focus(search);
    await waitFor(() => expect(screen.getByRole("option", { name: /AC-1001/ })).toBeInTheDocument());
    fireEvent.keyDown(search, { key: "Enter" });
    expect(setTicketSearchQuery).toHaveBeenCalledWith("AC-1001");

    fireEvent.click(screen.getByRole("button", { name: "Log out" }));
    expect(logout).toHaveBeenCalledOnce();
    expect(screen.getByText("Login")).toBeInTheDocument();
  });

  it("limits the agent shell to inbox navigation", () => {
    currentRole = "agent";
    renderShell("/agent/inbox");

    expect(screen.getByRole("link", { name: "Inbox" })).toHaveAttribute("aria-current", "page");
    expect(screen.queryByRole("link", { name: "Teach AI" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Users" })).not.toBeInTheDocument();
  });
});
