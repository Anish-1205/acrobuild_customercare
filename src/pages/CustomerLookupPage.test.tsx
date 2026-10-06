import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CustomerLookupPage } from "./CustomerLookupPage";

const api = vi.hoisted(() => ({
  getVerifiedCustomerByEmail: vi.fn(),
  requestEmailOtp: vi.fn(),
  verifyEmailOtp: vi.fn()
}));

vi.mock("../lib/api", () => api);
vi.mock("../contexts/RoleContext", () => ({
  useRole: () => ({ isAuthenticated: false, role: "agent" })
}));

function renderPage(path = "/home/project-support") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <CustomerLookupPage />
    </MemoryRouter>
  );
}

async function requestCode(email = "buyer@example.com") {
  fireEvent.change(screen.getByLabelText("Email", { selector: "#public-lookup-contact" }), {
    target: { value: email }
  });
  fireEvent.click(screen.getByRole("button", { name: "Send verification code" }));
  return screen.findByLabelText("Verification code");
}

describe("CustomerLookupPage", () => {
  beforeEach(() => {
    api.requestEmailOtp.mockResolvedValue({ expires_in: 600, message: "Verification code sent.", resend_after: 60 });
    api.verifyEmailOtp.mockResolvedValue({ access_token: "token-1", expires_in: 900, message: "Email verified." });
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders inside the public shell with labelled controls and no chat mount", () => {
    const { container } = renderPage();

    expect(screen.getByRole("navigation", { name: "Help center sections" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Footer" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login");
    expect(container.querySelectorAll("main")).toHaveLength(1);

    const breadcrumb = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(within(breadcrumb).getByRole("link", { name: "Home" })).toHaveAttribute("href", "/home");
    expect(within(breadcrumb).getByText("Project support")).toHaveAttribute("aria-current", "page");

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Enter the email or phone number linked to your project or property inquiry"
    );
    expect(screen.getByRole("group", { name: "Lookup mode" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Email" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "SMS" })).not.toBeChecked();
    expect(screen.getByRole("button", { name: "Send verification code" })).toBeDisabled();
    expect(container.querySelector(".store-chat-launcher, .store-chat-panel")).toBeNull();
  });

  it("keeps SMS selectable and reports that it is not configured without calling the API", () => {
    renderPage();

    fireEvent.click(screen.getByRole("radio", { name: "SMS" }));
    const phone = screen.getByLabelText("SMS", { selector: "#public-lookup-contact" });
    expect(phone).toHaveAttribute("type", "tel");

    fireEvent.change(phone, { target: { value: "5550100" } });
    fireEvent.click(screen.getByRole("button", { name: "Send verification code" }));

    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("SMS OTP is not configured yet. Please use email.");
    expect(phone.getAttribute("aria-describedby")).toContain(alert.id);
    expect(api.requestEmailOtp).not.toHaveBeenCalled();
  });

  it("requests a code with the trimmed email, then moves focus to the code field", async () => {
    renderPage();

    const otpInput = await requestCode("  buyer@example.com ");

    expect(api.requestEmailOtp).toHaveBeenCalledWith("buyer@example.com");
    expect(screen.getByRole("status")).toHaveTextContent(
      "A six-digit verification code was sent to buyer@example.com."
    );
    await waitFor(() => expect(otpInput).toHaveFocus());
    expect(otpInput).toHaveAttribute("autocomplete", "one-time-code");
    expect(otpInput).toHaveAttribute("inputmode", "numeric");
    expect(screen.getByText("Enter the verification code").closest("li")).toHaveAttribute("aria-current", "step");

    fireEvent.change(otpInput, { target: { value: "12a3" } });
    expect(otpInput).toHaveValue("123");
    expect(screen.getByRole("button", { name: "Verify and continue" })).toBeDisabled();
  });

  it("verifies the code, sends the existing verified-customer request, and shows the returned records", async () => {
    api.getVerifiedCustomerByEmail.mockResolvedValue({
      customer: { email: "buyer@example.com", name: "buyer", total_orders: 1, total_spent: 0 },
      orders: [{ id: "TCK-1", order_number: "TCK-1", status: "Open", total: 0, created_at: "2026-01-05T10:00:00" }],
      subscriptions: []
    });
    renderPage();

    fireEvent.change(await requestCode(), { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: "Verify and continue" }));

    const heading = await screen.findByRole("heading", { level: 2, name: "buyer" });
    expect(api.verifyEmailOtp).toHaveBeenCalledWith("buyer@example.com", "123456");
    expect(api.getVerifiedCustomerByEmail).toHaveBeenCalledWith(
      "buyer@example.com",
      "token-1",
      "http://10.10.1.23:9092"
    );
    await waitFor(() => expect(heading).toHaveFocus());
    expect(screen.getByRole("status")).toHaveTextContent("Email verified successfully.");

    const records = screen.getByRole("region", { name: "Project records" });
    expect(within(records).getByText("TCK-1")).toBeInTheDocument();
    expect(within(records).getByText("Open")).toBeInTheDocument();
    expect(within(records).getByText("0 entries")).toBeInTheDocument();
    expect(within(records).getByText("Jan 5, 2026")).toBeInTheDocument();
    expect(screen.getByText("No plans or schedules were returned for this customer.")).toBeInTheDocument();
  });

  it("reports an empty verified response without rendering a profile", async () => {
    api.getVerifiedCustomerByEmail.mockResolvedValue({ orders: [], subscriptions: [] });
    renderPage();

    fireEvent.change(await requestCode(), { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: "Verify and continue" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "No project records were found for that verified email."
    );
    expect(screen.queryByRole("heading", { level: 2 })).not.toBeInTheDocument();
  });

  it("surfaces a verification failure on the code field and allows a resend", async () => {
    api.verifyEmailOtp.mockRejectedValueOnce(new Error("Invalid verification code."));
    renderPage();

    const otpInput = await requestCode();
    fireEvent.change(otpInput, { target: { value: "000000" } });
    fireEvent.click(screen.getByRole("button", { name: "Verify and continue" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Invalid verification code.");
    expect(otpInput.getAttribute("aria-describedby")).toContain(alert.id);
    expect(api.getVerifiedCustomerByEmail).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Resend code" }));

    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent(
        "A new verification code was sent to buyer@example.com."
      )
    );
    expect(api.requestEmailOtp).toHaveBeenCalledTimes(2);
    expect(otpInput).toHaveValue("");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("resets the verification step when the email changes", async () => {
    renderPage();

    await requestCode();
    fireEvent.change(screen.getByLabelText("Email", { selector: "#public-lookup-contact" }), {
      target: { value: "other@example.com" }
    });

    expect(screen.queryByLabelText("Verification code")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send verification code" })).toBeEnabled();
  });
});
