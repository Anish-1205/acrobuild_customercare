import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { useRole } from "../contexts/RoleContext";
import { createSupportTicket, generateIndicVoiceAudio, getAdminArticles, getSupportAssist, streamSupportAssist } from "../lib/api";
import { knowledgeArticles, type KnowledgeArticle } from "../lib/articleAssist";
import { getRoleHomePath } from "../lib/roleNavigation";
import { loadWidgetConfig } from "../lib/widgetConfig";
import { AcrobuildLogo } from "../components/AcrobuildLogo";
import type {
  CreateTicketResponse,
  SupportConversationMessage,
  SupportArticleRecord,
  Ticket
} from "../types";

type SupportFlow = {
  articleId?: number;
  id: string;
  label: string;
  prompt: string;
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
  contextIssue?: string;
  feedbackState?: "negative" | "positive";
  id: number;
  isAutomated?: boolean;
  isComplete?: boolean;
  relatedArticles: KnowledgeArticle[];
  sender: "bot" | "customer";
  showHelpfulPrompt?: boolean;
  text: string;
  ticketResult?: CreateTicketResponse | null;
};

type BrowserSpeechRecognition = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onend: (() => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal?: boolean }> }) => void) | null;
  start: () => void;
  stop: () => void;
};

type SpeechRecognitionConstructor = new () => BrowserSpeechRecognition;

const VOICE_LANGUAGES = {
  "as-IN": "Assamese", "bn-IN": "Bengali", "brx-IN": "Bodo", "doi-IN": "Dogri",
  "en-IN": "English (India)", "gu-IN": "Gujarati", "hi-IN": "Hindi", "kn-IN": "Kannada",
  "kok-IN": "Konkani", "mai-IN": "Maithili", "ml-IN": "Malayalam", "mni-IN": "Manipuri",
  "mr-IN": "Marathi", "ne-NP": "Nepali", "or-IN": "Odia", "pa-IN": "Punjabi",
  "sa-IN": "Sanskrit", "sat-IN": "Santali", "sd-IN": "Sindhi", "ta-IN": "Tamil",
  "te-IN": "Telugu", "ur-IN": "Urdu"
} as const;

type VoiceLanguageCode = keyof typeof VOICE_LANGUAGES;

function resolveVoiceLanguage(issue: string, selectedLanguage: VoiceLanguageCode): VoiceLanguageCode {
  if (selectedLanguage !== "en-IN") {
    return selectedLanguage;
  }

  const normalizedIssue = issue.toLowerCase().replace(/[^a-z\s]/g, " ");
  const romanizedTeluguTerms = [
    "chestunnav", "chestunav", "enti", "emiti", "ela", "unnava", "unnaru",
    "naku", "naaku", "kavali", "kaavali", "cheppu", "cheppandi", "avunu",
    "ledu", "enduku", "eppudu", "ekkada", "bagunnara", "namaskaram"
  ];

  if (romanizedTeluguTerms.some((term) => normalizedIssue.split(/\s+/).includes(term))) {
    return "te-IN";
  }

  if (/[\u0C00-\u0C7F]/.test(issue)) {
    return "te-IN";
  }

  return selectedLanguage;
}

function detectSpeechLanguage(text: string, selectedLanguage: VoiceLanguageCode): VoiceLanguageCode {
  if (selectedLanguage !== "en-IN") {
    return selectedLanguage;
  }

  const scriptLanguages: Array<[RegExp, VoiceLanguageCode]> = [
    [/[\u0980-\u09FF]/, "bn-IN"],
    [/[\u0900-\u097F]/, "hi-IN"],
    [/[\u0A00-\u0A7F]/, "pa-IN"],
    [/[\u0A80-\u0AFF]/, "gu-IN"],
    [/[\u0B00-\u0B7F]/, "or-IN"],
    [/[\u0B80-\u0BFF]/, "ta-IN"],
    [/[\u0C00-\u0C7F]/, "te-IN"],
    [/[\u0C80-\u0CFF]/, "kn-IN"],
    [/[\u0D00-\u0D7F]/, "ml-IN"],
    [/[\u0600-\u06FF]/, "ur-IN"],
  ];
  return scriptLanguages.find(([pattern]) => pattern.test(text))?.[1] ?? selectedLanguage;
}
function buildVoiceAssistIssue(issue: string, languageCode: VoiceLanguageCode) {
  const languageName = VOICE_LANGUAGES[languageCode];
  return languageCode === "te-IN"
    ? `${issue}\n\nVoice language: Telugu. Reply in natural conversational Telugu-English (Tenglish): use Telugu sentence structure with familiar English words like update, payment, ticket, email, project, status, photos, and support. Keep Telugu in Telugu script, English terms in English. Sound like a helpful Hyderabad support agent, not formal or literary. Use 2-4 short sentences. Never say Good day, relevant information, most certainly, or further assistance.`
    : `${issue}\n\nVoice language: ${languageName}. Reply naturally in the customer's language, keeping common product and support terms in English.`;
}

function MessageLauncherIcon() {
  return (
    <svg aria-hidden="true" className="store-chat-launcher-icon" viewBox="0 0 24 24">
      <path
        d="M12 3c4.97 0 9 3.47 9 7.75S16.97 18.5 12 18.5c-.87 0-1.72-.1-2.52-.29L4.9 20.74c-.63.28-1.3-.23-1.19-.9l.76-4.59C3.54 13.97 3 12.4 3 10.75 3 6.47 7.03 3 12 3Z"
        fill="currentColor"
      />
    </svg>
  );
}

function PaperPlaneIcon() {
  return (
    <svg aria-hidden="true" className="store-chat-plane-icon" viewBox="0 0 24 24">
      <path
        d="M20.25 4.5 10.6 14.15"
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.9"
      />
      <path
        d="m20.25 4.5-6.1 15-2.2-5.15L6.8 12.15 20.25 4.5Z"
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.9"
      />
    </svg>
  );
}

