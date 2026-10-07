import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import "./CustomerChat.css";
import { useRole } from "../contexts/RoleContext";
import {
  createSiteVisit,
  createSupportTicket,
  generateIndicVoiceAudio,
  getAdminArticles,
  getPropertyInventory,
  getPropertyProjects,
  getPropertyTypologies,
  getPropertyWings,
  getConversationHistory,
  type SupportAssistRequest
} from "../lib/api";
import { knowledgeArticles, type KnowledgeArticle } from "../lib/articleAssist";
import {
  getQuickReplyDispatch,
  resolveProjectSelection,
  visibleMessageText
} from "../lib/customerChatContract";
import { getRoleHomePath } from "../lib/roleNavigation";
import { requestSupportAssist } from "../lib/supportAssistTransport";
import {
  CHAT_RECOVERY_COPY,
  deliveryStateForResponse,
  inspectRetryHistory,
  type ChatDeliveryState
} from "../lib/chatRecovery";
import { loadWidgetConfig } from "../lib/widgetConfig";
import { activeConversation, clearConversation, matchingPropertyFlow, matchingTranscript, replaceConversation, restoredTranscript, savePropertyFlow, saveTranscript } from "../lib/conversationSession";
import { PublicFooter, PublicHeader } from "../components/PublicShell";
import {
  HelpCenterBreadcrumbs,
  HelpCenterSearch,
  HelpCenterViewToggle
} from "../components/HelpCenterUi";
import { Button, Card, Input } from "../components/ui";
import type {
  CreateTicketResponse,
  PropertyInventoryUnit,
  PropertyProject,
  PropertyTypology,
  PropertyWing,
  SupportAssistResponse,
  SupportConversationMessage,
  SupportQuickReply,
  SupportArticleRecord,
  Ticket
} from "../types";

type SupportFlow = {
  articleId?: number;
  id: string;
  label: string;
  prompt: string;
};

type GreetingAction = {
  kind?: "projects";
  label: string;
  prompt: string;
};

const GREETING_ACTIONS: GreetingAction[] = [
  { kind: "projects", label: "Browse all projects", prompt: "Browse all projects" }
];

type PropertyFlowState = {
  inventory: PropertyInventoryUnit[];
  level: "projects" | "wings" | "floors" | "flats" | "flat_details";
  messageId: number;
  projects: PropertyProject[];
  selectedFloor?: number;
  selectedProject?: PropertyProject;
  selectedTypology?: PropertyTypology;
  selectedUnit?: PropertyInventoryUnit;
  selectedWing?: PropertyWing;
  wings: PropertyWing[];
};

type PropertyChoiceButtonProps = {
  index?: number;
  leading?: string | number;
  label: string;
  details?: string[];
  active?: boolean;
  onClick: () => void;
};

function PropertyChoiceButton({ index, leading, label, details = [], active, onClick }: PropertyChoiceButtonProps) {
  return (
    <button className={`store-chat-guided-button${active ? " active" : ""}`} onClick={onClick} type="button">
      {typeof index === "number" || leading !== undefined ? (
        <span className="store-chat-project-index">{leading ?? String(index! + 1).padStart(2, "0")}</span>
      ) : null}
      <span className="store-chat-guided-copy">
        <span className="store-chat-guided-label">{label}</span>
        {details.length ? <span className="store-chat-guided-details">{details.join(" · ")}</span> : null}
      </span>
      <span aria-hidden="true" className="store-chat-guided-arrow"><ChevronRightIcon /></span>
    </button>
  );
}

type SiteVisitFormState = {
  customer_email: string;
  customer_name: string;
  customer_phone: string;
  notes: string;
  preferred_date: string;
  preferred_time: string;
  project_name: string;
};
type HelpCenterAction = {
  description: string;
  href: string;
  icon: "cancel" | "issue" | "track";
  id: string;
  title: string;
};

type HelpCenterCategory = {
  articleCount: number;
  articleId?: number;
  description: string;
  id: string;
  prompt: string;
  title: string;
};

type ChatMessage = {
  backendText?: string;
  canRetry?: boolean;
  contextIssue?: string;
  deliveryState?: ChatDeliveryState;
  feedbackState?: "negative" | "positive";
  id: number;
  isAutomated?: boolean;
  isComplete?: boolean;
  offerActionMenu?: boolean;
  quickReplies?: SupportQuickReply[];
  relatedArticles: KnowledgeArticle[];
  retryError?: boolean;
  retrying?: boolean;
  sender: "bot" | "customer";
  serverTurn?: boolean;
  showHelpfulPrompt?: boolean;
  text: string;
  ticketResult?: CreateTicketResponse | null;
};

type RetryableAssistTurn = {
  botMessageId: number;
  customerMessageId: number;
  primaryArticleId?: number;
  request: SupportAssistRequest;
  serverHistoryBefore: SupportConversationMessage[];
};

function createDefaultChatMessages(): ChatMessage[] {
  return [{
    contextIssue: "Initial welcome",
    id: 1,
    isAutomated: true,
    isComplete: true,
    relatedArticles: [],
    sender: "bot",
    showHelpfulPrompt: false,
    text: "Hi! How can I help you today? You can chat in English, Hindi, Telugu or any Indian language."
  }];
}

import { MessageLauncherIcon, PaperPlaneIcon, ThumbsUpIcon, ThumbsDownIcon, CloseIcon, ChevronRightIcon, ChevronDownIcon, MailIcon, PhoneIcon, TrackOrderIcon, CancelOrderIcon, ReportIssueIcon } from "../components/chat/ChatIcons";
import { type BrowserSpeechRecognition, type SpeechRecognitionConstructor, VOICE_LANGUAGES, type VoiceLanguageCode, detectSpeechLanguage } from "../lib/voiceLanguage";
import { FLOW_TEXT, type ChatLanguage, chatLanguageFromReply, detectChatLanguage } from "../lib/chatLanguage";

const helpCenterArticlesPath = "/home";
const helpCenterHomePath = "/home";
const helpCenterActionDestinationPath = "/home/project-support";

const helpCenterActions: HelpCenterAction[] = [
  {
    description: "",
    href: helpCenterActionDestinationPath,
    icon: "track",
    id: "track-order",
    title: "Book site visit"
  },
  {
    description: "",
    href: helpCenterActionDestinationPath,
    icon: "cancel",
    id: "cancel-order",
    title: "Request pricing"
  },
  {
    description: "",
    href: helpCenterActionDestinationPath,
    icon: "issue",
    id: "report-issue",
    title: "Report site issue"
  }
];

function matchesSearchQuery(query: string, ...values: string[]) {
  if (!query) {
    return true;
  }

  return values.join(" ").toLowerCase().includes(query);
}

function normalizeSupportArticle(article: SupportArticleRecord): KnowledgeArticle {
  return {
    body: article.body,
    category: article.category,
    id: article.id,
    keywords: article.keywords,
    status: article.status,
    summary: article.summary,
    title: article.title,
    url: article.url
  };
}

function normalizeText(value: string) {
  return value.trim().toLowerCase();
}

function getArticlePrompt(article: KnowledgeArticle) {
  return [article.title, article.summary || article.body].filter(Boolean).join(". ");
}

function getArticleSlug(article: Pick<KnowledgeArticle, "id" | "title">) {
  const slug = article.title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");

  return `${article.id}-${slug || "support-article"}`;
}

function getCategorySlug(categoryName: string) {
  return (
    categoryName
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "") || "support"
  );
}

function buildArticlePath(article: Pick<KnowledgeArticle, "id" | "title">) {
  return `/home/articles/${getArticleSlug(article)}`;
}

function buildCategoryPath(categoryName: string) {
  return `/home/categories/${getCategorySlug(categoryName)}`;
}

function findArticleBySlug(articles: KnowledgeArticle[], articleSlug: string | undefined) {
  if (!articleSlug) {
    return null;
  }

  return articles.find((article) => getArticleSlug(article) === articleSlug) ?? null;
}

function findCategoryBySlug(articles: KnowledgeArticle[], categorySlug: string | undefined) {
  if (!categorySlug) {
    return null;
  }

  return (
    articles.find((article) => getCategorySlug(article.category) === categorySlug)?.category ?? null
  );
}

function getArticleExcerpt(article: KnowledgeArticle) {
  if (article.summary.trim()) {
    return article.summary.trim();
  }

  return article.body.replace(/\s+/g, " ").trim().slice(0, 170);
}

function getArticleParagraphs(article: KnowledgeArticle) {
  return article.body
    .split("\n")
    .map((paragraph) => paragraph.trim())
    .filter(Boolean);
}

function getArticleSearchBlob(article: KnowledgeArticle) {
  return normalizeText(
    [
      article.title,
      article.summary,
      article.body,
      article.category,
      article.keywords.join(" ")
    ].join(" ")
  );
}

function rankArticleForHelpCenter(article: KnowledgeArticle) {
  const blob = getArticleSearchBlob(article);

  if (
    blob.includes("site visit") ||
    blob.includes("inspection") ||
    blob.includes("tour") ||
    blob.includes("walkthrough") ||
    blob.includes("show apartment")
  ) {
    return 0;
  }

  if (
    blob.includes("price") ||
    blob.includes("pricing") ||
    blob.includes("quote") ||
    blob.includes("quotation") ||
    blob.includes("availability") ||
    blob.includes("payment")
  ) {
    return 1;
  }

  if (
    blob.includes("handover") ||
    blob.includes("possession") ||
    blob.includes("maintenance") ||
    blob.includes("repair") ||
    blob.includes("defect")
  ) {
    return 2;
  }

  if (
    blob.includes("construction") ||
    blob.includes("progress") ||
    blob.includes("timeline") ||
    blob.includes("documentation") ||
    blob.includes("approval")
  ) {
    return 3;
  }

  return 4;
}

function getOrderActionIcon(icon: HelpCenterAction["icon"]) {
  if (icon === "track") {
    return <TrackOrderIcon />;
  }

  if (icon === "cancel") {
    return <CancelOrderIcon />;
  }

  return <ReportIssueIcon />;
}

function buildSupportFlowsFromArticles(articles: KnowledgeArticle[]): SupportFlow[] {
  return [...articles]
    .sort((left, right) => {
      const rankDifference = rankArticleForHelpCenter(left) - rankArticleForHelpCenter(right);

      if (rankDifference !== 0) {
        return rankDifference;
      }

      return left.title.localeCompare(right.title);
    })
    .slice(0, 5)
    .map((article) => ({
      articleId: article.id,
      id: `article-${article.id}`,
      label: article.title,
      prompt: getArticlePrompt(article)
    }));
}

function buildHelpCenterCategoriesFromArticles(articles: KnowledgeArticle[]): HelpCenterCategory[] {
  const categoryMap = new Map<string, KnowledgeArticle[]>();

  for (const article of articles) {
    const key = article.category.trim() || "Support";
    const existingArticles = categoryMap.get(key) ?? [];
    existingArticles.push(article);
    categoryMap.set(key, existingArticles);
  }

  return [...categoryMap.entries()]
    .sort((left, right) => right[1].length - left[1].length || left[0].localeCompare(right[0]))
    .map(([categoryName, categoryArticles]) => {
      const leadArticle = [...categoryArticles].sort((left, right) =>
        left.title.localeCompare(right.title)
      )[0];

      return {
        articleCount: categoryArticles.length,
        articleId: leadArticle?.id,
        description:
          leadArticle?.summary || `Browse published ${categoryName.toLowerCase()} support articles.`,
        id: `category-${getCategorySlug(categoryName)}`,
        prompt: leadArticle ? getArticlePrompt(leadArticle) : `I need help with ${categoryName}.`,
        title: categoryName
      };
    });
}

function inferIssueType(issue: string) {
  const normalizedIssue = issue.trim().toLowerCase();

  if (
    normalizedIssue.includes("payment") ||
    normalizedIssue.includes("invoice") ||
    normalizedIssue.includes("receipt") ||
    normalizedIssue.includes("refund") ||
    normalizedIssue.includes("installment") ||
    normalizedIssue.includes("instalment") ||
    normalizedIssue.includes("emi")
  ) {
    return "Payments";
  }

  if (
    normalizedIssue.includes("portal") ||
    normalizedIssue.includes("account") ||
    normalizedIssue.includes("login") ||
    normalizedIssue.includes("sign in") ||
    normalizedIssue.includes("access")
  ) {
    return "Account";
  }

  if (
    normalizedIssue.includes("document") ||
    normalizedIssue.includes("agreement") ||
    normalizedIssue.includes("registration") ||
    normalizedIssue.includes("registry") ||
    normalizedIssue.includes("approval") ||
    normalizedIssue.includes("kyc") ||
    normalizedIssue.includes("legal")
  ) {
    return "Documentation";
  }

  if (
    normalizedIssue.includes("site visit") ||
    normalizedIssue.includes("inspection") ||
    normalizedIssue.includes("tour") ||
    normalizedIssue.includes("walkthrough") ||
    normalizedIssue.includes("sample flat")
  ) {
    return "Site Visit";
  }

  if (
    normalizedIssue.includes("handover") ||
    normalizedIssue.includes("possession") ||
    normalizedIssue.includes("key handover")
  ) {
    return "Handover";
  }

  if (
    normalizedIssue.includes("maintenance") ||
    normalizedIssue.includes("repair") ||
    normalizedIssue.includes("defect") ||
    normalizedIssue.includes("leak") ||
    normalizedIssue.includes("crack") ||
    normalizedIssue.includes("plumbing") ||
    normalizedIssue.includes("electrical")
  ) {
    return "Maintenance";
  }

  if (
    normalizedIssue.includes("construction") ||
    normalizedIssue.includes("progress") ||
    normalizedIssue.includes("timeline") ||
    normalizedIssue.includes("milestone") ||
    normalizedIssue.includes("delay")
  ) {
    return "Construction";
  }

  if (
    normalizedIssue.includes("price") ||
    normalizedIssue.includes("pricing") ||
    normalizedIssue.includes("quote") ||
    normalizedIssue.includes("quotation") ||
    normalizedIssue.includes("availability") ||
    normalizedIssue.includes("inventory") ||
    normalizedIssue.includes("unit") ||
    normalizedIssue.includes("apartment") ||
    normalizedIssue.includes("villa") ||
    normalizedIssue.includes("plot") ||
    normalizedIssue.includes("brochure") ||
    normalizedIssue.includes("floor plan")
  ) {
    return "Sales";
  }

  return "General";
}

function inferIntent(issue: string) {
  const normalizedIssue = issue.trim().toLowerCase();

  if (normalizedIssue.includes("refund")) {
    return "Refund Review";
  }

  if (
    normalizedIssue.includes("payment") ||
    normalizedIssue.includes("invoice") ||
    normalizedIssue.includes("receipt") ||
    normalizedIssue.includes("installment") ||
    normalizedIssue.includes("instalment") ||
    normalizedIssue.includes("emi")
  ) {
    return "Payment Plan";
  }

  if (
    normalizedIssue.includes("portal") ||
    normalizedIssue.includes("account") ||
    normalizedIssue.includes("login") ||
    normalizedIssue.includes("access")
  ) {
    return "Account Access";
  }

  if (
    normalizedIssue.includes("document") ||
    normalizedIssue.includes("agreement") ||
    normalizedIssue.includes("registration") ||
    normalizedIssue.includes("approval") ||
    normalizedIssue.includes("kyc") ||
    normalizedIssue.includes("legal")
  ) {
    return "Legal Documentation";
  }

  if (
    normalizedIssue.includes("site visit") ||
    normalizedIssue.includes("inspection") ||
    normalizedIssue.includes("tour") ||
    normalizedIssue.includes("walkthrough")
  ) {
    return "Site Visit Request";
  }

  if (
    normalizedIssue.includes("handover") ||
    normalizedIssue.includes("possession") ||
    normalizedIssue.includes("key handover")
  ) {
    return "Possession / Handover";
  }

  if (
    normalizedIssue.includes("maintenance") ||
    normalizedIssue.includes("repair") ||
    normalizedIssue.includes("defect") ||
    normalizedIssue.includes("leak") ||
    normalizedIssue.includes("crack")
  ) {
    return "Maintenance Request";
  }

  if (
    normalizedIssue.includes("construction") ||
    normalizedIssue.includes("progress") ||
    normalizedIssue.includes("timeline") ||
    normalizedIssue.includes("milestone") ||
    normalizedIssue.includes("delay")
  ) {
    return "Construction Update";
  }

  if (
    normalizedIssue.includes("availability") ||
    normalizedIssue.includes("inventory") ||
    normalizedIssue.includes("unit") ||
    normalizedIssue.includes("floor plan")
  ) {
    return "Availability Check";
  }

  if (
    normalizedIssue.includes("price") ||
    normalizedIssue.includes("pricing") ||
    normalizedIssue.includes("quote") ||
    normalizedIssue.includes("quotation") ||
    normalizedIssue.includes("brochure")
  ) {
    return "Quotation Request";
  }

  return "General Inquiry";
}

