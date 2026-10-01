import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  activeConversation,
  clearConversation,
  matchingTranscript,
  matchingPropertyFlow,
  replaceConversation,
  restoredTranscript,
  savePropertyFlow,
  saveTranscript
} from "./conversationSession";

beforeEach(() => window.sessionStorage.clear());

describe("active support conversation", () => {
  it("creates an ID, reuses it on refresh, and replaces it for a new conversation", () => {
    const first = activeConversation();
    expect(first.restored).toBe(false);
    expect(activeConversation()).toEqual({ id: first.id, restored: true });
    const next = replaceConversation();
    expect(next).not.toBe(first.id);
    expect(activeConversation().id).toBe(next);
    clearConversation(next);
    expect(activeConversation().id).not.toBe(next);
  });

  it("still creates an ID when session storage is unavailable", () => {
    const getter = vi.spyOn(window, "sessionStorage", "get").mockImplementation(() => {
      throw new Error("storage blocked");
    });
    try {
      expect(activeConversation().id).toBeTruthy();
      expect(replaceConversation()).toBeTruthy();
    } finally {
      getter.mockRestore();
    }
  });

  it("restores ordered visible turns once and retains a local greeting without duplicating it", () => {
    const { id } = activeConversation();
    const visible = [
      { id: 1, sender: "bot" as const, text: "Welcome", isComplete: true },
      { id: 2, sender: "customer" as const, text: "Show 3 BHK", backendText: "Show 3 BHK", serverTurn: true },
      { id: 3, sender: "bot" as const, text: "Choose an area", isComplete: true, serverTurn: true,
        quickReplies: [{ label: "Wakad", value: "Wakad" }] }
    ];
    const history = [
      { sender: "customer" as const, text: "Show 3 BHK" },
      { sender: "bot" as const, text: "Choose an area" }
    ];
    saveTranscript(id, visible);
    expect(restoredTranscript(id, history, [])).toEqual(visible.map((message) => ({
      backendText: "backendText" in message ? message.backendText : undefined,
      contextIssue: undefined,
      id: message.id,
      isComplete: message.isComplete,
      offerActionMenu: undefined,
      quickReplies: "quickReplies" in message ? message.quickReplies : undefined,
      sender: message.sender,
      serverTurn: "serverTurn" in message ? message.serverTurn : undefined,
      text: message.text
    })));
    expect(restoredTranscript(id, history, [])).toHaveLength(3);
  });

  it("uses server history when the local snapshot is stale or an answer was incomplete", () => {
    const { id } = activeConversation();
    saveTranscript(id, [
      { id: 1, sender: "customer", text: "Hi", serverTurn: true },
      { id: 2, sender: "bot", text: "partial", isComplete: false }
    ]);
    const history = [
      { sender: "customer" as const, text: "Hi" },
      { sender: "bot" as const, text: "Complete" }
    ];
    expect(matchingTranscript(id, history)).toBeNull();
    expect(restoredTranscript(id, history, [])).toMatchObject(history);
    expect(restoredTranscript(id, history, [])).toHaveLength(2);
  });

  it("does not reuse a snapshot after its server conversation has expired", () => {
    const { id } = activeConversation();
    saveTranscript(id, [
      { id: 1, sender: "customer", text: "Hi", serverTurn: true },
      { id: 2, sender: "bot", text: "Hello", isComplete: true, serverTurn: true }
    ]);
    expect(matchingTranscript(id, [])).toBeNull();
  });

  it("keeps the current guided property choices with the same visible transcript", () => {
    const { id } = activeConversation();
    const visible = [
      { id: 1, sender: "customer" as const, text: "Browse all projects" },
      { id: 2, sender: "bot" as const, text: "Choose a project", isComplete: true }
    ];
    const flow = { level: "projects", messageId: 2, projects: [{ id: 1, projectName: "Example" }], wings: [], inventory: [] };
    saveTranscript(id, visible);
    savePropertyFlow(id, flow);
    expect(matchingPropertyFlow(id, [], visible)).toEqual(flow);
    expect(matchingPropertyFlow(id, [], visible.slice(0, 1))).toBeNull();
    replaceConversation();
    expect(matchingPropertyFlow(id, [], visible)).toBeNull();
  });
});