function MicrophoneIcon() {
  return (
    <svg aria-hidden="true" className="store-chat-microphone-icon" viewBox="0 0 24 24">
      <path d="M12 14.5a3.5 3.5 0 0 0 3.5-3.5V6a3.5 3.5 0 1 0-7 0v5a3.5 3.5 0 0 0 3.5 3.5Z" fill="currentColor" />
      <path d="M18.25 10.5v.5a6.25 6.25 0 0 1-12.5 0v-.5M12 17.25V21M9.25 21h5.5" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" />
    </svg>
  );
}

function ThumbsUpIcon() {
  return (
    <svg aria-hidden="true" className="store-chat-feedback-icon" viewBox="0 0 24 24">
      <path
        d="M9.5 10.25V20H6.25A2.25 2.25 0 0 1 4 17.75v-5.25a2.25 2.25 0 0 1 2.25-2.25H9.5Z"
        fill="none"
        stroke="currentColor"
        strokeLinejoin="round"
        strokeWidth="1.8"
      />
      <path
        d="M9.5 10.25 13 4.75c.31-.49.86-.79 1.44-.79h.06c.83 0 1.5.67 1.5 1.5v3.29h2.16A1.84 1.84 0 0 1 20 10.59l-1.11 7.2A2.5 2.5 0 0 1 16.42 20H9.5"
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.8"
      />
    </svg>
  );
}

function ThumbsDownIcon() {
  return (
    <svg aria-hidden="true" className="store-chat-feedback-icon" viewBox="0 0 24 24">
      <path
        d="M9.5 13.75V4H6.25A2.25 2.25 0 0 0 4 6.25v5.25a2.25 2.25 0 0 0 2.25 2.25H9.5Z"
        fill="none"
        stroke="currentColor"
        strokeLinejoin="round"
        strokeWidth="1.8"
      />
      <path
        d="m9.5 13.75 3.5 5.5c.31.49.86.79 1.44.79h.06c.83 0 1.5-.67 1.5-1.5v-3.29h2.16A1.84 1.84 0 0 0 20 13.41l-1.11-7.2A2.5 2.5 0 0 0 16.42 4H9.5"
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.8"
      />
    </svg>
  );
}

function SearchIcon() {
  return (
    <svg aria-hidden="true" className="help-center-icon" viewBox="0 0 24 24">
      <path
        d="m17.5 17.5 3.75 3.75"
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.8"
      />
      <circle
        cx="10.5"
        cy="10.5"
        fill="none"
        r="6.25"
        stroke="currentColor"
        strokeWidth="1.8"
      />
    </svg>
  );
}

function ChevronLeftIcon() {
  return (
    <svg aria-hidden="true" className="store-chat-symbol-icon" viewBox="0 0 24 24">
      <path
        d="M14.75 5.75 8.5 12l6.25 6.25"
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2.2"
      />
    </svg>
  );
}

function ChevronRightIcon() {
  return (
    <svg aria-hidden="true" className="store-chat-symbol-icon" viewBox="0 0 24 24">
      <path
        d="M9.25 5.75 15.5 12l-6.25 6.25"
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2.2"
      />
    </svg>
  );
}

function ChevronDownIcon() {
  return (
    <svg aria-hidden="true" className="store-chat-symbol-icon" viewBox="0 0 24 24">
      <path
        d="M6.75 9.5 12 14.75 17.25 9.5"
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2.2"
      />
    </svg>
  );
}

function GridViewIcon() {
  return (
    <svg aria-hidden="true" className="help-center-icon small" viewBox="0 0 24 24">
      <path
        d="M4.5 4.5h6v6h-6Zm9 0h6v6h-6Zm-9 9h6v6h-6Zm9 0h6v6h-6Z"
        fill="none"
        stroke="currentColor"
        strokeLinejoin="round"
        strokeWidth="1.8"
      />
    </svg>
  );
}

function ListViewIcon() {
  return (
    <svg aria-hidden="true" className="help-center-icon small" viewBox="0 0 24 24">
      <path
        d="M6 7.25h12M6 12h12M6 16.75h12"
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeWidth="1.8"
      />
      <circle cx="3.5" cy="7.25" fill="currentColor" r="1.2" />
      <circle cx="3.5" cy="12" fill="currentColor" r="1.2" />
      <circle cx="3.5" cy="16.75" fill="currentColor" r="1.2" />
    </svg>
  );
}

function MailIcon() {
  return (
    <svg aria-hidden="true" className="help-center-icon small" viewBox="0 0 24 24">
      <path
        d="M4.5 6.75h15a1.5 1.5 0 0 1 1.5 1.5v7.5a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 15.75v-7.5a1.5 1.5 0 0 1 1.5-1.5Z"
        fill="none"
        stroke="currentColor"
        strokeLinejoin="round"
        strokeWidth="1.8"
      />
      <path
        d="m4.5 8.25 7.5 5.25 7.5-5.25"
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.8"
      />
    </svg>
  );
}

function PhoneIcon() {
  return (
    <svg aria-hidden="true" className="help-center-icon small" viewBox="0 0 24 24">
      <path
        d="M7.8 4.5h2.35l1.2 4.25-1.55 1.55a15.6 15.6 0 0 0 3.9 3.9l1.55-1.55 4.25 1.2v2.35A1.8 1.8 0 0 1 17.7 18C10.1 18 6 13.9 6 6.3A1.8 1.8 0 0 1 7.8 4.5Z"
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.8"
      />
    </svg>
  );
}

