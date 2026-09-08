import { useLocation, useNavigate } from "react-router-dom";
import { useRole, type RoleId } from "../contexts/RoleContext";
import {
  getRoleHomePath,
  getRolePanelPath,
  getWorkspacePanelFromLocation
} from "../lib/roleNavigation";

export function RoleSelector() {
  const { role, setRole } = useRole();
  const location = useLocation();
  const navigate = useNavigate();

  const roles: Array<{ id: RoleId; label: string }> = [
    { id: "admin", label: "Admin" },
    { id: "owner", label: "Owner" },
    { id: "agent", label: "Agent" }
  ];

  function handleRoleChange(nextRole: RoleId) {
    const activePanel = getWorkspacePanelFromLocation(location.pathname, location.search);
    const nextPath = activePanel
      ? getRolePanelPath(nextRole, activePanel)
      : getRoleHomePath(nextRole);

    setRole(nextRole);
    navigate(nextPath, { replace: true });
  }

  return (
    <div className="support-role-selector">
      <span className="support-role-label">View as</span>
      <select
        className="field-input support-console-input"
        value={role}
        onChange={(event) => handleRoleChange(event.target.value as RoleId)}
      >
        {roles.map((r) => (
          <option key={r.id} value={r.id}>
            {r.label}
          </option>
        ))}
      </select>
    </div>
  );
}
