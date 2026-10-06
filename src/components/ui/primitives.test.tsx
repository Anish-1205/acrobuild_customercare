import { render, screen } from "@testing-library/react";
import { createRef } from "react";
import { describe, expect, it } from "vitest";
import { Badge, Button, Card, IconButton, Input } from ".";

describe("design-system primitives", () => {
  it("renders every approved button style with safe native defaults", () => {
    const { rerender } = render(<Button>Continue</Button>);
    const button = screen.getByRole("button", { name: "Continue" });
    expect(button.getAttribute("type")).toBe("button");
    expect(button.className).toContain("ab-button--primary");

    for (const variant of ["secondary", "ghost", "destructive"] as const) {
      rerender(<Button variant={variant}>Continue</Button>);
      expect(screen.getByRole("button", { name: "Continue" }).className).toContain(`ab-button--${variant}`);
    }
  });

  it("preserves native disabled and submit behavior", () => {
    render(<Button disabled type="submit">Save</Button>);
    const button = screen.getByRole("button", { name: "Save" }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    expect(button.type).toBe("submit");
  });

  it("requires an accessible name for icon-only controls", () => {
    render(<IconButton aria-label="Close"><span aria-hidden="true">×</span></IconButton>);
    expect(screen.getByRole("button", { name: "Close" })).toBeTruthy();
  });

  it("maps the error state to the native accessibility contract", () => {
    const ref = createRef<HTMLInputElement>();
    render(<Input aria-label="Email" invalid placeholder="name@example.com" ref={ref} />);
    const input = screen.getByRole("textbox", { name: "Email" });
    expect(input.getAttribute("aria-invalid")).toBe("true");
    expect(ref.current).toBe(input);
  });

  it("renders all approved badge tones and a reusable card surface", () => {
    const { rerender } = render(<Badge>Neutral</Badge>);
    expect(screen.getByText("Neutral").className).toContain("ab-badge--neutral");

    for (const tone of ["success", "warning", "error", "info"] as const) {
      rerender(<Badge tone={tone}>{tone}</Badge>);
      expect(screen.getByText(tone).className).toContain(`ab-badge--${tone}`);
    }

    rerender(<Card aria-label="Summary">Content</Card>);
    expect(screen.getByLabelText("Summary").className).toContain("ab-card");
  });
});
