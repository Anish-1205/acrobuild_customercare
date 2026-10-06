import { describe, expect, it } from "vitest";
import {
  deliveryStateForResponse,
  inspectRetryHistory
} from "./chatRecovery";

describe("chat recovery state", () => {
  it("distinguishes failed, degraded, and snapshot responses from normal answers", () => {
    expect(deliveryStateForResponse({ answer: "Current", source_status: "live_api" })).toBeUndefined();
    expect(deliveryStateForResponse({ answer: "Saved", source_status: "snapshot" })).toBe("snapshot");
    expect(deliveryStateForResponse({ answer: "Fallback", source_status: "fallback" })).toBe("degraded");
    expect(deliveryStateForResponse({ answer: "Unavailable", source_status: "unavailable" })).toBe("failed");
  });

  it("allows retry only while authoritative history is unchanged", () => {
    const before = [
      { sender: "customer" as const, text: "Hi" },
      { sender: "bot" as const, text: "Hello" }
    ];
    expect(inspectRetryHistory(before, before, "Prices?")).toEqual({ kind: "unchanged" });
    expect(inspectRetryHistory([
      ...before,
      { sender: "customer", text: "Prices?" },
      { sender: "bot", text: "Here is the answer" }
    ], before, "Prices?")).toEqual({ answer: "Here is the answer", kind: "completed" });
    expect(inspectRetryHistory([
      ...before,
      { sender: "customer", text: "A different turn" }
    ], before, "Prices?")).toEqual({ kind: "diverged" });
  });
});
