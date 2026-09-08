import { useEffect, useMemo, useState } from "react";
import { createAdminUser, getAdminUsers, updateAdminUser } from "../lib/api";
import type { SupportWorkspaceUser } from "../types";

type UsersPageProps = {
  embedded?: boolean;
};

type RoleId = SupportWorkspaceUser["role"];

type RoleDefinition = {
  description: string;
  id: RoleId;
  permissions: string[];
  title: string;
};

const roleDefinitions: RoleDefinition[] = [
  {
    id: "owner",
    title: "Owner",
    description: "Full account ownership, billing oversight, and role management control.",
    permissions: [
      "Manage billing and storefront settings",
      "Create and remove admins",
      "Manage chat widget installation",
      "Upload and publish AI knowledge documents"
    ]
  },
  {
    id: "admin",
    title: "Admin",
    description: "Operational admin with inbox, automation, analytics, and workspace configuration access.",
    permissions: [
      "Manage macros, tags, and schedules",
      "Configure article-first chat settings",
      "Invite and edit agents",
      "Review analytics and queue performance",
      "Train the AI with internal knowledge uploads"
    ]
  },
  {
    id: "agent",
    title: "Agent",
    description: "Frontline support role focused on inbox handling, notes, and customer communication.",
    permissions: [
      "Reply to tickets and chats",
      "Use macros and support articles",
      "Apply macros and tags",
      "View assigned analytics dashboards"
    ]
  }
];

function roleToBadgeColor(role: RoleId) {
  if (role === "owner") {
    return "#8b5cf6";
  }

  if (role === "admin") {
    return "#2563eb";
  }

  return "#22c55e";
}

function statusToTone(status: SupportWorkspaceUser["status"]) {
  if (status === "Active") {
    return "success";
  }

  if (status === "Invited") {
    return "pending";
  }

  return "muted";
}

