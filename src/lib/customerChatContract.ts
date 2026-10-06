import type { SupportQuickReply } from "../types";

export type ChatContractMessage = {
  contextIssue?: string;
  isComplete?: boolean;
  quickReplies?: SupportQuickReply[];
  sender: "bot" | "customer";
  text: string;
};

export type QuickReplyDispatch =
  | { kind: "ticket"; issue: string }
  | { kind: "site_visit"; projectName: string }
  | { customerMessageText: string; issue: string; kind: "assist"; resetConversation: boolean };

// The answer's bullet list is the plain-text fallback for API clients; when the
// same options are shown as quick-reply buttons, show and speak only the prompt.
export function visibleMessageText(message: ChatContractMessage): string {
  return message.quickReplies?.length && message.quickReplies.every((option) => !option.action)
    ? message.text.split(/\n\s*[-•*]\s/)[0].trim()
    : message.text;
}

export function getNumberedProjectSelection(messages: ChatContractMessage[], value: string): string {
  const selectionMatch = value.trim().match(/^(?:project\s*)?(?:number\s*)?(\d{1,2})[).:-]?$/i);
  if (!selectionMatch) return "";

  const latestBotMessage = [...messages].reverse().find(
    (message) => message.sender === "bot" && message.isComplete
  );
  if (!latestBotMessage) return "";

  const numberedProjects = [...latestBotMessage.text.matchAll(/^\s*(\d+)[).]\s*([^\n]+)$/gm)];
  const selectedNumber = Number(selectionMatch[1]);
  return numberedProjects.find((match) => Number(match[1]) === selectedNumber)?.[2]?.trim() ?? "";
}

export function getNamedProjectSelection(messages: ChatContractMessage[], value: string): string {
  const normalizedValue = value.trim().toLowerCase();
  if (!normalizedValue) return "";
  const recentBotMessages = [...messages].reverse().filter(
    (message) => message.sender === "bot" && message.isComplete
  ).slice(0, 3);
  for (const message of recentBotMessages) {
    const numberedProjects = [...message.text.matchAll(/^\s*\d+[).]\s*([^\n]+)$/gm)];
    const match = numberedProjects.find((project) => project[1].trim().toLowerCase() === normalizedValue);
    if (match) return match[1].trim();
  }
  return "";
}

export function resolveProjectSelection(messages: ChatContractMessage[], value: string): string {
  const latestBotMessage = [...messages].reverse().find((message) => message.sender === "bot");
  if (latestBotMessage?.quickReplies?.length) return "";
  return getNamedProjectSelection(messages, value) || getNumberedProjectSelection(messages, value);
}

export function getQuickReplyDispatch(
  option: SupportQuickReply,
  message: Pick<ChatContractMessage, "contextIssue" | "text">
): QuickReplyDispatch {
  if (option.action === "ticket") {
    return { kind: "ticket", issue: message.contextIssue || message.text };
  }
  if (option.action === "site_visit") {
    return { kind: "site_visit", projectName: option.project_name ?? "" };
  }
  const resetConversation = option.action === "browse_projects";
  return {
    customerMessageText: resetConversation ? option.label : option.value,
    issue: option.value,
    kind: "assist",
    resetConversation
  };
}