function TrackOrderIcon() {
  return (
    <svg aria-hidden="true" className="help-center-order-icon" viewBox="0 0 56 56">
      <path
        d="M28 7.5 40.5 14.5 28 21.5 15.5 14.5 28 7.5Z"
        fill="none"
        stroke="currentColor"
        strokeLinejoin="round"
        strokeWidth="1.8"
      />
      <path
        d="M15.5 14.5v16l12.5 7 12.5-7v-16"
        fill="none"
        stroke="currentColor"
        strokeLinejoin="round"
        strokeWidth="1.8"
      />
      <path
        d="M28 21.5v16"
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeWidth="1.8"
      />
      <circle
        cx="40.75"
        cy="33.75"
        fill="none"
        r="6.25"
        stroke="currentColor"
        strokeWidth="1.8"
      />
      <path
        d="m45.25 38.25 4.25 4.25"
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeWidth="1.8"
      />
    </svg>
  );
}

function CancelOrderIcon() {
  return (
    <svg aria-hidden="true" className="help-center-order-icon" viewBox="0 0 56 56">
      <path
        d="M28 7.5 40.5 14.5 28 21.5 15.5 14.5 28 7.5Z"
        fill="none"
        stroke="currentColor"
        strokeLinejoin="round"
        strokeWidth="1.8"
      />
      <path
        d="M15.5 14.5v16l12.5 7 12.5-7v-16"
        fill="none"
        stroke="currentColor"
        strokeLinejoin="round"
        strokeWidth="1.8"
      />
      <path
        d="M28 21.5v16"
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeWidth="1.8"
      />
      <circle cx="41" cy="33.5" fill="currentColor" r="6.5" />
      <path
        d="m38.4 30.9 5.2 5.2m0-5.2-5.2 5.2"
        fill="none"
        stroke="#fff"
        strokeLinecap="round"
        strokeWidth="1.8"
      />
    </svg>
  );
}

function ReportIssueIcon() {
  return (
    <svg aria-hidden="true" className="help-center-order-icon" viewBox="0 0 56 56">
      <path
        d="M28 7.5 40.5 14.5 28 21.5 15.5 14.5 28 7.5Z"
        fill="none"
        stroke="currentColor"
        strokeLinejoin="round"
        strokeWidth="1.8"
      />
      <path
        d="M15.5 14.5v16l12.5 7 12.5-7v-16"
        fill="none"
        stroke="currentColor"
        strokeLinejoin="round"
        strokeWidth="1.8"
      />
      <path
        d="M28 21.5v16"
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeWidth="1.8"
      />
      <path d="M42 26.5 49.75 41H34.25L42 26.5Z" fill="currentColor" />
      <path
        d="M42 31.25v4.5m0 2.65h.01"
        fill="none"
        stroke="#fff"
        strokeLinecap="round"
        strokeWidth="1.8"
      />
    </svg>
  );
}

const helpCenterArticlesPath = "/home";
const helpCenterHomePath = "/home/about";
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

const helpCenterNav = [
  { isHome: true, to: helpCenterHomePath, label: "Home" },
  { to: `${helpCenterArticlesPath}#popular-questions`, label: "Popular questions" },
  { to: `${helpCenterArticlesPath}#more-information`, label: "All articles" },
  { to: `${helpCenterArticlesPath}#get-support`, label: "Get support" }
];

const homeDemoHeroImage =
  "https://images.unsplash.com/photo-1504307651254-35680f356dfd?auto=format&fit=crop&w=1600&q=80";
const homeDemoCommandImage =
  "https://images.unsplash.com/photo-1517048676732-d65bc937f952?auto=format&fit=crop&w=1400&q=80";
