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
// same options are shown as quick-reply buttons, show and speak only the prompt
// -- but only when every bulleted line is nothing more than a restated option
// label. A shortlist bullet can carry its own content (e.g. "- Acro Iris:
// estimated base amount from INR 50.00 lakh") or be followed by more text
// (a pricing disclaimer, a closing prompt); dropping that content would hide
// information the quick replies never duplicated in the first place.
function bulletsAreRedundantWithQuickReplies(text: string, quickReplies: SupportQuickReply[]): boolean {
  const lines = text.split("\n");
  const bulletIndex = lines.findIndex((line) => /^\s*[-•*]\s/.test(line));
  if (bulletIndex === -1) return false;
  const labels = new Set(quickReplies.map((option) => option.label.trim()));
  return lines.slice(bulletIndex).every((line) => {
    const match = line.match(/^\s*[-•*]\s(.*)$/);
    return !!match && labels.has(match[1].trim());
  });
}

export function visibleMessageText(message: ChatContractMessage): string {
  const quickReplies = message.quickReplies ?? [];
  return quickReplies.length
    && quickReplies.every((option) => !option.action)
    && bulletsAreRedundantWithQuickReplies(message.text, quickReplies)
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
