import type { SupportConversationMessage } from "../types";

const ACTIVE_ID_KEY = "acrobuild.support.activeConversationId.v1";
const TRANSCRIPT_KEY = "acrobuild.support.transcript.v1";
const PROPERTY_FLOW_KEY = "acrobuild.support.propertyFlow.v1";
const MAX_AGE_MS = 2 * 60 * 60 * 1000;

export type RestorableMessage = {
  backendText?: string;
  contextIssue?: string;
  id: number;
  isComplete?: boolean;
  offerActionMenu?: boolean;
  quickReplies?: { label: string; value: string; action?: "ticket" | "site_visit" | "call" | "browse_projects"; project_name?: string }[];
  sender: "bot" | "customer";
  serverTurn?: boolean;
  text: string;
};

function storage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.sessionStorage;
  } catch {
    return null;
  }
}

function readItem(key: string): string | null {
  try { return storage()?.getItem(key) ?? null; }
  catch { return null; }
}

function writeItem(key: string, value: string): void {
  try { storage()?.setItem(key, value); }
  catch { /* Storage is optional. */ }
}

function removeItem(key: string): void {
  try { storage()?.removeItem(key); }
  catch { /* Storage is optional. */ }
}

export function createConversationId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `conv-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function activeConversation(): { id: string; restored: boolean } {
  const saved = readItem(ACTIVE_ID_KEY);
  if (saved && /^[A-Za-z0-9_-]{1,128}$/.test(saved)) return { id: saved, restored: true };
  const id = createConversationId();
  writeItem(ACTIVE_ID_KEY, id);
  return { id, restored: false };
}

export function replaceConversation(): string {
  const id = createConversationId();
  removeItem(TRANSCRIPT_KEY);
  removeItem(PROPERTY_FLOW_KEY);
  writeItem(ACTIVE_ID_KEY, id);
  return id;
}

export function clearConversation(id: string): void {
  if (readItem(ACTIVE_ID_KEY) === id) {
    removeItem(ACTIVE_ID_KEY);
    removeItem(TRANSCRIPT_KEY);
    removeItem(PROPERTY_FLOW_KEY);
  }
}

function serverTurns(messages: RestorableMessage[]): SupportConversationMessage[] {
  return messages.filter((message) => message.serverTurn).map((message) => ({
    sender: message.sender,
    text: message.backendText ?? message.text
  }));
}

export function saveTranscript(id: string, messages: RestorableMessage[]): void {
  const store = storage();
  if (!store || readItem(ACTIVE_ID_KEY) !== id) return;
  const complete = messages.filter((message) => message.sender === "customer" || message.isComplete).map((message) => ({
    backendText: message.backendText,
    contextIssue: message.contextIssue,
    id: message.id,
    isComplete: message.isComplete,
    offerActionMenu: message.offerActionMenu,
    quickReplies: message.quickReplies,
    sender: message.sender,
    serverTurn: message.serverTurn,
    text: message.text
  }));
  try {
    store.setItem(TRANSCRIPT_KEY, JSON.stringify({ id, savedAt: Date.now(), messages: complete, serverTurns: serverTurns(complete).slice(-60) }));
  } catch {
    // Storage is optional. The server still retains the authoritative turns.
  }
}

export function matchingTranscript(id: string, history: SupportConversationMessage[]): RestorableMessage[] | null {
  try {
    const raw = readItem(TRANSCRIPT_KEY);
    if (!raw) return null;
    const saved = JSON.parse(raw) as { id?: string; savedAt?: number; messages?: RestorableMessage[]; serverTurns?: SupportConversationMessage[] };
    if (saved.id !== id || typeof saved.savedAt !== "number" || Date.now() - saved.savedAt > MAX_AGE_MS ||
        !Array.isArray(saved.messages) || !Array.isArray(saved.serverTurns)) return null;
    if (serverTurns(saved.messages).length > 60) return null;
    if (JSON.stringify(saved.serverTurns) !== JSON.stringify(history)) return null;
    return saved.messages;
  } catch {
    return null;
  }
}

export function restoredTranscript(
  id: string,
  history: SupportConversationMessage[],
  quickReplies: RestorableMessage["quickReplies"]
): RestorableMessage[] {
  const snapshot = matchingTranscript(id, history);
  if (snapshot) return snapshot;
  return history.map((message, index) => ({
    backendText: message.text,
    id: index - history.length,
    isComplete: message.sender === "bot",
    quickReplies: index === history.length - 1 && message.sender === "bot" ? quickReplies : [],
    sender: message.sender,
    serverTurn: true,
    text: message.text
  }));
}

export function savePropertyFlow(id: string, flow: unknown): void {
  const store = storage();
  if (!store || readItem(ACTIVE_ID_KEY) !== id) return;
  try {
    if (flow === null) store.removeItem(PROPERTY_FLOW_KEY);
    else store.setItem(PROPERTY_FLOW_KEY, JSON.stringify({ id, savedAt: Date.now(), flow }));
  } catch {
    // Chat can still continue through the server conversation.
  }
}

export function matchingPropertyFlow<T extends { messageId: number; level: string }>(
  id: string,
  history: SupportConversationMessage[],
  visible: RestorableMessage[]
): T | null {
  if (!matchingTranscript(id, history)) return null;
  try {
    const raw = readItem(PROPERTY_FLOW_KEY);
    if (!raw) return null;
    const saved = JSON.parse(raw) as { id?: string; savedAt?: number; flow?: T };
    if (saved.id !== id || typeof saved.savedAt !== "number" || Date.now() - saved.savedAt > MAX_AGE_MS ||
        !saved.flow || !["projects", "wings", "floors", "flats", "flat_details"].includes(saved.flow.level) ||
        !Array.isArray((saved.flow as { projects?: unknown }).projects) ||
        !Array.isArray((saved.flow as { wings?: unknown }).wings) ||
        !Array.isArray((saved.flow as { inventory?: unknown }).inventory) ||
        !visible.some((message) => message.id === saved.flow?.messageId && message.sender === "bot")) return null;
    return saved.flow;
  } catch {
    return null;
  }
}
