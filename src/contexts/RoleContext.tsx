import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { getWorkspaceSession, loginWorkspace, logoutWorkspace } from "../lib/api";

export type RoleId = "admin" | "owner" | "agent";

export type AuthUser = {
  email: string;
  name: string;
  role: RoleId;
};

export interface RolePermissions {
  canAccessInbox: boolean;
  canAccessAnalytics: boolean;
  canAccessArticles: boolean;
  canAccessBusinessHours: boolean;
  canAccessChatWidget: boolean;
  canAccessDashboard: boolean;
  canAccessSearch: boolean;
  canAccessMacros: boolean;
  canAccessTags: boolean;
  canAccessUsers: boolean;
  canAccessOrderTrack: boolean;
  canViewAllTickets: boolean;
  canAssignTickets: boolean;
  canManageUsers: boolean;
  canEditMacros: boolean;
  canEditTags: boolean;
  canAccessSettings: boolean;
}

const rolePermissionsMap: Record<RoleId, RolePermissions> = {
  admin: {
    canAccessInbox: true,
    canAccessAnalytics: true,
    canAccessArticles: true,
    canAccessBusinessHours: true,
    canAccessChatWidget: true,
    canAccessDashboard: true,
    canAccessSearch: true,
    canAccessMacros: true,
    canAccessTags: true,
    canAccessUsers: true,
    canAccessOrderTrack: true,
    canViewAllTickets: true,
    canAssignTickets: true,
    canManageUsers: true,
    canEditMacros: true,
    canEditTags: true,
    canAccessSettings: true
  },
  owner: {
    canAccessInbox: true,
    canAccessAnalytics: true,
    canAccessArticles: true,
    canAccessBusinessHours: true,
    canAccessChatWidget: true,
    canAccessDashboard: true,
    canAccessSearch: true,
    canAccessMacros: true,
    canAccessTags: true,
    canAccessUsers: true,
    canAccessOrderTrack: true,
    canViewAllTickets: true,
    canAssignTickets: true,
    canManageUsers: true,
    canEditMacros: true,
    canEditTags: true,
    canAccessSettings: true
  },
  agent: {
    canAccessInbox: true,
    canAccessAnalytics: false,
    canAccessArticles: false,
    canAccessBusinessHours: false,
    canAccessChatWidget: false,
    canAccessDashboard: false,
    canAccessSearch: false,
    canAccessMacros: false,
    canAccessTags: false,
    canAccessUsers: false,
    canAccessOrderTrack: false,
    canViewAllTickets: false,
    canAssignTickets: false,
    canManageUsers: false,
    canEditMacros: false,
    canEditTags: false,
    canAccessSettings: false
  }
};

interface RoleContextType {
  currentUser: AuthUser | null;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<AuthUser | null>;
  logout: () => void;
  role: RoleId;
  setRole: (role: RoleId) => void;
  permissions: RolePermissions;
}

const RoleContext = createContext<RoleContextType | undefined>(undefined);

const ROLE_STORAGE_KEY = "supportConsole_userRole";
const USER_STORAGE_KEY = "supportConsole_authUser";
const TOKEN_STORAGE_KEY = "supportConsole_accessToken";

export function RoleProvider({ children }: { children: ReactNode }) {
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);

  const [role, setRoleState] = useState<RoleId>(() => {
    if (typeof window === "undefined") {
      return "admin";
    }

    const storedUser = localStorage.getItem(USER_STORAGE_KEY);

    if (storedUser) {
      try {
        return (JSON.parse(storedUser) as AuthUser).role;
      } catch {
        // Fall back to the persisted role key below.
      }
    }

    const storedRole = localStorage.getItem(ROLE_STORAGE_KEY);
    return (storedRole as RoleId) || "admin";
  });

  const setRole = (newRole: RoleId) => {
    if (!currentUser || currentUser.role !== newRole) {
      return;
    }
    setRoleState(newRole);
    localStorage.setItem(ROLE_STORAGE_KEY, newRole);
  };

  useEffect(() => {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    getWorkspaceSession().then(({ user }) => {
      const verifiedUser: AuthUser = { email: user.email, name: user.name, role: user.role };
      setCurrentUser(verifiedUser);
      setRoleState(verifiedUser.role);
      localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(verifiedUser));
    }).catch(() => { setCurrentUser(null); });
  }, []);

  const login = async (email: string, password: string) => {
    try {
      const response = await loginWorkspace(email, password);
      const nextUser: AuthUser = {
        email: response.user.email,
        name: response.user.name,
        role: response.user.role
      };
      setCurrentUser(nextUser);
      setRoleState(nextUser.role);
      localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(nextUser));
      localStorage.setItem(ROLE_STORAGE_KEY, nextUser.role);
      return nextUser;
    } catch {
      return null;
    }
  };

  const logout = () => {
    void logoutWorkspace().catch(() => undefined);
    setCurrentUser(null);
    setRoleState("admin");
    localStorage.removeItem(USER_STORAGE_KEY);
    localStorage.removeItem(ROLE_STORAGE_KEY);
    localStorage.removeItem(TOKEN_STORAGE_KEY);
  };

  return (
    <RoleContext.Provider
      value={{
        currentUser,
        isAuthenticated: Boolean(currentUser),
        login,
        logout,
        role,
        setRole,
        permissions: rolePermissionsMap[role]
      }}
    >
      {children}
    </RoleContext.Provider>
  );
}

export function useRole() {
  const context = useContext(RoleContext);
  if (!context) {
    throw new Error("useRole must be used within RoleProvider");
  }
  return context;
}
