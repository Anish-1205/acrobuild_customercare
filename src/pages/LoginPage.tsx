import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useRole } from "../contexts/RoleContext";
import { getRoleHomePath } from "../lib/roleNavigation";
import { AcrobuildLogo } from "../components/AcrobuildLogo";
import { Button, Card, Input } from "../components/ui";
import "./LoginPage.css";

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

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setIsSubmitting(true);
    setError("");

    const matchedUser = await login(email, password);

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
    <main className="staff-login-page">
      <div className="staff-login-shell">
        <aside className="staff-login-story" aria-label="AcroBuild workspace overview">
          <img
            alt="Acrobuild support and project operations team collaborating at a workspace"
            className="staff-login-story-image"
            src="/images/real-world/workspace-ops.png"
          />
          <div className="staff-login-story-copy">
            <span className="staff-login-eyebrow">AcroBuild live workspace</span>
            <h2>One workspace for every project conversation.</h2>
            <p>
              Support, routing, and handover updates stay visible to the whole team,
              so nobody loses the thread.
            </p>
            <ul className="staff-login-benefits">
              <li>Buyer updates</li>
              <li>Internal routing</li>
              <li>Handover support</li>
            </ul>
          </div>
        </aside>

        <Card className="staff-login-card">
          <div className="staff-login-card-inner">
            <header className="staff-login-header">
              <AcrobuildLogo className="staff-login-brand" subtitle="Workspace access" />
              <span className="staff-login-eyebrow">Secure sign in</span>
              <h1>Welcome back</h1>
              <p>
                Sign in to the support workspace to review conversations, route tickets,
                and keep project follow-up moving.
              </p>
            </header>

            <form className="staff-login-form" onSubmit={handleLogin}>
              <div className="staff-login-field">
                <label htmlFor="email">Email</label>
                <Input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="admin@acrobuild.com"
                  autoComplete="email"
                  invalid={Boolean(error)}
                  required
                />
              </div>

              <div className="staff-login-field">
                <label htmlFor="password">Password</label>
                <div className="staff-login-password-field">
                  <Input
                    id="password"
                    type={showPassword ? "text" : "password"}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Enter your password"
                    autoComplete="current-password"
                    invalid={Boolean(error)}
                    required
                  />
                  <Button
                    type="button"
                    className="staff-login-password-toggle"
                    variant="ghost"
                    aria-controls="password"
                    aria-pressed={showPassword}
                    onClick={() => setShowPassword((currentValue) => !currentValue)}
                  >
                    {showPassword ? "Hide" : "Show"}
                  </Button>
                </div>
              </div>

              {error ? (
                <div className="staff-login-error" role="alert">
                  {error}
                </div>
              ) : null}

              <div className="staff-login-options">
                <label className="staff-login-remember">
                  <input
                    type="checkbox"
                    checked={rememberMe}
                    onChange={(e) => setRememberMe(e.target.checked)}
                  />
                  <span>Remember me</span>
                </label>
                <span className="staff-login-support-copy">
                  Need a reset? Contact your workspace owner.
                </span>
              </div>

              <Button
                type="submit"
                className="staff-login-submit"
                disabled={isSubmitting}
              >
                {isSubmitting ? "Signing in..." : "Sign in to workspace"}
              </Button>
            </form>
          </div>
        </Card>
      </div>
    </main>
  );
}
