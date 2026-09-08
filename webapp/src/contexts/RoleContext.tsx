import { createContext, useContext, useState, ReactNode } from "react";

export type RoleId = "admin" | "owner" | "agent";

export type AuthUser = {
  email: string;
  name: string;
  password: string;
  role: RoleId;
};

const demoEmailByLocalPart: Record<string, string> = {
  admin: "admin@acrobuild.com",
  agent: "agent@acrobuild.com",
  owner: "owner@acrobuild.com"
};

function normalizeDemoEmail(email: string) {
  const normalizedEmail = email.trim().toLowerCase();
  const localPart = normalizedEmail.split("@")[0] ?? "";
  return demoEmailByLocalPart[localPart] ?? normalizedEmail;
}

function normalizeStoredUser(user: Omit<AuthUser, "password">) {
  return {
    ...user,
    email: normalizeDemoEmail(user.email)
  };
}

export const demoAccounts: AuthUser[] = [
  {
    email: "owner@acrobuild.com",
    name: "Michael Ross",
    password: "demo@123",
    role: "owner"
  },
  {
    email: "admin@acrobuild.com",
    name: "Sarah Khan",
    password: "demo@123",
    role: "admin"
  },
  {
    email: "agent@acrobuild.com",
    name: "John Lewis",
    password: "demo@123",
    role: "agent"
  }
];

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
  currentUser: Omit<AuthUser, "password"> | null;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Omit<AuthUser, "password"> | null;
  logout: () => void;
  role: RoleId;
  setRole: (role: RoleId) => void;
  permissions: RolePermissions;
}

const RoleContext = createContext<RoleContextType | undefined>(undefined);

const ROLE_STORAGE_KEY = "supportConsole_userRole";
const USER_STORAGE_KEY = "supportConsole_authUser";

export function RoleProvider({ children }: { children: ReactNode }) {
  const [currentUser, setCurrentUser] = useState<Omit<AuthUser, "password"> | null>(() => {
    if (typeof window === "undefined") {
      return null;
    }

    try {
      const rawUser = localStorage.getItem(USER_STORAGE_KEY);

      if (!rawUser) {
        return null;
      }

      return normalizeStoredUser(JSON.parse(rawUser) as Omit<AuthUser, "password">);
    } catch {
      return null;
    }
  });

  const [role, setRoleState] = useState<RoleId>(() => {
    if (typeof window === "undefined") {
      return "admin";
    }

    const storedUser = localStorage.getItem(USER_STORAGE_KEY);

    if (storedUser) {
      try {
        return normalizeStoredUser(JSON.parse(storedUser) as Omit<AuthUser, "password">).role;
      } catch {
        // Fall back to the persisted role key below.
      }
    }

    const storedRole = localStorage.getItem(ROLE_STORAGE_KEY);
    return (storedRole as RoleId) || "admin";
  });

  const setRole = (newRole: RoleId) => {
    setRoleState(newRole);
    localStorage.setItem(ROLE_STORAGE_KEY, newRole);
  };

  const login = (email: string, password: string) => {
    const matchedAccount = demoAccounts.find(
      (account) =>
        normalizeDemoEmail(account.email) === normalizeDemoEmail(email) &&
        account.password === password
    );

    if (!matchedAccount) {
      return null;
    }

    const nextUser = {
      email: matchedAccount.email,
      name: matchedAccount.name,
      role: matchedAccount.role
    };

    setCurrentUser(nextUser);
    setRoleState(matchedAccount.role);
    localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(nextUser));
    localStorage.setItem(ROLE_STORAGE_KEY, matchedAccount.role);
    return nextUser;
  };

  const logout = () => {
    setCurrentUser(null);
    setRoleState("admin");
    localStorage.removeItem(USER_STORAGE_KEY);
    localStorage.removeItem(ROLE_STORAGE_KEY);
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
