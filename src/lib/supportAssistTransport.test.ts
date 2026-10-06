import { beforeEach, describe, expect, it, vi } from "vitest";
import { getSupportAssist, streamSupportAssist } from "./api";
import { requestSupportAssist } from "./supportAssistTransport";

vi.mock("./api", () => ({
  getSupportAssist: vi.fn(),
  streamSupportAssist: vi.fn()
}));

const onDelta = vi.fn();
const onDone = vi.fn();
const onPartial = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
});

describe("support assist transport", () => {
  it("delivers streaming deltas and the final response without a JSON retry", async () => {
    vi.mocked(streamSupportAssist).mockImplementation(async (_payload, handlers) => {
      handlers.onDelta?.("Hello ");
      handlers.onDelta?.("there");
      handlers.onDone({ answer: "Hello there", route: "general", source_status: "live" });
    });

    await expect(requestSupportAssist({ issue: "Hi" }, { onDelta, onDone, onPartial }))
      .resolves.toBe("stream");
    expect(onDelta.mock.calls.flat()).toEqual(["Hello ", "there"]);
    expect(onDone).toHaveBeenCalledWith(expect.objectContaining({ answer: "Hello there" }));
    expect(getSupportAssist).not.toHaveBeenCalled();
  });

  it("falls back to the JSON endpoint when the stream fails before a delta", async () => {
    vi.mocked(streamSupportAssist).mockRejectedValue(new Error("stream unavailable"));
    vi.mocked(getSupportAssist).mockResolvedValue({
      answer: "JSON answer",
      quick_replies: [{ label: "Any area", value: "Any area" }]
    });

    await expect(requestSupportAssist({ issue: "Show projects" }, { onDelta, onDone, onPartial }))
      .resolves.toBe("json");
    expect(getSupportAssist).toHaveBeenCalledWith({ issue: "Show projects" });
    expect(onDone).toHaveBeenCalledWith(expect.objectContaining({ answer: "JSON answer" }));
  });

  it("falls back to JSON when the server closes the stream with an error event", async () => {
    vi.mocked(streamSupportAssist).mockImplementation(async (_payload, handlers) => {
      handlers.onError?.({ answer: "Stream failed", source_status: "fallback" });
    });
    vi.mocked(getSupportAssist).mockResolvedValue({ answer: "JSON answer", source_status: "workspace" });

    await expect(requestSupportAssist({ issue: "Help" }, { onDelta, onDone, onPartial }))
      .resolves.toBe("json");
    expect(getSupportAssist).toHaveBeenCalledOnce();
    expect(onDone).toHaveBeenCalledWith(expect.objectContaining({ answer: "JSON answer" }));
  });

  it("keeps streamed text visibly partial when an error event follows a delta", async () => {
    vi.mocked(streamSupportAssist).mockImplementation(async (_payload, handlers) => {
      handlers.onDelta?.("Partial answer");
      handlers.onError?.({ answer: "Stream failed", source_status: "fallback" });
    });

    await expect(requestSupportAssist({ issue: "Help" }, { onDelta, onDone, onPartial }))
      .resolves.toBe("partial");
    expect(onPartial).toHaveBeenCalledWith("Partial answer");
    expect(getSupportAssist).not.toHaveBeenCalled();
    expect(onDone).not.toHaveBeenCalled();
  });

  it("rejects honestly when both stream and JSON transports fail", async () => {
    vi.mocked(streamSupportAssist).mockRejectedValue(new Error("stream unavailable"));
    vi.mocked(getSupportAssist).mockRejectedValue(new Error("JSON unavailable"));

    await expect(requestSupportAssist({ issue: "Help" }, { onDelta, onDone, onPartial }))
      .rejects.toThrow("JSON unavailable");
    expect(onDone).not.toHaveBeenCalled();
    expect(onPartial).not.toHaveBeenCalled();
  });

  it("keeps a partial streamed answer instead of duplicating the request", async () => {
    vi.mocked(streamSupportAssist).mockImplementation(async (_payload, handlers) => {
      handlers.onDelta?.("Partial answer");
      throw new Error("stream interrupted");
    });

    await expect(requestSupportAssist({ issue: "Hi" }, { onDelta, onDone, onPartial }))
      .resolves.toBe("partial");
    expect(onPartial).toHaveBeenCalledWith("Partial answer");
    expect(getSupportAssist).not.toHaveBeenCalled();
  });
});
