import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { getVerifiedCustomerByEmail, requestEmailOtp, verifyEmailOtp } from "../lib/api";
import { AcrobuildLogo } from "../components/AcrobuildLogo";
import type { CustomerLookupResponse, Order, SubscriptionRecord } from "../types";

type LookupMode = "email" | "sms";

const helpCenterHomePath = "/home";
const customerLookupPath = "/home/project-support";
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
    <div className="help-center-page customer-lookup-page">
      <header className="help-center-header">
        <div className="help-center-shell customer-lookup-header-inner">
          <Link className="help-center-header-home" to={helpCenterHomePath}>
            Home
          </Link>

          <Link className="help-center-header-brand customer-lookup-brand" to={customerLookupPath}>
            <AcrobuildLogo className="acrobuild-logo-compact" subtitle="Project support" />
          </Link>

          <div className="customer-lookup-header-spacer" />
        </div>
      </header>

      <main className="help-center-main customer-lookup-main">
        <div className="help-center-shell customer-lookup-shell">
          <div className="help-center-breadcrumbs customer-lookup-breadcrumbs">
            <Link to={helpCenterHomePath}>Home</Link>
            <span>&gt;</span>
            <strong>Project support</strong>
          </div>

          <section className="customer-lookup-card">
            <div className="customer-lookup-card-head">
              <h1>Enter the email or phone number linked to your project or property inquiry</h1>
            </div>

            <form className="customer-lookup-form" onSubmit={handleLookup}>
              <div className="customer-lookup-mode-grid" role="radiogroup" aria-label="Lookup mode">
                <button
                  aria-pressed={isEmailMode}
                  className={`customer-lookup-mode-card${isEmailMode ? " active" : ""}`}
                  onClick={() => setLookupMode("email")}
                  type="button"
                >
                  <span className="customer-lookup-mode-dot" />
                  Email
                </button>
                <button
                  aria-pressed={!isEmailMode}
                  className={`customer-lookup-mode-card${!isEmailMode ? " active" : ""}`}
                  onClick={() => setLookupMode("sms")}
                  type="button"
                >
                  <span className="customer-lookup-mode-dot" />
                  SMS
                </button>
              </div>

              <label className="field-block customer-lookup-field">
                <span>{isEmailMode ? "Email" : "SMS"}</span>
                <input
                  className="field-input customer-lookup-input"
                  onChange={(event) =>
                    isEmailMode ? handleEmailChange(event.target.value) : setSmsValue(event.target.value)
                  }
                  placeholder={isEmailMode ? "email@domain.com" : "Enter your phone number"}
                  type={isEmailMode ? "email" : "tel"}
                  value={isEmailMode ? email : smsValue}
                />
              </label>

              {otpSent && isEmailMode ? (
                <label className="field-block customer-lookup-field">
                  <span>Verification code</span>
                  <input
                    autoComplete="one-time-code"
                    className="field-input customer-lookup-input customer-lookup-otp-input"
                    inputMode="numeric"
                    maxLength={6}
                    onChange={(event) => setOtpCode(event.target.value.split("").filter((character) => character >= "0" && character <= "9").join(""))}
                    placeholder="Enter 6-digit code"
                    value={otpCode}
                  />
                </label>
              ) : null}

              {successMessage ? <div className="customer-lookup-success">{successMessage}</div> : null}
              {error ? <div className="banner-error customer-lookup-error">{error}</div> : null}

              <div className="customer-lookup-actions">
                <button
                  className="customer-lookup-submit"
                  disabled={isLoading || !canSubmit || (otpSent && otpCode.length !== 6)}
                  type="submit"
                >
                  {isLoading ? "Please wait..." : otpSent ? "Verify and continue" : "Send verification code"}
                </button>
                {otpSent && isEmailMode ? (
                  <button className="customer-lookup-resend" disabled={isLoading} onClick={() => void handleResendOtp()} type="button">
                    Resend code
                  </button>
                ) : null}
              </div>
            </form>
          </section>

          {customerData ? (
            <section className="customer-lookup-results">
              <div className="customer-lookup-results-head">
                <div>
                  <div className="help-center-article-kicker">Buyer profile</div>
                  <h2>{formatDisplayText(customerProfile.name, "Buyer found")}</h2>
                  <p>
                    Project and support records linked to this contact
                  </p>
                </div>
              </div>

              <div className="customer-lookup-metric-grid">
                <article className="customer-lookup-metric-card">
                  <span>Email</span>
                  <strong>{formatDisplayText(customerProfile.email ?? email, "N/A")}</strong>
                </article>
                <article className="customer-lookup-metric-card">
                  <span>Phone</span>
                  <strong>{formatDisplayText(customerProfile.phone, "N/A")}</strong>
                </article>
                <article className="customer-lookup-metric-card">
                  <span>Project records</span>
                  <strong>
                    {formatDisplayText(customerProfile.total_orders, String(customerOrders.length))}
                  </strong>
                </article>
                <article className="customer-lookup-metric-card">
                  <span>Portfolio value</span>
                  <strong>{formatCurrency(customerProfile.total_spent)}</strong>
                </article>
              </div>

              <div className="customer-lookup-detail-grid">
                <section className="customer-lookup-detail-card">
                  <div className="customer-lookup-detail-head">
                    <strong>Project records</strong>
                    <span>{customerOrders.length}</span>
                  </div>

                  {customerOrders.length ? (
                    <div className="customer-lookup-record-list">
                      {customerOrders.map((order, index) => {
                        const orderNumber = formatDisplayText(order.order_number ?? order.id, "N/A");
                        const orderStatus = formatDisplayText(order.status, "Unknown");
                        const orderTotal = formatCurrency(order.total ?? "0");
                        const orderDate = formatOrderDate((order as { created_at?: string }).created_at);
                        const itemCount = getOrderItemsCount(order);

                        return (
                          <article className="customer-lookup-record-card" key={`${orderNumber}-${index}`}>
                            <div className="customer-lookup-record-top">
                              <strong>{orderNumber}</strong>
                              <span>{orderStatus}</span>
                            </div>
                            <div className="customer-lookup-record-meta">
                              <span>{orderTotal}</span>
                              <span>{itemCount} entr{itemCount === 1 ? "y" : "ies"}</span>
                              <span>{orderDate}</span>
                            </div>
                          </article>
                        );
                      })}
                    </div>
                  ) : (
                    <div className="customer-lookup-empty">No project records were returned for this customer.</div>
                  )}
                </section>

                <section className="customer-lookup-detail-card">
                  <div className="customer-lookup-detail-head">
                    <strong>Plans and schedules</strong>
                    <span>{customerSubscriptions.length}</span>
                  </div>

                  {customerSubscriptions.length ? (
                    <div className="customer-lookup-record-list">
                      {customerSubscriptions.map((subscription, index) => (
                        <article className="customer-lookup-record-card" key={`${subscription.id ?? index}`}>
                          <div className="customer-lookup-record-top">
                            <strong>
                              {formatDisplayText(subscription.product_name, "Plan record")}
                            </strong>
                            <span>{formatDisplayText(subscription.status, "Unknown")}</span>
                          </div>
                          <div className="customer-lookup-record-meta">
                            <span>{formatCurrency(subscription.amount ?? subscription.price)}</span>
                            <span>{formatDisplayText(subscription.frequency, "Scheduled")}</span>
                            <span>
                              Next review: {formatDisplayText(subscription.next_billing_date, "N/A")}
                            </span>
                          </div>
                        </article>
                      ))}
                    </div>
                  ) : (
                    <div className="customer-lookup-empty">No plans or schedules were returned for this customer.</div>
                  )}
                </section>
              </div>
            </section>
          ) : null}
        </div>
      </main>

    </div>
  );
}