function getFirstNameFromEmail(email: string) {
  const normalizedEmail = email.trim();

  if (!normalizedEmail) {
    return "there";
  }

  const firstPart = normalizedEmail.split("@")[0] ?? "there";
  const firstName = firstPart.replace(/[._-]+/g, " ").trim().split(" ")[0] ?? "there";

  return firstName.charAt(0).toUpperCase() + firstName.slice(1);
}

function getAssistantBrandName(assistantName: string) {
  const trimmed = assistantName.replace(/\bsupport\b/i, "").trim();
  return trimmed || assistantName.trim() || "Support";
}

function buildPreviewTicket(
  issue: string
): Pick<
  Ticket,
  "business_hours_tag" | "intent_tag" | "issue" | "issue_type" | "priority" | "queue_name" | "status"
> {
  const issueType = inferIssueType(issue);
  const intentTag = inferIntent(issue);

  const priorityMap: Record<string, string> = {
    Account: "Medium",
    Construction: "Medium",
    Documentation: "High",
    General: "Low",
    Handover: "High",
    Maintenance: "High",
    Payments: "High",
    Sales: "Medium",
    "Site Visit": "Medium"
  };

  let queueName = "General Queue";

  if (intentTag === "Refund Review" || intentTag === "Payment Plan") {
    queueName = "Project Finance Desk";
  } else if (
    intentTag === "Site Visit Request" ||
    intentTag === "Construction Update"
  ) {
    queueName = "Site Operations Desk";
  } else if (intentTag === "Legal Documentation" || intentTag === "Account Access") {
    queueName = "Documentation Desk";
  } else if (intentTag === "Possession / Handover" || intentTag === "Maintenance Request") {
    queueName = "Handover and Maintenance Desk";
  } else if (intentTag === "Quotation Request" || intentTag === "Availability Check") {
    queueName = "Sales Advisory Desk";
  }

  return {
    business_hours_tag: "Business Hours",
    intent_tag: intentTag,
    issue,
    issue_type: issueType,
    priority: priorityMap[issueType] ?? "Low",
    queue_name: queueName,
    status: "Open"
  };
}

function getRelatedArticlesFromPool(
  articles: KnowledgeArticle[],
  ticket: Pick<
    Ticket,
    "business_hours_tag" | "intent_tag" | "issue" | "issue_type" | "priority" | "queue_name" | "status"
  >
) {
  const searchBlob = normalizeText(
    [
      ticket.issue_type,
      ticket.intent_tag,
      ticket.issue,
      ticket.priority,
      ticket.status,
      ticket.queue_name,
      ticket.business_hours_tag
    ]
      .filter(Boolean)
      .join(" ")
  );

  return [...articles]
    .map((article) => ({
      article,
      score: article.keywords.reduce(
        (total, keyword) => (searchBlob.includes(normalizeText(keyword)) ? total + 1 : total),
        0
      )
    }))
    .filter(({ score, article }) => score > 0 || searchBlob.includes(normalizeText(article.category)))
    .sort((left, right) => right.score - left.score || left.article.title.localeCompare(right.article.title))
    .map(({ article }) => article)
    .slice(0, 3);
}

function mergeRelatedArticles(
  primaryArticleId: number | undefined,
  issue: string,
  articlePool: KnowledgeArticle[]
) {
  const previewTicket = buildPreviewTicket(issue);
  const dynamicArticles = getRelatedArticlesFromPool(
    articlePool.length ? articlePool : knowledgeArticles,
    previewTicket
  );
  const primaryArticle = articlePool.find((article) => article.id === primaryArticleId);
  const orderedArticles = [primaryArticle, ...dynamicArticles].filter(
    (article): article is KnowledgeArticle => Boolean(article)
  );
  const uniqueArticles: KnowledgeArticle[] = [];
  const seenArticleIds = new Set<number>();

  for (const article of orderedArticles) {
    if (seenArticleIds.has(article.id)) {
      continue;
    }

    seenArticleIds.add(article.id);
    uniqueArticles.push(article);
  }

  return {
    relatedArticles: uniqueArticles.slice(0, 3)
  };
}

function buildArticleBasedText(customerEmail: string, article: KnowledgeArticle | undefined) {
  const customerFirstName = getFirstNameFromEmail(customerEmail);

  if (!article) {
    return [
      `Hi ${customerFirstName},`,
      "",
      "I could not find the right help article for that topic yet.",
      "If you still need help, tap Need more help and send us your email plus a short message."
    ].join("\n");
  }

  return [
    `Hi ${customerFirstName},`,
    "",
    `Based on "${article.title}", ${getArticleExcerpt(article)}.`,
    "If you still need help, tap Need more help and send us your email plus a short message."
  ].join("\n");
}

function buildDemoBotResponse(
  issue: string,
  customerEmail: string,
  primaryArticleId: number | undefined,
  articlePool: KnowledgeArticle[]
) {
  const { relatedArticles } = mergeRelatedArticles(primaryArticleId, issue, articlePool);
  const topArticle = relatedArticles[0];

  if (topArticle) {
    return {
      relatedArticles,
      text: buildArticleBasedText(customerEmail, topArticle)
    };
  }

  return {
    relatedArticles,
    text: buildArticleBasedText(customerEmail, undefined)
  };
}

function getHelpfulPromptMessage(feedbackState?: ChatMessage["feedbackState"]) {
  if (feedbackState === "positive") {
    return "Thanks for the thumbs up. I am glad this answer helped.";
  }

  if (feedbackState === "negative") {
    return "Thanks for the feedback. Tell me what is missing, or tap Need more help.";
  }

  return "Was this helpful?";
}

function detectHelpfulFeedback(text: string): ChatMessage["feedbackState"] | undefined {
  const normalizedText = normalizeText(text);

  if (!normalizedText) {
    return undefined;
  }

  const positivePatterns = [
    "thanks",
    "thank you",
    "helpful",
    "great",
    "good",
    "perfect",
    "resolved",
    "clear",
    "got it",
    "understood",
    "that helps",
    "all good"
  ];
  const negativePatterns = [
    "not helpful",
    "still not",
    "still need",
    "did not help",
    "didn't help",
    "wrong",
    "bad",
    "confusing",
    "unclear",
    "not clear",
    "issue",
    "problem",
    "not solved",
    "no help"
  ];

  if (negativePatterns.some((pattern) => normalizedText.includes(pattern))) {
    return "negative";
  }

  if (positivePatterns.some((pattern) => normalizedText.includes(pattern))) {
    return "positive";
  }

  if (normalizedText === "yes" || normalizedText === "yep" || normalizedText === "sure") {
    return "positive";
  }

  if (normalizedText === "no" || normalizedText === "nope") {
    return "negative";
  }

  return undefined;
}

function isShortHelpfulReview(text: string) {
  const trimmedText = text.trim();

  if (!trimmedText || trimmedText.includes("?")) {
    return false;
  }

  return trimmedText.split(/\s+/).length <= 8;
}

function findLatestHelpfulPrompt(messages: ChatMessage[]) {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];

    if (
      message.sender === "bot" &&
      message.showHelpfulPrompt &&
      !message.feedbackState
    ) {
      return message;
    }
  }

  return undefined;
}

function applyHelpfulFeedback(
  messages: ChatMessage[],
  messageId: number,
  feedbackState: NonNullable<ChatMessage["feedbackState"]>
) {
  return messages.map((message) =>
    message.id === messageId
      ? {
          ...message,
          feedbackState
        }
      : message
  );
}

function buildAssistConversationMessages(
  messages: ChatMessage[],
  nextCustomerMessage: string,
  shouldResetConversation: boolean
): SupportConversationMessage[] {
  const normalizedNextMessage = nextCustomerMessage.trim();

  if (shouldResetConversation) {
    return normalizedNextMessage
      ? [
          {
            sender: "customer",
            text: normalizedNextMessage
          }
        ]
      : [];
  }

  const history = messages
    .map((message) => ({
      sender: message.sender,
      text: message.text.trim()
    }))
    .filter((message) => message.text);

  if (normalizedNextMessage) {
    history.push({
      sender: "customer",
      text: normalizedNextMessage
    });
  }

  return history;
}

function buildServerConversationHistory(messages: ChatMessage[]): SupportConversationMessage[] {
  return messages
    .filter((message) => message.serverTurn)
    .map((message) => ({
      sender: message.sender,
      text: message.backendText ?? message.text
    }));
}

function markCustomerTurnStored(messages: ChatMessage[], customerMessageId: number) {
  return messages.map((message) =>
    message.id === customerMessageId
      ? { ...message, serverTurn: true }
      : message
  );
}

function appendBotMessageDelta(
  messages: ChatMessage[],
  messageId: number,
  contextIssue: string,
  delta: string
) {
  const existingMessageIndex = messages.findIndex((message) => message.id === messageId);

  if (existingMessageIndex === -1) {
    const nextMessage: ChatMessage = {
      contextIssue,
      feedbackState: undefined,
      id: messageId,
      isAutomated: true,
      isComplete: false,
      relatedArticles: [],
      sender: "bot",
      showHelpfulPrompt: false,
      text: delta
    };

    return [
      ...messages,
      nextMessage
    ];
  }

  return messages.map((message) =>
    message.id === messageId
      ? {
          ...message,
          text: `${message.text}${delta}`
        }
      : message
  );
}

function finalizeBotMessage(
  messages: ChatMessage[],
  messageId: number,
  contextIssue: string,
  finalMessage: Omit<ChatMessage, "id" | "sender">
) {
  const existingMessageIndex = messages.findIndex((message) => message.id === messageId);
  const nextMessage: ChatMessage = {
    ...finalMessage,
    isComplete: true,
    contextIssue,
    id: messageId,
    sender: "bot"
  };

  if (existingMessageIndex === -1) {
    return [...messages, nextMessage];
  }

  return messages.map((message) => (message.id === messageId ? nextMessage : message));
}

function formatPropertyPrice(value?: number) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "";
  return new Intl.NumberFormat("en-IN", {
    currency: "INR",
    maximumFractionDigits: 0,
    style: "currency"
  }).format(value);
}
function formatArticleCount(count: number) {
  return `${count} ${count === 1 ? "article" : "articles"}`;
}

function prepareConversationalSpeech(value: string) {
  const boilerplatePatterns = [
    /^hi(?:\s+[^,]+)?,?$/i,
    /^hello(?:\s+[^,]+)?,?$/i,
    /i checked (?:the|our) (?:published )?workspace knowledge/i,
    /i checked our saved .*support guidance/i,
    /^based on (?:the )?(?:support article|training document)/i,
    /^reply here/i,
    /^tap need more help/i,
    /^i have linked the closest support content/i
  ];
  const cleanedText = value
    .replace(/https?:\/\/\S+/gi, "")
    .replace(/[*_#]/g, "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line && !boilerplatePatterns.some((pattern) => pattern.test(line)))
    .join(" ")
    .replace(/\s+/g, " ")
    .trim();
  const sentences = cleanedText.split(/(?<=[.!?])\s+/).filter(Boolean);
  let questionUsed = false;

  return sentences
    .filter((sentence) => {
      if (!sentence.includes("?")) return true;
      if (questionUsed) return false;
      questionUsed = true;
      return true;
    })
    .slice(0, 4)
    .join(" ")
    .trim();
}
function isSiteVisitBookingRequest(value: string) {
  const normalizedValue = value.trim().toLowerCase();
  return normalizedValue.includes("visit") && ["book", "schedule", "arrange", "request"]
    .some((word) => normalizedValue.includes(word));
}
function isVoiceTicketRequest(value: string) {
  const normalizedValue = value.trim().toLowerCase();
  const mentionsTicket = normalizedValue.includes("ticket");
  const hasTicketAction = ["create", "raise", "open", "generate", "make", "log", "set"]
    .some((word) => normalizedValue.includes(word));
  const asksForHuman =
    normalizedValue.includes("human agent") ||
    normalizedValue.includes("talk to a human") ||
    normalizedValue.includes("connect me to a human");

  return (mentionsTicket && hasTicketAction) || asksForHuman;
}

function isValidEmail(email: string) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim());
}

