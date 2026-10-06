import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { HelpCenterBreadcrumbs, HelpCenterSearch, HelpCenterViewToggle } from "./HelpCenterUi";

describe("HelpCenterUi", () => {
  afterEach(cleanup);

  it("renders semantic breadcrumbs while preserving supplied destinations", () => {
    render(
      <MemoryRouter>
        <HelpCenterBreadcrumbs
          items={[
            { label: "Home", to: "/home" },
            { label: "All articles", to: "/home" },
            { label: "Construction" }
          ]}
        />
      </MemoryRouter>
    );

    expect(screen.getByRole("navigation", { name: "Breadcrumb" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Home" })).toHaveAttribute("href", "/home");
    expect(screen.getByRole("link", { name: "All articles" })).toHaveAttribute("href", "/home");
    expect(screen.getByText("Construction")).toHaveAttribute("aria-current", "page");
  });

  it("keeps search value, clear, and submit behavior controlled by its caller", () => {
    const onChange = vi.fn();
    const onSubmit = vi.fn();

    render(
      <HelpCenterSearch
        label="Search help center"
        onChange={onChange}
        onSubmit={onSubmit}
        placeholder="Search support articles and categories"
        showClear
        value="handover"
      />
    );

    fireEvent.change(screen.getByRole("searchbox", { name: "Search help center" }), {
      target: { value: "payments" }
    });
    expect(onChange).toHaveBeenCalledWith("payments");

    fireEvent.click(screen.getByRole("button", { name: "Clear search" }));
    expect(onChange).toHaveBeenCalledWith("");

    fireEvent.submit(screen.getByRole("search", { name: "Search help center" }));
    expect(onSubmit).toHaveBeenCalledOnce();
  });

  it("exposes the active layout and dispatches view changes", () => {
    const onChange = vi.fn();

    render(<HelpCenterViewToggle label="Article layout" onChange={onChange} value="grid" />);

    expect(screen.getByRole("button", { name: "Grid view" })).toHaveAttribute(
      "aria-pressed",
      "true"
    );
    fireEvent.click(screen.getByRole("button", { name: "List view" }));
    expect(onChange).toHaveBeenCalledWith("list");
  });
});