const homeDemoSceneCards = [
  {
    alt: "Construction professionals reviewing live site progress.",
    copy: "Field teams, buyers, and support all stay aligned on the same update path.",
    image: "https://images.unsplash.com/photo-1541888946425-d81bb19240f5?auto=format&fit=crop&w=1200&q=80",
    title: "Live site coordination"
  },
  {
    alt: "Modern residential tower ready for buyer handover.",
    copy: "Confident possession, snagging, and aftercare communication from day one.",
    image: "https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?auto=format&fit=crop&w=1200&q=80",
    title: "Buyer-ready handover"
  }
];
const homeDemoLifecycleCards = [
  {
    alt: "Architectural planning and preconstruction coordination.",
    copy: "Support buyers with pricing questions, brochure access, availability checks, and early-stage guidance before the project moves into execution.",
    eyebrow: "01 Preconstruction clarity",
    image: "https://images.unsplash.com/photo-1503387762-592deb58ef4e?auto=format&fit=crop&w=1200&q=80",
    title: "Sales, quotation, and document answers that feel project-ready."
  },
  {
    alt: "Active construction site with cranes and structural work underway.",
    copy: "Turn construction updates, site visit requests, milestone explanations, and project follow-ups into a single clean support journey.",
    eyebrow: "02 Delivery visibility",
    image: "https://images.unsplash.com/photo-1504307651254-35680f356dfd?auto=format&fit=crop&w=1200&q=80",
    title: "Live delivery support built around real construction milestones."
  },
  {
    alt: "Completed interior space prepared for possession and maintenance support.",
    copy: "Keep possession timelines, defect reports, maintenance triage, and documentation requests structured after project delivery.",
    eyebrow: "03 Handover discipline",
    image: "https://images.unsplash.com/photo-1494526585095-c41746248156?auto=format&fit=crop&w=1200&q=80",
    title: "Aftercare and possession workflows that stay polished under pressure."
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

function getHomeDemoCategoryImage(title: string, index: number) {
  const normalizedTitle = normalizeText(title);

  if (
    normalizedTitle.includes("price") ||
    normalizedTitle.includes("quote") ||
    normalizedTitle.includes("sales") ||
    normalizedTitle.includes("availability")
  ) {
    return "https://images.unsplash.com/photo-1520607162513-77705c0f0d4a?auto=format&fit=crop&w=1200&q=80";
  }

  if (
    normalizedTitle.includes("construction") ||
    normalizedTitle.includes("visit") ||
    normalizedTitle.includes("project")
  ) {
    return "https://images.unsplash.com/photo-1541888946425-d81bb19240f5?auto=format&fit=crop&w=1200&q=80";
  }

  if (
    normalizedTitle.includes("handover") ||
    normalizedTitle.includes("maintenance") ||
    normalizedTitle.includes("defect") ||
    normalizedTitle.includes("possession")
  ) {
    return "https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?auto=format&fit=crop&w=1200&q=80";
  }

  if (
    normalizedTitle.includes("document") ||
    normalizedTitle.includes("payment") ||
    normalizedTitle.includes("receipt")
  ) {
    return "https://images.unsplash.com/photo-1517048676732-d65bc937f952?auto=format&fit=crop&w=1200&q=80";
  }

  const fallbackImages = [
    "https://images.unsplash.com/photo-1504307651254-35680f356dfd?auto=format&fit=crop&w=1200&q=80",
    "https://images.unsplash.com/photo-1541888946425-d81bb19240f5?auto=format&fit=crop&w=1200&q=80",
    "https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?auto=format&fit=crop&w=1200&q=80"
  ];

  return fallbackImages[index % fallbackImages.length];
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
    .slice(-12)
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
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [isCreatingTicket, setIsCreatingTicket] = useState(false);
  const [isTypingReply, setIsTypingReply] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isVoiceConversation, setIsVoiceConversation] = useState(false);
  const [isVoiceMuted, setIsVoiceMuted] = useState(false);
  const [voiceTranscript, setVoiceTranscript] = useState("");
  const [voiceLanguage, setVoiceLanguage] = useState<VoiceLanguageCode>("en-IN");
  const [isFollowUpFormVisible, setIsFollowUpFormVisible] = useState(false);
  const [storefrontError, setStorefrontError] = useState("");
  const [activeFollowUpIssue, setActiveFollowUpIssue] = useState("");
  const chatBodyRef = useRef<HTMLDivElement | null>(null);
  const chatEmailRef = useRef<HTMLInputElement | null>(null);
  const chatComposeRef = useRef<HTMLTextAreaElement | null>(null);
  const chatContactComposeRef = useRef<HTMLInputElement | null>(null);
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
    window.scrollTo({
      behavior: "smooth",
      top: 0
    });
  }, [articleSlug, categorySlug]);

  useEffect(() => {
    if (!chatBodyRef.current) {
      return;
    }

    const customerMessages = chatBodyRef.current.querySelectorAll<HTMLElement>(
      ".store-chat-message.customer"
    );
    const latestCustomerMessage = customerMessages.item(customerMessages.length - 1);

    chatBodyRef.current.scrollTo({
      behavior: "smooth",
      top: latestCustomerMessage
        ? Math.max(0, latestCustomerMessage.offsetTop - 16)
        : chatBodyRef.current.scrollHeight
    });
  }, [chatMessages, isChatOpen, isTypingReply]);

  function resetChatHome() {
    setChatMessages([]);
    setChatDraft("");
    setActiveFollowUpIssue("");
    setIsFollowUpFormVisible(false);
    setStorefrontError("");
    setIsTypingReply(false);
  }

  function openFollowUpForm(issue: string) {
    setActiveFollowUpIssue(issue.trim());
    setIsFollowUpFormVisible(true);
    setStorefrontError("");
    setChatDraft("");
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
  async function queueBotResponse(
    issue: string,
    primaryArticleId: number | undefined,
    shouldResetConversation: boolean,
    customerMessageText = issue
  ) {
    const trimmedIssue = issue.trim();
    const trimmedCustomerMessage = customerMessageText.trim();
    const customerMessageId = Date.now();
    const botMessageId = customerMessageId + 1;
    const conversationMessages = buildAssistConversationMessages(
      chatMessages,
      trimmedCustomerMessage || trimmedIssue,
      shouldResetConversation
    );

    if (!trimmedIssue) {
      return;
    }

    const primaryArticle =
      publishedSupportArticles.find((article) => article.id === primaryArticleId) ?? undefined;

    setStorefrontError("");
    setIsTypingReply(true);
    setIsChatOpen(true);
    setIsFollowUpFormVisible(false);
    setActiveFollowUpIssue("");
    setChatDraft("");
    setChatMessages((current) => {
      const nextCustomerMessage: ChatMessage = {
        contextIssue: trimmedIssue,
        id: customerMessageId,
        relatedArticles: [],
        sender: "customer",
        text: trimmedCustomerMessage || trimmedIssue
      };

      if (shouldResetConversation) {
        return [nextCustomerMessage];
      }

      return [...current, nextCustomerMessage];
    });

    const resolvedVoiceLanguage = resolveVoiceLanguage(trimmedIssue, voiceLanguage);
    const assistIssue = resolvedVoiceLanguage === "en-IN"
      ? trimmedIssue
      : buildVoiceAssistIssue(trimmedIssue, resolvedVoiceLanguage);

    try {
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
            contextIssue: trimmedIssue,
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
        return;
      }

      await streamSupportAssist({
        article_hint_url: isVoiceConversation ? "" : (primaryArticle?.url ?? ""),
        conversation_messages: conversationMessages,
        customer_email: chatEmail.trim(),
        issue: assistIssue,
        issue_type: inferIssueType(trimmedCustomerMessage || trimmedIssue),
        limit: isVoiceConversation ? 6 : 2,
        prefer_fast_response: !isVoiceConversation,
        prefer_qwen_response: true
      }, {
        onDelta: (text) => {
          setIsTypingReply(false);
          setChatMessages((current) =>
            appendBotMessageDelta(current, botMessageId, trimmedIssue, text)
          );
        },
        onDone: (assistResponse) => {
          setIsTypingReply(false);

          setChatMessages((current) =>
            finalizeBotMessage(current, botMessageId, trimmedIssue, {
              feedbackState: undefined,
              isAutomated: true,
              relatedArticles: [],
              showHelpfulPrompt: false,
              text: assistResponse.answer
            })
          );
        }
      });
    } catch {
      try {
        const assistResponse = await getSupportAssist({
          article_hint_url: isVoiceConversation ? "" : (primaryArticle?.url ?? ""),
          conversation_messages: conversationMessages,
          customer_email: chatEmail.trim(),
          issue: assistIssue,
          issue_type: inferIssueType(trimmedCustomerMessage || trimmedIssue),
          limit: isVoiceConversation ? 6 : 2,
          prefer_fast_response: !isVoiceConversation,
          prefer_qwen_response: true
        });

        setIsTypingReply(false);
        setChatMessages((current) =>
          finalizeBotMessage(current, botMessageId, trimmedIssue, {
            feedbackState: undefined,
            isAutomated: true,
            relatedArticles: [],
            showHelpfulPrompt: false,
            text: assistResponse.answer
          })
        );
      } catch {
        const demoResponse = buildDemoBotResponse(
          trimmedIssue,
          chatEmail,
          primaryArticleId,
          publishedSupportArticles
        );

        setIsTypingReply(false);
        setChatMessages((current) =>
          finalizeBotMessage(current, botMessageId, trimmedIssue, {
            feedbackState: undefined,
            isAutomated: true,
            relatedArticles: [],
            showHelpfulPrompt: false,
            text: demoResponse.text
          })
        );
      }
    } finally {
      setIsTypingReply(false);
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

  const hasActiveConversation = chatMessages.length > 0 || isTypingReply;
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
    const spokenText = prepareConversationalSpeech(latestBotMessage.text);
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
  const homeDemoMetrics = [
    {
      detail:
        "Buyer-facing answers, pricing logic, documentation help, and handover support kept in one published system.",
      label: "Published guides",
      value: String(totalPublishedArticles).padStart(2, "0")
    },
    {
      detail:
        "Clear support lanes for sales, construction updates, possession, maintenance, and document requests.",
      label: "Support sectors",
      value: String(totalPublishedCategories).padStart(2, "0")
    },
    {
      detail:
        "Fast entry points for quote requests, site visits, payment clarification, and defect follow-up.",
      label: "Quick response tracks",
      value: String(supportFlows.length).padStart(2, "0")
    }
  ];
  const homeDemoSectorShowcase = featuredHelpCenterCategories.map((category, index) => ({
    ...category,
    image: getHomeDemoCategoryImage(category.title, index)
  }));
  const homeDemoCommandPoints = [
    {
      copy:
        "Buyers can move from first-interest pricing questions to documented next steps without losing context.",
      label: "Sales confidence"
    },
    {
      copy:
        "Construction updates, visit coordination, and delivery explanations stay aligned with the latest published guidance.",
      label: "Site visibility"
    },
    {
      copy:
        "Post-handover defects, snagging, and document follow-up route into the right service path quickly.",
      label: "Aftercare discipline"
    }
  ];

  return (
    <div className="help-center-page" id="top">
      <header className="help-center-header">
        <div className="help-center-shell help-center-header-inner">
          <Link className="help-center-header-brand" to={helpCenterHomePath}>
            <AcrobuildLogo subtitle="Project support desk" />
          </Link>

          <nav className="help-center-header-nav" aria-label="Help center sections">
            {helpCenterNav.map((item) => (
              <Link
                className={item.isHome ? "help-center-header-home" : undefined}
                key={item.to}
                to={item.to}
              >
                {item.label}
              </Link>
            ))}
          </nav>

          <Link className="help-center-header-link" to={workspaceLink}>
            {workspaceLabel}
          </Link>
        </div>
      </header>

      <main className="help-center-main">
        {isHomeDemoPage ? (
          <>
            <section className="help-center-demo-hero">
              <div className="help-center-shell help-center-demo-hero-inner">
                <div className="help-center-demo-copy">
                  <div className="help-center-article-kicker">Acrobuild buyer experience</div>
                  <h1>One premium front door for pricing, construction updates, and final handover support.</h1>
                  <p>
                    Acrobuild now feels closer to a modern construction brand: visual, credible,
                    and structured around the real buyer journey from inquiry to possession.
                  </p>

                  <div className="help-center-demo-actions">
                    <Link
                      className="help-center-inline-button help-center-inline-button-solid help-center-inline-link"
                      to={helpCenterArticlesPath}
                    >
                      Explore help center
                    </Link>
                    <button
                      className="help-center-inline-button help-center-inline-button-ghost"
                      onClick={() => openContactMode("")}
                      type="button"
                    >
                      Talk to support
                    </button>
                  </div>

                  <div className="help-center-demo-metric-grid">
                    {homeDemoMetrics.map((metric) => (
                      <article className="help-center-demo-metric-card" key={metric.label}>
                        <small>{metric.label}</small>
                        <strong>{metric.value}</strong>
                        <p>{metric.detail}</p>
                      </article>
                    ))}
                  </div>
                </div>

                <div className="help-center-demo-visual-stage">
                  <div className="help-center-demo-hero-image-shell">
                    <img
                      alt="Acrobuild construction site hero view"
                      className="help-center-demo-hero-image"
                      loading="eager"
                      src={homeDemoHeroImage}
                    />
                    <div className="help-center-demo-hero-badge">
                      <strong>Project-ready support storytelling</strong>
                      <span>
                        A stronger first impression without changing the help-center structure or
                        the live chat experience.
                      </span>
                    </div>
                  </div>

                  <div className="help-center-demo-scene-grid">
                    {homeDemoSceneCards.map((card) => (
                      <article className="help-center-demo-scene-card" key={card.title}>
                        <img
                          alt={card.alt}
                          className="help-center-demo-scene-image"
                          loading="lazy"
                          src={card.image}
                        />
                        <div className="help-center-demo-scene-body">
                          <strong>{card.title}</strong>
                          <span>{card.copy}</span>
                        </div>
                      </article>
                    ))}
                  </div>
                </div>
              </div>
            </section>

            <section className="help-center-shell help-center-section help-center-demo-section">
              <div className="help-center-section-head">
                <div>
                  <h2>Built around the real project lifecycle</h2>
                  <p>
                    The landing page now mirrors how premium construction brands present trust,
                    momentum, and delivery clarity across every stage.
                  </p>
                </div>
              </div>

              <div className="help-center-demo-lifecycle-grid">
                {homeDemoLifecycleCards.map((card) => (
                  <article className="help-center-demo-lifecycle-card" key={card.eyebrow}>
                    <img
                      alt={card.alt}
                      className="help-center-demo-lifecycle-image"
                      loading="lazy"
                      src={card.image}
                    />
                    <div className="help-center-demo-lifecycle-body">
                      <small>{card.eyebrow}</small>
                      <strong>{card.title}</strong>
                      <p>{card.copy}</p>
                    </div>
                  </article>
                ))}
              </div>
            </section>

            <section className="help-center-shell help-center-section help-center-demo-section">
              <div className="help-center-section-head">
                <div>
                  <h2>Featured support sectors</h2>
                  <p>
                    These sections still come from your live published help-center categories. The
                    visual upgrade just presents them with more polish.
                  </p>
                </div>
              </div>

              <div className="help-center-demo-sector-grid">
                {homeDemoSectorShowcase.map((category) => (
                  <Link
                    className="help-center-demo-sector-card"
                    key={category.id}
                    to={buildCategoryPath(category.title)}
                  >
                    <img
                      alt={category.title}
                      className="help-center-demo-sector-image"
                      loading="lazy"
                      src={category.image}
                    />
                    <div className="help-center-demo-sector-body">
                      <small>{formatArticleCount(category.articleCount)}</small>
                      <strong>{category.title}</strong>
                      <span>
                        {category.description ||
                          "Support routes tailored for this stage of the buyer and homeowner journey."}
                      </span>
                    </div>
                  </Link>
                ))}
              </div>
            </section>

            <section className="help-center-shell help-center-section help-center-demo-section">
              <div className="help-center-demo-command-grid">
                <div className="help-center-demo-command-panel">
                  <div className="help-center-article-kicker">Support operations</div>
                  <h2>A cleaner command layer behind the buyer-facing experience.</h2>
                  <p>
                    The public help center looks stronger, while your team still works from the
                    same published articles, support categories, and conversation flows.
                  </p>

                  <div className="help-center-demo-command-list">
                    {homeDemoCommandPoints.map((point, index) => (
                      <div className="help-center-demo-command-point" key={point.label}>
                        <span className="help-center-demo-command-index">{`0${index + 1}`}</span>
                        <div>
                          <strong>{point.label}</strong>
                          <p>{point.copy}</p>
                        </div>
                      </div>
                    ))}
                  </div>

                  <Link
                    className="help-center-inline-button help-center-inline-button-solid help-center-inline-link"
                    to={helpCenterArticlesPath}
                  >
                    Open full help center
                  </Link>
                </div>

                <div className="help-center-demo-command-visual">
                  <img
                    alt="Acrobuild support team coordinating project communication"
                    className="help-center-demo-command-image"
                    loading="lazy"
                    src={homeDemoCommandImage}
                  />
                  <div className="help-center-demo-command-note">
                    <strong>Construction-ready answers</strong>
                    <span>
                      Published guidance, chat replies, and support routing continue to reinforce
                      the same buyer journey.
                    </span>
                  </div>
                </div>
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

                  <form
                    className="help-center-search-shell"
                    onSubmit={(event) => {
                      event.preventDefault();
                      handleHelpCenterSearchSubmit();
                    }}
                  >
                    <label className="help-center-searchbar">
                      <SearchIcon />
                      <input
                        aria-label="Search help center"
                        onChange={(event) => setHelpCenterQuery(event.target.value)}
                        placeholder="Search support articles and categories"
                        value={helpCenterQuery}
                      />
                      {helpCenterQuery.trim() ? (
                        <button
                          aria-label="Clear search"
                          className="help-center-search-clear"
                          onClick={() => setHelpCenterQuery("")}
                          type="button"
                        >
                          x
                        </button>
                      ) : null}
                    </label>
                  </form>

                  {normalizedHelpCenterQuery ? (
                    <div className="help-center-search-meta">
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

            <section className="help-center-shell help-center-section" id="popular-questions">
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

            <section className="help-center-shell help-center-section" id="more-information">
              <div className="help-center-section-head">
                <div>
                  <h2>All article categories</h2>
                  <p>Browse published Acrobuild categories for sales, construction, documentation, and handover support.</p>
                </div>

                <div className="help-center-view-toggle" role="group" aria-label="Category layout">
                  <button
                    className={`help-center-view-button${categoryView === "grid" ? " active" : ""}`}
                    onClick={() => setCategoryView("grid")}
                    type="button"
                  >
                    <GridViewIcon />
                  </button>
                  <button
                    className={`help-center-view-button${categoryView === "list" ? " active" : ""}`}
                    onClick={() => setCategoryView("list")}
                    type="button"
                  >
                    <ListViewIcon />
                  </button>
                </div>
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
            </section>

            <section className="help-center-shell help-center-section" id="get-support">
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
              <div className="help-center-breadcrumbs">
                <Link to={helpCenterHomePath}>Home</Link>
                <span>/</span>
                <Link to={helpCenterArticlesPath}>All articles</Link>
                <span>/</span>
                <strong>{selectedCategory ?? "Category"}</strong>
              </div>

              <form
                className="help-center-subpage-search"
                onSubmit={(event) => {
                  event.preventDefault();
                  handleHelpCenterSearchSubmit();
                }}
              >
                <label className="help-center-searchbar compact">
                  <SearchIcon />
                  <input
                    aria-label="Search support articles"
                    onChange={(event) => setHelpCenterQuery(event.target.value)}
                    placeholder="Search"
                    value={helpCenterQuery}
                  />
                </label>
              </form>
            </div>

            <div className="help-center-section-head help-center-article-head">
              <div>
                <div className="help-center-article-kicker">All articles</div>
                <h2>{selectedCategory ?? "Article category"}</h2>
              </div>

              <div className="help-center-view-toggle" role="group" aria-label="Article layout">
                <button
                  className={`help-center-view-button${categoryView === "grid" ? " active" : ""}`}
                  onClick={() => setCategoryView("grid")}
                  type="button"
                >
                  <GridViewIcon />
                </button>
                <button
                  className={`help-center-view-button${categoryView === "list" ? " active" : ""}`}
                  onClick={() => setCategoryView("list")}
                  type="button"
                >
                  <ListViewIcon />
                </button>
              </div>
            </div>

            <div className={`help-center-article-grid ${categoryView === "list" ? "list" : ""}`}>
              {filteredCategoryArticles.map((article) => (
                <Link
                  className="help-center-article-card"
                  key={article.id}
                  to={buildArticlePath(article)}
                >
                  <strong>{article.title}</strong>
                  <p>{getArticleExcerpt(article)}</p>
                </Link>
              ))}
            </div>

            {!filteredCategoryArticles.length ? (
              <div className="help-center-empty-state">
                <strong>No articles matched that search in this category.</strong>
                <p>Try another keyword or go back to all help-center categories.</p>
                <Link className="help-center-inline-button help-center-inline-link" to={helpCenterArticlesPath}>
                  Back to help center
                </Link>
              </div>
            ) : null}
          </section>
        ) : null}

        {isArticlePage ? (
          <section className="help-center-shell help-center-article-shell">
            {selectedArticle ? (
              <>
                <div className="help-center-subpage-topbar">
                  <div className="help-center-breadcrumbs">
                    <Link to={helpCenterHomePath}>Home</Link>
                    <span>/</span>
                    <Link to={helpCenterArticlesPath}>All articles</Link>
                    <span>/</span>
                    <Link to={buildCategoryPath(selectedArticle.category)}>
                      {selectedArticle.category}
                    </Link>
                    <span>/</span>
                    <strong>{selectedArticle.title}</strong>
                  </div>

                  <form
                    className="help-center-subpage-search"
                    onSubmit={(event) => {
                      event.preventDefault();
                      handleHelpCenterSearchSubmit();
                    }}
                  >
                    <label className="help-center-searchbar compact">
                      <SearchIcon />
                      <input
                        aria-label="Search support articles"
                        onChange={(event) => setHelpCenterQuery(event.target.value)}
                        placeholder="Search"
                        value={helpCenterQuery}
                      />
                    </label>
                  </form>
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
                        className="help-center-inline-button"
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
                        className="help-center-inline-button"
                        onClick={() => openContactMode(getArticlePrompt(selectedArticle))}
                        type="button"
                      >
                        Need more help
                      </button>
                    </div>
                  </article>

                  <aside className="help-center-related-panel">
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
                    </div>
                  </aside>
                </div>
              </>
            ) : (
              <div className="help-center-empty-state">
                <strong>That article could not be found.</strong>
                <p>Go back to the help center home and open another published support article.</p>
                <Link className="help-center-inline-button help-center-inline-link" to={helpCenterArticlesPath}>
                  Back to help center
                </Link>
              </div>
            )}
          </section>
        ) : null}
      </main>

      <footer className="help-center-footer">
        <div className="help-center-shell help-center-footer-inner">
          <Link className="help-center-footer-brand" to={helpCenterHomePath}>
            <AcrobuildLogo className="acrobuild-logo-compact" subtitle="Buyer & homeowner support" />
          </Link>
          <div className="help-center-footer-links">
            <Link to={helpCenterArticlesPath}>All articles</Link>
            <Link to={`${helpCenterArticlesPath}#popular-questions`}>Popular questions</Link>
            <a href={`${helpCenterArticlesPath}#get-support`}>Contact</a>
          </div>
          <span>English (US)</span>
        </div>
      </footer>

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
                        ? "Speaking — you can interrupt"
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
                ? <><span className="voice-call-transcript-label">I heard</span>“{voiceTranscript}”</>
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
            className="store-chat-panel"
            style={{
              fontFamily: widgetConfig.fontFamily,
              width: `min(${widgetConfig.widgetWidth}px, calc(100vw - 1rem))`
            }}
          >
            <header
              className="store-chat-header"
              style={{ backgroundColor: widgetConfig.accentColor }}
            >
              <div className="store-chat-header-top">
                <button
                  aria-label={showBackControl ? "Back to support options" : "Collapse chat"}
                  className="store-chat-icon-button"
                  onClick={() => {
                    if (hasActiveConversation) {
                      resetChatHome();
                      return;
                    }

                    if (isContactMode) {
                      setIsFollowUpFormVisible(false);
                      setStorefrontError("");
                      setChatDraft("");
                      return;
                    }

                    setIsChatOpen(false);
                  }}
                  type="button"
                >
                  {showBackControl ? <ChevronLeftIcon /> : <ChevronDownIcon />}
                </button>

                <div className="store-chat-brand-lockup">
                  <strong>{widgetConfig.assistantName}</strong>
                </div>
              </div>
            </header>

            <div
              className={`store-chat-body${isMenuMode ? " menu-mode" : ""}`}
              ref={chatBodyRef}
            >
              {!hasActiveConversation ? (
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
                  <div className="store-chat-home menu-mode">
                    <div className="store-chat-menu-kicker">{assistantBrandName.toUpperCase()}</div>
                    <h2 className="store-chat-menu-title">How can we help?</h2>

                    <div className="store-chat-menu-card">
                      <div className="store-chat-flow-list compact">
                        {supportFlows.map((flow) => (
                          <button
                            className="store-chat-flow-button"
                            key={flow.id}
                            onClick={() => handleChatFlowSelect(flow)}
                            type="button"
                          >
                            <span>{flow.label}</span>
                            <span className="store-chat-flow-arrow">
                              <ChevronRightIcon />
                            </span>
                          </button>
                        ))}
                      </div>
                    </div>

                    <button
                      className="store-chat-contact-card"
                      onClick={() => openContactMode("")}
                      type="button"
                    >
                      <span className="store-chat-contact-card-brand">
                        <span className={`store-chat-contact-card-logo${widgetLogoUrl ? " has-image" : ""}`}>
                          {widgetLogoUrl ? (
                            <img alt="" className="store-chat-contact-card-logo-image" src={widgetLogoUrl} />
                          ) : (
                            assistantInitial
                          )}
                        </span>
                        <span className="store-chat-contact-card-copy">
                          <strong>{assistantBrandName}</strong>
                          <span>Send us a message</span>
                        </span>
                      </span>
                      <span className="store-chat-contact-card-action">
                        <PaperPlaneIcon />
                      </span>
                    </button>
                  </div>
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
                                      backgroundColor: widgetConfig.accentColor,
                                      borderColor: widgetConfig.accentColor
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
                                  <div className="store-chat-message-text">{message.text}</div>
                                </div>
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

                    {isTypingReply ? (
                      <div className="store-chat-typing">
                        <span />
                        <span />
                        <span />
                      </div>
                    ) : null}

                    {isFollowUpFormVisible ? (
                      <section className="store-chat-follow-up-card">
                        <div className="store-chat-follow-up-head">
                          <strong>Tell us what still needs help</strong>
                          <span>
                            We will raise a support ticket after the customer enters an email and
                            message.
                          </span>
                        </div>

                        <label className="store-chat-email-row">
                          <span>Email for follow-up</span>
                          <input
                            className="store-chat-email-input"
                            onChange={(event) => setChatEmail(event.target.value)}
                            placeholder="you@example.com"
                            ref={chatEmailRef}
                            value={chatEmail}
                          />
                        </label>

                        <label className="store-chat-email-row">
                          <span>What do you still need help with?</span>
                          <textarea
                            className="store-chat-compose-input"
                            onChange={(event) => setChatDraft(event.target.value)}
                            placeholder="Add the customer's remaining question here..."
                            ref={chatComposeRef}
                            rows={4}
                            value={chatDraft}
                          />
                        </label>

                        <div className="store-chat-follow-up-actions">
                          <button
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
                          </button>
                          <button
                            className="store-chat-help-button dark"
                            disabled={isCreatingTicket}
                            onClick={() => void createTicketForIssue(activeFollowUpIssue, chatDraft)}
                            type="button"
                          >
                            {isCreatingTicket ? "Creating..." : "Submit ticket"}
                          </button>
                        </div>
                      </section>
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
                    aria-label={isVoiceConversation ? "Stop voice conversation" : "Start voice conversation"}
                    aria-pressed={isVoiceConversation}
                    className={`store-chat-voice-button${isListening ? " listening" : ""}${isVoiceConversation ? " active" : ""}`}
                    disabled={!supportsSpeechRecognition}
                    onClick={handleVoiceToggle}
                    title={supportsSpeechRecognition ? (isVoiceConversation ? "Stop voice conversation" : "Start a hands-free voice conversation") : "Voice input is not supported in this browser"}
                    type="button"
                  >
                    <MicrophoneIcon />
                  </button>                  <button
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

                  if (!chatDraft.trim() || isTypingReply) {
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
                    className="store-chat-message-input"
                    onChange={(event) => setChatDraft(event.target.value)}
                    placeholder={hasActiveConversation ? "Reply to the assistant" : "Ask a support question"}
                    value={chatDraft}
                  />
                  <button
                    aria-label={isVoiceConversation ? "Stop voice conversation" : "Start voice conversation"}
                    aria-pressed={isVoiceConversation}
                    className={`store-chat-voice-button${isListening ? " listening" : ""}${isVoiceConversation ? " active" : ""}`}
                    disabled={!supportsSpeechRecognition}
                    onClick={handleVoiceToggle}
                    title={supportsSpeechRecognition ? (isVoiceConversation ? "Stop voice conversation" : "Start a hands-free voice conversation") : "Voice input is not supported in this browser"}
                    type="button"
                  >
                    <MicrophoneIcon />
                  </button>                  <button
                    aria-label="Send message"
                    className="store-chat-compose-submit"
                    disabled={isTypingReply || !chatDraft.trim()}
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
                <div className="store-chat-error">{storefrontError}</div>
              </div>
            ) : null}
          </section>
        ) : null}

        <button
          aria-label={widgetConfig.launcherLabel}
          className={`store-chat-launcher${isChatOpen ? " raised" : ""}${widgetLogoUrl && !isChatOpen ? " has-logo" : ""}`}
          onClick={() => setIsChatOpen((current) => !current)}
          style={{
            backgroundColor: widgetLogoUrl && !isChatOpen ? "#ffffff" : widgetConfig.accentColor,
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