export function CustomerHomePage() {
  const { isAuthenticated, role } = useRole();
  const location = useLocation();
  const navigate = useNavigate();
  const { articleSlug, categorySlug } = useParams<{
    articleSlug?: string;
    categorySlug?: string;
  }>();
  const widgetConfig = useMemo(() => loadWidgetConfig(), []);
  const [helpCenterQuery, setHelpCenterQuery] = useState("");
  const [categoryView, setCategoryView] = useState<"grid" | "list">("grid");
  const [supportArticles, setSupportArticles] = useState<SupportArticleRecord[]>([]);
  const [chatEmail, setChatEmail] = useState("");
  const [chatDraft, setChatDraft] = useState("");
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>(createDefaultChatMessages);
  const [isChatOpen, setIsChatOpen] = useState(true);
  const [isCreatingTicket, setIsCreatingTicket] = useState(false);
  const [isTypingReply, setIsTypingReply] = useState(false);
  const [isAssistPending, setIsAssistPending] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isVoiceConversation, setIsVoiceConversation] = useState(false);
  const [isVoiceMuted, setIsVoiceMuted] = useState(false);
  const [voiceTranscript, setVoiceTranscript] = useState("");
  const [voiceLanguage, setVoiceLanguage] = useState<VoiceLanguageCode>("en-IN");
  const [isFollowUpFormVisible, setIsFollowUpFormVisible] = useState(false);
  const [storefrontError, setStorefrontError] = useState("");
  const [activeFollowUpIssue, setActiveFollowUpIssue] = useState("");
  const [propertyFlow, setPropertyFlow] = useState<PropertyFlowState | null>(null);
  const [chatLanguage, setChatLanguage] = useState<ChatLanguage>("en");
  const chatLanguageRef = useRef<ChatLanguage>("en");
  const [isSiteVisitFormVisible, setIsSiteVisitFormVisible] = useState(false);
  const [isSubmittingSiteVisit, setIsSubmittingSiteVisit] = useState(false);
  const [siteVisitProjects, setSiteVisitProjects] = useState<PropertyProject[]>([]);
  const [siteVisitForm, setSiteVisitForm] = useState<SiteVisitFormState>({
    customer_email: "",
    customer_name: "",
    customer_phone: "",
    notes: "",
    preferred_date: "",
    preferred_time: "",
    project_name: ""
  });
  const chatBodyRef = useRef<HTMLDivElement | null>(null);
  const initialConversationRef = useRef<ReturnType<typeof activeConversation> | null>(null);
  if (!initialConversationRef.current) initialConversationRef.current = activeConversation();
  const conversationIdRef = useRef<string>(initialConversationRef.current.id);
  const [isRestoringChat, setIsRestoringChat] = useState(initialConversationRef.current.restored);
  const [restoreState, setRestoreState] = useState<"failed" | "loading" | "ready">(
    initialConversationRef.current.restored ? "loading" : "ready"
  );
  const [canSaveTranscript, setCanSaveTranscript] = useState(!initialConversationRef.current.restored);
  const chatEmailRef = useRef<HTMLInputElement | null>(null);
  const chatComposeRef = useRef<HTMLTextAreaElement | null>(null);
  const chatMessageInputRef = useRef<HTMLInputElement | null>(null);
  const retryButtonRef = useRef<HTMLButtonElement | null>(null);
  const restoreRetryButtonRef = useRef<HTMLButtonElement | null>(null);
  const restoreAttemptRef = useRef(0);
  const activeAssistRef = useRef(false);
  const retryTurnsRef = useRef(new Map<number, RetryableAssistTurn>());
  const siteVisitNameRef = useRef<HTMLInputElement | null>(null);
  const chatContactComposeRef = useRef<HTMLInputElement | null>(null);
  const chatCloseButtonRef = useRef<HTMLButtonElement | null>(null);
  const chatLauncherRef = useRef<HTMLButtonElement | null>(null);
  const previousChatOpenRef = useRef(isChatOpen);
  const speechRecognitionRef = useRef<BrowserSpeechRecognition | null>(null);
  const lastSpokenMessageIdRef = useRef<number | null>(null);
  const voiceSessionActiveRef = useRef(false);
  const voiceAwaitingReplyRef = useRef(false);
  const voiceReplyPendingRef = useRef(false);
  const speechUtteranceRef = useRef<SpeechSynthesisUtterance | null>(null);
  const voiceAudioRef = useRef<HTMLAudioElement | null>(null);
  const voiceAudioUrlRef = useRef<string | null>(null);
  const submittedVoiceTranscriptRef = useRef("");
  const voiceMutedRef = useRef(false);
  const voiceLanguageRef = useRef<VoiceLanguageCode>("en-IN");

  useEffect(() => {
    if (previousChatOpenRef.current === isChatOpen) return;
    previousChatOpenRef.current = isChatOpen;
    const frame = window.requestAnimationFrame(() => {
      if (isChatOpen) chatCloseButtonRef.current?.focus();
      else chatLauncherRef.current?.focus();
    });
    return () => window.cancelAnimationFrame(frame);
  }, [isChatOpen]);

  useEffect(() => {
    if (restoreState !== "failed") return;
    const frame = window.requestAnimationFrame(() => restoreRetryButtonRef.current?.focus());
    return () => window.cancelAnimationFrame(frame);
  }, [restoreState]);

  async function restoreConversationHistory(id: string) {
    const attempt = ++restoreAttemptRef.current;
    setRestoreState("loading");
    setIsRestoringChat(true);
    setCanSaveTranscript(false);
    try {
      const history = await getConversationHistory(id);
      if (attempt !== restoreAttemptRef.current || conversationIdRef.current !== id) return;
      const snapshot = matchingTranscript(id, history.messages);
      if (snapshot && (history.exists || !history.messages.length)) {
        setChatMessages(snapshot.map((message) => ({ ...message, relatedArticles: [], isAutomated: message.sender === "bot" })));
        setPropertyFlow(matchingPropertyFlow<PropertyFlowState>(id, history.messages, snapshot));
      } else if (history.exists) {
        setChatMessages(restoredTranscript(id, history.messages, history.quick_replies).map((message) => ({
          ...message, relatedArticles: [], isAutomated: message.sender === "bot"
        })));
      } else {
        clearConversation(id);
        conversationIdRef.current = activeConversation().id;
        setChatMessages(createDefaultChatMessages());
      }
      setRestoreState("ready");
      setIsRestoringChat(false);
      setCanSaveTranscript(true);
    } catch {
      if (attempt !== restoreAttemptRef.current || conversationIdRef.current !== id) return;
      setRestoreState("failed");
      setIsRestoringChat(false);
    }
  }

  useEffect(() => {
    if (!initialConversationRef.current?.restored) return;
    void restoreConversationHistory(initialConversationRef.current.id);
    return () => { restoreAttemptRef.current += 1; };
  }, []);

  useEffect(() => {
    if (canSaveTranscript && !isRestoringChat) {
      saveTranscript(conversationIdRef.current, chatMessages);
      savePropertyFlow(conversationIdRef.current, propertyFlow);
    }
  }, [canSaveTranscript, isRestoringChat, chatMessages, propertyFlow]);

  const normalizedHelpCenterQuery = helpCenterQuery.trim().toLowerCase();
  const publishedSupportArticles = useMemo(() => {
    const publishedArticles = supportArticles
      .filter((article) => article.status === "Published")
      .map(normalizeSupportArticle);

    return publishedArticles.length ? publishedArticles : knowledgeArticles;
  }, [supportArticles]);
  const supportFlows = useMemo(
    () => buildSupportFlowsFromArticles(publishedSupportArticles),
    [publishedSupportArticles]
  );
  const helpCenterCategories = useMemo(
    () => buildHelpCenterCategoriesFromArticles(publishedSupportArticles),
    [publishedSupportArticles]
  );
  const selectedArticle = useMemo(
    () => findArticleBySlug(publishedSupportArticles, articleSlug),
    [articleSlug, publishedSupportArticles]
  );
  const selectedCategory = useMemo(
    () => findCategoryBySlug(publishedSupportArticles, categorySlug),
    [categorySlug, publishedSupportArticles]
  );
  const isHomeDemoPage = location.pathname === helpCenterHomePath;
  const isArticlePage = Boolean(articleSlug);
  const isCategoryPage = Boolean(categorySlug) && !isArticlePage;
  const isHelpCenterLandingPage = !isHomeDemoPage && !isArticlePage && !isCategoryPage;
  const categoryArticles = useMemo(() => {
    if (!selectedCategory) {
      return [];
    }

    return publishedSupportArticles.filter((article) => article.category === selectedCategory);
  }, [publishedSupportArticles, selectedCategory]);
  const relatedCategoryArticles = useMemo(() => {
    if (!selectedArticle) {
      return [];
    }

    return publishedSupportArticles
      .filter(
        (article) =>
          article.category === selectedArticle.category && article.id !== selectedArticle.id
      )
      .slice(0, 4);
  }, [publishedSupportArticles, selectedArticle]);
  const featuredHelpCenterCategories = useMemo(
    () => helpCenterCategories.slice(0, 3),
    [helpCenterCategories]
  );
  const totalPublishedArticles = publishedSupportArticles.length;
  const totalPublishedCategories = helpCenterCategories.length;

  useEffect(() => {
    let isMounted = true;

    void getAdminArticles()
      .then((response) => {
        if (!isMounted) {
          return;
        }

        setSupportArticles(response.articles);
      })
      .catch(() => {
        if (!isMounted) {
          return;
        }

        setSupportArticles([]);
      });

    return () => {
      isMounted = false;
    };
  }, []);

  const filteredSupportFlows = useMemo(
    () =>
      supportFlows.filter((flow) => {
        const matchedArticle = publishedSupportArticles.find((article) => article.id === flow.articleId);

        return matchesSearchQuery(
          normalizedHelpCenterQuery,
          flow.label,
          flow.prompt,
          matchedArticle?.title ?? "",
          matchedArticle?.category ?? ""
        );
      }),
    [normalizedHelpCenterQuery, publishedSupportArticles, supportFlows]
  );
  const filteredHelpCenterActions = useMemo(
    () =>
      helpCenterActions.filter((action) => {
        return matchesSearchQuery(
          normalizedHelpCenterQuery,
          action.title,
          action.description
        );
      }),
    [normalizedHelpCenterQuery]
  );
  const filteredHelpCenterCategories = useMemo(
    () =>
      helpCenterCategories.filter((category) => {
        const matchedArticle = publishedSupportArticles.find((article) => article.id === category.articleId);

        return matchesSearchQuery(
          normalizedHelpCenterQuery,
          category.title,
          category.description,
          category.prompt,
          matchedArticle?.title ?? "",
          matchedArticle?.category ?? ""
        );
      }),
    [helpCenterCategories, normalizedHelpCenterQuery, publishedSupportArticles]
  );
  const matchingPublishedArticles = useMemo(
    () =>
      publishedSupportArticles.filter((article) =>
        matchesSearchQuery(
          normalizedHelpCenterQuery,
          article.title,
          article.summary,
          article.body,
          article.category,
          article.keywords.join(" ")
        )
      ),
    [normalizedHelpCenterQuery, publishedSupportArticles]
  );
  const filteredCategoryArticles = useMemo(
    () =>
      categoryArticles.filter((article) =>
        matchesSearchQuery(
          normalizedHelpCenterQuery,
          article.title,
          article.summary,
          article.body,
          article.category,
          article.keywords.join(" ")
        )
      ),
    [categoryArticles, normalizedHelpCenterQuery]
  );
  const searchMatchCount = matchingPublishedArticles.length + filteredHelpCenterCategories.length;

  useEffect(() => {
    if (location.hash) {
      let targetId = location.hash.slice(1);

      try {
        targetId = decodeURIComponent(targetId);
      } catch {
        // Keep the literal hash when a malformed escape sequence is supplied.
      }

      const target = document.getElementById(targetId);

      if (target) {
        target.scrollIntoView({ behavior: "smooth", block: "start" });
        target.focus({ preventScroll: true });
      }

      return;
    }

    window.scrollTo({
      behavior: "smooth",
      top: 0
    });
  }, [articleSlug, categorySlug, location.hash, location.pathname]);

  useEffect(() => {
    if (!chatBodyRef.current) {
      return;
    }

    const customerMessages = chatBodyRef.current.querySelectorAll<HTMLElement>(
      ".store-chat-message.customer"
    );
    const latestCustomerMessage = customerMessages.item(customerMessages.length - 1);
    const latestMessage = chatMessages[chatMessages.length - 1];
    const shouldShowLatestAnswer = latestMessage?.sender === "bot" && latestMessage.isComplete;

    chatBodyRef.current.scrollTo({
      behavior: "smooth",
      top: shouldShowLatestAnswer
        ? chatBodyRef.current.scrollHeight
        : latestCustomerMessage
          ? Math.max(0, latestCustomerMessage.offsetTop - 16)
          : chatBodyRef.current.scrollHeight
    });
  }, [chatMessages, isChatOpen, isTypingReply]);

  function resetChatHome() {
    setChatMessages(createDefaultChatMessages());
    setChatDraft("");
    setActiveFollowUpIssue("");
    setIsFollowUpFormVisible(false);
    setStorefrontError("");
    setIsTypingReply(false);
    setPropertyFlow(null);
    setIsSiteVisitFormVisible(false);
  }

  function openFollowUpForm(issue: string, prefillNote = "") {
    setActiveFollowUpIssue(issue.trim());
    setIsFollowUpFormVisible(true);
    setStorefrontError("");
    setChatDraft(prefillNote);
    window.setTimeout(() => {
      if (chatEmail.trim()) {
        chatComposeRef.current?.focus();
        return;
      }

      chatEmailRef.current?.focus();
    }, 0);
  }

  function openContactMode(issue = "") {
    setIsChatOpen(true);
    openFollowUpForm(issue);
  }

  function handleHelpfulFeedbackSelection(
    messageId: number,
    feedbackState: NonNullable<ChatMessage["feedbackState"]>
  ) {
    setChatMessages((current) => applyHelpfulFeedback(current, messageId, feedbackState));
  }

  function handleHelpfulReviewFromText(reviewText: string) {
    const feedbackState = detectHelpfulFeedback(reviewText);
    const pendingMessage = findLatestHelpfulPrompt(chatMessages);

    if (!feedbackState || !pendingMessage || !isShortHelpfulReview(reviewText)) {
      return false;
    }

    const nextId = Date.now();

    setChatMessages((current) => {
      const updatedMessages = applyHelpfulFeedback(
        current,
        pendingMessage.id,
        feedbackState
      );

      const nextMessages: ChatMessage[] = [
        ...updatedMessages,
        {
          contextIssue: pendingMessage.contextIssue ?? "",
          id: nextId,
          relatedArticles: [],
          sender: "customer",
          text: reviewText.trim()
        }
      ];

      if (feedbackState === "negative") {
        nextMessages.push({
          contextIssue: pendingMessage.contextIssue ?? "",
          id: nextId + 1,
          isAutomated: true,
          relatedArticles: [],
          sender: "bot",
          text:
            "I am sorry that answer missed the mark. Share what is missing, or tap Need more help and I will route this to Acrobuild support."
        });
      }

      return nextMessages;
    });
    setChatDraft("");
    setIsChatOpen(true);
    return true;
  }

  async function createTicketForIssue(issue: string, customerNote: string) {
    const cleanedIssue = issue.trim();
    const cleanedNote = customerNote.trim();

    if (!isValidEmail(chatEmail)) {
      setStorefrontError("Enter a valid email address so we know where to follow up.");
      return;
    }

    if (!cleanedNote) {
      setStorefrontError("Add a short message so the support team knows what still needs help.");
      return;
    }

    try {
      setIsCreatingTicket(true);
      setStorefrontError("");
      const combinedIssue = cleanedIssue
        ? `${cleanedIssue}\n\nCustomer follow-up:\n${cleanedNote}`
        : cleanedNote;
      const ticketResult = await createSupportTicket({
        customer_email: chatEmail.trim(),
        issue: combinedIssue
      });

      const confirmationText = [
        `Thanks ${getFirstNameFromEmail(chatEmail)}.`,
        "",
        `I have logged this for the team as ticket ${ticketResult.ticket_id}.`,
        `It is currently routed to ${ticketResult.assigned_agent} in the ${ticketResult.queue_name}.`
      ].join("\n");

      setChatMessages((current) => [
        ...current,
        {
          contextIssue: cleanedIssue,
          id: Date.now() - 1,
          relatedArticles: [],
          sender: "customer",
          text: cleanedNote
        },
        {
          contextIssue: cleanedIssue,
          id: Date.now(),
          isAutomated: true,
          isComplete: true,
          relatedArticles: [],
          sender: "bot",
          text: confirmationText,
          ticketResult
        }
      ]);
      setChatDraft("");
      setActiveFollowUpIssue("");
      setIsFollowUpFormVisible(false);
      setIsChatOpen(true);
    } catch (ticketError) {
      setStorefrontError(
        ticketError instanceof Error ? ticketError.message : "Unable to create the support ticket."
      );
    } finally {
      setIsCreatingTicket(false);
    }
  }

  function buildVoiceTicketContext() {
    const customerMessages = chatMessages
      .filter((message) => message.sender === "customer")
      .slice(-4)
      .map((message) => message.text.trim())
      .filter(Boolean);

    return customerMessages.join(" - ") || "Voice support request";
  }

  function requestTicketFromVoice() {
    const ticketContext = buildVoiceTicketContext();

    if (isValidEmail(chatEmail)) {
      voiceAwaitingReplyRef.current = true;
      void createTicketForIssue(
        ticketContext,
        "Customer requested a support ticket during the voice conversation."
      );
      return;
    }

    voiceSessionActiveRef.current = false;
    voiceAwaitingReplyRef.current = false;
    setIsVoiceConversation(false);
    setIsListening(false);
    setIsSpeaking(false);
    speechRecognitionRef.current?.stop();
    speechRecognitionRef.current = null;
    window.speechSynthesis?.cancel();
    openFollowUpForm(ticketContext);
    setChatDraft("Customer requested a support ticket during the voice conversation.");
    setStorefrontError("Enter your email to create the ticket and receive follow-up updates.");
  }
  function focusRetryControl() {
    window.requestAnimationFrame(() => retryButtonRef.current?.focus());
  }

  function finishRetryableAssistFailure(
    turn: RetryableAssistTurn,
    deliveryState: "interrupted" | "offline",
    text: string
  ) {
    retryTurnsRef.current.set(turn.botMessageId, turn);
    setChatMessages((current) =>
      finalizeBotMessage(current, turn.botMessageId, turn.request.issue, {
        canRetry: true,
        deliveryState,
        feedbackState: undefined,
        isAutomated: true,
        relatedArticles: [],
        retryError: false,
        retrying: false,
        showHelpfulPrompt: false,
        text
      })
    );
    focusRetryControl();
  }

  async function performAssistTurn(turn: RetryableAssistTurn) {
    try {
      await requestSupportAssist(turn.request, {
        onDelta: (text) => {
          setIsTypingReply(false);
          setChatMessages((current) =>
            appendBotMessageDelta(current, turn.botMessageId, turn.request.issue, text)
          );
        },
        onDone: (assistResponse) => {
          retryTurnsRef.current.delete(turn.botMessageId);
          setIsTypingReply(false);
          applyReplyLanguage(assistResponse);
          setChatMessages((current) =>
            finalizeBotMessage(
              markCustomerTurnStored(current, turn.customerMessageId),
              turn.botMessageId,
              turn.request.issue,
              {
                canRetry: false,
                deliveryState: deliveryStateForResponse(assistResponse),
                feedbackState: undefined,
                isAutomated: true,
                offerActionMenu: assistResponse.offer_action_menu ?? false,
                quickReplies: assistResponse.quick_replies ?? [],
                relatedArticles: [],
                retryError: false,
                retrying: false,
                serverTurn: true,
                showHelpfulPrompt: false,
                text: assistResponse.answer
              }
            )
          );
        },
        onPartial: (answer) => {
          setIsTypingReply(false);
          finishRetryableAssistFailure(turn, "interrupted", answer);
        }
      });
    } catch {
      const demoResponse = buildDemoBotResponse(
        turn.request.issue,
        chatEmail,
        turn.primaryArticleId,
        publishedSupportArticles
      );
      setIsTypingReply(false);
      finishRetryableAssistFailure(turn, "offline", demoResponse.text);
    } finally {
      activeAssistRef.current = false;
      setIsAssistPending(false);
      setIsTypingReply(false);
    }
  }

  async function retryAssistTurn(botMessageId: number) {
    const turn = retryTurnsRef.current.get(botMessageId);
    if (!turn || activeAssistRef.current || restoreState !== "ready") return;
    if (turn.request.conversation_id !== conversationIdRef.current) return;

    activeAssistRef.current = true;
    setIsAssistPending(true);
    setIsTypingReply(true);
    setChatMessages((current) => current.map((message) =>
      message.id === botMessageId
        ? { ...message, retryError: false, retrying: true }
        : message
    ));

    let handedOff = false;
    try {
      const history = await getConversationHistory(conversationIdRef.current);
      const result = inspectRetryHistory(
        history.messages,
        turn.serverHistoryBefore,
        turn.request.issue
      );

      if (result.kind === "completed") {
        retryTurnsRef.current.delete(botMessageId);
        setChatMessages((current) =>
          finalizeBotMessage(
            markCustomerTurnStored(current, turn.customerMessageId),
            botMessageId,
            turn.request.issue,
            {
              canRetry: false,
              deliveryState: "recovered",
              feedbackState: undefined,
              isAutomated: true,
              quickReplies: history.quick_replies,
              relatedArticles: [],
              retryError: false,
              retrying: false,
              serverTurn: true,
              showHelpfulPrompt: false,
              text: result.answer
            }
          )
        );
        window.requestAnimationFrame(() => chatMessageInputRef.current?.focus());
        return;
      }

      if (result.kind === "diverged") {
        setChatMessages((current) => current.map((message) =>
          message.id === botMessageId
            ? { ...message, retryError: true, retrying: false }
            : message
        ));
        focusRetryControl();
        return;
      }

      setChatMessages((current) => current.map((message) =>
        message.id === botMessageId
          ? {
              ...message,
              canRetry: false,
              deliveryState: undefined,
              retryError: false,
              retrying: false,
              text: ""
            }
          : message
      ));
      handedOff = true;
      await performAssistTurn(turn);
    } catch {
      setChatMessages((current) => current.map((message) =>
        message.id === botMessageId
          ? { ...message, retryError: true, retrying: false }
          : message
      ));
      focusRetryControl();
    } finally {
      if (!handedOff) {
        activeAssistRef.current = false;
        setIsAssistPending(false);
        setIsTypingReply(false);
      }
    }
  }

  async function queueBotResponse(
    issue: string,
    primaryArticleId: number | undefined,
    shouldResetConversation: boolean,
    customerMessageText = issue
  ) {
    if (activeAssistRef.current || restoreState !== "ready") return;
    const trimmedIssue = issue.trim();
    const trimmedCustomerMessage = customerMessageText.trim();
    if (!trimmedIssue) return;

    activeAssistRef.current = true;
    setIsAssistPending(true);
    const customerMessageId = Date.now();
    const botMessageId = customerMessageId + 1;
    const conversationMessages = buildAssistConversationMessages(
      chatMessages,
      trimmedCustomerMessage || trimmedIssue,
      shouldResetConversation
    );
    const serverHistoryBefore = shouldResetConversation
      ? []
      : buildServerConversationHistory(chatMessages);

    if (shouldResetConversation) conversationIdRef.current = replaceConversation();

    const primaryArticle =
      publishedSupportArticles.find((article) => article.id === primaryArticleId) ?? undefined;
    const languageHint = isVoiceConversation && voiceLanguage !== "en-IN" ? VOICE_LANGUAGES[voiceLanguage] : "";
    const turn: RetryableAssistTurn = {
      botMessageId,
      customerMessageId,
      primaryArticleId,
      request: {
        article_hint_url: isVoiceConversation ? "" : (primaryArticle?.url ?? ""),
        conversation_id: conversationIdRef.current,
        conversation_messages: conversationMessages,
        customer_email: chatEmail.trim(),
        issue: trimmedIssue,
        issue_type: inferIssueType(trimmedCustomerMessage || trimmedIssue),
        language_hint: languageHint,
        limit: isVoiceConversation ? 6 : 2,
        prefer_fast_response: !isVoiceConversation,
        prefer_qwen_response: true
      },
      serverHistoryBefore
    };

    setStorefrontError("");
    setIsTypingReply(true);
    setPropertyFlow(null);
    setIsChatOpen(true);
    setIsFollowUpFormVisible(false);
    setActiveFollowUpIssue("");
    setChatDraft("");
    setChatMessages((current) => {
      const nextCustomerMessage: ChatMessage = {
        backendText: trimmedIssue,
        contextIssue: trimmedIssue,
        id: customerMessageId,
        relatedArticles: [],
        sender: "customer",
        serverTurn: false,
        text: trimmedCustomerMessage || trimmedIssue
      };
      return shouldResetConversation ? [nextCustomerMessage] : [...current, nextCustomerMessage];
    });

    if (!widgetConfig.aiResponsesEnabled) {
      const demoResponse = buildDemoBotResponse(
        trimmedIssue,
        chatEmail,
        primaryArticleId,
        publishedSupportArticles
      );
      setChatMessages((current) => [
        ...current,
        {
          canRetry: false,
          contextIssue: trimmedIssue,
          deliveryState: "degraded",
          feedbackState: undefined,
          id: botMessageId,
          isAutomated: true,
          isComplete: true,
          relatedArticles: [],
          sender: "bot",
          showHelpfulPrompt: false,
          text: demoResponse.text
        }
      ]);
      activeAssistRef.current = false;
      setIsAssistPending(false);
      setIsTypingReply(false);
      return;
    }

    await performAssistTurn(turn);
  }

  function beginPropertyFlowStep(label: string, contextIssue: string) {
    const customerMessageId = Date.now();
    setStorefrontError("");
    setIsTypingReply(true);
    setIsSiteVisitFormVisible(false);
    setChatMessages((current) => [
      ...current,
      {
        contextIssue,
        id: customerMessageId,
        relatedArticles: [],
        sender: "customer",
        text: label
      }
    ]);
    return customerMessageId + 1;
  }

  function finishPropertyFlowStep(
    botMessageId: number,
    contextIssue: string,
    text: string,
    nextFlow: PropertyFlowState
  ) {
    setIsTypingReply(false);
    setPropertyFlow({ ...nextFlow, messageId: botMessageId });
    setChatMessages((current) => [
      ...current,
      {
        contextIssue,
        id: botMessageId,
        isAutomated: true,
        isComplete: true,
        relatedArticles: [],
        sender: "bot",
        showHelpfulPrompt: false,
        text
      }
    ]);
  }

  function failPropertyFlowStep(botMessageId: number, contextIssue: string, error: unknown) {
    const message = error instanceof Error ? error.message : "Unable to load live property data.";
    setIsTypingReply(false);
    setStorefrontError(message);
    setChatMessages((current) => [
      ...current,
      {
        contextIssue,
        id: botMessageId,
        isAutomated: true,
        isComplete: true,
        relatedArticles: [],
        sender: "bot",
        showHelpfulPrompt: false,
        text: FLOW_TEXT[chatLanguageRef.current].stepFailed
      }
    ]);
  }

  function applyReplyLanguage(response: SupportAssistResponse) {
    const nextLanguage = chatLanguageFromReply(response.reply_language, response.reply_script, chatLanguageRef.current);
    chatLanguageRef.current = nextLanguage;
    setChatLanguage(nextLanguage);
  }

  function updateChatLanguage(text: string) {
    const nextLanguage = detectChatLanguage(text, voiceLanguageRef.current, chatLanguageRef.current);
    chatLanguageRef.current = nextLanguage;
    setChatLanguage(nextLanguage);
  }

  async function startProjectsFlow(label = FLOW_TEXT[chatLanguageRef.current].browseAll, location?: string | null) {
    const t = FLOW_TEXT[chatLanguageRef.current];
    const contextIssue = location ? `Browse live projects in ${location}` : "Browse live projects";
    const botMessageId = beginPropertyFlowStep(label, contextIssue);
    try {
      const response = await getPropertyProjects();
      const normalizedLocation = location?.trim().toLowerCase();
      const projects = normalizedLocation
        ? response.items.filter((project) => {
            const city = project.city?.trim().toLowerCase() ?? "";
            const locality = project.locality?.trim().toLowerCase() ?? "";
            return (
              (city && (city.includes(normalizedLocation) || normalizedLocation.includes(city))) ||
              (locality && (locality.includes(normalizedLocation) || normalizedLocation.includes(locality)))
            );
          })
        : response.items;
      const message = location
        ? projects.length ? t.chooseProjectInLocation(projects.length, location) : t.noProjectsInLocation(location)
        : projects.length ? t.chooseProject(projects.length) : t.noProjects;
      finishPropertyFlowStep(
        botMessageId,
        contextIssue,
        message,
        {
          inventory: [],
          level: "projects",
          messageId: botMessageId,
          projects,
          wings: []
        }
      );
    } catch (error) {
      failPropertyFlowStep(botMessageId, contextIssue, error);
    }
  }

  async function selectPropertyProject(
    project: PropertyProject,
    customerLabel = project.projectName,
    projects = propertyFlow?.projects ?? [project]
  ) {
    const t = FLOW_TEXT[chatLanguageRef.current];
    const contextIssue = `Project ${project.projectName}`;
    const botMessageId = beginPropertyFlowStep(customerLabel, contextIssue);
    try {
      const response = await getPropertyWings(project.id);
      const wings = response.items;
      finishPropertyFlowStep(
        botMessageId,
        contextIssue,
        wings.length ? t.chooseWing(project.projectName) : t.noWings(project.projectName),
        {
          inventory: [],
          level: "wings",
          messageId: botMessageId,
          projects,
          selectedProject: project,
          wings
        }
      );
    } catch (error) {
      failPropertyFlowStep(botMessageId, contextIssue, error);
    }
  }

  async function selectNumberedProject(projectName: string, customerLabel: string) {
    try {
      const response = await getPropertyProjects();
      const selectedProject = response.items.find(
        (project) => project.projectName.trim().toLowerCase() === projectName.trim().toLowerCase()
      );
      if (!selectedProject) {
        throw new Error("That project is no longer present in the live project list.");
      }
      await selectPropertyProject(selectedProject, customerLabel, response.items);
    } catch (error) {
      setStorefrontError(error instanceof Error ? error.message : "Unable to verify that project.");
    }
  }

  function handlePropertyFlowTextSelection(value: string) {
    if (!propertyFlow) return false;
    const normalizedValue = value.trim().toLowerCase();
    if (propertyFlow.level === "projects") {
      const numberMatch = normalizedValue.match(/^(?:project\s*)?(\d{1,2})$/);
      const selectedProject = propertyFlow.projects.find(
        (project) => project.projectName.trim().toLowerCase() === normalizedValue
      ) ?? (numberMatch ? propertyFlow.projects[Number(numberMatch[1]) - 1] : undefined);
      if (selectedProject) {
        setChatDraft("");
        void selectPropertyProject(selectedProject, value.trim());
        return true;
      }
    }
    if (propertyFlow.level === "wings") {
      const numberMatch = normalizedValue.match(/^(?:wing\s*)?(\d{1,2})$/);
      const selectedWing = propertyFlow.wings.find((wing) =>
        [wing.name, wing.code].some((label) => label?.trim().toLowerCase() === normalizedValue)
      ) ?? (numberMatch ? propertyFlow.wings[Number(numberMatch[1]) - 1] : undefined)
        ?? (/^wings?$/.test(normalizedValue) && propertyFlow.wings.length === 1 ? propertyFlow.wings[0] : undefined);
      if (selectedWing) {
        setChatDraft("");
        void selectPropertyWing(selectedWing);
        return true;
      }
    }
    return false;
  }

  async function selectPropertyWing(wing: PropertyWing) {
    const t = FLOW_TEXT[chatLanguageRef.current];
    const project = propertyFlow?.selectedProject;
    const contextIssue = `Wing ${wing.name}`;
    const botMessageId = beginPropertyFlowStep(wing.name, contextIssue);
    try {
      const response = await getPropertyInventory(wing.id);
      const inventory = response.items;
      const floors = [...new Set(
        inventory
          .map((unit) => unit.floorNumber)
          .filter((floor): floor is number => typeof floor === "number")
      )].sort((left, right) => left - right);
      finishPropertyFlowStep(
        botMessageId,
        contextIssue,
        floors.length ? t.chooseFloor(wing.name) : t.noFlatsInWing(wing.name),
        {
          inventory,
          level: "floors",
          messageId: botMessageId,
          projects: propertyFlow?.projects ?? [],
          selectedProject: project,
          selectedWing: wing,
          wings: propertyFlow?.wings ?? [wing]
        }
      );
    } catch (error) {
      failPropertyFlowStep(botMessageId, contextIssue, error);
    }
  }

  function selectPropertyFloor(floor: number) {
    const t = FLOW_TEXT[chatLanguageRef.current];
    const flats = (propertyFlow?.inventory ?? []).filter((unit) => unit.floorNumber === floor);
    const contextIssue = `Floor ${floor}`;
    const customerMessageId = Date.now();
    const botMessageId = customerMessageId + 1;
    setChatMessages((current) => [
      ...current,
      {
        contextIssue,
        id: customerMessageId,
        relatedArticles: [],
        sender: "customer",
        text: t.floor(floor)
      },
      {
        contextIssue,
        id: botMessageId,
        isAutomated: true,
        isComplete: true,
        relatedArticles: [],
        sender: "bot",
        showHelpfulPrompt: false,
        text: flats.length ? t.chooseFlat(floor) : t.noFlatsOnFloor(floor)
      }
    ]);
    setPropertyFlow((current) => current ? {
      ...current,
      inventory: flats,
      level: "flats",
      messageId: botMessageId,
      selectedFloor: floor,
      selectedUnit: undefined
    } : current);
  }

  async function selectInventoryUnit(unit: PropertyInventoryUnit) {
    const wing = propertyFlow?.selectedWing;
    if (!wing) return;
    const t = FLOW_TEXT[chatLanguageRef.current];
    const flatLabel = t.flat(unit.unitNumber ?? unit.id);
    const contextIssue = `${flatLabel} price`;
    const botMessageId = beginPropertyFlowStep(flatLabel, contextIssue);
    try {
      const typologies = (await getPropertyTypologies(wing.id)).items;
      const typology = typologies.find((item) => item.id === unit.typologyId);
      const minimumPrice = formatPropertyPrice(typology?.minBasePrice);
      const maximumPrice = formatPropertyPrice(typology?.maxBasePrice);
      const priceText = minimumPrice && maximumPrice
        ? minimumPrice === maximumPrice
          ? minimumPrice
          : `${minimumPrice} – ${maximumPrice}`
        : minimumPrice || maximumPrice || t.priceNotListed;
      const rateLabel = typology?.rateType ? ` (${typology.rateType})` : "";
      const areaParts = [
        typology?.carpetArea ? `${t.carpetArea}: ${typology.carpetArea} sq ft` : "",
        typology?.saleableArea ? `${t.saleableArea}: ${typology.saleableArea} sq ft` : ""
      ].filter(Boolean);
      finishPropertyFlowStep(
        botMessageId,
        contextIssue,
        [
          `${flatLabel}${typology?.typologyName ? ` · ${typology.typologyName}` : ""}`,
          `${t.livePrice}: ${priceText}${rateLabel}`,
          ...areaParts,
          t.canBookVisit
        ].join("\n"),
        {
          inventory: propertyFlow?.inventory ?? [unit],
          level: "flat_details",
          messageId: botMessageId,
          projects: propertyFlow?.projects ?? [],
          selectedFloor: propertyFlow?.selectedFloor,
          selectedProject: propertyFlow?.selectedProject,
          selectedTypology: typology,
          selectedUnit: unit,
          selectedWing: wing,
          wings: propertyFlow?.wings ?? [wing]
        }
      );
    } catch (error) {
      failPropertyFlowStep(botMessageId, contextIssue, error);
    }
  }

  async function openSiteVisitBooking(projectName?: string) {
    setStorefrontError("");
    let projects = propertyFlow?.projects ?? siteVisitProjects;
    if (!projects.length) {
      try {
        projects = (await getPropertyProjects()).items;
        setSiteVisitProjects(projects);
      } catch (error) {
        setStorefrontError(error instanceof Error ? error.message : "Unable to load projects.");
        return;
      }
    }
    const selectedProjectName = projectName ?? propertyFlow?.selectedProject?.projectName ?? "";
    setSiteVisitProjects(projects);
    setSiteVisitForm((current) => ({
      ...current,
      customer_email: current.customer_email || chatEmail,
      project_name: projectName !== undefined ? projectName : selectedProjectName || current.project_name
    }));
    setIsSiteVisitFormVisible(true);
    setIsFollowUpFormVisible(false);
    window.setTimeout(() => siteVisitNameRef.current?.focus(), 0);
  }

  async function submitSiteVisitBooking() {
    if (
      !siteVisitForm.customer_name.trim() ||
      !isValidEmail(siteVisitForm.customer_email) ||
      !siteVisitForm.customer_phone.trim() ||
      !siteVisitForm.project_name.trim() ||
      !siteVisitForm.preferred_date ||
      !siteVisitForm.preferred_time
    ) {
      setStorefrontError("Enter name, valid email, phone, project, preferred date, and preferred time.");
      return;
    }

    setIsSubmittingSiteVisit(true);
    setStorefrontError("");
    try {
      const result = await createSiteVisit({
        ...siteVisitForm,
        typology_name: propertyFlow?.selectedTypology?.typologyName ?? propertyFlow?.selectedUnit?.typologyName ?? propertyFlow?.selectedUnit?.typologyType ?? "",
        unit_number: String(propertyFlow?.selectedUnit?.unitNumber ?? ""),
        wing_name: propertyFlow?.selectedWing?.name ?? ""
      });
      const messageId = Date.now();
      setChatEmail(siteVisitForm.customer_email.trim());
      setChatMessages((current) => [
        ...current,
        {
          contextIssue: "Site visit booking",
          id: messageId,
          relatedArticles: [],
          sender: "customer",
          text: "Book a site visit"
        },
        {
          contextIssue: "Site visit booking",
          id: messageId + 1,
          isAutomated: true,
          isComplete: true,
          relatedArticles: [],
          sender: "bot",
          showHelpfulPrompt: false,
          text: `Your site visit request has been submitted. Ticket ${result.ticket_id} is assigned to ${result.assigned_agent}.`,
          ticketResult: result
        }
      ]);
      setIsSiteVisitFormVisible(false);
    } catch (error) {
      setStorefrontError(error instanceof Error ? error.message : "Unable to submit the site visit.");
    } finally {
      setIsSubmittingSiteVisit(false);
    }
  }
  function handleChatFlowSelect(flow: SupportFlow) {
    void queueBotResponse(flow.prompt, flow.articleId, true, flow.label);
  }

  function openArticlePage(articleId: number | undefined) {
    if (!articleId) {
      return;
    }

    const targetArticle = publishedSupportArticles.find((article) => article.id === articleId);

    if (!targetArticle) {
      return;
    }

    navigate(buildArticlePath(targetArticle));
  }

  function handleHelpCenterArticleOpen(flow: SupportFlow) {
    openArticlePage(flow.articleId);
  }

  function handleActionSelect(action: HelpCenterAction) {
    navigate(action.href);
  }

  function handleCategorySelect(category: HelpCenterCategory) {
    navigate(buildCategoryPath(category.title));
  }

  function handleHelpCenterSearchSubmit() {
    const matchingArticle = matchingPublishedArticles[0];

    if (matchingArticle) {
      navigate(buildArticlePath(matchingArticle));
      return;
    }

    if (filteredHelpCenterCategories[0]) {
      navigate(buildCategoryPath(filteredHelpCenterCategories[0].title));
      return;
    }

    openContactMode(helpCenterQuery);
  }

  const latestCompletedBotMessageId = [...chatMessages]
    .reverse()
    .find((message) => message.sender === "bot" && message.isComplete)?.id;  const hasActiveConversation = chatMessages.length > 0 || isTypingReply;
  const isContactMode = !hasActiveConversation && isFollowUpFormVisible;
  const isMenuMode = !hasActiveConversation && !isContactMode;
  const showBackControl = hasActiveConversation || isContactMode;
  const supportsSpeechRecognition = Boolean(
    (window as typeof window & {
      SpeechRecognition?: SpeechRecognitionConstructor;
      webkitSpeechRecognition?: SpeechRecognitionConstructor;
    }).SpeechRecognition ||
      (window as typeof window & {
        webkitSpeechRecognition?: SpeechRecognitionConstructor;
      }).webkitSpeechRecognition
  );

  function startVoiceRecognition() {
    const speechWindow = window as typeof window & {
      SpeechRecognition?: SpeechRecognitionConstructor;
      webkitSpeechRecognition?: SpeechRecognitionConstructor;
    };
    const Recognition = speechWindow.SpeechRecognition ?? speechWindow.webkitSpeechRecognition;

    if (!Recognition) {
      setStorefrontError("Voice input is not supported in this browser. Try Chrome or Edge.");
      voiceSessionActiveRef.current = false;
      voiceAwaitingReplyRef.current = false;
      setIsVoiceConversation(false);
      return;
    }

    if (!voiceSessionActiveRef.current || voiceMutedRef.current || speechRecognitionRef.current) {
      return;
    }

    const recognition = new Recognition();
    recognition.lang = voiceLanguageRef.current;
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.onresult = (event) => {
      const speechResults = Array.from(event.results);
      const transcript = speechResults
        .map((result) => result[0]?.transcript ?? "")
        .join(" ")
        .trim();

      if (!transcript) {
        return;
      }

      setChatDraft(transcript);
      setVoiceTranscript(transcript);

      const hasFinalResult = speechResults[speechResults.length - 1]?.isFinal === true;
      if (!hasFinalResult) {
        return;
      }
      if (submittedVoiceTranscriptRef.current === transcript) {
        return;
      }
      submittedVoiceTranscriptRef.current = transcript;

      if (isVoiceTicketRequest(transcript)) {
        requestTicketFromVoice();
        return;
      }

      if (!isContactMode && !isFollowUpFormVisible && !isTypingReply) {
        if (!handleHelpfulReviewFromText(transcript)) {
          voiceAwaitingReplyRef.current = true;
          voiceReplyPendingRef.current = true;
          void queueBotResponse(transcript, undefined, !hasActiveConversation);
        }
      }
    };
    recognition.onerror = (event) => {
      if (event.error === "not-allowed") {
        voiceSessionActiveRef.current = false;
      voiceAwaitingReplyRef.current = false;
        setIsVoiceConversation(false);
        setStorefrontError("Microphone access was blocked. Allow microphone permission and try again.");
      } else if (event.error !== "aborted" && event.error !== "no-speech") {
        setStorefrontError("I could not hear that clearly. Please try again.");
      }
      setIsListening(false);
    };
    recognition.onend = () => {
      setIsListening(false);
      speechRecognitionRef.current = null;

      if (voiceSessionActiveRef.current && !voiceMutedRef.current && !voiceAwaitingReplyRef.current && !isTypingReply && !window.speechSynthesis.speaking) {
        window.setTimeout(startVoiceRecognition, 350);
      }
    };

    speechRecognitionRef.current = recognition;
    setStorefrontError("");
    setIsListening(true);

    try {
      recognition.start();
    } catch {
      speechRecognitionRef.current = null;
      setIsListening(false);
      setStorefrontError("Unable to start the microphone. Please try again.");
    }
  }

  function handleVoiceToggle() {
    if (voiceSessionActiveRef.current) {
      voiceSessionActiveRef.current = false;
      voiceAwaitingReplyRef.current = false;
      setIsVoiceConversation(false);
      setIsListening(false);
      speechRecognitionRef.current?.stop();
      speechRecognitionRef.current = null;
      voiceAudioRef.current?.pause();
      voiceAudioRef.current = null;
      window.speechSynthesis?.cancel();
      voiceMutedRef.current = false;
      setIsVoiceMuted(false);
      setVoiceTranscript("");
      submittedVoiceTranscriptRef.current = "";
      return;
    }

    const latestBotMessage = [...chatMessages].reverse().find((message) => message.sender === "bot");
    lastSpokenMessageIdRef.current = latestBotMessage?.id ?? null;
    voiceSessionActiveRef.current = true;
    voiceMutedRef.current = false;
    setIsVoiceMuted(false);
    setIsVoiceConversation(true);
    window.speechSynthesis?.cancel();
    startVoiceRecognition();
  }
  function toggleVoiceMicrophone() {
    if (voiceMutedRef.current) {
      voiceMutedRef.current = false;
      setIsVoiceMuted(false);
      submittedVoiceTranscriptRef.current = "";
      window.setTimeout(startVoiceRecognition, 100);
      return;
    }
    voiceMutedRef.current = true;
    setIsVoiceMuted(true);
    setIsListening(false);
    speechRecognitionRef.current?.stop();
    speechRecognitionRef.current = null;
  }

  function interruptVoiceReply() {
    voiceAudioRef.current?.pause();
    voiceAudioRef.current = null;
    if (voiceAudioUrlRef.current) {
      URL.revokeObjectURL(voiceAudioUrlRef.current);
      voiceAudioUrlRef.current = null;
    }
    window.speechSynthesis?.cancel();
    speechUtteranceRef.current = null;
    voiceAwaitingReplyRef.current = false;
    voiceReplyPendingRef.current = false;
    setIsSpeaking(false);
    submittedVoiceTranscriptRef.current = "";
    window.setTimeout(startVoiceRecognition, 100);
  }
  useEffect(() => {
    if ((!isVoiceConversation && !voiceReplyPendingRef.current) || isTypingReply || !isChatOpen) {
      return;
    }

    const latestBotMessage = [...chatMessages].reverse().find((message) => message.sender === "bot");
    if (
      !latestBotMessage?.text.trim() ||
      latestBotMessage.isComplete !== true ||
      latestBotMessage.id === lastSpokenMessageIdRef.current ||
      !("speechSynthesis" in window)
    ) {
      return;
    }

    lastSpokenMessageIdRef.current = latestBotMessage.id;
    const spokenText = prepareConversationalSpeech(visibleMessageText(latestBotMessage));
    const utterance = new SpeechSynthesisUtterance(spokenText);
    speechUtteranceRef.current = utterance;
    const availableVoices = window.speechSynthesis.getVoices();
    const detectedSpeechLanguage = detectSpeechLanguage(spokenText, voiceLanguage);
    const selectedLanguagePrefix = detectedSpeechLanguage.split("-")[0].toLowerCase();
    const matchingVoices = availableVoices.filter((voice) =>
      voice.lang.toLowerCase().replace("_", "-").startsWith(selectedLanguagePrefix)
    );
    const naturalVoice = matchingVoices.find((voice) =>
      /natural|neural|google|online/i.test(voice.name)
    ) ?? matchingVoices.find((voice) =>
      voice.lang.toLowerCase().replace("_", "-") === detectedSpeechLanguage.toLowerCase()
    ) ?? matchingVoices[0];

    if (naturalVoice) {
      utterance.voice = naturalVoice;
      utterance.lang = naturalVoice.lang;
    } else {
      utterance.lang = detectedSpeechLanguage;
    }
    utterance.rate = 0.96;
    utterance.pitch = 1.02;
    utterance.volume = 1;
    utterance.onstart = () => {
      setIsSpeaking(true);
      setStorefrontError("");
    };
    utterance.onend = () => {
      setIsSpeaking(false);
      speechUtteranceRef.current = null;
      voiceAwaitingReplyRef.current = false;
      voiceReplyPendingRef.current = false;
      if (voiceSessionActiveRef.current) {
        window.setTimeout(startVoiceRecognition, 250);
      }
    };
    utterance.onerror = (event) => {
      setIsSpeaking(false);
      speechUtteranceRef.current = null;

      if (event.error === "canceled" || event.error === "interrupted") {
        return;
      }

      voiceAwaitingReplyRef.current = false;
      setStorefrontError("Audio playback could not start. Check the site sound permission.");
    };
    function playGeneratedIndicVoice() {
      setStorefrontError(`Preparing a clear ${VOICE_LANGUAGES[detectedSpeechLanguage]} voice. This device may take about a minute.`);
      void generateIndicVoiceAudio(spokenText, detectedSpeechLanguage)
        .then((audioBlob) => {
          const audioUrl = URL.createObjectURL(audioBlob);
          const audio = new Audio(audioUrl);
          voiceAudioUrlRef.current = audioUrl;
          voiceAudioRef.current = audio;
          audio.onplay = () => {
            setIsSpeaking(true);
            setStorefrontError("");
          };
          audio.onended = () => {
            setIsSpeaking(false);
            voiceAwaitingReplyRef.current = false;
            voiceReplyPendingRef.current = false;
            voiceAudioRef.current = null;
            URL.revokeObjectURL(audioUrl);
            voiceAudioUrlRef.current = null;
            if (voiceSessionActiveRef.current) {
              window.setTimeout(startVoiceRecognition, 250);
            }
          };
          return audio.play();
        })
        .catch(() => {
          voiceAwaitingReplyRef.current = false;
          voiceReplyPendingRef.current = false;
          setStorefrontError(`A ${VOICE_LANGUAGES[detectedSpeechLanguage]} voice is not installed and local voice generation failed.`);
        });
    }

    // Never let an English/system-default voice read Telugu script. It is
    // fast but unintelligible. Use it only when a genuine language voice exists.
    if (naturalVoice) {
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(utterance);
    } else if (detectedSpeechLanguage !== "en-IN") {
      playGeneratedIndicVoice();
    } else {
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(utterance);
    }
  }, [chatMessages, isChatOpen, isTypingReply, isVoiceConversation]);

  useEffect(
    () => () => {
      speechRecognitionRef.current?.stop();
      voiceAudioRef.current?.pause();
      if (voiceAudioUrlRef.current) {
        URL.revokeObjectURL(voiceAudioUrlRef.current);
      }
      window.speechSynthesis?.cancel();
    },
    []
  );
  const assistantBrandName = getAssistantBrandName(widgetConfig.assistantName);
  const assistantInitial = assistantBrandName.charAt(0).toUpperCase() || "S";
  const assistantBotLabel = `${assistantBrandName} Support`;
  const conversationBotLabel = "Acrobuild Support";
  const contactWelcomeMessage =
    widgetConfig.introMessage.trim() ||
    "Welcome! Please enter your email and send us a message to connect with our team.";
  const widgetLogoUrl = widgetConfig.logoUrl.trim();
  const chatAccentColor = widgetConfig.accentColor.trim().toLowerCase() === "#1f2937"
    ? "#0055ff"
    : widgetConfig.accentColor;
  const chatFontFamily = widgetConfig.fontFamily.includes("Inter")
    ? "var(--font-family-product)"
    : widgetConfig.fontFamily;
  const conversationDateLabel = useMemo(
    () =>
      new Intl.DateTimeFormat("en-US", {
        day: "numeric",
        month: "long"
      }).format(new Date()),
    []
  );
  const workspaceLink = isAuthenticated ? getRoleHomePath(role) : "/login";
  const workspaceLabel = isAuthenticated ? "Open workspace" : "Sign in";
  const helpCenterHeroSignals = [
    "Pricing & inventory",
    "Construction updates",
    "Documents & approvals",
    "Handover & maintenance"
  ];
  const helpCenterHeroMetrics = [
    { label: "Published articles", value: String(totalPublishedArticles).padStart(2, "0") },
    { label: "Support categories", value: String(totalPublishedCategories).padStart(2, "0") },
    { label: "Quick response paths", value: String(supportFlows.length).padStart(2, "0") }
  ];
  const helpCenterHeroCategories = (
    featuredHelpCenterCategories.length ? featuredHelpCenterCategories : helpCenterCategories
  ).slice(0, 3);
  const selectedArticleParagraphs = selectedArticle ? getArticleParagraphs(selectedArticle) : [];
  const publicHomeServices = [
    {
      alt: "Residential buildings set around landscaped shared spaces.",
      copy: "Ask the assistant for current project options and the home types available in the connected catalogue.",
      image: "/images/real-world/projects-available-homes-card.png",
      label: "Project discovery",
      title: "Explore projects and home types"
    },
    {
      alt: "A home plan and material samples being reviewed at a table.",
      copy: "Ask a specific question about pricing, availability, project details, or documents and review the answer provided.",
      image: "/images/real-world/pricing-home-details-card.png",
      label: "Property questions",
      title: "Understand the details"
    },
    {
      alt: "A couple viewing a home with a property advisor.",
      copy: "Send a site-visit request or ask for support when you are ready for a team follow-up.",
      image: "/images/real-world/site-visit-buyer-support-card.png",
      label: "Next steps",
      title: "Request a follow-up"
    }
  ];
  const publicHomeSteps = [
    {
      copy: "Share what you want to know in the Acrobuild assistant.",
      title: "Start with your question"
    },
    {
      copy: "When a property choice needs clarification, select from the options the assistant provides.",
      title: "Narrow the request"
    },
    {
      copy: "Continue in chat or send a supported request when you need the team to follow up.",
      title: "Choose the next step"
    }
  ];

  return (
    <div className={`help-center-page${isHomeDemoPage ? " help-center-marketing-home" : " help-center-content-page"}`} id="top">
      <PublicHeader workspaceLabel={workspaceLabel} workspaceLink={workspaceLink} />

      <main className="help-center-main">
        {isHomeDemoPage ? (
          <>
            <section className="public-home-hero">
              <div className="help-center-shell public-home-hero-inner">
                <div className="public-home-hero-copy">
                  <p className="public-home-eyebrow">Acrobuild property support</p>
                  <h1>
                    Clear answers for your <span>property journey.</span>
                  </h1>
                  <p>
                    Explore Acrobuild projects, ask about homes and pricing, browse support guides,
                    or request the next step through one connected support experience.
                  </p>

                  <div className="public-home-actions">
                    <button
                      className="public-home-action"
                      onClick={() => setIsChatOpen(true)}
                      type="button"
                    >
                      Ask the assistant
                    </button>
                    <Link className="public-home-action secondary" to={helpCenterArticlesPath}>
                      Browse support guides
                    </Link>
                  </div>

                  <div className="public-home-hero-note">
                    Property-specific answers follow the information available from Acrobuild's
                    connected services.
                  </div>
                </div>

                <div className="public-home-visual">
                  <figure className="public-home-visual-frame">
                    <img
                      alt="A couple walking through a residential community with a property advisor."
                      src="/images/real-world/property-support-hero-v2.png"
                    />
                    <figcaption className="public-home-visual-caption">
                      <strong>Start with what matters to you</strong>
                      <span>
                        Ask a question, review the options provided, and continue at your own pace.
                      </span>
                    </figcaption>
                  </figure>
                </div>
              </div>
            </section>

            <section className="public-home-section">
              <div className="help-center-shell">
                <div className="public-home-section-head">
                  <p className="public-home-eyebrow">How we can help</p>
                  <h2>Support for questions before and after you choose a home.</h2>
                  <p>
                    Use the assistant for property questions, or move into the existing support
                    paths when you need a follow-up.
                  </p>
                </div>

                <div className="public-home-card-grid">
                  {publicHomeServices.map((service) => (
                    <button
                      className="public-home-card"
                      key={service.title}
                      onClick={() => setIsChatOpen(true)}
                      type="button"
                    >
                      <img alt={service.alt} loading="lazy" src={service.image} />
                      <span className="public-home-card-body">
                        <span className="public-home-card-label">{service.label}</span>
                        <strong>{service.title}</strong>
                        <span>{service.copy}</span>
                        <span className="public-home-card-link">Open assistant</span>
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            </section>

            {featuredHelpCenterCategories.length ? (
              <section className="public-home-section is-subtle">
                <div className="help-center-shell">
                  <div className="public-home-section-head">
                    <p className="public-home-eyebrow">Support guides</p>
                    <h2>Browse help by topic.</h2>
                    <p>
                      Open the same published support categories already available in the Acrobuild
                      help centre.
                    </p>
                  </div>

                  <div className="public-home-guide-grid">
                    {featuredHelpCenterCategories.map((category, index) => (
                      <Link
                        className="public-home-guide-card"
                        key={category.id}
                        to={buildCategoryPath(category.title)}
                      >
                        <span className="public-home-guide-number">{String(index + 1).padStart(2, "0")}</span>
                        <strong>{category.title}</strong>
                        <span>{formatArticleCount(category.articleCount)}</span>
                      </Link>
                    ))}
                  </div>
                </div>
              </section>
            ) : null}

            <section className="public-home-section">
              <div className="help-center-shell public-home-support-grid">
                <div className="public-home-support-copy">
                  <p className="public-home-eyebrow">A simple support path</p>
                  <h2>Begin with a question. Continue with the context intact.</h2>
                  <p>
                    The Acrobuild assistant helps you move through supported property and service
                    questions without changing the existing chat journey.
                  </p>

                  <ol className="public-home-steps">
                    {publicHomeSteps.map((step, index) => (
                      <li className="public-home-step" key={step.title}>
                        <span className="public-home-step-number">{index + 1}</span>
                        <div>
                          <strong>{step.title}</strong>
                          <p>{step.copy}</p>
                        </div>
                      </li>
                    ))}
                  </ol>

                  <div className="public-home-actions">
                    <button
                      className="public-home-action"
                      onClick={() => setIsChatOpen(true)}
                      type="button"
                    >
                      Open support chat
                    </button>
                    <Link className="public-home-action secondary" to={helpCenterArticlesPath}>
                      Visit the help centre
                    </Link>
                  </div>
                </div>

                <figure className="public-home-support-image">
                  <img
                    alt="A property advisor reviewing information with customers."
                    loading="lazy"
                    src="/images/real-world/help-center-support.png"
                  />
                </figure>
              </div>
            </section>
          </>
        ) : null}

        {isHelpCenterLandingPage ? (
          <>
            <section className="help-center-hero">
              <div className="help-center-shell help-center-hero-inner">
                <div className="help-center-hero-copy">
                  <div className="help-center-article-kicker help-center-hero-kicker">
                    Acrobuild support desk
                  </div>
                  <h1>Buyer guidance, project updates, and final handover help in one command center.</h1>
                  <p>
                    Browse published articles, move into the right support lane fast, or message the
                    team when your project question needs a human follow-up.
                  </p>

                  <div className="help-center-hero-chip-row">
                    {helpCenterHeroSignals.map((signal) => (
                      <span className="help-center-hero-chip" key={signal}>
                        {signal}
                      </span>
                    ))}
                  </div>

                  <HelpCenterSearch
                    label="Search help center"
                    onChange={setHelpCenterQuery}
                    onSubmit={handleHelpCenterSearchSubmit}
                    placeholder="Search support articles and categories"
                    showClear
                    value={helpCenterQuery}
                  />

                  {normalizedHelpCenterQuery ? (
                    <div aria-live="polite" className="help-center-search-meta" role="status">
                      {searchMatchCount
                        ? `Showing ${searchMatchCount} matching support articles and categories for "${helpCenterQuery.trim()}".`
                        : `No exact article matches for "${helpCenterQuery.trim()}". You can still contact the team below.`}
                    </div>
                  ) : null}

                  <div className="help-center-hero-metric-row">
                    {helpCenterHeroMetrics.map((metric) => (
                      <article className="help-center-hero-metric" key={metric.label}>
                        <strong>{metric.value}</strong>
                        <span>{metric.label}</span>
                      </article>
                    ))}
                  </div>
                </div>

                <aside className="help-center-hero-panel">
                  <div className="help-center-hero-panel-visual">
                    <img
                      alt="Acrobuild advisor guiding homeowners through support and handover details"
                      className="help-center-hero-panel-image"
                      loading="lazy"
                      src="/images/real-world/help-center-support.png"
                    />
                    <div className="help-center-hero-panel-visual-note">
                      <strong>Human support, built into the buyer journey.</strong>
                      <span>Clear handover answers and real people when a project question needs a follow-up.</span>
                    </div>
                  </div>

                  <div className="help-center-hero-panel-head">
                    <small>Fast answer lanes</small>
                    <strong>Open the right support path without losing the buyer journey.</strong>
                  </div>

                  <div className="help-center-hero-panel-grid">
                    {helpCenterHeroCategories.map((category, index) => (
                      <button
                        className="help-center-hero-panel-card"
                        key={category.id}
                        onClick={() => handleCategorySelect(category)}
                        type="button"
                      >
                        <div className="help-center-hero-panel-card-top">
                          <small>{`Lane 0${index + 1}`}</small>
                          <span>{formatArticleCount(category.articleCount)}</span>
                        </div>
                        <strong>{category.title}</strong>
                        <p>
                          {category.description ||
                            "Published guidance tailored to this stage of the project and homeowner journey."}
                        </p>
                      </button>
                    ))}
                  </div>

                  <div className="help-center-hero-panel-actions">
                    <Link
                      className="help-center-inline-button help-center-inline-button-solid help-center-inline-link"
                      to={helpCenterArticlesPath}
                    >
                      Browse all articles
                    </Link>
                    <button
                      className="help-center-inline-button help-center-inline-button-ghost"
                      onClick={() => openContactMode(helpCenterQuery)}
                      type="button"
                    >
                      Talk to support
                    </button>
                  </div>
                </aside>
              </div>
            </section>

            <section className="help-center-shell help-center-section" id="popular-questions" tabIndex={-1}>
              <div className="help-center-section-head">
                <div>
                  <h2>Popular questions</h2>
                  <p>Open the most common published support articles directly.</p>
                </div>
              </div>

              <div className="help-center-question-grid">
                {filteredSupportFlows.map((flow) => (
                  <button
                    className="help-center-question-card"
                    key={flow.id}
                    onClick={() => handleHelpCenterArticleOpen(flow)}
                    type="button"
                  >
                    <span>{flow.label}</span>
                    <span className="help-center-arrow">
                      <ChevronRightIcon />
                    </span>
                  </button>
                ))}
              </div>

              {!filteredSupportFlows.length ? (
                <div className="help-center-empty-state">
                  <strong>No popular questions matched that search.</strong>
                  <p>Try a broader topic or contact the support team directly.</p>
                  <button
                    className="help-center-inline-button"
                    onClick={() => openContactMode(helpCenterQuery)}
                    type="button"
                  >
                    Contact us
                  </button>
                </div>
              ) : null}
            </section>

            <section className="help-center-shell help-center-section">
              <div className="help-center-order-grid">
                {filteredHelpCenterActions.map((action) => (
                  <button
                    className="help-center-order-card"
                    key={action.id}
                    onClick={() => handleActionSelect(action)}
                    type="button"
                  >
                    <span className="help-center-order-icon-shell">
                      {getOrderActionIcon(action.icon)}
                    </span>
                    <span className="help-center-order-copy">
                      <strong>{action.title}</strong>
                      {action.description ? <span>{action.description}</span> : null}
                    </span>
                  </button>
                ))}
              </div>
            </section>

            <section className="help-center-shell help-center-section" id="more-information" tabIndex={-1}>
              <div className="help-center-section-head">
                <div>
                  <h2>All article categories</h2>
                  <p>Browse published Acrobuild categories for sales, construction, documentation, and handover support.</p>
                </div>

                <HelpCenterViewToggle
                  label="Category layout"
                  onChange={setCategoryView}
                  value={categoryView}
                />
              </div>

              <div className={`help-center-category-grid ${categoryView === "list" ? "list" : ""}`}>
                {filteredHelpCenterCategories.map((category) => (
                  <button
                    className="help-center-category-card"
                    key={category.id}
                    onClick={() => handleCategorySelect(category)}
                    type="button"
                  >
                    <span className="help-center-category-copy">
                      <strong>{category.title}</strong>
                      <span>{category.description}</span>
                    </span>
                    <span className="help-center-category-meta">
                      <small>{formatArticleCount(category.articleCount)}</small>
                      <span className="help-center-arrow">
                        <ChevronRightIcon />
                      </span>
                    </span>
                  </button>
                ))}
              </div>

              {!filteredHelpCenterCategories.length ? (
                <div aria-live="polite" className="help-center-empty-state" role="status">
                  <strong>No categories matched that search.</strong>
                  <p>Try another keyword or browse the popular questions above.</p>
                </div>
              ) : null}
            </section>

            <section className="help-center-shell help-center-section" id="get-support" tabIndex={-1}>
              <div className="help-center-section-head">
                <div>
                  <h2>Get support</h2>
                  <p>Reach the Acrobuild team when the self-serve guides are not enough.</p>
                </div>
              </div>

              <div className="help-center-support-grid">
                <button
                  className="help-center-support-card"
                  onClick={() => openContactMode(helpCenterQuery)}
                  type="button"
                >
                  <div className="help-center-support-card-head">
                    <span className="help-center-support-icon">
                      <MailIcon />
                    </span>
                    <strong>Contact us</strong>
                    <span className="help-center-arrow">
                      <ChevronRightIcon />
                    </span>
                  </div>
                  <div className="help-center-support-card-body">
                    Send a message from the chat and we will raise a support ticket with your email
                    and project notes.
                  </div>
                </button>

                <a className="help-center-support-card" href="tel:+611800592299">
                  <div className="help-center-support-card-head">
                    <span className="help-center-support-icon">
                      <PhoneIcon />
                    </span>
                    <strong>Call us</strong>
                  </div>
                  <div className="help-center-support-card-body">
                    <span className="help-center-support-phone">+61 1800 592 299</span>
                    <span className="help-center-support-hours">
                      Monday to Friday, 9:00 AM - 5:00 PM AEST
                    </span>
                  </div>
                </a>
              </div>
            </section>
          </>
        ) : null}

        {isCategoryPage ? (
          <section className="help-center-shell help-center-article-shell">
            <div className="help-center-subpage-topbar">
              <HelpCenterBreadcrumbs
                items={[
                  { label: "Home", to: helpCenterHomePath },
                  { label: "All articles", to: helpCenterArticlesPath },
                  { label: selectedCategory ?? "Category" }
                ]}
              />

              <HelpCenterSearch
                compact
                label="Search support articles"
                onChange={setHelpCenterQuery}
                onSubmit={handleHelpCenterSearchSubmit}
                placeholder="Search"
                value={helpCenterQuery}
              />
            </div>

            {selectedCategory ? (
              <>
                <div className="help-center-section-head help-center-article-head">
                  <div>
                    <div className="help-center-article-kicker">All articles</div>
                    <h1>{selectedCategory}</h1>
                    <p>{formatArticleCount(categoryArticles.length)} in this category.</p>
                  </div>

                  <HelpCenterViewToggle
                    label="Article layout"
                    onChange={setCategoryView}
                    value={categoryView}
                  />
                </div>

                <div className={`help-center-article-grid ${categoryView === "list" ? "list" : ""}`}>
                  {filteredCategoryArticles.map((article) => (
                    <Link
                      className="help-center-article-card"
                      key={article.id}
                      to={buildArticlePath(article)}
                    >
                      <span className="help-center-card-kicker">{article.category}</span>
                      <strong>{article.title}</strong>
                      <p>{getArticleExcerpt(article)}</p>
                      <span className="help-center-card-link">Read article</span>
                    </Link>
                  ))}
                </div>

                {!filteredCategoryArticles.length ? (
                  <div aria-live="polite" className="help-center-empty-state" role="status">
                    <strong>No articles matched that search in this category.</strong>
                    <p>Try another keyword or go back to all help-center categories.</p>
                    <Link className="help-center-inline-button help-center-inline-link" to={helpCenterArticlesPath}>
                      Back to help center
                    </Link>
                  </div>
                ) : null}
              </>
            ) : (
              <div className="help-center-empty-state help-center-not-found">
                <span className="help-center-empty-icon" aria-hidden="true">?</span>
                <h1>That category could not be found.</h1>
                <p>Go back to the help center and open another published support category.</p>
                <Link className="help-center-inline-button help-center-inline-link" to={helpCenterArticlesPath}>
                  Back to help center
                </Link>
              </div>
            )}
          </section>
        ) : null}

        {isArticlePage ? (
          <section className="help-center-shell help-center-article-shell">
            {selectedArticle ? (
              <>
                <div className="help-center-subpage-topbar">
                  <HelpCenterBreadcrumbs
                    items={[
                      { label: "Home", to: helpCenterHomePath },
                      { label: "All articles", to: helpCenterArticlesPath },
                      {
                        label: selectedArticle.category,
                        to: buildCategoryPath(selectedArticle.category)
                      },
                      { label: selectedArticle.title }
                    ]}
                  />

                  <HelpCenterSearch
                    compact
                    label="Search support articles"
                    onChange={setHelpCenterQuery}
                    onSubmit={handleHelpCenterSearchSubmit}
                    placeholder="Search"
                    value={helpCenterQuery}
                  />
                </div>

                <div className="help-center-article-layout">
                  <article className="help-center-article-detail">
                    <div className="help-center-article-kicker">{selectedArticle.category}</div>
                    <h1>{selectedArticle.title}</h1>
                    {selectedArticle.summary.trim() ? (
                      <p className="help-center-article-summary">{selectedArticle.summary}</p>
                    ) : null}

                    <div className="help-center-article-body">
                      {selectedArticleParagraphs.map((paragraph, index) => (
                        <p key={`${selectedArticle.id}-${index}`}>{paragraph}</p>
                      ))}
                    </div>

                    <div className="help-center-article-actions">
                      <button
                        className="help-center-inline-button primary"
                        onClick={() =>
                          void queueBotResponse(
                            getArticlePrompt(selectedArticle),
                            selectedArticle.id,
                            true,
                            selectedArticle.title
                          )
                        }
                        type="button"
                      >
                        Open in chat
                      </button>
                      <button
                        className="help-center-inline-button secondary"
                        onClick={() => openContactMode(getArticlePrompt(selectedArticle))}
                        type="button"
                      >
                        Need more help
                      </button>
                    </div>
                  </article>

                  <aside aria-label={`More from ${selectedArticle.category}`} className="help-center-related-panel">
                    <div className="help-center-related-head">
                      <strong>More from {selectedArticle.category}</strong>
                      <Link to={buildCategoryPath(selectedArticle.category)}>View all</Link>
                    </div>

                    <div className="help-center-related-grid">
                      {relatedCategoryArticles.map((article) => (
                        <Link
                          className="help-center-related-article"
                          key={article.id}
                          to={buildArticlePath(article)}
                        >
                          <strong>{article.title}</strong>
                          <span>{getArticleExcerpt(article)}</span>
                        </Link>
                      ))}
                      {!relatedCategoryArticles.length ? (
                        <p className="help-center-related-empty">
                          No other published articles are available in this category.
                        </p>
                      ) : null}
                    </div>
                  </aside>
                </div>
              </>
            ) : (
              <div className="help-center-empty-state help-center-not-found">
                <span className="help-center-empty-icon" aria-hidden="true">?</span>
                <h1>That article could not be found.</h1>
                <p>Go back to the help center home and open another published support article.</p>
                <Link className="help-center-inline-button help-center-inline-link" to={helpCenterArticlesPath}>
                  Back to help center
                </Link>
              </div>
            )}
          </section>
        ) : null}
      </main>

      <PublicFooter />

      {isVoiceConversation ? (
        <section
          aria-label="Voice support call"
          aria-live="polite"
          className="voice-call-overlay"
          role="dialog"
        >
          <div className="voice-call-card">
            <div className="voice-call-brand">{assistantBrandName}</div>
            <div className={`voice-call-avatar${isSpeaking ? " speaking" : ""}`}>
              <span>{assistantInitial}</span>
              <div className="voice-call-avatar-ring ring-one" />
              <div className="voice-call-avatar-ring ring-two" />
            </div>
            <div className="voice-call-copy">
              <h2>{assistantBrandName} Support</h2>
              <p>
                {isVoiceMuted
                  ? "Microphone paused"
                  : isListening
                    ? "Listening..."
                    : isTypingReply
                      ? "Finding the best answer..."
                      : isSpeaking
                        ? "Speaking â€” you can interrupt"
                        : "Ready for your question"}
              </p>
            </div>
            <label className="voice-call-language">
              <span>Conversation language</span>
              <select
                aria-label="Voice conversation language"
                onChange={(event) => {
                  const nextLanguage = event.target.value as VoiceLanguageCode;
                  voiceLanguageRef.current = nextLanguage;
                  setVoiceLanguage(nextLanguage);
                  setVoiceTranscript("");
                  submittedVoiceTranscriptRef.current = "";
                  speechRecognitionRef.current?.stop();
                }}
                value={voiceLanguage}
              >
                {Object.entries(VOICE_LANGUAGES).map(([code, name]) => (
                  <option key={code} value={code}>{name}</option>
                ))}
              </select>
            </label>
            <div className={`voice-call-waveform${isListening || isSpeaking ? " active" : ""}${isVoiceMuted ? " muted" : ""}`} aria-hidden="true">
              {Array.from({ length: 15 }, (_, index) => (
                <span key={index} />
              ))}
            </div>
            <div className="voice-call-hint">
              {voiceTranscript
                ? <><span className="voice-call-transcript-label">I heard</span>â€œ{voiceTranscript}â€</>
                : isVoiceMuted
                  ? "Resume the microphone when you're ready."
                  : isListening
                    ? "Speak naturally. I'll send your question when you finish."
                    : isSpeaking
                      ? "Tap Interrupt answer to speak now."
                      : "Your voice session is active."}
            </div>
            <div className="voice-call-actions">
              <button
                aria-pressed={isVoiceMuted}
                className="voice-call-control-button"
                onClick={toggleVoiceMicrophone}
                type="button"
              >
                {isVoiceMuted ? "Resume microphone" : "Pause microphone"}
              </button>
              {isSpeaking ? (
                <button className="voice-call-control-button interrupt" onClick={interruptVoiceReply} type="button">
                  Interrupt answer
                </button>
              ) : null}
              <button
                className="voice-call-ticket-button"
                disabled={isCreatingTicket}
                onClick={requestTicketFromVoice}
                type="button"
              >
                {isCreatingTicket ? "Creating ticket..." : "Create support ticket"}
              </button>
            <button
              aria-label="End voice call"
              className="voice-call-end-button"
              onClick={handleVoiceToggle}
              type="button"
            >
              <span aria-hidden="true">X</span>
              End call
            </button>
          </div>
          </div>
        </section>
      ) : null}
      <div className="store-chat-layer" id="help">
        {isChatOpen ? (
          <section
            aria-labelledby="store-chat-title"
            className="store-chat-panel"
            id="store-chat-panel"
            role="dialog"
            style={{
              fontFamily: chatFontFamily,
              width: `min(${widgetConfig.widgetWidth}px, calc(100vw - 1rem))`
            }}
          >
            <header className="store-chat-header">
              <div className="store-chat-header-top">
                <button aria-label="Close chat" className="store-chat-back-button" onClick={() => setIsChatOpen(false)} ref={chatCloseButtonRef} type="button">
                  <CloseIcon />
                </button>
                <span aria-hidden="true" className="store-chat-header-avatar">
                  <img alt="" src="/Acrobuild_logo.png?v=20260730-2" />
                </span>
                <div className="store-chat-brand-lockup">
                  <strong id="store-chat-title">Acrobuild Assistant</strong>
                  <span>Property support</span>
                </div>
                <span className="store-chat-online" title="Online"><i aria-hidden="true" />Online</span>
              </div>
            </header>
            <div
              className={`store-chat-body${isMenuMode ? " menu-mode" : ""}`}
              ref={chatBodyRef}
            >
              {restoreState !== "ready" ? (
                <div
                  aria-live={restoreState === "loading" ? "polite" : "assertive"}
                  className={`store-chat-restore-state is-${restoreState}`}
                  role={restoreState === "loading" ? "status" : "alert"}
                >
                  <strong>{restoreState === "loading" ? "Restoring your conversation" : "Conversation could not be restored"}</strong>
                  <span>
                    {restoreState === "loading"
                      ? "Loading your earlier messages and conversation context."
                      : "Your earlier messages and context could not be verified. Retry before continuing so context is not lost."}
                  </span>
                  {restoreState === "failed" ? (
                    <button
                      className="store-chat-retry-button"
                      disabled={isRestoringChat}
                      onClick={() => void restoreConversationHistory(conversationIdRef.current)}
                      ref={restoreRetryButtonRef}
                      type="button"
                    >
                      Retry restore
                    </button>
                  ) : (
                    <span aria-hidden="true" className="store-chat-restore-spinner" />
                  )}
                </div>
              ) : !hasActiveConversation ? (
                isContactMode ? (
                  <div className="store-chat-home contact-mode">
                    <div className="store-chat-intake-thread">
                      <div className="store-chat-intake-row">
                        <span className="store-chat-avatar">{assistantInitial}</span>
                        <div className="store-chat-intake-stack">
                          <div className="store-chat-intake-author">{assistantBotLabel}</div>
                          <div className="store-chat-intake-bubble">{contactWelcomeMessage}</div>
                        </div>
                      </div>

                      <div className="store-chat-intake-row">
                        <span className="store-chat-avatar">{assistantInitial}</span>
                        <label className="store-chat-email-card">
                          <span className="store-chat-email-card-title">Email *</span>
                          <span className="store-chat-email-card-field">
                            <input
                              autoComplete="email"
                              className="store-chat-email-card-input"
                              inputMode="email"
                              onChange={(event) => {
                                setChatEmail(event.target.value);
                                if (storefrontError) {
                                  setStorefrontError("");
                                }
                              }}
                              onKeyDown={(event) => {
                                if (event.key !== "Enter") {
                                  return;
                                }

                                event.preventDefault();
                                if (!isValidEmail(chatEmail)) {
                                  setStorefrontError("Enter a valid email address so we know where to follow up.");
                                  return;
                                }

                                setStorefrontError("");
                                chatComposeRef.current?.focus();
                              }}
                              placeholder="owner@acrobuild.com"
                              ref={chatEmailRef}
                              type="email"
                              value={chatEmail}
                            />
                          </span>
                          <span className="store-chat-email-card-help">
                            Press Enter, then type your question below.
                          </span>
                        </label>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div aria-label="Start a conversation" className="store-chat-home menu-mode conversation-welcome" />
                )
                ) : (
                  <div className="store-chat-conversation">
                    <div className="store-chat-date">{conversationDateLabel}</div>
                    {chatMessages.map((message) => {
                      const isCustomerMessage = message.sender === "customer";

                      return (
                        <article
                          className={`store-chat-message ${isCustomerMessage ? "customer" : "bot"}`}
                          key={message.id}
                        >
                          {!isCustomerMessage ? (
                            <span className={`store-chat-avatar${widgetLogoUrl ? " has-image" : ""}`}>
                              {widgetLogoUrl ? (
                                <img alt="" className="store-chat-avatar-image" src={widgetLogoUrl} />
                              ) : (
                                assistantInitial
                              )}
                            </span>
                          ) : null}

                          <div className="store-chat-message-stack">
                            {!isCustomerMessage ? (
                              <div className="store-chat-message-author">{conversationBotLabel}</div>
                            ) : null}

                            <div
                              className="store-chat-bubble"
                              style={
                                isCustomerMessage
                                  ? {
                                      backgroundColor: chatAccentColor,
                                      borderColor: chatAccentColor
                                    }
                                  : undefined
                              }
                            >
                              {message.text.trim() ? (
                                <div
                                  className={
                                    isCustomerMessage ? undefined : "store-chat-automated-card"
                                  }
                                >
                                  <div className="store-chat-message-text">{visibleMessageText(message)}</div>
                                </div>
                              ) : null}

                              {!isCustomerMessage && message.deliveryState ? (
                                <div
                                  aria-live={["failed", "interrupted", "offline"].includes(message.deliveryState) ? "assertive" : "polite"}
                                  className={`store-chat-delivery-state is-${message.deliveryState}`}
                                  role={["failed", "interrupted", "offline"].includes(message.deliveryState) ? "alert" : "status"}
                                >
                                  <strong>{CHAT_RECOVERY_COPY[message.deliveryState].title}</strong>
                                  <span>{CHAT_RECOVERY_COPY[message.deliveryState].detail}</span>
                                  {message.retryError ? (
                                    <span className="store-chat-retry-error">
                                      Retry paused because the conversation could not be safely reconciled. Try again after the connection recovers.
                                    </span>
                                  ) : null}
                                  {message.canRetry && message.id === latestCompletedBotMessageId ? (
                                    <button
                                      className="store-chat-retry-button"
                                      disabled={isAssistPending || isRestoringChat}
                                      onClick={() => void retryAssistTurn(message.id)}
                                      ref={retryButtonRef}
                                      type="button"
                                    >
                                      {message.retrying ? "Retrying..." : "Retry answer"}
                                    </button>
                                  ) : null}
                                </div>
                              ) : null}

                              {!isCustomerMessage && message.id === latestCompletedBotMessageId && !isSiteVisitFormVisible ? (
                                message.quickReplies?.length ? (
                                  <div className="store-chat-guided-grid project-grid store-chat-quick-replies">
                                    {message.quickReplies.map((option) => (
                                      <button
                                        className={`store-chat-guided-button${option.action ? ` store-chat-action-${option.action}` : ""}`}
                                        disabled={isAssistPending || isRestoringChat}
                                        key={option.value}
                                        onClick={() => {
                                          const dispatch = getQuickReplyDispatch(option, message);
                                          if (dispatch.kind === "ticket") {
                                            openFollowUpForm(dispatch.issue);
                                          } else if (dispatch.kind === "site_visit") {
                                            void openSiteVisitBooking(dispatch.projectName);
                                          } else {
                                            void queueBotResponse(
                                              dispatch.issue,
                                              undefined,
                                              dispatch.resetConversation,
                                              dispatch.customerMessageText
                                            );
                                          }
                                        }}
                                        type="button"
                                      >
                                        <span className="store-chat-guided-label">{option.label}</span>
                                        <span className="store-chat-guided-arrow"><ChevronRightIcon /></span>
                                      </button>
                                    ))}
                                  </div>
                                ) : propertyFlow?.messageId === message.id ? (
                                  <div className="store-chat-guided-grid project-grid">
                                    {propertyFlow.level === "projects"
                                      ? propertyFlow.projects.map((project, index) => (
                                          <PropertyChoiceButton
                                            details={[project.locality || project.city, project.projectType].filter((value): value is string => Boolean(value?.trim()))}
                                            index={index}
                                            key={project.id}
                                            label={project.projectName}
                                            onClick={() => void selectPropertyProject(project)}
                                          />
                                        ))
                                      : null}
                                    {propertyFlow.level === "wings"
                                      ? propertyFlow.wings.map((wing, index) => (
                                          <PropertyChoiceButton
                                            details={[wing.code, wing.constructionStatus, typeof wing.totalFloors === "number" ? `${wing.totalFloors} floors` : undefined].filter((value): value is string => Boolean(value?.trim()))}
                                            index={index}
                                            key={wing.id}
                                            label={wing.name}
                                            onClick={() => void selectPropertyWing(wing)}
                                          />
                                        ))
                                      : null}
                                    {propertyFlow.level === "floors"
                                      ? [...new Set(
                                          propertyFlow.inventory
                                            .map((unit) => unit.floorNumber)
                                            .filter((floor): floor is number => typeof floor === "number")
                                        )]
                                          .sort((left, right) => left - right)
                                          .map((floor) => (
                                            <PropertyChoiceButton
                                              key={floor}
                                              leading={floor}
                                              label={FLOW_TEXT[chatLanguage].floor(floor)}
                                              onClick={() => selectPropertyFloor(floor)}
                                            />
                                          ))
                                      : null}
                                    {propertyFlow.level === "flats"
                                      ? propertyFlow.inventory.map((unit) => (
                                          <PropertyChoiceButton
                                            active={propertyFlow.selectedUnit?.id === unit.id}
                                            details={[unit.typologyName, typeof unit.floorNumber === "number" ? FLOW_TEXT[chatLanguage].floor(unit.floorNumber) : undefined].filter((value): value is string => Boolean(value?.trim()))}
                                            key={unit.id}
                                            leading={unit.unitNumber ?? "–"}
                                            label={FLOW_TEXT[chatLanguage].flat(unit.unitNumber ?? unit.id)}
                                            onClick={() => void selectInventoryUnit(unit)}
                                          />
                                        ))
                                      : null}
                                    {propertyFlow.level === "flat_details" ? (
                                      <button
                                        className="store-chat-guided-button primary"
                                        onClick={() => void openSiteVisitBooking()}
                                        type="button"
                                      >
                                        {FLOW_TEXT[chatLanguage].bookVisit}
                                      </button>
                                    ) : null}
                                  </div>
                                ) : !isAssistPending && message.contextIssue === "Initial welcome" ? (
                                  <div className="store-chat-guided-grid greeting-action">
                                    {GREETING_ACTIONS.map((action) => (
                                      <button
                                        className="store-chat-guided-button store-chat-action-browse_projects"
                                        key={action.label}
                                        onClick={() => {
                                          void queueBotResponse(action.prompt, undefined, false, action.label);
                                        }}
                                        type="button"
                                      >
                                        <span className="store-chat-guided-label">
                                          {action.kind === "projects" ? FLOW_TEXT[chatLanguage].browseAll : action.label}
                                        </span>
                                        <span className="store-chat-guided-arrow"><ChevronRightIcon /></span>
                                      </button>
                                    ))}
                                  </div>
                                ) : message.offerActionMenu ? (
                                  <div className="store-chat-guided-grid action-menu">
                                    <button
                                      className="store-chat-guided-button store-chat-action-ticket"
                                      disabled={isAssistPending || isRestoringChat}
                                      onClick={() => openFollowUpForm(message.contextIssue ?? "")}
                                      type="button"
                                    >
                                      <span className="store-chat-guided-label">Raise a ticket</span>
                                      <span className="store-chat-guided-arrow"><ChevronRightIcon /></span>
                                    </button>
                                    <button
                                      className="store-chat-guided-button store-chat-action-site_visit"
                                      disabled={isAssistPending || isRestoringChat}
                                      onClick={() => void openSiteVisitBooking()}
                                      type="button"
                                    >
                                      <span className="store-chat-guided-label">Request a site visit</span>
                                      <span className="store-chat-guided-arrow"><ChevronRightIcon /></span>
                                    </button>
                                  </div>
                                ) : null
                              ) : null}
                              {message.showHelpfulPrompt ? (
                                <div className={`store-chat-feedback-card${message.feedbackState ? ` is-${message.feedbackState}` : ""}`}>
                                  <div className="store-chat-feedback-copy">
                                    {getHelpfulPromptMessage(message.feedbackState)}
                                  </div>
                                  <div className="store-chat-feedback-actions">
                                    <button
                                      aria-label="Helpful answer"
                                      className={`store-chat-feedback-button positive${message.feedbackState === "positive" ? " active" : ""}`}
                                      onClick={() => handleHelpfulFeedbackSelection(message.id, "positive")}
                                      type="button"
                                    >
                                      <ThumbsUpIcon />
                                    </button>
                                    <button
                                      aria-label="Not helpful"
                                      className={`store-chat-feedback-button negative${message.feedbackState === "negative" ? " active" : ""}`}
                                      onClick={() => handleHelpfulFeedbackSelection(message.id, "negative")}
                                      type="button"
                                    >
                                      <ThumbsDownIcon />
                                    </button>
                                  </div>
                                </div>
                              ) : null}

                              {message.sender === "bot" && message.feedbackState === "negative" && !message.ticketResult ? (
                                <div className="store-chat-help-actions single">
                                  <button
                                    className="store-chat-help-button dark"
                                    onClick={() => openContactMode(message.contextIssue ?? "")}
                                    type="button"
                                  >
                                    Need more help
                                  </button>
                                </div>
                              ) : null}

                              {message.ticketResult ? (
                                <div className="store-chat-ticket-card">
                                  <strong>{message.ticketResult.ticket_id}</strong>
                                  <span>{message.ticketResult.assigned_agent}</span>
                                  <span>{message.ticketResult.queue_name}</span>
                                </div>
                              ) : null}
                            </div>

                            {!isCustomerMessage && message.isAutomated ? (
                              <div className="store-chat-automation-note">Automated</div>
                            ) : null}
                          </div>
                        </article>
                      );
                    })}

                    {isSiteVisitFormVisible ? (
                      <form
                        className="store-chat-visit-card ab-card"
                        onSubmit={(event) => {
                          event.preventDefault();
                          void submitSiteVisitBooking();
                        }}
                      >
                        <div className="store-chat-visit-head">
                          <span>Site visit request</span>
                          <strong>Share your preferred visit details</strong>
                          <p>We’ll create a request for the site team to review.</p>
                        </div>
                        <label className="store-chat-visit-field" htmlFor="site-visit-name">
                          <span>Name *</span>
                          <Input
                            autoComplete="name"
                            id="site-visit-name"
                            onChange={(event) => setSiteVisitForm((current) => ({ ...current, customer_name: event.target.value }))}
                            required
                            ref={siteVisitNameRef}
                            value={siteVisitForm.customer_name}
                          />
                        </label>
                        <label className="store-chat-visit-field" htmlFor="site-visit-email">
                          <span>Email *</span>
                          <Input
                            autoComplete="email"
                            id="site-visit-email"
                            onChange={(event) => setSiteVisitForm((current) => ({ ...current, customer_email: event.target.value }))}
                            required
                            type="email"
                            value={siteVisitForm.customer_email}
                          />
                        </label>
                        <label className="store-chat-visit-field" htmlFor="site-visit-phone">
                          <span>Phone *</span>
                          <Input
                            autoComplete="tel"
                            id="site-visit-phone"
                            inputMode="tel"
                            onChange={(event) => setSiteVisitForm((current) => ({ ...current, customer_phone: event.target.value }))}
                            required
                            type="tel"
                            value={siteVisitForm.customer_phone}
                          />
                        </label>
                        <label className="store-chat-visit-field" htmlFor="site-visit-project">
                          <span>Project *</span>
                          <select
                            onChange={(event) => setSiteVisitForm((current) => ({ ...current, project_name: event.target.value }))}
                            required
                            id="site-visit-project"
                            value={siteVisitForm.project_name}
                          >
                            <option value="">Select a project</option>
                            {siteVisitProjects.map((project) => (
                              <option key={project.id} value={project.projectName}>{project.projectName}</option>
                            ))}
                          </select>
                        </label>
                        <div className="store-chat-visit-row">
                          <label>
                            <span>Preferred date *</span>
                            <Input
                              aria-label="Preferred date"
                              min={new Date().toISOString().slice(0, 10)}
                              onChange={(event) => setSiteVisitForm((current) => ({ ...current, preferred_date: event.target.value }))}
                              required
                              type="date"
                              value={siteVisitForm.preferred_date}
                            />
                          </label>
                          <label>
                            <span>Preferred time *</span>
                            <Input
                              aria-label="Preferred time"
                              onChange={(event) => setSiteVisitForm((current) => ({ ...current, preferred_time: event.target.value }))}
                              required
                              type="time"
                              value={siteVisitForm.preferred_time}
                            />
                          </label>
                        </div>
                        <label className="store-chat-visit-field" htmlFor="site-visit-notes">
                          <span>Notes</span>
                          <textarea
                            onChange={(event) => setSiteVisitForm((current) => ({ ...current, notes: event.target.value }))}
                            placeholder="Questions, accessibility needs, or preferred callback details"
                            id="site-visit-notes"
                            rows={3}
                            value={siteVisitForm.notes}
                          />
                        </label>
                        <Button className="store-chat-visit-submit" disabled={isSubmittingSiteVisit} type="submit">
                          {isSubmittingSiteVisit ? "Submitting..." : "Request site visit"}
                        </Button>
                        <Button
                          variant="secondary"
                          className="store-chat-help-button"
                          onClick={() => setIsSiteVisitFormVisible(false)}
                          type="button"
                        >
                          Cancel
                        </Button>
                        <small>Required fields help the site team review your request for the right project and preferred time.</small>
                      </form>
                    ) : null}
                    {isTypingReply ? (
                      <div aria-label="Assistant is typing" className="store-chat-typing" role="status">
                        <span aria-hidden="true" />
                        <span aria-hidden="true" />
                        <span aria-hidden="true" />
                      </div>
                    ) : null}

                    {isFollowUpFormVisible ? (
                      <Card className="store-chat-follow-up-card">
                        <div className="store-chat-follow-up-head">
                          <strong>Tell us what still needs help</strong>
                          <span>
                            We will raise a support ticket after the customer enters an email and
                            message.
                          </span>
                        </div>

                          <label className="store-chat-email-row" htmlFor="support-follow-up-email">
                          <span>Email for follow-up</span>
                            <Input
                            id="support-follow-up-email"
                            className="store-chat-email-input"
                            onChange={(event) => setChatEmail(event.target.value)}
                            placeholder="you@example.com"
                            ref={chatEmailRef}
                            value={chatEmail}
                          />
                        </label>

                          <label className="store-chat-email-row" htmlFor="support-follow-up-message">
                          <span>What do you still need help with?</span>
                          <textarea
                            className="store-chat-compose-input"
                            id="support-follow-up-message"
                            onChange={(event) => setChatDraft(event.target.value)}
                            placeholder="Add the customer's remaining question here..."
                            ref={chatComposeRef}
                            rows={4}
                            value={chatDraft}
                          />
                        </label>

                        <div className="store-chat-follow-up-actions">
                          <Button
                            variant="secondary"
                            className="store-chat-help-button"
                            onClick={() => {
                              setIsFollowUpFormVisible(false);
                              setActiveFollowUpIssue("");
                              setStorefrontError("");
                              setChatDraft("");
                            }}
                            type="button"
                          >
                            Cancel
                          </Button>
                          <Button
                            className="store-chat-help-button dark"
                            disabled={isCreatingTicket}
                            onClick={() => void createTicketForIssue(activeFollowUpIssue, chatDraft)}
                            type="button"
                          >
                            {isCreatingTicket ? "Creating..." : "Submit ticket"}
                          </Button>
                        </div>
                      </Card>
                    ) : null}
                  </div>
              )}
            </div>

            {isContactMode ? (
              <form
                className="store-chat-compose-shell"
                onSubmit={(event) => {
                  event.preventDefault();
                  void createTicketForIssue(activeFollowUpIssue, chatDraft);
                }}
              >
                <div className="store-chat-compose-inline">
                  <input
                    aria-label="Support question"
                    className="store-chat-message-input"
                    onChange={(event) => {
                      setChatDraft(event.target.value);
                      if (storefrontError) {
                        setStorefrontError("");
                      }
                    }}
                    placeholder="Type your support question"
                    ref={chatContactComposeRef}
                    value={chatDraft}
                  />
                  <button
                    aria-label="Send message"
                    className="store-chat-compose-submit"
                    disabled={isCreatingTicket || !chatDraft.trim()}
                    type="submit"
                  >
                    <PaperPlaneIcon />
                  </button>
                </div>
              </form>
            ) : !isFollowUpFormVisible ? (
              <form
                className="store-chat-compose-shell"
                onSubmit={(event) => {
                  event.preventDefault();

                  if (!chatDraft.trim() || isAssistPending || restoreState !== "ready") {
                    return;
                  }

                  updateChatLanguage(chatDraft);

                  if (handlePropertyFlowTextSelection(chatDraft)) {
                    return;
                  }

                  const selectedProject = resolveProjectSelection(chatMessages, chatDraft);
                  if (selectedProject) {
                    const customerSelection = chatDraft.trim();
                    setChatDraft("");
                    void selectNumberedProject(selectedProject, customerSelection);
                    return;
                  }

                  if (isSiteVisitBookingRequest(chatDraft)) {
                    setChatDraft("");
                    void openSiteVisitBooking();
                    return;
                  }

                  if (handleHelpfulReviewFromText(chatDraft)) {
                    return;
                  }

                  void queueBotResponse(
                    chatDraft,
                    undefined,
                    !hasActiveConversation
                  );
                }}
              >
                <div className="store-chat-compose-inline">
                  <input
                    aria-label="Message Acrobuild Assistant"
                    className="store-chat-message-input"
                    disabled={isAssistPending || restoreState !== "ready"}
                    onChange={(event) => setChatDraft(event.target.value)}
                    placeholder={restoreState === "failed"
                      ? "Restore the conversation to continue"
                      : hasActiveConversation ? "Reply to the assistant" : "Ask a support question"}
                    ref={chatMessageInputRef}
                    value={chatDraft}
                  />
                  <button
                    aria-label="Send message"
                    className="store-chat-compose-submit"
                    disabled={isAssistPending || restoreState !== "ready" || !chatDraft.trim()}
                    type="submit"
                  >
                    <PaperPlaneIcon />
                  </button>
                </div>
              </form>
            ) : null}

            {isListening ? (
              <div aria-live="polite" className="store-chat-voice-status">
                <span />
                Listening... speak naturally
              </div>
            ) : null}

            {storefrontError ? (
              <div className="store-chat-inline-error-shell">
                <div className="store-chat-error" role="alert">{storefrontError}</div>
              </div>
            ) : null}
          </section>
        ) : null}

        <button
          aria-controls="store-chat-panel"
          aria-expanded={isChatOpen}
          aria-label={isChatOpen ? "Minimize support chat" : widgetConfig.launcherLabel}
          className={`store-chat-launcher${isChatOpen ? " raised" : ""}${widgetLogoUrl && !isChatOpen ? " has-logo" : ""}`}
          onClick={() => setIsChatOpen((current) => !current)}
          ref={chatLauncherRef}
          style={{
            backgroundColor: widgetLogoUrl && !isChatOpen ? "#ffffff" : chatAccentColor,
            height: `${widgetConfig.launcherWidth}px`,
            width: `${widgetConfig.launcherWidth}px`
          }}
          type="button"
        >
          {isChatOpen ? (
            <ChevronDownIcon />
          ) : widgetLogoUrl ? (
            <img alt="" className="store-chat-launcher-image" src={widgetLogoUrl} />
          ) : (
            <MessageLauncherIcon />
          )}
        </button>
      </div>
    </div>
  );
}





