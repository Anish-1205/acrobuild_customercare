import { useEffect, useMemo, useRef, useState } from "react";
import { HelpCenterBreadcrumbs } from "../components/HelpCenterUi";
import { PublicFooter, PublicHeader } from "../components/PublicShell";
import { Badge, Button, Input } from "../components/ui";
import { useRole } from "../contexts/RoleContext";
import { getVerifiedCustomerByEmail, requestEmailOtp, verifyEmailOtp } from "../lib/api";
import { getRoleHomePath } from "../lib/roleNavigation";
import type { CustomerLookupResponse, Order, SubscriptionRecord } from "../types";

type LookupMode = "email" | "sms";

const helpCenterHomePath = "/home";
const customerLookupApiBaseUrl = "http://10.10.1.23:9092";

function formatCurrency(value: unknown) {
  const amount = Number(String(value ?? "").replace(/[^0-9.-]+/g, ""));

  if (Number.isNaN(amount)) {
    return String(value ?? "N/A") || "N/A";
  }

  return new Intl.NumberFormat("en-US", {
    currency: "USD",
    style: "currency"
  }).format(amount);
}

function formatDisplayText(value: unknown, fallback: string) {
  const cleanedValue = String(value ?? "").trim();
  return cleanedValue || fallback;
}

function formatOrderDate(value: unknown) {
  const parsedDate = Date.parse(String(value ?? ""));

  if (Number.isNaN(parsedDate)) {
    return formatDisplayText(value, "N/A");
  }

  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium"
  }).format(parsedDate);
}

function getOrderItemsCount(order: Order) {
  if (Array.isArray(order.items)) {
    return order.items.length;
  }

  if (Array.isArray(order.line_items)) {
    return order.line_items.length;
  }

  if (Array.isArray(order.order_items)) {
    return order.order_items.length;
  }

  if (Array.isArray(order.products)) {
    return order.products.length;
  }

  return 0;
}

