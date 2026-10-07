import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import { PublicFooter, PublicHeader } from "./PublicShell";

describe("PublicShell", () => {
  afterEach(cleanup);

  it("routes navigation to the existing help-centre sections and exposes an accessible menu control", () => {
    const { container } = render(
      <MemoryRouter>
        <PublicHeader workspaceLabel="Sign in" workspaceLink="/login" />
      </MemoryRouter>
    );

    const menu = screen.getByRole("button", { name: "Menu" });
    const navigation = screen.getByRole("navigation", { name: "Help center sections" });

    expect(menu).toHaveAttribute("aria-controls", "public-navigation");
    expect(menu).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByRole("link", { name: "Home" })).toHaveAttribute("href", "/home");
    expect(screen.getByRole("link", { name: "Acrobuild home" })).toHaveAttribute("href", "/home");
    expect(screen.getByRole("link", { name: "Popular questions" })).toHaveAttribute(
      "href",
      "/home/about#popular-questions"
    );
    expect(screen.getByRole("link", { name: "All articles" })).toHaveAttribute(
      "href",
      "/home/about#more-information"
    );
    expect(screen.getByRole("link", { name: "Get support" })).toHaveAttribute(
      "href",
      "/home/about#get-support"
    );
    expect(screen.getByText("ACROBUILD")).toBeVisible();
    expect(container.querySelector(".acrobuild-logo-mark")).toHaveAttribute(
      "src",
      "/Acrobuild_logo.png?v=20260730-2"
    );
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login");

    fireEvent.click(menu);
    expect(menu).toHaveAttribute("aria-expanded", "true");
    expect(navigation).toHaveClass("is-open");

    fireEvent.click(screen.getByRole("link", { name: "Home" }));
    expect(menu).toHaveAttribute("aria-expanded", "false");
    expect(navigation).not.toHaveClass("is-open");
  });

  it("renders footer navigation without the non-functional language label", () => {
    render(
      <MemoryRouter>
        <PublicFooter />
      </MemoryRouter>
    );

    expect(screen.getByRole("navigation", { name: "Footer" })).toBeInTheDocument();
    expect(screen.queryByText("English (US)")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Contact" })).toHaveAttribute(
      "href",
      "/home/about#get-support"
    );
    expect(screen.getByRole("link", { name: "All articles" })).toHaveAttribute(
      "href",
      "/home/about#more-information"
    );
    expect(screen.getByRole("link", { name: "Popular questions" })).toHaveAttribute(
      "href",
      "/home/about#popular-questions"
    );
  });
});
