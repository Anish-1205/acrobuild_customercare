import type { RoleId } from "../contexts/RoleContext";

export type WorkspacePanelId =
  | "ai-agent"
  | "analytics"
  | "articles"
  | "business-hours"
  | "chat-widget"
  | "inbox"
  | "knowledge-base"
  | "macros"
  | "manage-tags"
  | "order-track"
  | "products"
  | "rules"
  | "shopping-assistant"
  | "support-actions"
  | "ticket-dashboard"
  | "users";

type RoleExperience = {
  homePath: string;
  inboxPath: string;
  label: string;
  shortLabel: string;
  summary: string;
  workspacePath: string;
};

const allWorkspacePanels = new Set<WorkspacePanelId>([
  "ai-agent",
  "analytics",
  "articles",
  "business-hours",
  "chat-widget",
  "inbox",
  "knowledge-base",
  "macros",
  "manage-tags",
  "order-track",
  "products",
  "rules",
  "shopping-assistant",
  "support-actions",
  "ticket-dashboard",
  "users"
]);

const rolePanelAccessMap: Record<RoleId, Set<WorkspacePanelId>> = {
  admin: new Set(allWorkspacePanels),
  owner: new Set(allWorkspacePanels),
  agent: new Set(["inbox"])
};

const workspaceAliasMap: Record<string, WorkspacePanelId> = {
  "/ai-agent": "ai-agent",
  "/admin/analytics": "analytics",
  "/articles": "articles",
  "/business-hours": "business-hours",
  "/chat-widget": "chat-widget",
  "/knowledge-base": "knowledge-base",
  "/macros": "macros",
  "/manage-tags": "manage-tags",
  "/order-track": "order-track",
  "/products": "products",
  "/shopping-assistant": "shopping-assistant",
  "/support-actions": "support-actions",
  "/ticket-dashboard": "ticket-dashboard",
  "/workflow-rules": "rules",
  "/users": "users"
};

export const roleExperienceMap: Record<RoleId, RoleExperience> = {
  admin: {
    homePath: "/admin/workspace",
    inboxPath: "/admin/inbox",
    label: "Admin Command Center",
    shortLabel: "Admin",
    summary: "Automation, reporting, routing, and every workspace control in one place.",
    workspacePath: "/admin/workspace"
  },
  owner: {
    homePath: "/owner/inbox",
    inboxPath: "/owner/inbox",
    label: "Owner Oversight Hub",
    shortLabel: "Owner",
    summary: "Full workspace access across inbox, reporting, routing, content, and settings.",
    workspacePath: "/owner/inbox"
  },
  agent: {
    homePath: "/agent/inbox",
    inboxPath: "/agent/inbox",
    label: "Agent Service Desk",
    shortLabel: "Agent",
    summary: "A faster frontline workspace centered on queue handling, notes, and customer replies.",
    workspacePath: "/agent/inbox"
  }
};

export function getRoleHomePath(role: RoleId) {
  return roleExperienceMap[role].homePath;
}

export function canRoleAccessPanel(role: RoleId, panel: WorkspacePanelId) {
  return rolePanelAccessMap[role].has(panel);
}

export function getRolePanelPath(role: RoleId, panel: WorkspacePanelId = "inbox") {
  const roleExperience = roleExperienceMap[role];

  if (!canRoleAccessPanel(role, panel)) {
    return getRoleHomePath(role);
  }

  if (panel === "inbox") {
    return roleExperience.inboxPath;
  }

  if (role === "admin" && panel === "rules") {
    return roleExperience.workspacePath;
  }

  return `${roleExperience.workspacePath}?panel=${panel}`;
}

export function getWorkspacePanelFromLocation(pathname: string, search: string) {
  if (pathname.endsWith("/inbox") || pathname.endsWith("/workspace")) {
    const panel = new URLSearchParams(search).get("panel");

    if (panel && allWorkspacePanels.has(panel as WorkspacePanelId)) {
      return panel as WorkspacePanelId;
    }

    if (pathname.endsWith("/workspace")) {
      return "ai-agent";
    }

    return "inbox";
  }

  return workspaceAliasMap[pathname] ?? null;
}
