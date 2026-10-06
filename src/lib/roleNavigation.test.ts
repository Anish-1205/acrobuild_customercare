import { describe, expect, it } from "vitest";
import {
  getRolePanelPath,
  getStaffNavigationItems,
  getWorkspacePanelFromLocation
} from "./roleNavigation";

describe("staff role navigation", () => {
  it("keeps the existing role-visible destinations", () => {
    expect(getStaffNavigationItems("admin").map((item) => item.panel)).toEqual([
      "ai-agent",
      "inbox",
      "analytics",
      "ticket-dashboard",
      "articles",
      "business-hours",
      "macros",
      "manage-tags",
      "users",
      "api-activity",
      "data-api-logs",
      "cs-api-settings"
    ]);
    expect(getStaffNavigationItems("owner").map((item) => item.panel)).toEqual([
      "ai-agent",
      "inbox",
      "analytics",
      "ticket-dashboard",
      "articles",
      "business-hours",
      "macros",
      "manage-tags",
      "users"
    ]);
    expect(getStaffNavigationItems("agent").map((item) => item.panel)).toEqual(["inbox"]);
  });

  it("preserves inbox paths, query parameters, and the admin rules special case", () => {
    expect(getRolePanelPath("admin", "inbox")).toBe("/admin/inbox");
    expect(getRolePanelPath("owner", "inbox")).toBe("/owner/inbox");
    expect(getRolePanelPath("agent", "inbox")).toBe("/agent/inbox");
    expect(getRolePanelPath("admin", "analytics")).toBe("/admin/workspace?panel=analytics");
    expect(getRolePanelPath("owner", "analytics")).toBe("/owner/inbox?panel=analytics");
    expect(getRolePanelPath("admin", "rules")).toBe("/admin/workspace");
  });

  it("preserves direct URL defaults and panel parsing", () => {
    expect(getWorkspacePanelFromLocation("/admin/workspace", "")).toBe("ai-agent");
    expect(getWorkspacePanelFromLocation("/admin/inbox", "")).toBe("inbox");
    expect(getWorkspacePanelFromLocation("/owner/inbox", "?panel=articles")).toBe("articles");
    expect(getWorkspacePanelFromLocation("/agent/inbox", "")).toBe("inbox");
    expect(getWorkspacePanelFromLocation("/admin/automation", "")).toBeNull();
  });
});
