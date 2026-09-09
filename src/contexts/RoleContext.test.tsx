import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";

vi.mock("../lib/api", () => ({
  getWorkspaceSession: vi.fn(),
  loginWorkspace: vi.fn(),
  logoutWorkspace: vi.fn().mockResolvedValue({})
}));

import { getWorkspaceSession, loginWorkspace } from "../lib/api";
import { RoleProvider, useRole } from "./RoleContext";

const wrapper = ({ children }: { children: ReactNode }) => <RoleProvider>{children}</RoleProvider>;

describe("RoleProvider server-verified sessions", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.resetAllMocks();
    vi.mocked(getWorkspaceSession).mockRejectedValue(new Error("unauthorized"));
  });

  it("does not trust a forged user stored without a server token", () => {
    localStorage.setItem("supportConsole_authUser", JSON.stringify({ email: "attacker@example.com", name: "Attacker", role: "admin" }));
    const { result } = renderHook(() => useRole(), { wrapper });
    expect(result.current.isAuthenticated).toBe(false);
  });

  it("uses the role returned by login rather than a client-selected role", async () => {
    vi.mocked(loginWorkspace).mockResolvedValue({
      user: { id: 3, email: "agent@example.com", name: "Agent", role: "agent", status: "Active", team: "Support" }
    });
    const { result } = renderHook(() => useRole(), { wrapper });
    await act(async () => { await result.current.login("agent@example.com", "password"); });
    act(() => result.current.setRole("admin"));
    expect(result.current.role).toBe("agent");
    expect(localStorage.getItem("supportConsole_accessToken")).toBeNull();
  });

  it("clears a rejected persisted session", async () => {
    localStorage.setItem("supportConsole_accessToken", "expired");
    localStorage.setItem("supportConsole_authUser", JSON.stringify({ email: "owner@example.com", name: "Owner", role: "owner" }));
    vi.mocked(getWorkspaceSession).mockRejectedValue(new Error("unauthorized"));
    const { result } = renderHook(() => useRole(), { wrapper });
    await act(async () => { await Promise.resolve(); });
    expect(result.current.isAuthenticated).toBe(false);
    expect(localStorage.getItem("supportConsole_accessToken")).toBeNull();
  });
});