export function CustomerLookupPage() {
  const { isAuthenticated, role } = useRole();
  const otpInputRef = useRef<HTMLInputElement>(null);
  const resultsHeadingRef = useRef<HTMLHeadingElement>(null);
  const [lookupMode, setLookupMode] = useState<LookupMode>("email");
  const [email, setEmail] = useState("");
  const [smsValue, setSmsValue] = useState("");
  const [customerData, setCustomerData] = useState<CustomerLookupResponse | null>(null);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [otpCode, setOtpCode] = useState("");
  const [otpSent, setOtpSent] = useState(false);
  const [successMessage, setSuccessMessage] = useState("");

  const customerOrders = useMemo(
    () => customerData?.orders ?? customerData?.data?.orders ?? [],
    [customerData]
  );
  const customerSubscriptions = useMemo(
    () => (customerData?.subscriptions ?? []) as SubscriptionRecord[],
    [customerData]
  );
  const customerProfile = customerData?.customer ?? {};

  const isEmailMode = lookupMode === "email";
  const canSubmit = isEmailMode ? Boolean(email.trim()) : Boolean(smsValue.trim());
  const showOtpField = otpSent && isEmailMode;
  const workspaceLink = isAuthenticated ? getRoleHomePath(role) : "/login";
  const workspaceLabel = isAuthenticated ? "Open workspace" : "Sign in";

  useEffect(() => {
    if (otpSent) {
      otpInputRef.current?.focus();
    }
  }, [otpSent]);

  useEffect(() => {
    if (customerData) {
      resultsHeadingRef.current?.focus();
    }
  }, [customerData]);

  async function handleLookup(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!isEmailMode) {
      setError("SMS OTP is not configured yet. Please use email.");
      setCustomerData(null);
      return;
    }

    try {
      setIsLoading(true);
      setError("");
      setSuccessMessage("");

      if (!otpSent) {
        await requestEmailOtp(email.trim());
        setOtpSent(true);
        setSuccessMessage("A six-digit verification code was sent to " + email.trim() + ".");
        return;
      }

      const verification = await verifyEmailOtp(email.trim(), otpCode);
      const response = await getVerifiedCustomerByEmail(
        email.trim(),
        verification.access_token,
        customerLookupApiBaseUrl
      );
      const hasCustomerData =
        Boolean(response.customer) ||
        Boolean((response.orders ?? response.data?.orders ?? []).length) ||
        Boolean((response.subscriptions ?? []).length);

      if (!hasCustomerData) {
        setCustomerData(null);
        setError("No project records were found for that verified email.");
        return;
      }

      setCustomerData(response);
      setSuccessMessage("Email verified successfully.");
    } catch (lookupError) {
      setCustomerData(null);
      setError(
        lookupError instanceof Error
          ? lookupError.message
          : "We could not verify your email right now. Please try again."
      );
    } finally {
      setIsLoading(false);
    }
  }

  async function handleResendOtp() {
    try {
      setIsLoading(true);
      setError("");
      setSuccessMessage("");
      await requestEmailOtp(email.trim());
      setOtpCode("");
      setSuccessMessage("A new verification code was sent to " + email.trim() + ".");
      otpInputRef.current?.focus();
    } catch (resendError) {
      setError(resendError instanceof Error ? resendError.message : "Unable to resend the code.");
    } finally {
      setIsLoading(false);
    }
  }

  function handleEmailChange(value: string) {
    setEmail(value);
    setOtpSent(false);
    setOtpCode("");
    setCustomerData(null);
    setError("");
    setSuccessMessage("");
  }

  return (
    <div className="help-center-page help-center-content-page public-lookup-page">
      <PublicHeader workspaceLabel={workspaceLabel} workspaceLink={workspaceLink} />

      <main className="help-center-main public-lookup-main">
        <div className="help-center-shell public-lookup-shell">
          <HelpCenterBreadcrumbs
            items={[{ label: "Home", to: helpCenterHomePath }, { label: "Project support" }]}
          />

          <section aria-labelledby="public-lookup-title" className="public-lookup-card">
            <div className="public-lookup-card-head">
              <h1 id="public-lookup-title">
                Enter the email or phone number linked to your project or property inquiry
              </h1>
              <p id="public-lookup-instructions">
                For email, we send a six-digit verification code. Enter it here before any records are shown.
              </p>
            </div>

            <form
              aria-busy={isLoading}
              aria-labelledby="public-lookup-title"
              className="public-lookup-form"
              onSubmit={handleLookup}
            >
              <fieldset className="public-lookup-mode">
                <legend>Lookup mode</legend>
                <div className="public-lookup-mode-grid">
                  <label className={`public-lookup-mode-option${isEmailMode ? " active" : ""}`}>
                    <input
                      checked={isEmailMode}
                      name="lookup-mode"
                      onChange={() => setLookupMode("email")}
                      type="radio"
                      value="email"
                    />
                    <span>Email</span>
                  </label>
                  <label className={`public-lookup-mode-option${!isEmailMode ? " active" : ""}`}>
                    <input
                      checked={!isEmailMode}
                      name="lookup-mode"
                      onChange={() => setLookupMode("sms")}
                      type="radio"
                      value="sms"
                    />
                    <span>SMS</span>
                  </label>
                </div>
              </fieldset>

              {isEmailMode ? (
                <ol aria-label="Verification steps" className="public-lookup-steps">
                  <li aria-current={otpSent ? undefined : "step"}>
                    <span aria-hidden="true">1</span>
                    Enter your email
                  </li>
                  <li aria-current={otpSent ? "step" : undefined}>
                    <span aria-hidden="true">2</span>
                    Enter the verification code
                  </li>
                </ol>
              ) : null}

              <div className="public-lookup-field">
                <label htmlFor="public-lookup-contact">{isEmailMode ? "Email" : "SMS"}</label>
                <Input
                  aria-describedby={
                    error && !showOtpField
                      ? "public-lookup-instructions public-lookup-error"
                      : "public-lookup-instructions"
                  }
                  autoComplete={isEmailMode ? "email" : "tel"}
                  id="public-lookup-contact"
                  name={isEmailMode ? "email" : "phone"}
                  onChange={(event) =>
                    isEmailMode ? handleEmailChange(event.target.value) : setSmsValue(event.target.value)
                  }
                  placeholder={isEmailMode ? "email@domain.com" : "Enter your phone number"}
                  type={isEmailMode ? "email" : "tel"}
                  value={isEmailMode ? email : smsValue}
                />
              </div>

              {showOtpField ? (
                <div className="public-lookup-field">
                  <label htmlFor="public-lookup-otp">Verification code</label>
                  <Input
                    aria-describedby={
                      error ? "public-lookup-otp-hint public-lookup-error" : "public-lookup-otp-hint"
                    }
                    autoComplete="one-time-code"
                    className="public-lookup-otp-input"
                    id="public-lookup-otp"
                    inputMode="numeric"
                    maxLength={6}
                    name="one-time-code"
                    onChange={(event) => setOtpCode(event.target.value.split("").filter((character) => character >= "0" && character <= "9").join(""))}
                    placeholder="Enter 6-digit code"
                    ref={otpInputRef}
                    value={otpCode}
                  />
                  <p className="public-lookup-hint" id="public-lookup-otp-hint">
                    Enter the six digits from the email. Only numbers are accepted.
                  </p>
                </div>
              ) : null}

              <div className="public-lookup-status" role="status">
                {successMessage ? <p className="public-lookup-success">{successMessage}</p> : null}
              </div>
              {error ? (
                <p className="public-lookup-error" id="public-lookup-error" role="alert">
                  {error}
                </p>
              ) : null}

              <div className="public-lookup-actions">
                <Button
                  className="public-lookup-submit"
                  disabled={isLoading || !canSubmit || (otpSent && otpCode.length !== 6)}
                  type="submit"
                >
                  {isLoading ? "Please wait..." : otpSent ? "Verify and continue" : "Send verification code"}
                </Button>
                {showOtpField ? (
                  <Button disabled={isLoading} onClick={() => void handleResendOtp()} variant="secondary">
                    Resend code
                  </Button>
                ) : null}
              </div>
            </form>
          </section>

          {customerData ? (
            <section aria-labelledby="public-lookup-results-title" className="public-lookup-results">
              <div className="public-lookup-results-head">
                <p className="help-center-article-kicker">Buyer profile</p>
                <h2 id="public-lookup-results-title" ref={resultsHeadingRef} tabIndex={-1}>
                  {formatDisplayText(customerProfile.name, "Buyer found")}
                </h2>
                <p>Project and support records linked to this contact</p>
              </div>

              <dl className="public-lookup-metric-grid">
                <div className="public-lookup-metric">
                  <dt>Email</dt>
                  <dd>{formatDisplayText(customerProfile.email ?? email, "N/A")}</dd>
                </div>
                <div className="public-lookup-metric">
                  <dt>Phone</dt>
                  <dd>{formatDisplayText(customerProfile.phone, "N/A")}</dd>
                </div>
                <div className="public-lookup-metric">
                  <dt>Project records</dt>
                  <dd>{formatDisplayText(customerProfile.total_orders, String(customerOrders.length))}</dd>
                </div>
                <div className="public-lookup-metric">
                  <dt>Portfolio value</dt>
                  <dd>{formatCurrency(customerProfile.total_spent)}</dd>
                </div>
              </dl>

              <div className="public-lookup-detail-grid">
                <section aria-labelledby="public-lookup-records-title" className="public-lookup-detail">
                  <div className="public-lookup-detail-head">
                    <h3 id="public-lookup-records-title">Project records</h3>
                    <Badge>{customerOrders.length}</Badge>
                  </div>

                  {customerOrders.length ? (
                    <ul className="public-lookup-record-list">
                      {customerOrders.map((order, index) => {
                        const orderNumber = formatDisplayText(order.order_number ?? order.id, "N/A");
                        const orderStatus = formatDisplayText(order.status, "Unknown");
                        const orderTotal = formatCurrency(order.total ?? "0");
                        const orderDate = formatOrderDate((order as { created_at?: string }).created_at);
                        const itemCount = getOrderItemsCount(order);

                        return (
                          <li className="public-lookup-record" key={`${orderNumber}-${index}`}>
                            <div className="public-lookup-record-top">
                              <strong>{orderNumber}</strong>
                              <Badge>{orderStatus}</Badge>
                            </div>
                            <div className="public-lookup-record-meta">
                              <span>{orderTotal}</span>
                              <span>{itemCount} entr{itemCount === 1 ? "y" : "ies"}</span>
                              <span>{orderDate}</span>
                            </div>
                          </li>
                        );
                      })}
                    </ul>
                  ) : (
                    <p className="public-lookup-empty">No project records were returned for this customer.</p>
                  )}
                </section>

                <section aria-labelledby="public-lookup-plans-title" className="public-lookup-detail">
                  <div className="public-lookup-detail-head">
                    <h3 id="public-lookup-plans-title">Plans and schedules</h3>
                    <Badge>{customerSubscriptions.length}</Badge>
                  </div>

                  {customerSubscriptions.length ? (
                    <ul className="public-lookup-record-list">
                      {customerSubscriptions.map((subscription, index) => (
                        <li className="public-lookup-record" key={`${subscription.id ?? index}`}>
                          <div className="public-lookup-record-top">
                            <strong>{formatDisplayText(subscription.product_name, "Plan record")}</strong>
                            <Badge>{formatDisplayText(subscription.status, "Unknown")}</Badge>
                          </div>
                          <div className="public-lookup-record-meta">
                            <span>{formatCurrency(subscription.amount ?? subscription.price)}</span>
                            <span>{formatDisplayText(subscription.frequency, "Scheduled")}</span>
                            <span>Next review: {formatDisplayText(subscription.next_billing_date, "N/A")}</span>
                          </div>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="public-lookup-empty">No plans or schedules were returned for this customer.</p>
                  )}
                </section>
              </div>
            </section>
          ) : null}
        </div>
      </main>

      <PublicFooter />
    </div>
  );
}