export function UsersPage({ embedded = false }: UsersPageProps) {
  const [users, setUsers] = useState<SupportWorkspaceUser[]>([]);
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState<"all" | RoleId>("all");
  const [selectedUserId, setSelectedUserId] = useState<number>(0);
  const [manageMessage, setManageMessage] = useState("");
  const [error, setError] = useState("");
  const [isWorking, setIsWorking] = useState(false);
  const [surface, setSurface] = useState<"list" | "invite" | "manage">("list");
  const [inviteDraft, setInviteDraft] = useState({
    email: "",
    name: "",
    role: "agent" as RoleId,
    team: "Support"
  });

  useEffect(() => {
    let cancelled = false;

    async function hydrate() {
      try {
        setError("");
        const response = await getAdminUsers();

        if (!cancelled) {
          setUsers(response.users);
          setSelectedUserId((current) => current || response.users[0]?.id || 0);
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : "Unable to load users.");
        }
      }
    }

    void hydrate();

    return () => {
      cancelled = true;
    };
  }, []);

  const filteredUsers = useMemo(() => {
    const searchValue = search.trim().toLowerCase();

    return users.filter((user) => {
      const matchesRole = roleFilter === "all" || user.role === roleFilter;
      const matchesSearch =
        !searchValue ||
        `${user.name} ${user.email} ${user.team} ${user.role}`.toLowerCase().includes(searchValue);

      return matchesRole && matchesSearch;
    });
  }, [roleFilter, search, users]);

  const selectedUser = users.find((user) => user.id === selectedUserId) ?? filteredUsers[0] ?? users[0];
  function updateLocalUser(userId: number, patch: Partial<SupportWorkspaceUser>) {
    setUsers((current) =>
      current.map((user) =>
        user.id === userId
          ? {
              ...user,
              ...patch
            }
          : user
      )
    );
  }

  function openInviteSurface() {
    setInviteDraft({
      email: "",
      name: "",
      role: "agent",
      team: "Support"
    });
    setManageMessage("");
    setSurface("invite");
  }

  function openManageSurface(userId: number) {
    setSelectedUserId(userId);
    setManageMessage("");
    setSurface("manage");
  }

  async function handleInviteUser() {
    if (!inviteDraft.name.trim() || !inviteDraft.email.trim()) {
      return;
    }

    try {
      setIsWorking(true);
      setError("");
      const response = await createAdminUser({
        email: inviteDraft.email.trim(),
        name: inviteDraft.name.trim(),
        role: inviteDraft.role,
        team: inviteDraft.team.trim() || "Support"
      });

      setUsers((current) => [response.user, ...current]);
      setSelectedUserId(response.user.id);
      setManageMessage(`Invite prepared for ${response.user.name}.`);
      setSurface("manage");
      setInviteDraft({
        email: "",
        name: "",
        role: "agent",
        team: "Support"
      });
    } catch (inviteError) {
      setError(inviteError instanceof Error ? inviteError.message : "Unable to invite user.");
    } finally {
      setIsWorking(false);
    }
  }

  function handleManageAction(action: "reset" | "resend" | "toggle-status") {
    if (!selectedUser) {
      return;
    }

    if (action === "toggle-status") {
      const nextStatus =
        selectedUser.status === "Suspended"
          ? "Active"
          : selectedUser.status === "Invited"
            ? "Active"
            : "Suspended";

      updateLocalUser(selectedUser.id, { status: nextStatus });
      setManageMessage(
        nextStatus === "Suspended"
          ? `${selectedUser.name} has been suspended.`
          : `${selectedUser.name} is now ${nextStatus.toLowerCase()}.`
      );
      return;
    }

    setManageMessage(
      action === "resend"
        ? `Invitation resent to ${selectedUser.email}.`
        : `Password reset link sent to ${selectedUser.email}.`
    );
  }

  async function handleSaveSelectedUser() {
    if (!selectedUser) {
      return;
    }

    try {
      setIsWorking(true);
      setError("");
      const response = await updateAdminUser(selectedUser.id, {
        name: selectedUser.name,
        role: selectedUser.role,
        status: selectedUser.status,
        team: selectedUser.team
      });

      setUsers((current) =>
        current.map((user) => (user.id === response.user.id ? response.user : user))
      );
      setManageMessage("Changes saved.");
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Unable to save user changes.");
    } finally {
      setIsWorking(false);
    }
  }

  return (
    <div className="stack-page">
      {!embedded ? (
        <section className="hero-card compact">
          <div className="hero-kicker">Team Access</div>
          <h2>Users</h2>
          <p>Keep teammate access easier to scan with a simple list view and focused manage panels.</p>
        </section>
      ) : null}

      {error ? <div className="banner-error">{error}</div> : null}

      {surface === "list" ? (
        <section className="plain-card workspace-directory-shell">
          <div className="workspace-directory-header">
            <div>
              <div className="section-title">Users</div>
              <div className="section-copy">{filteredUsers.length} teammates in the support workspace</div>
            </div>

            <button className="primary-button management-plus-button" onClick={openInviteSurface} type="button">
              <span>+</span>
              Invite user
            </button>
          </div>

          <div className="toolbar-row wrap">
            <input
              className="rail-search wide"
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search by name, email, or team"
              value={search}
            />
            <select
              className="field-input"
              onChange={(event) => setRoleFilter(event.target.value as "all" | RoleId)}
              value={roleFilter}
            >
              <option value="all">All roles</option>
              {roleDefinitions.map((role) => (
                <option key={role.id} value={role.id}>
                  {role.title}
                </option>
              ))}
            </select>
          </div>

          <div className="workspace-directory-grid">
            {filteredUsers.map((user) => (
              <article className="workspace-record-card users-record-card" key={user.id}>
                <div className="workspace-record-icon">{user.name.slice(0, 1).toUpperCase()}</div>
                <div className="workspace-record-main">
                  <div className="workspace-record-title-row">
                    <strong>{user.name}</strong>
                  </div>
                  <div className="workspace-record-copy">{user.email}</div>
                  <div className="badge-row compact workspace-record-tag-row">
                    <span className="badge-chip dark">
                      <span className="badge-dot" style={{ backgroundColor: roleToBadgeColor(user.role) }} />
                      {roleDefinitions.find((role) => role.id === user.role)?.title}
                    </span>
                    <span className="badge-chip dark">
                      <span className="badge-dot" style={{ backgroundColor: "#94a3b8" }} />
                      {user.team}
                    </span>
                  </div>
                </div>
                <div className="workspace-record-meta users-record-meta">
                  <span className={`users-status-pill users-record-status ${statusToTone(user.status)}`}>{user.status}</span>
                  <button className="ghost-button small workspace-record-manage users-record-manage" onClick={() => openManageSurface(user.id)} type="button">
                    Manage
                  </button>
                </div>
              </article>
            ))}

            {!filteredUsers.length ? <div className="empty-card">No teammates matched the current filters.</div> : null}
          </div>
        </section>
      ) : null}

      {surface === "invite" ? (
        <section className="plain-card workspace-detail-shell">
          <div className="workspace-detail-topbar">
            <div>
              <div className="workspace-detail-kicker">User workspace</div>
              <div className="section-title">Invite teammate</div>
              <div className="section-copy">Create a new support login and pre-assign the right role before they enter the workspace.</div>
            </div>

            <div className="workspace-detail-actions">
              <button className="ghost-button" onClick={() => setSurface("list")} type="button">
                Back to users
              </button>
              <button className="primary-button" disabled={isWorking} onClick={() => void handleInviteUser()} type="button">
                Send invite
              </button>
            </div>
          </div>

          <div className="editor-grid">
            <label className="field-block">
              <span>Full name</span>
              <input
                className="field-input"
                onChange={(event) => setInviteDraft((current) => ({ ...current, name: event.target.value }))}
                value={inviteDraft.name}
              />
            </label>

            <label className="field-block">
              <span>Email</span>
              <input
                className="field-input"
                onChange={(event) => setInviteDraft((current) => ({ ...current, email: event.target.value }))}
                value={inviteDraft.email}
              />
            </label>
          </div>

          <div className="editor-grid">
            <label className="field-block">
              <span>Role</span>
              <select
                className="field-input"
                onChange={(event) => setInviteDraft((current) => ({ ...current, role: event.target.value as RoleId }))}
                value={inviteDraft.role}
              >
                {roleDefinitions.map((role) => (
                  <option key={role.id} value={role.id}>
                    {role.title}
                  </option>
                ))}
              </select>
            </label>

            <label className="field-block">
              <span>Team</span>
              <input
                className="field-input"
                onChange={(event) => setInviteDraft((current) => ({ ...current, team: event.target.value }))}
                value={inviteDraft.team}
              />
            </label>
          </div>
        </section>
      ) : null}

      {surface === "manage" && selectedUser ? (
        <section className="plain-card workspace-detail-shell">
          <div className="workspace-detail-topbar">
            <div>
              <div className="workspace-detail-kicker">Access management</div>
              <div className="section-title">Manage {selectedUser.name}</div>
              <div className="section-copy">Update role, team, login status, and access actions from one focused panel.</div>
            </div>

            <div className="workspace-detail-actions">
              <button className="ghost-button" onClick={() => setSurface("list")} type="button">
                Back to users
              </button>
              <button className="primary-button" disabled={isWorking} onClick={() => void handleSaveSelectedUser()} type="button">
                Save changes
              </button>
            </div>
          </div>

          {manageMessage ? <div className="banner-success">{manageMessage}</div> : null}

          <div className="editor-grid">
            <label className="field-block">
              <span>Full name</span>
              <input
                className="field-input"
                onChange={(event) => updateLocalUser(selectedUser.id, { name: event.target.value })}
                value={selectedUser.name}
              />
            </label>

            <label className="field-block">
              <span>Email</span>
              <input className="field-input" readOnly value={selectedUser.email} />
            </label>
          </div>

          <div className="editor-grid">
            <label className="field-block">
              <span>Role</span>
              <select
                className="field-input"
                onChange={(event) => updateLocalUser(selectedUser.id, { role: event.target.value as RoleId })}
                value={selectedUser.role}
              >
                {roleDefinitions.map((role) => (
                  <option key={role.id} value={role.id}>
                    {role.title}
                  </option>
                ))}
              </select>
            </label>

            <label className="field-block">
              <span>Status</span>
              <select
                className="field-input"
                onChange={(event) =>
                  updateLocalUser(selectedUser.id, {
                    status: event.target.value as SupportWorkspaceUser["status"]
                  })
                }
                value={selectedUser.status}
              >
                <option value="Active">Active</option>
                <option value="Invited">Invited</option>
                <option value="Suspended">Suspended</option>
              </select>
            </label>
          </div>

          <label className="field-block">
            <span>Team</span>
            <input
              className="field-input"
              onChange={(event) => updateLocalUser(selectedUser.id, { team: event.target.value })}
              value={selectedUser.team}
            />
          </label>

          <div className="toolbar-row wrap">
            <button
              className="ghost-button"
              onClick={() => handleManageAction(selectedUser.status === "Invited" ? "resend" : "reset")}
              type="button"
            >
              {selectedUser.status === "Invited" ? "Resend invite" : "Send reset link"}
            </button>
            <button className="ghost-button" onClick={() => handleManageAction("toggle-status")} type="button">
              {selectedUser.status === "Suspended" ? "Reactivate user" : "Suspend user"}
            </button>
          </div>

          <div className="users-role-grid">
            {roleDefinitions.map((role) => (
              <div className={`role-card${role.id === selectedUser.role ? " active" : ""}`} key={role.id}>
                <div className="role-card-head">
                  <span className="badge-chip dark">
                    <span className="badge-dot" style={{ backgroundColor: roleToBadgeColor(role.id) }} />
                    {role.title}
                  </span>
                </div>
                <p>{role.description}</p>
                <ul className="flat-list">
                  {role.permissions.map((permission) => (
                    <li key={permission}>{permission}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}
