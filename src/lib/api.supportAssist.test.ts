import { afterEach, describe, expect, it, vi } from "vitest";
import { streamSupportAssist } from "./api";

afterEach(() => {
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

describe("support assist stream protocol", () => {
  it("parses deltas and the final response payload", async () => {
    const finalResponse = {
      answer: "Choose an area",
      clarification_entity: "locality" as const,
      discovery_slots: { awaiting: "locality" as const, config: ["3"] },
      quick_replies: [{ label: "Wakad", value: "Wakad" }],
      route: "property" as const,
      source_status: "live_api" as const
    };
    const body = [
      JSON.stringify({ type: "delta", text: "Choose " }),
      JSON.stringify({ type: "progress", stage: "finalizing" }),
      JSON.stringify({ type: "done", response: finalResponse })
    ].join("\n") + "\n";
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(body, { status: 200 })));
    const deltas: string[] = [];
    const onDone = vi.fn();

    await streamSupportAssist({ issue: "Show me 3 BHK" }, {
      onDelta: (text) => deltas.push(text),
      onDone
    });

    expect(deltas).toEqual(["Choose "]);
    expect(onDone).toHaveBeenCalledOnce();
    expect(onDone).toHaveBeenCalledWith(finalResponse);
  });

  it("reports a server error event separately from a successful completion", async () => {
    const errorResponse = {
      answer: "Please try again.",
      source_status: "fallback" as const
    };
    const body = `${JSON.stringify({ type: "error", response: errorResponse })}\n`;
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(body, { status: 200 })));
    const onDone = vi.fn();
    const onError = vi.fn();

    await streamSupportAssist({ issue: "Show me 3 BHK" }, { onDone, onError });

    expect(onError).toHaveBeenCalledWith(errorResponse);
    expect(onDone).not.toHaveBeenCalled();
  });
});
