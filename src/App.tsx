import type { ReactElement } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useRole, type RoleId } from "./contexts/RoleContext";
import { AppShell } from "./components/AppShell";
import {
  getRoleHomePath,
  getRolePanelPath,
  type WorkspacePanelId
} from "./lib/roleNavigation";
import { AdminInboxPage } from "./pages/AdminInboxPage";
import { OwnerInboxPage } from "./pages/OwnerInboxPage";
import { AgentInboxPage } from "./pages/AgentInboxPage";
import { CustomerHomePage } from "./pages/CustomerHomePage";
import { ApiActivityPage } from "./pages/ApiActivityPage";
import { DataApiLogsPage } from "./pages/DataApiLogsPage";
import { CustomerLookupPage } from "./pages/CustomerLookupPage";
import { LoginPage } from "./pages/LoginPage";
import { AutomationPage } from "./pages/AutomationPage";

function RoleRoute({
  allowedRole,
  element
}: {
  allowedRole: RoleId;
  element: ReactElement;
}) {
  const { isAuthenticated, role } = useRole();

  if (!isAuthenticated) {
    return <Navigate replace to="/login" />;
  }

  if (role !== allowedRole) {
    return <Navigate replace to={getRoleHomePath(role)} />;
  }

  return element;
}

function RoleRedirect({ panel }: { panel?: WorkspacePanelId }) {
  const { isAuthenticated, role } = useRole();

  if (!isAuthenticated) {
    return <Navigate replace to="/login" />;
  }

  return <Navigate replace to={panel ? getRolePanelPath(role, panel) : getRoleHomePath(role)} />;
}

function ProtectedAppShell() {
  const { isAuthenticated } = useRole();

  if (!isAuthenticated) {
    return <Navigate replace to="/login" />;
  }

  return <AppShell />;
}

function LoginRoute() {
  const { isAuthenticated, role } = useRole();

  if (isAuthenticated) {
    return <Navigate replace to={getRoleHomePath(role)} />;
  }

  return <LoginPage />;
}

export default function App() {
  return (
    <Routes>
      <Route element={<CustomerHomePage />} path="/home" />
      <Route element={<CustomerHomePage />} path="/home/about" />
      <Route element={<ApiActivityPage />} path="/home/api-activity" />
      <Route element={<DataApiLogsPage />} path="/home/data-api-logs" />
      <Route element={<CustomerLookupPage />} path="/home/project-support" />
      <Route element={<CustomerLookupPage />} path="/home/order-lookup" />
      <Route element={<CustomerHomePage />} path="/home/categories/:categorySlug" />
      <Route element={<CustomerHomePage />} path="/home/articles/:articleSlug" />
      <Route element={<LoginRoute />} path="/login" />
      <Route element={<ProtectedAppShell />} path="/">
        <Route element={<RoleRoute allowedRole="admin" element={<AutomationPage />} />} path="admin/automation" />
        <Route element={<RoleRoute allowedRole="owner" element={<AutomationPage />} />} path="owner/automation" />
        <Route element={<RoleRedirect />} index />
        <Route element={<RoleRedirect />} path="admin" />
        <Route element={<RoleRedirect />} path="owner" />
        <Route element={<RoleRedirect />} path="agent" />
        <Route element={<RoleRoute allowedRole="admin" element={<AdminInboxPage />} />} path="admin/workspace" />
        <Route element={<RoleRoute allowedRole="admin" element={<AdminInboxPage />} />} path="admin/inbox" />
        <Route element={<RoleRoute allowedRole="owner" element={<OwnerInboxPage />} />} path="owner/inbox" />
        <Route element={<RoleRoute allowedRole="agent" element={<AgentInboxPage />} />} path="agent/inbox" />
        <Route element={<RoleRedirect panel="ai-agent" />} path="ai-agent" />
        <Route element={<RoleRedirect panel="business-hours" />} path="business-hours" />
        <Route element={<RoleRedirect panel="analytics" />} path="admin/analytics" />
        <Route element={<RoleRedirect panel="articles" />} path="articles" />
        <Route element={<RoleRedirect panel="knowledge-base" />} path="knowledge-base" />
        <Route element={<RoleRedirect panel="rules" />} path="workflow-rules" />
        <Route element={<RoleRedirect panel="chat-widget" />} path="chat-widget" />
        <Route element={<RoleRedirect panel="macros" />} path="macros" />
        <Route element={<RoleRedirect panel="manage-tags" />} path="manage-tags" />
        <Route element={<RoleRedirect panel="ticket-dashboard" />} path="ticket-dashboard" />
        <Route element={<RoleRedirect />} path="customer-portal" />
        <Route element={<RoleRedirect panel="order-track" />} path="order-track" />
        <Route element={<RoleRedirect panel="users" />} path="users" />
        <Route element={<RoleRedirect />} path="chat-ui" />
        <Route element={<RoleRedirect />} path="*" />
      </Route>
    </Routes>
  );
}
