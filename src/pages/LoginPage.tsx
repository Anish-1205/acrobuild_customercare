import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useRole } from "../contexts/RoleContext";
import { getRoleHomePath } from "../lib/roleNavigation";
import { AcrobuildLogo } from "../components/AcrobuildLogo";

const demoAccounts = [
  {
    role: "Admin",
    email: "admin@acrobuild.com",
    description: "Full workspace access, analytics, routing, and macros."
  },
  {
    role: "Owner",
    email: "owner@acrobuild.com",
    description: "Project oversight, escalations, and executive ticket visibility."
  },
  {
    role: "Agent",
    email: "agent@acrobuild.com",
    description: "Fast inbox triage, customer replies, and assignment follow-through."
  }
] as const;

function getRememberedEmail() {
  if (typeof window === "undefined") {
    return "";
  }

  const rememberedEmail = localStorage.getItem("rememberedEmail") || "";
  const normalizedEmail = rememberedEmail.trim().toLowerCase();
  const localPart = normalizedEmail.split("@")[0] ?? "";

  if (localPart === "admin") {
    return "admin@acrobuild.com";
  }

  if (localPart === "agent") {
    return "agent@acrobuild.com";
  }

  if (localPart === "owner") {
    return "owner@acrobuild.com";
  }

  return rememberedEmail;
}

export function LoginPage() {
  const navigate = useNavigate();
  const { login } = useRole();
  const [email, setEmail] = useState(getRememberedEmail());
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(Boolean(getRememberedEmail()));
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  function handleDemoSelect(nextEmail: string) {
    setEmail(nextEmail);
    setPassword("demo@123");
    setError("");
  }

  function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setIsSubmitting(true);
    setError("");

    const matchedUser = login(email, password);

    if (!matchedUser) {
      setError("Invalid email or password");
      setIsSubmitting(false);
      return;
    }

    if (rememberMe) {
      localStorage.setItem("rememberedEmail", email.trim().toLowerCase());
    } else {
      localStorage.removeItem("rememberedEmail");
    }

    navigate(getRoleHomePath(matchedUser.role), { replace: true });
  }

  return (
    <div className="login-page">
      <div className="login-shell">
        <aside className="login-visual-panel">
          <img
            alt="Acrobuild support and project operations team collaborating at a workspace"
            className="login-visual-image"
            src="/images/real-world/workspace-ops.png"
          />
          <div className="login-visual-copy">
            <span className="login-kicker">Acrobuild live workspace</span>
            <h2>One workspace for every project conversation.</h2>
            <p>
              Support, routing, and handover updates stay visible to the whole team,
              so nobody loses the thread.
            </p>
            <div className="login-visual-pill-row">
              <span>Buyer updates</span>
              <span>Internal routing</span>
              <span>Handover support</span>
            </div>
            <div className="login-visual-stat-grid">
              <div className="login-visual-stat">
                <strong>Shared context</strong>
                <span>Every ticket keeps history, ownership, and next steps in view.</span>
              </div>
              <div className="login-visual-stat">
                <strong>Faster routing</strong>
                <span>Priority cues and role-based handoffs stay clear.</span>
              </div>
            </div>
          </div>
        </aside>

        <div className="login-container">
          <div className="login-header">
            <AcrobuildLogo subtitle="Workspace access" />
            <div className="login-intro">
              <span className="login-kicker">Secure sign in</span>
              <h1>Welcome back</h1>
              <p>
                Sign in to the support workspace to review conversations, route tickets,
                and keep project follow-up moving.
              </p>
            </div>
          </div>

          <div className="login-demo-panel">
            <div className="login-demo-copy">
              <strong>Demo access</strong>
              <span>Any role below uses the shared password <code>demo@123</code>.</span>
            </div>
            <div className="login-demo-list">
              {demoAccounts.map((account) => {
                const isActive = email.trim().toLowerCase() === account.email;

                return (
                  <button
                    key={account.email}
                    type="button"
                    className={`login-demo-button${isActive ? " active" : ""}`}
                    onClick={() => handleDemoSelect(account.email)}
                  >
                    <strong>{account.role}</strong>
                    <span>{account.email}</span>
                    <small>{account.description}</small>
                  </button>
                );
              })}
            </div>
          </div>

          <form className="login-form" onSubmit={handleLogin}>
            <div className="form-group">
              <label htmlFor="email">Email</label>
              <input
                id="email"
                className="form-input"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="admin@acrobuild.com"
                required
              />
            </div>

            <div className="form-group">
              <label htmlFor="password">Password</label>
              <div className="login-password-field">
                <input
                  id="password"
                  className="form-input"
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter your password"
                  required
                />
                <button
                  type="button"
                  className="login-password-toggle"
                  onClick={() => setShowPassword((currentValue) => !currentValue)}
                >
                  {showPassword ? "Hide" : "Show"}
                </button>
              </div>
            </div>

            {error ? <div className="error-message">{error}</div> : null}

            <div className="login-options">
              <label className="remember-me">
                <input
                  type="checkbox"
                  checked={rememberMe}
                  onChange={(e) => setRememberMe(e.target.checked)}
                />
                <span>Remember me</span>
              </label>
              <span className="login-support-copy">Need a reset? Contact your workspace owner.</span>
            </div>

            <button
              type="submit"
              className="sign-in-button"
              disabled={isSubmitting}
            >
              {isSubmitting ? "Signing in..." : "Sign in to workspace"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
