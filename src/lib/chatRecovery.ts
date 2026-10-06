import type {
  SupportAssistResponse,
  SupportConversationMessage
} from "../types";

export type ChatDeliveryState =
  | "degraded"
  | "failed"
  | "interrupted"
  | "offline"
  | "recovered"
  | "snapshot";

export const CHAT_RECOVERY_COPY: Record<ChatDeliveryState, { detail: string; title: string }> = {
  degraded: {
    detail: "This reply uses local help content and is not a confirmed live property answer.",
    title: "Limited answer"
  },
  failed: {
    detail: "The service could not provide a confirmed answer for this request.",
    title: "Answer unavailable"
  },
  interrupted: {
    detail: "The connection ended before this response finished. The text above may be incomplete.",
    title: "Response interrupted"
  },
  offline: {
    detail: "The online request failed. This reply uses local help content and is not a confirmed live property answer.",
    title: "Support service unavailable"
  },
  recovered: {
    detail: "This answer was recovered from conversation history. Some original action buttons may be unavailable.",
    title: "Answer recovered"
  },
  snapshot: {
    detail: "This answer uses an approved saved snapshot, not a current live property check.",
    title: "Saved information"
  }
};

const FAILED_SOURCE_STATUSES = new Set([
  "error",
  "failed",
  "unavailable",
  "unverified"
]);

export function deliveryStateForResponse(
  response: SupportAssistResponse
): ChatDeliveryState | undefined {
  const sourceStatus = response.source_status?.trim().toLowerCase();
  if (sourceStatus === "snapshot") return "snapshot";
  if (sourceStatus === "fallback") return "degraded";
  if (sourceStatus && FAILED_SOURCE_STATUSES.has(sourceStatus)) return "failed";
  if (response.assist_error?.trim()) return "failed";
  return undefined;
}

export type RetryHistoryResult =
  | { kind: "completed"; answer: string }
  | { kind: "diverged" }
  | { kind: "unchanged" };

function sameHistory(
  left: SupportConversationMessage[],
  right: SupportConversationMessage[]
) {
  return JSON.stringify(left) === JSON.stringify(right);
}

export function inspectRetryHistory(
  current: SupportConversationMessage[],
  before: SupportConversationMessage[],
  issue: string
): RetryHistoryResult {
  if (sameHistory(current, before)) return { kind: "unchanged" };

  const completed = [
    ...before,
    { sender: "customer" as const, text: issue },
  ];
  const answer = current[current.length - 1];
  if (
    answer?.sender === "bot" &&
    current.length === completed.length + 1 &&
    sameHistory(current.slice(0, -1), completed)
  ) {
    return { answer: answer.text, kind: "completed" };
  }

  return { kind: "diverged" };
}
