import {
  startTransition,
  type KeyboardEvent as ReactKeyboardEvent,
  useDeferredValue,
  useEffect,
  useMemo,
  useRef,
  useState
} from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { PhotoEmptyState } from "../components/PhotoEmptyState";
import { useRole } from "../contexts/RoleContext";
import { useSearch } from "../contexts/SearchContext";
import type { TicketSearchSuggestion } from "../contexts/SearchContext";
import { AdminAnalyticsPage } from "./AdminAnalyticsPage";
import { AIAgentPage } from "./AIAgentPage";
import { ArticlesPage } from "./ArticlesPage";
import { BusinessHoursPage } from "./BusinessHoursPage";
import { ChatWidgetPage } from "./ChatWidgetPage";
import { MacrosPage } from "./MacrosPage";
import { ManageTagsPage } from "./ManageTagsPage";
import { TicketDashboardPage } from "./TicketDashboardPage";
import { UsersPage } from "./UsersPage";
import {
  closeAdminTicket,
  createAdminTicketNote,
  getAdminCustomerByEmail,
  getAdminMacros,
  getAdminRecommendedMacros,
  getAdminTags,
  getAdminTicketDetail,
  getAdminTickets,
  getOrdersByEmail,
  markAdminTicketRead,
  postAdminTicketReply,
  updateAdminTicketAssignee,
  updateAdminTicketStatus,
  updateAdminTicketTags
} from "../lib/api";
import {
  formatTicketTimestamp,
  getStatusColor
} from "../lib/ticketPresentation";
import {
  getRoleHomePath,
  getRolePanelPath,
  type WorkspacePanelId
} from "../lib/roleNavigation";
import type {
  CustomerLookupResponse,
  Macro,
  Order,
  OrderItem,
  SubscriptionRecord,
  Ticket,
  TicketDetailResponse,
  TicketTag
} from "../types";

type BrandKey = "nufoodz";
type SortMode = "Newest Activity" | "Priority" | "Assigned Agent";
type TicketViewId =
  | "assigned-to-me"
  | "unassigned"
  | "all"
  | "courier-queries"
  | "my-closed"
  | "closed"
  | "my-open"
  | "all-unassigned"
  | "sent-tracking"
  | "tickets"
  | "chats";

type WorkspacePanelItem = {
  copy: string;
  id: WorkspacePanelId;
  label: string;
};

type AttachmentPreview = {
  alt: string;
  src: string;
};

type TicketViewPreset = {
  id: TicketViewId;
  label: string;
};

const defaultAssignableAgents = ["Agent Michael", "Agent Sarah", "Agent John", "Agent Anika"];
const defaultViewPresets: TicketViewPreset[] = [
  { id: "assigned-to-me", label: "Assigned to me" },
  { id: "unassigned", label: "Unassigned" },
  { id: "all", label: "All" }
];
const sharedViewPresets: TicketViewPreset[] = [
  { id: "courier-queries", label: "Courier Queries" },
  { id: "my-closed", label: "My Closed" },
  { id: "closed", label: "Closed" },
  { id: "my-open", label: "My Open" },
  { id: "all-unassigned", label: "All Unassigned" },
  { id: "sent-tracking", label: "Sent tracking" },
  { id: "tickets", label: "Tickets" },
  { id: "chats", label: "Chats" }
];
const workspacePanelItems: WorkspacePanelItem[] = [
  {
    id: "ai-agent",
    label: "AI Agent",
    copy: "Upload PDF, add URL, write answers, and test what the AI will say."
  },
  {
    id: "inbox",
    label: "Inbox",
    copy: "Queue, thread, and customer context in one place."
  },
  {
    id: "analytics",
    label: "Analytics",
    copy: "Routing coverage, volume, and queue pressure."
  },
  {
    id: "rules",
    label: "Safety Rules",
    copy: "If this happens, do this. Simple AI safety rules."
  },
  {
    id: "articles",
    label: "Articles",
    copy: "Support articles used across the widget and inbox."
  },
  {
    id: "knowledge-base",
    label: "Add Answers",
    copy: "Add team-only rules, customer answers, files, and links."
  },
  {
    id: "business-hours",
    label: "Open Hours",
    copy: "Choose what happens in work hours and after hours."
  },
  {
    id: "support-actions",
    label: "Make AI Safe",
    copy: "Rules, saved replies, and hours for safe AI behavior."
  },
  {
    id: "products",
    label: "Add Product Info",
    copy: "Website pages, links, and files for product questions."
  },
  {
    id: "shopping-assistant",
    label: "Turn On Chat",
    copy: "Test the AI, then turn on the live customer chat."
  },
  {
    id: "chat-widget",
    label: "Chat Box",
    copy: "Chat look, size, and install code."
  },
  {
    id: "ticket-dashboard",
    label: "Dashboard",
    copy: "High-volume queue table and live inspector."
  },
  {
    id: "macros",
    label: "Saved Replies",
    copy: "Ready-made replies your team can reuse."
  },
  {
    id: "manage-tags",
    label: "Manage Tags",
    copy: "Edit labels used by routing and organization."
  },
  {
    id: "users",
    label: "Users",
    copy: "Owner, admin, and agent access with role management."
  }
];

const workspacePanelIds = new Set<WorkspacePanelId>(workspacePanelItems.map((item) => item.id));
const hiddenWorkspaceSidebarPanels = new Set<WorkspacePanelId>([
  "ai-agent",
  "chat-widget",
  "knowledge-base",
  "products",
  "rules",
  "shopping-assistant",
  "support-actions"
]);
const teachAiPanelIds = new Set<WorkspacePanelId>([
  "ai-agent",
  "chat-widget",
  "knowledge-base",
  "products",
  "rules",
  "shopping-assistant",
  "support-actions"
]);
const simplifiedTeachAiPanelIds = new Set<WorkspacePanelId>([
  "ai-agent",
  "knowledge-base",
  "products",
  "rules",
  "shopping-assistant",
  "support-actions"
]);

const BRANDS: Record<
  BrandKey,
  {
    apiBaseUrl: string;
    label: string;
  }
> = {
  nufoodz: {
    apiBaseUrl: "http://10.10.1.23:9092",
    label: "Acrobuild"
  }
};

const hiddenTagKeys = new Set([
  "after-hours",
  "business-hours",
  "during-business-hours",
  "outside-business-hours"
]);

function getWorkspacePanelId(
  value: string | null,
  fallbackPanelId: WorkspacePanelId = "inbox"
): WorkspacePanelId {
  if (value && workspacePanelIds.has(value as WorkspacePanelId)) {
    return value as WorkspacePanelId;
  }

  return fallbackPanelId;
}

function normalizeKey(value: string) {
  return value.trim().toLowerCase().replace(/_/g, "-").replace(/\s+/g, "-");
}

function formatDisplayText(value: unknown, fallback: string) {
  const cleanedValue = String(value ?? "").trim();
  return cleanedValue || fallback;
}

function getBrandKeyFromTicket(ticket: Ticket | null): BrandKey {
  const normalizedBrand = normalizeKey(String(ticket?.brand_tag || ""));

  if (normalizedBrand === "nufoodz" || normalizedBrand === "nu-foodz" || normalizedBrand === "acrobuild" || normalizedBrand === "acro-build") {
    return "nufoodz";
  }

  return "nufoodz";
}

function getActiveTicketCount(tickets: Ticket[]) {
  return tickets.filter((ticket) => !["Resolved", "Closed"].includes(ticket.status)).length;
}

function getUnreadTicketCount(tickets: Ticket[]) {
  return tickets.reduce((sum, ticket) => sum + Number(ticket.unread_count || 0), 0);
}

function getTicketSortValue(ticket: Ticket) {
  const timestamp = Date.parse(ticket.updated_at || ticket.created_at || "");
  return Number.isNaN(timestamp) ? 0 : timestamp;
}

function sortTickets(tickets: Ticket[], sortBy: SortMode) {
  if (sortBy === "Priority") {
    const priorityOrder: Record<string, number> = {
      High: 0,
      Medium: 1,
      Low: 2
    };

    return [...tickets].sort(
      (left, right) =>
        (priorityOrder[left.priority] ?? 3) - (priorityOrder[right.priority] ?? 3) ||
        getTicketSortValue(right) - getTicketSortValue(left)
    );
  }

  if (sortBy === "Assigned Agent") {
    return [...tickets].sort(
      (left, right) =>
        left.assigned_agent.localeCompare(right.assigned_agent) ||
        getTicketSortValue(right) - getTicketSortValue(left)
    );
  }

  return [...tickets].sort((left, right) => getTicketSortValue(right) - getTicketSortValue(left));
}

function getVisibleTags(tags: TicketTag[]) {
  return tags.filter((tag) => {
    const key = normalizeKey(tag.slug || tag.name);
    return !hiddenTagKeys.has(key);
  });
}

function getCustomerFirstName(email: string) {
  const localPart = email.split("@")[0] ?? "Customer";
  const normalized = localPart.replace(/[._-]+/g, " ").trim();
  const first = normalized.split(" ")[0] ?? "Customer";

  return first.charAt(0).toUpperCase() + first.slice(1);
}

function getCustomerSearchLabel(email: string) {
  const localPart = email.split("@")[0] ?? "Customer";
  const normalized = localPart.replace(/[._-]+/g, " ").trim();

  if (!normalized) {
    return "Customer";
  }

  return normalized
    .split(/\s+/)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function getAgentFirstName(agentName: string) {
  const normalized = agentName.replace(/^Agent\s+/i, "").trim();
  const first = normalized.split(" ")[0] ?? "Support";

  return first.charAt(0).toUpperCase() + first.slice(1);
}

function getInitials(value: string, fallback: string) {
  const cleaned = value
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");

  return cleaned || fallback;
}

function buildMacroVariables(ticket: Ticket) {
  return {
    agent_first_name: getAgentFirstName(ticket.assigned_agent),
    assigned_agent: formatDisplayText(ticket.assigned_agent, "Support"),
    brand_tag: formatDisplayText(ticket.brand_tag, "Acrobuild"),
    customer_email: formatDisplayText(ticket.customer_email, ""),
    customer_first_name: getCustomerFirstName(ticket.customer_email),
    intent_tag: formatDisplayText(ticket.intent_tag, "General Inquiry"),
    queue_name: formatDisplayText(ticket.queue_name, "General Queue"),
    status: formatDisplayText(ticket.status, "Open"),
    ticket_id: formatDisplayText(ticket.ticket_id, ""),
    user_name: getCustomerFirstName(ticket.customer_email)
  };
}

function renderMacroTemplate(template: string, variables: Record<string, string>) {
  return template.replace(/\{\{\s*([^}]+?)\s*\}\}/g, (_, variableName: string) => {
    const key = variableName.trim().toLowerCase();
    return variables[key] ?? "";
  });
}

function buildOrderedMacros(recommendedMacros: Macro[], allMacros: Macro[]) {
  const orderedMacros: Macro[] = [];
  const seenMacroIds = new Set<number>();

  for (const macro of [...recommendedMacros, ...allMacros]) {
    const macroId = Number(macro.id);

    if (seenMacroIds.has(macroId)) {
      continue;
    }

    seenMacroIds.add(macroId);
    orderedMacros.push(macro);
  }

  return orderedMacros;
}

function getOrderItems(order: Order): OrderItem[] {
  return order.items ?? order.line_items ?? order.order_items ?? order.products ?? [];
}

function getOrderItemImageUrl(item: OrderItem) {
  return (
    item.image?.toString() ??
    item.image_url?.toString() ??
    item.thumbnail?.toString() ??
    item.product_image?.toString() ??
    item.featured_image?.toString() ??
    undefined
  );
}

function getMessageAttachmentImageUrl(attachment: {
  absolute_path?: string;
  mime_type?: string;
  path?: string;
  url?: string;
}) {
  const url = attachment.url ?? attachment.path ?? attachment.absolute_path;

  if (!url) {
    return undefined;
  }

  return attachment.mime_type?.startsWith("image/") ? url : undefined;
}

function formatOrderValue(value: unknown, fallback: string) {
  if (value == null || typeof value === "object") {
    return fallback;
  }

  return String(value);
}

function formatTicketButtonTitle(ticket: Ticket) {
  return `${formatDisplayText(ticket.issue_type, "General")} ${ticket.ticket_id}`;
}

function formatTicketButtonMeta(ticket: Ticket) {
  const unreadCount = Number(ticket.unread_count || 0);
  return unreadCount > 0 ? `${ticket.status} â€¢ ${unreadCount} unread` : ticket.status;
}

function getQuickActionState(status: string) {
  const normalizedStatus = status.trim().toLowerCase();

  if (normalizedStatus === "in progress") {
    return {
      canMoveToInProgress: false,
      canReopen: false,
      canResolve: true
    };
  }

  if (normalizedStatus === "resolved" || normalizedStatus === "closed") {
    return {
      canMoveToInProgress: false,
      canReopen: true,
      canResolve: false
    };
  }

  return {
    canMoveToInProgress: true,
    canReopen: false,
    canResolve: false
  };
}

function buildAssignableAgents(tickets: Ticket[], currentAgent: string) {
  const uniqueAgents = new Set<string>();

  for (const agentName of [...defaultAssignableAgents, currentAgent, ...tickets.map((ticket) => ticket.assigned_agent)]) {
    const cleanedAgentName = agentName.trim();

    if (!cleanedAgentName) {
      continue;
    }

    uniqueAgents.add(cleanedAgentName);
  }

  return [...uniqueAgents].sort((left, right) => left.localeCompare(right));
}

function getViewerAssignmentLabel(role: "admin" | "owner" | "agent") {
  if (role === "owner") {
    return "Owner";
  }

  if (role === "agent") {
    return "Help Desk";
  }

  return "Inbox Admin";
}

function buildManagerTicketSearchBlob(ticket: Ticket) {
  const customerLabel = getCustomerSearchLabel(ticket.customer_email);

  return [
    ticket.ticket_id,
    ticket.customer_email,
    customerLabel,
    ticket.issue,
    ticket.issue_type,
    ticket.intent_tag,
    ticket.queue_name,
    ticket.brand_tag,
    ticket.assigned_agent,
    ticket.status
  ]
    .join(" ")
    .toLowerCase();
}

function buildManagerSearchSuggestions(tickets: Ticket[]) {
  const suggestions: TicketSearchSuggestion[] = [];
  const seen = new Set<string>();

  function addSuggestion(
    kind: TicketSearchSuggestion["kind"],
    value: string,
    primary: string,
    secondary: string,
    searchText: string
  ) {
    const cleanValue = value.trim();
    const cleanPrimary = primary.trim();

    if (!cleanValue || !cleanPrimary) {
      return;
    }

    const key = `${kind}:${cleanValue.toLowerCase()}`;

    if (seen.has(key)) {
      return;
    }

    seen.add(key);
    suggestions.push({
      id: key.replace(/[^a-z0-9:-]+/g, "-"),
      kind,
      primary: cleanPrimary,
      secondary: secondary.trim(),
      searchText: searchText.toLowerCase(),
      value: cleanValue
    });
  }

  for (const ticket of tickets) {
    const email = formatDisplayText(ticket.customer_email, "");
    const customerLabel = getCustomerSearchLabel(ticket.customer_email);
    const topic = formatDisplayText(ticket.issue, formatDisplayText(ticket.issue_type, "Support request"));
    const queueLabel = formatDisplayText(ticket.queue_name, "General Queue");
    const searchText = buildManagerTicketSearchBlob(ticket);

    addSuggestion("ticket", ticket.ticket_id, ticket.ticket_id, `${email} â€¢ ${topic}`, searchText);
    addSuggestion("customer", customerLabel, customerLabel, `${email} â€¢ ${ticket.ticket_id}`, searchText);
    addSuggestion("email", email, email, `${ticket.ticket_id} â€¢ ${queueLabel}`, searchText);
    addSuggestion("topic", topic, topic, `${ticket.ticket_id} â€¢ ${email}`, searchText);
  }

  return suggestions.slice(0, 200);
}

function getCustomerContextErrorMessage(error: unknown) {
  const fallbackMessage = "Customer data is temporarily unavailable. You can still work the ticket.";

  if (!(error instanceof Error)) {
    return fallbackMessage;
  }

  const normalizedMessage = error.message.toLowerCase();

  if (
    normalizedMessage.includes("timed out") ||
    normalizedMessage.includes("could not reach the api") ||
    normalizedMessage.includes("unable to load customer data")
  ) {
    return "Customer data is temporarily unavailable because the Acrobuild lookup timed out. You can still continue with the ticket.";
  }

  return fallbackMessage;
}

function matchesTicketView(ticket: Ticket, viewId: TicketViewId, viewerAssignmentLabel: string) {
  const normalizedAssignedAgent = ticket.assigned_agent.trim();
  const normalizedIssue = ticket.issue.toLowerCase();
  const normalizedIntent = ticket.intent_tag.toLowerCase();
  const normalizedQueue = ticket.queue_name.toLowerCase();
  const normalizedStatus = ticket.status.toLowerCase();
  const isClosed = normalizedStatus === "resolved" || normalizedStatus === "closed";
  const isOpen = !isClosed;
  const isTrackingTicket =
    normalizedIntent.includes("tracking") ||
    normalizedIssue.includes("tracking") ||
    normalizedIssue.includes("track") ||
    normalizedQueue.includes("delivery") ||
    normalizedQueue.includes("logistics");

  switch (viewId) {
    case "assigned-to-me":
      return normalizedAssignedAgent === viewerAssignmentLabel;
    case "unassigned":
    case "all-unassigned":
      return !normalizedAssignedAgent;
    case "all":
    case "tickets":
      return true;
    case "courier-queries":
      return ticket.issue_type === "Logistics" || normalizedQueue.includes("delivery") || normalizedQueue.includes("logistics");
    case "my-closed":
      return normalizedAssignedAgent === viewerAssignmentLabel && isClosed;
    case "closed":
      return isClosed;
    case "my-open":
      return normalizedAssignedAgent === viewerAssignmentLabel && isOpen;
    case "sent-tracking":
      return isTrackingTicket;
    case "chats":
      return isOpen && Number(ticket.unread_count || 0) > 0;
    default:
      return true;
  }
}

function readFileAsDataUrl(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();

    reader.onload = () => {
      resolve(String(reader.result || ""));
    };

    reader.onerror = () => {
      reject(new Error(`Unable to read ${file.name}.`));
    };

    reader.readAsDataURL(file);
  });
}

function getDefaultWorkspacePanel(role: "admin" | "owner" | "agent", pathname: string): WorkspacePanelId {
  if (role === "admin" && pathname.endsWith("/workspace")) {
    return "ai-agent";
  }

  return "inbox";
}

function SharedManagerInboxPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const { role } = useRole();
  const {
    ticketSearchQuery,
    setSearchSuggestions,
    setTicketSearchQuery,
    setVisibleTicketCount
  } = useSearch();
  const [searchParams] = useSearchParams();
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [detail, setDetail] = useState<TicketDetailResponse | null>(null);
  const [availableTags, setAvailableTags] = useState<TicketTag[]>([]);
  const [allMacros, setAllMacros] = useState<Macro[]>([]);
  const [recommendedMacros, setRecommendedMacros] = useState<Macro[]>([]);
  const [selectedTicketId, setSelectedTicketId] = useState("");
  const [sortBy, setSortBy] = useState<SortMode>("Newest Activity");
  const [activeTicketView, setActiveTicketView] = useState<TicketViewId>("tickets");
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [selectedMacroId, setSelectedMacroId] = useState(0);
  const [appliedMacroId, setAppliedMacroId] = useState<number | null>(null);
  const [reply, setReply] = useState("");
  const [replyFiles, setReplyFiles] = useState<File[]>([]);
  const [replyUploadVersion, setReplyUploadVersion] = useState(0);
  const [noteDraft, setNoteDraft] = useState("");
  const [selectedBrandKey, setSelectedBrandKey] = useState<BrandKey>("nufoodz");
  const [selectedAssignee, setSelectedAssignee] = useState("");
  const [customerEmailQuery, setCustomerEmailQuery] = useState("");
  const [customerData, setCustomerData] = useState<CustomerLookupResponse | null>(null);
  const [tagSearch, setTagSearch] = useState("");
  const [selectedManualTagIds, setSelectedManualTagIds] = useState<number[]>([]);
  const [selectedOrderNumber, setSelectedOrderNumber] = useState("");
  const [isTagEditorOpen, setIsTagEditorOpen] = useState(false);
  const [attachmentPreview, setAttachmentPreview] = useState<AttachmentPreview | null>(null);
  const [showInboxWorkspaceMenu, setShowInboxWorkspaceMenu] = useState(
    role === "admin" && location.pathname.endsWith("/workspace")
  );
  const [isBootstrapping, setIsBootstrapping] = useState(true);
  const [isLoadingCustomerContext, setIsLoadingCustomerContext] = useState(false);
  const [isWorking, setIsWorking] = useState(false);
  const [customerContextError, setCustomerContextError] = useState("");
  const [error, setError] = useState("");
  const [newTicketNotification, setNewTicketNotification] = useState("");
  const [successMessage, setSuccessMessage] = useState("");
  const knownTicketIdsRef = useRef<Set<string>>(new Set());
  const notificationTimeoutRef = useRef<number | null>(null);
  const threadScrollRef = useRef<HTMLDivElement | null>(null);
  const replyTextareaRef = useRef<HTMLTextAreaElement | null>(null);
  const deferredTicketSearch = useDeferredValue(ticketSearchQuery);
  const deferredCustomerEmail = useDeferredValue(customerEmailQuery);
  const defaultWorkspacePanel = getDefaultWorkspacePanel(role, location.pathname);
  const activePanel = getWorkspacePanelId(searchParams.get("panel"), defaultWorkspacePanel);
  const isTeachAiActive = teachAiPanelIds.has(activePanel);
  const workspaceSurfacePanel = simplifiedTeachAiPanelIds.has(activePanel) ? "ai-agent" : activePanel;
  const isInboxPanel = activePanel === "inbox";
  const isCompactInboxSidebar = isInboxPanel && !showInboxWorkspaceMenu;
  const activeWorkspace =
    workspacePanelItems.find((item) => item.id === workspaceSurfacePanel) ??
    workspacePanelItems[0];
  const visibleWorkspacePanelItems = workspacePanelItems.filter(
    (item) => !hiddenWorkspaceSidebarPanels.has(item.id)
  );
  const viewerAssignmentLabel = getViewerAssignmentLabel(role);

  useEffect(() => {
    if (!isInboxPanel) {
      setShowInboxWorkspaceMenu(true);
      return;
    }

    setShowInboxWorkspaceMenu(false);
  }, [isInboxPanel, location.pathname, location.search]);

  useEffect(() => {
    if (!successMessage) {
      return;
    }

    const timeoutId = window.setTimeout(() => {
      setSuccessMessage("");
    }, 2500);

    return () => window.clearTimeout(timeoutId);
  }, [successMessage]);
  const selectedTicket =
    detail?.ticket ??
    tickets.find((ticket) => ticket.ticket_id === selectedTicketId) ??
    null;

  const sidebarCandidateTickets = useMemo(
    () =>
      sortTickets(
        tickets.filter((ticket) => !unreadOnly || Number(ticket.unread_count || 0) > 0),
        sortBy
      ),
    [sortBy, tickets, unreadOnly]
  );
  const candidateTickets = useMemo(
    () =>
      sidebarCandidateTickets.filter((ticket) =>
        matchesTicketView(ticket, activeTicketView, viewerAssignmentLabel)
      ),
    [activeTicketView, sidebarCandidateTickets, viewerAssignmentLabel]
  );
  const sidebarTickets = useMemo(
    () =>
      sidebarCandidateTickets.filter(
        (ticket) =>
          !deferredTicketSearch.trim() ||
          buildManagerTicketSearchBlob(ticket).includes(deferredTicketSearch.trim().toLowerCase())
      ),
    [sidebarCandidateTickets, deferredTicketSearch]
  );
  const visibleTickets = useMemo(
    () =>
      candidateTickets.filter(
        (ticket) =>
          !deferredTicketSearch.trim() ||
          buildManagerTicketSearchBlob(ticket).includes(deferredTicketSearch.trim().toLowerCase())
      ),
    [candidateTickets, deferredTicketSearch]
  );
  const ticketSearchSuggestions = useMemo(
    () => buildManagerSearchSuggestions(sidebarCandidateTickets),
    [sidebarCandidateTickets]
  );

  useEffect(() => {
    setVisibleTicketCount(sidebarTickets.length);
  }, [sidebarTickets.length, setVisibleTicketCount]);

  useEffect(() => {
    setSearchSuggestions(isInboxPanel ? ticketSearchSuggestions : []);

    return () => {
      setSearchSuggestions([]);
    };
  }, [isInboxPanel, setSearchSuggestions, ticketSearchSuggestions]);

  const visibleTicketTags = getVisibleTags(detail?.tags ?? []);
  const availableVisibleTags = getVisibleTags(availableTags);
  const orderedMacros = buildOrderedMacros(recommendedMacros, allMacros);
  const selectedMacro = orderedMacros.find((macro) => Number(macro.id) === Number(selectedMacroId)) ?? null;
  const manualTagIds = (detail?.tags ?? [])
    .filter((tag) => tag.source === "manual")
    .map((tag) => Number(tag.id));
  const ruleTagIds = new Set(
    (detail?.tags ?? [])
      .filter((tag) => tag.source === "rule")
      .map((tag) => Number(tag.id))
  );

  const customerProfile = customerData?.customer ?? {};
  const customerOrders =
    customerData?.orders ??
    customerData?.data?.orders ??
    [];
  const customerSubscriptions = (customerData?.subscriptions ?? []) as SubscriptionRecord[];
  const filteredAvailableTags = availableVisibleTags.filter((tag) =>
    tag.name.toLowerCase().includes(tagSearch.trim().toLowerCase())
  );
  const currentStatus = formatDisplayText(selectedTicket?.status, "Open");
  const quickActionState = getQuickActionState(currentStatus);
  const currentQueue = formatDisplayText(selectedTicket?.queue_name, "No team");
  const currentAgent = formatDisplayText(selectedTicket?.assigned_agent, "Unassigned");
  const assignableAgents = buildAssignableAgents(tickets, selectedTicket?.assigned_agent ?? "");
  const customerDisplayName = formatDisplayText(
    customerProfile.name,
    selectedTicket ? getCustomerFirstName(selectedTicket.customer_email) : "Customer"
  );
  const suggestedMacros = orderedMacros.slice(0, 4);
  const customerInitials = getInitials(customerDisplayName, "CU");
  const agentInitials = getInitials(currentAgent.replace(/^Agent\s+/i, ""), "HD");
  const activeTicketCount = getActiveTicketCount(tickets);
  const unreadTicketCount = getUnreadTicketCount(tickets);
  const threadMessageCount = detail?.messages.length ?? 0;
  const detailNoteCount = detail?.notes.length ?? 0;
  const threadAttachmentCount =
    detail?.messages.reduce((count, message) => count + (message.attachments?.length ?? 0), 0) ??
    0;
  const lastUpdatedLabel = selectedTicket ? formatTicketTimestamp(selectedTicket.updated_at) : "N/A";

  function setActivePanel(panelId: WorkspacePanelId) {
    setShowInboxWorkspaceMenu(panelId !== "inbox");
    navigate(getRolePanelPath(role, panelId), { replace: true });
  }

  function openTeachAiWorkspace() {
    setShowInboxWorkspaceMenu(true);
    navigate(getRolePanelPath(role, "ai-agent"), {
      replace: true
    });
  }

  function showNewTicketNotification(message: string) {
    setNewTicketNotification(message);

    if (notificationTimeoutRef.current) {
      window.clearTimeout(notificationTimeoutRef.current);
    }

    notificationTimeoutRef.current = window.setTimeout(() => {
      setNewTicketNotification("");
      notificationTimeoutRef.current = null;
    }, 5000);
  }

  function syncTickets(nextTickets: Ticket[], preferredTicketId?: string, shouldNotify = false) {
    const knownTicketIds = knownTicketIdsRef.current;
    const nextTicketIds = new Set(nextTickets.map((ticket) => ticket.ticket_id));
    const newTickets =
      shouldNotify && knownTicketIds.size
        ? nextTickets.filter((ticket) => !knownTicketIds.has(ticket.ticket_id))
        : [];

    setTickets(nextTickets);

    if (!nextTickets.length) {
      setSelectedTicketId("");
      setDetail(null);
      knownTicketIdsRef.current = nextTicketIds;
      return;
    }

    setSelectedTicketId((current) => {
      if (preferredTicketId && nextTicketIds.has(preferredTicketId)) {
        return preferredTicketId;
      }

      if (current && nextTicketIds.has(current)) {
        return current;
      }

      return nextTickets[0].ticket_id;
    });

    knownTicketIdsRef.current = nextTicketIds;

    if (newTickets.length === 1) {
      showNewTicketNotification(`New ticket received: ${newTickets[0].ticket_id}`);
      return;
    }

    if (newTickets.length > 1) {
      showNewTicketNotification(`${newTickets.length} new tickets received`);
    }
  }

  async function loadTickets(preferredTicketId?: string) {
    const response = await getAdminTickets();
    syncTickets(response.tickets, preferredTicketId, false);
  }

  async function loadSelectedTicketWorkspace(ticketId: string) {
    const [detailResponse, macroResponse] = await Promise.all([
      getAdminTicketDetail(ticketId),
      getAdminRecommendedMacros(ticketId)
    ]);

    setDetail(detailResponse);
    setRecommendedMacros(macroResponse.macros);

    const unreadCount = Number(detailResponse.ticket.unread_count || 0);

    if (unreadCount > 0) {
      try {
        const readResponse = await markAdminTicketRead(ticketId);
        setDetail((current) =>
          current
            ? {
                ...current,
                ticket: readResponse.ticket
              }
            : current
        );
        setTickets((current) =>
          current.map((ticket) =>
            ticket.ticket_id === ticketId
              ? {
                  ...ticket,
                  unread_count: 0
                }
              : ticket
          )
        );
      } catch (readError) {
        setError(readError instanceof Error ? readError.message : "Unable to mark the ticket as read.");
      }
    }
  }

  async function refreshInbox(preferredTicketId?: string) {
    await Promise.all([
      loadTickets(preferredTicketId),
      getAdminTags().then((response) => setAvailableTags(response.tags)),
      getAdminMacros().then((response) => setAllMacros(response.macros))
    ]);
  }

  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      try {
        setIsBootstrapping(true);
        setError("");
        setSuccessMessage("");
        const [ticketsResponse, tagsResponse, macrosResponse] = await Promise.all([
          getAdminTickets(),
          getAdminTags(),
          getAdminMacros()
        ]);

        if (cancelled) {
          return;
        }

        syncTickets(ticketsResponse.tickets, ticketsResponse.tickets[0]?.ticket_id, false);
        setAvailableTags(tagsResponse.tags);
        setAllMacros(macrosResponse.macros);
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : "Unable to load inbox.");
        }
      } finally {
        if (!cancelled) {
          setIsBootstrapping(false);
        }
      }
    }

    void bootstrap();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (isBootstrapping) {
      return;
    }

    let cancelled = false;

    async function pollForNewTickets() {
      if (document.visibilityState === "hidden") {
        return;
      }

      try {
        const response = await getAdminTickets();

        if (cancelled) {
          return;
        }

        syncTickets(response.tickets, undefined, true);
      } catch {
        // Keep background polling quiet; manual actions already surface errors.
      }
    }

    const intervalId = window.setInterval(() => {
      void pollForNewTickets();
    }, 5000);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [isBootstrapping]);

  useEffect(() => {
    let cancelled = false;

    async function hydrateSelectedTicket() {
      if (!isInboxPanel) {
        return;
      }

      if (!selectedTicketId) {
        setDetail(null);
        setRecommendedMacros([]);
        return;
      }

      try {
        setError("");
        const [detailResponse, macroResponse] = await Promise.all([
          getAdminTicketDetail(selectedTicketId),
          getAdminRecommendedMacros(selectedTicketId)
        ]);

        if (cancelled) {
          return;
        }

        setDetail(detailResponse);
        setRecommendedMacros(macroResponse.macros);

        const unreadCount = Number(detailResponse.ticket.unread_count || 0);

        if (unreadCount > 0) {
          try {
            const readResponse = await markAdminTicketRead(selectedTicketId);

            if (!cancelled) {
              setDetail((current) =>
                current
                  ? {
                      ...current,
                      ticket: readResponse.ticket
                    }
                  : current
              );
              setTickets((current) =>
                current.map((ticket) =>
                  ticket.ticket_id === selectedTicketId
                    ? {
                        ...ticket,
                        unread_count: 0
                      }
                    : ticket
                )
              );
            }
          } catch (readError) {
            if (!cancelled) {
              setError(readError instanceof Error ? readError.message : "Unable to mark the ticket as read.");
            }
          }
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : "Unable to load ticket detail.");
        }
      }
    }

    void hydrateSelectedTicket();

    return () => {
      cancelled = true;
    };
  }, [isInboxPanel, selectedTicketId]);

  useEffect(() => {
    setReply("");
    setReplyFiles([]);
    setReplyUploadVersion((current) => current + 1);
    setNoteDraft("");
    setTagSearch("");
    setAppliedMacroId(null);
    setIsTagEditorOpen(false);
    setAttachmentPreview(null);
    setSelectedOrderNumber("");

    if (selectedTicket) {
      setSelectedBrandKey(getBrandKeyFromTicket(selectedTicket));
      setSelectedAssignee(selectedTicket.assigned_agent || "");
      setCustomerEmailQuery(selectedTicket.customer_email || "");
      setCustomerContextError("");
    } else {
      setSelectedAssignee("");
      setCustomerEmailQuery("");
      setCustomerData(null);
      setCustomerContextError("");
    }
  }, [selectedTicket?.ticket_id]);

  useEffect(() => {
    setSelectedManualTagIds(manualTagIds);
  }, [selectedTicket?.ticket_id, detail?.tags]);

  useEffect(() => {
    if (!visibleTickets.length) {
      return;
    }

    if (!visibleTickets.some((ticket) => ticket.ticket_id === selectedTicketId)) {
      setSelectedTicketId(visibleTickets[0].ticket_id);
    }
  }, [selectedTicketId, visibleTickets.map((ticket) => ticket.ticket_id).join("|")]);

  useEffect(() => {
    const orderedMacroIds = orderedMacros.map((macro) => Number(macro.id));

    if (!orderedMacroIds.length) {
      setSelectedMacroId(0);
      return;
    }

    if (!orderedMacroIds.includes(Number(selectedMacroId))) {
      setSelectedMacroId(orderedMacroIds[0]);
    }
  }, [orderedMacros.length, orderedMacros.map((macro) => macro.id).join(","), selectedTicket?.ticket_id, selectedMacroId]);

  useEffect(() => {
    let cancelled = false;

    async function hydrateCustomerContext() {
      if (!isInboxPanel) {
        return;
      }

      const email = deferredCustomerEmail.trim();

      if (!email) {
        setCustomerData(null);
        setCustomerContextError("");
        return;
      }

      try {
        setIsLoadingCustomerContext(true);
        setCustomerContextError("");
        const brandConfig = BRANDS[selectedBrandKey];
        const customerResponse = await getAdminCustomerByEmail(
          email,
          brandConfig.apiBaseUrl
        );

        if (cancelled) {
          return;
        }

        let resolvedOrders = customerResponse.orders ?? customerResponse.data?.orders ?? [];

        if (!resolvedOrders.length) {
          const ordersResponse = await getOrdersByEmail(email, brandConfig.apiBaseUrl);

          if (cancelled) {
            return;
          }

          resolvedOrders = ordersResponse.orders ?? [];
        }

        setCustomerData({
          ...customerResponse,
          orders: resolvedOrders
        });
      } catch (customerError) {
        if (!cancelled) {
          setCustomerData(null);
          setCustomerContextError(getCustomerContextErrorMessage(customerError));
        }
      } finally {
        if (!cancelled) {
          setIsLoadingCustomerContext(false);
        }
      }
    }

    void hydrateCustomerContext();

    return () => {
      cancelled = true;
    };
  }, [deferredCustomerEmail, isInboxPanel, selectedBrandKey]);

  useEffect(() => {
    if (!isInboxPanel) {
      setShowInboxWorkspaceMenu(true);
    }
  }, [isInboxPanel]);

  useEffect(() => {
    if (!isInboxPanel || !detail?.messages.length || !threadScrollRef.current) {
      return;
    }

    const threadElement = threadScrollRef.current;
    const animationFrame = window.requestAnimationFrame(() => {
      threadElement.scrollTop = threadElement.scrollHeight;
    });

    return () => {
      window.cancelAnimationFrame(animationFrame);
    };
  }, [detail?.messages.length, isInboxPanel, selectedTicket?.ticket_id]);

  useEffect(() => {
    if (!attachmentPreview) {
      return;
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setAttachmentPreview(null);
      }
    }

    window.addEventListener("keydown", handleKeyDown);

    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [attachmentPreview]);

  useEffect(() => {
    return () => {
      if (notificationTimeoutRef.current) {
        window.clearTimeout(notificationTimeoutRef.current);
      }
    };
  }, []);

  function focusReplyComposer() {
    window.requestAnimationFrame(() => {
      replyTextareaRef.current?.focus();
      replyTextareaRef.current?.setSelectionRange(
        replyTextareaRef.current.value.length,
        replyTextareaRef.current.value.length
      );
    });
  }

  function clearAppliedMacro() {
    setAppliedMacroId(null);
    setSuccessMessage("");
    setError("");
    focusReplyComposer();
  }

  function handleReplyKeyDown(event: ReactKeyboardEvent<HTMLTextAreaElement>) {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter" && !isWorking) {
      event.preventDefault();

      if (reply.trim() || replyFiles.length) {
        void handleSendReply();
      }
    }
  }

  async function handleSendReply() {
    if (!selectedTicket) {
      return;
    }

    if (!reply.trim() && !replyFiles.length) {
      setError("Add a reply or at least one image before sending.");
      return;
    }

    try {
      setIsWorking(true);
      setError("");
      setSuccessMessage("");
      const attachments = await Promise.all(
        replyFiles.map(async (file) => ({
          content_base64: await readFileAsDataUrl(file),
          mime_type: file.type,
          name: file.name
        }))
      );

      await postAdminTicketReply(selectedTicket.ticket_id, {
        applied_macro_id: appliedMacroId,
        attachments,
        message: reply.trim()
      });

      setReply("");
      setReplyFiles([]);
      setReplyUploadVersion((current) => current + 1);
      setAppliedMacroId(null);
      setSuccessMessage("Reply sent.");

      await Promise.all([
        refreshInbox(selectedTicket.ticket_id),
        loadSelectedTicketWorkspace(selectedTicket.ticket_id)
      ]);
    } catch (replyError) {
      setError(replyError instanceof Error ? replyError.message : "Unable to send reply.");
    } finally {
      setIsWorking(false);
    }
  }

  async function handleStatusChange(status: string) {
    if (!selectedTicket) {
      return;
    }

    try {
      setIsWorking(true);
      setError("");
      setSuccessMessage("");
      await updateAdminTicketStatus(selectedTicket.ticket_id, status);
      setSuccessMessage(
        status === "Resolved"
          ? "Ticket marked as resolved."
          : status === "Open"
            ? "Ticket reopened."
            : "Ticket moved to In Progress."
      );
      await Promise.all([
        refreshInbox(selectedTicket.ticket_id),
        loadSelectedTicketWorkspace(selectedTicket.ticket_id)
      ]);
    } catch (statusError) {
      setError(statusError instanceof Error ? statusError.message : "Unable to update ticket status.");
    } finally {
      setIsWorking(false);
    }
  }

  async function handleCloseTicket() {
    if (!selectedTicket) {
      return;
    }

    try {
      setIsWorking(true);
      setError("");
      setSuccessMessage("");
      await closeAdminTicket(selectedTicket.ticket_id);
      setSuccessMessage("Ticket closed.");
      await Promise.all([
        refreshInbox(selectedTicket.ticket_id),
        loadSelectedTicketWorkspace(selectedTicket.ticket_id)
      ]);
    } catch (closeError) {
      setError(closeError instanceof Error ? closeError.message : "Unable to close ticket.");
    } finally {
      setIsWorking(false);
    }
  }

  async function handleAssigneeUpdate(agentName: string) {
    if (!selectedTicket) {
      return;
    }

    try {
      setIsWorking(true);
      setError("");
      setSuccessMessage("");
      await updateAdminTicketAssignee(selectedTicket.ticket_id, agentName.trim());
      setSuccessMessage(
        agentName.trim() ? `Ticket assigned to ${agentName.trim()}.` : "Ticket unassigned."
      );
      await Promise.all([
        refreshInbox(selectedTicket.ticket_id),
        loadSelectedTicketWorkspace(selectedTicket.ticket_id)
      ]);
    } catch (assigneeError) {
      setError(
        assigneeError instanceof Error ? assigneeError.message : "Unable to update the assignee."
      );
    } finally {
      setIsWorking(false);
    }
  }

  async function handleRefresh() {
    if (!selectedTicket) {
      return;
    }

    try {
      setIsWorking(true);
      setError("");
      setSuccessMessage("");
      await Promise.all([
        refreshInbox(selectedTicket.ticket_id),
        loadSelectedTicketWorkspace(selectedTicket.ticket_id)
      ]);
      setSuccessMessage("Inbox refreshed.");
    } catch (refreshError) {
      setError(refreshError instanceof Error ? refreshError.message : "Unable to refresh inbox.");
    } finally {
      setIsWorking(false);
    }
  }

  async function handleSaveTags() {
    if (!selectedTicket) {
      return;
    }

    try {
      setIsWorking(true);
      setError("");
      setSuccessMessage("");
      await updateAdminTicketTags(selectedTicket.ticket_id, selectedManualTagIds);
      await Promise.all([
        refreshInbox(selectedTicket.ticket_id),
        loadSelectedTicketWorkspace(selectedTicket.ticket_id)
      ]);
      setIsTagEditorOpen(false);
      setSuccessMessage("Tags updated.");
    } catch (tagError) {
      setError(tagError instanceof Error ? tagError.message : "Unable to update tags.");
    } finally {
      setIsWorking(false);
    }
  }

  async function handleSaveNote() {
    if (!selectedTicket || !noteDraft.trim()) {
      setError("Add a note before saving.");
      return;
    }

    try {
      setIsWorking(true);
      setError("");
      setSuccessMessage("");
      await createAdminTicketNote(selectedTicket.ticket_id, {
        author: formatDisplayText(selectedTicket.assigned_agent, "Inbox Admin"),
        note: noteDraft.trim()
      });
      setNoteDraft("");
      await loadSelectedTicketWorkspace(selectedTicket.ticket_id);
      setSuccessMessage("Internal note saved.");
    } catch (noteError) {
      setError(noteError instanceof Error ? noteError.message : "Unable to save note.");
    } finally {
      setIsWorking(false);
    }
  }

  function applyMacroTemplate(macro: Macro) {
    if (!selectedTicket) {
      return;
    }

    setReply(renderMacroTemplate(macro.response_text, buildMacroVariables(selectedTicket)));
    setSelectedMacroId(Number(macro.id));
    setAppliedMacroId(Number(macro.id));
    setSuccessMessage("");
    setError("");
    focusReplyComposer();
  }

  function renderWorkspaceSurface() {
    if (simplifiedTeachAiPanelIds.has(activePanel)) {
      return <AIAgentPage embedded />;
    }

    if (activePanel === "analytics") {
      return <AdminAnalyticsPage embedded />;
    }

    if (activePanel === "business-hours") {
      return <BusinessHoursPage embedded />;
    }

    if (activePanel === "articles") {
      return <ArticlesPage embedded />;
    }

    if (activePanel === "chat-widget") {
      return <ChatWidgetPage embedded />;
    }

    if (activePanel === "ticket-dashboard") {
      return <TicketDashboardPage embedded />;
    }

    if (activePanel === "macros") {
      return <MacrosPage embedded />;
    }

    if (activePanel === "manage-tags") {
      return <ManageTagsPage embedded />;
    }

    if (activePanel === "order-track") {
      return (
        <div className="support-workspace-placeholder support-workspace-placeholder-photo">
          <div className="support-workspace-placeholder-copy">
            <div className="support-workspace-placeholder-title">Order Track</div>
            <p>
              The order follow-up view is being folded into the inbox workspace next so
              agents can review delivery context without leaving this screen.
            </p>
            <div className="support-workspace-placeholder-note">
              A photo-led handoff view for delivery follow-ups, order updates, and calmer
              customer check-ins.
            </div>
          </div>

          <div className="support-workspace-placeholder-media">
            <img
              alt="Support advisor helping a homeowner with order and handover follow-up"
              src="/images/real-world/help-center-support.png"
            />
          </div>
        </div>
      );
    }

    if (activePanel === "users") {
      return <UsersPage embedded />;
    }

    return null;
  }

  return (
    <div className={`support-console-page${isInboxPanel ? " legacy-inbox" : ""}`}>
      <div className="support-console-toast-stack">
        {error ? <div className="banner-error support-console-banner">{error}</div> : null}
        {successMessage ? (
          <div className="banner-success support-console-banner">{successMessage}</div>
        ) : null}
      </div>

      <div
        className={`support-console-grid${isInboxPanel ? "" : " workspace-mode"}${
          isCompactInboxSidebar ? " inbox-sidebar-compact" : ""
        }`}
      >
        <aside className="support-console-sidebar">
          <div className="support-sidebar-panel">
            <div className="support-sidebar-top">
              <Link
                className="support-sidebar-home"
                onClick={() => setShowInboxWorkspaceMenu(false)}
                to={getRoleHomePath(role)}
              >
                {role.slice(0, 2).toUpperCase()}
              </Link>

              <div className="support-sidebar-heading">
                <div className="support-sidebar-title-row">
                  <div className="support-sidebar-title">
                    {isInboxPanel ? "Inbox" : activeWorkspace.label}
                  </div>
                  <span className="support-sidebar-title-count">
                    {isInboxPanel ? tickets.length : workspacePanelItems.length}
                  </span>
                </div>
                <div className="support-sidebar-copy">
                  {isInboxPanel
                    ? `${tickets.length} total / ${activeTicketCount} active / ${unreadTicketCount} unread`
                    : activeWorkspace.copy}
                </div>
              </div>
            </div>

            {isCompactInboxSidebar ? (
              <>
                <button
                  className="support-sidebar-back-button"
                  onClick={() => setShowInboxWorkspaceMenu(true)}
                  type="button"
                >
                  <span className="support-sidebar-back-arrow">&lt;</span>
                  Workspace
                </button>

                <div className="support-sidebar-controls support-sidebar-controls-elevated">
                  <div className="support-sidebar-filter-grid">
                    <input
                      className="field-input support-console-input"
                      onChange={(event) => setTicketSearchQuery(event.target.value)}
                      placeholder="Search tickets"
                      value={ticketSearchQuery}
                    />

                    <select
                      className="field-input support-console-input"
                      onChange={(event) => setSortBy(event.target.value as SortMode)}
                      value={sortBy}
                    >
                      <option value="Newest Activity">Newest Activity</option>
                      <option value="Priority">Priority</option>
                      <option value="Assigned Agent">Assigned Agent</option>
                    </select>

                    <label className="support-check-card">
                      <input
                        checked={unreadOnly}
                        onChange={(event) => setUnreadOnly(event.target.checked)}
                        type="checkbox"
                      />
                      <span>Unread only</span>
                      <small>Only surface tickets waiting on a fresh reply.</small>
                    </label>
                  </div>
                </div>

                <div className="support-sidebar-section">
                  <div className="support-sidebar-section-label">Default views</div>
                  <div className="support-view-list">
                    {defaultViewPresets.map((view) => {
                      const count = tickets.filter((ticket) =>
                        matchesTicketView(ticket, view.id, viewerAssignmentLabel)
                      ).length;

                      return (
                        <button
                          className={`support-view-row${activeTicketView === view.id ? " active" : ""}`}
                          key={view.id}
                          onClick={() => setActiveTicketView(view.id)}
                          type="button"
                        >
                          <span>{view.label}</span>
                          <span>{count}</span>
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div className="support-sidebar-section">
                  <div className="support-sidebar-section-label">Shared views</div>
                  <div className="support-view-list">
                    {sharedViewPresets.map((view) => {
                      const count = tickets.filter((ticket) =>
                        matchesTicketView(ticket, view.id, viewerAssignmentLabel)
                      ).length;

                      return (
                        <button
                          className={`support-view-row${activeTicketView === view.id ? " active" : ""}`}
                          key={view.id}
                          onClick={() => setActiveTicketView(view.id)}
                          type="button"
                        >
                          <span>{view.label}</span>
                          <span>{count}</span>
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div className="support-ticket-list compact simple">
                  {isBootstrapping ? (
                    <PhotoEmptyState
                      className="support-empty-state sidebar"
                      description="We are syncing the latest ticket list, unread counts, and queue status for this inbox."
                      eyebrow="Inbox queue"
                      highlights={["Queue sync", "Unread counts"]}
                      title="Loading tickets"
                      variant="compact"
                    />
                  ) : null}
                  {!isBootstrapping && !sidebarTickets.length ? (
                    <PhotoEmptyState
                      className="support-empty-state sidebar"
                      description="Try another workspace view or search term to bring matching tickets back into the list."
                      eyebrow="Inbox filter"
                      highlights={["Change filter", "Broaden search"]}
                      title="No tickets match this inbox view"
                      variant="compact"
                    />
                  ) : null}

                  {sidebarTickets.map((ticket) => (
                    <button
                      className={`support-ticket-item simple${
                        ticket.ticket_id === selectedTicketId ? " active" : ""
                      }${Number(ticket.unread_count || 0) > 0 ? " unread" : ""}`}
                      key={ticket.ticket_id}
                      onClick={() =>
                        startTransition(() => {
                          if (!matchesTicketView(ticket, activeTicketView, viewerAssignmentLabel)) {
                            setActiveTicketView("tickets");
                          }

                          setSelectedTicketId(ticket.ticket_id);
                        })
                      }
                      type="button"
                    >
                      <div className="support-ticket-item-row">
                        <div className="support-ticket-item-copy">
                          <span className="support-ticket-kicker">Ticket ID</span>
                          <div className="support-ticket-subject support-ticket-id">
                            {formatDisplayText(ticket.ticket_id, "No ticket ID")}
                          </div>
                        </div>
                        {Number(ticket.unread_count || 0) > 0 ? (
                          <span className="support-ticket-counter">{ticket.unread_count}</span>
                        ) : null}
                      </div>

                      <div className="support-ticket-status-row">
                        <span
                          className="support-ticket-dot"
                          style={{ backgroundColor: getStatusColor(ticket.status) }}
                        />
                        <span>{formatTicketButtonMeta(ticket)}</span>
                      </div>
                    </button>
                  ))}
                </div>
              </>
            ) : (
              <>
                <div className="support-sidebar-section">
                  <div className="support-sidebar-section-label">Workspace</div>
                  <div className="support-nav-list">
                    <div className={`support-nav-group${isTeachAiActive ? " active" : ""}`}>
                      <button
                        className="support-nav-group-button"
                        onClick={openTeachAiWorkspace}
                        type="button"
                      >
                        <div className="support-nav-item-body">
                          <span className="support-nav-item-title">Teach AI</span>
                          <span className="support-nav-item-copy">
                            Upload PDF, add URL, type an answer, then test it.
                          </span>
                        </div>
                        <span className="support-nav-item-count">1 page</span>
                      </button>
                    </div>

                    {visibleWorkspacePanelItems.map((item) => (
                      <button
                        className={`support-nav-item${item.id === activePanel ? " active" : ""}`}
                        key={item.id}
                        onClick={() => setActivePanel(item.id)}
                        type="button"
                      >
                        <div className="support-nav-item-body">
                          <span className="support-nav-item-title">{item.label}</span>
                        </div>
                        {item.id === "inbox" ? (
                          <span className="support-nav-item-count">{tickets.length}</span>
                        ) : null}
                      </button>
                    ))}
                  </div>
                </div>

                {!isInboxPanel ? (
                  <div className="support-sidebar-section">
                    <div className="support-sidebar-section-label">Current tool</div>
                    <div className="support-sidebar-note">
                      <strong>{activeWorkspace.label}</strong>
                      <span>{activeWorkspace.copy}</span>
                    </div>
                  </div>
                ) : null}
              </>
            )}

          </div>
        </aside>

        {isInboxPanel ? (
          <>
        <section className="support-console-main">
          {!visibleTickets.length ? (
            <PhotoEmptyState
              className="support-empty-state support-empty-panel support-empty-panel-main"
              description="This filtered inbox is clear right now, so there is no active conversation to open in the workspace."
              eyebrow="Conversation workspace"
              highlights={["Try another shared view", "Clear the search", "Watch for new replies"]}
              title="No tickets in this inbox view"
              variant="compact"
            />
          ) : !selectedTicket || !detail ? (
            <PhotoEmptyState
              className="support-empty-state support-empty-panel support-empty-panel-main"
              description="Select any ticket from the left column to open the thread, suggested macros, and reply composer."
              eyebrow="Conversation workspace"
              highlights={["Thread history", "Suggested macros", "Reply composer"]}
              title="Choose a ticket"
              variant="compact"
            />
          ) : (
            <>
              <header className="support-main-header">
                <div className="support-main-header-copy">
                  <div className="support-main-breadcrumb">
                    <span>{currentStatus}</span>
                    <span>/</span>
                    <span>{customerDisplayName}</span>
                    <span>/</span>
                    <span>{formatDisplayText(selectedTicket.intent_tag, "Support Request")}</span>
                  </div>
                  <h1 className="support-main-title">{formatTicketButtonTitle(selectedTicket)}</h1>
                </div>

                <div className="support-main-header-actions">
                  <span className="support-toolbar-pill">
                    <span
                      className="support-toolbar-pill-dot"
                      style={{ backgroundColor: getStatusColor(currentStatus) }}
                    />
                    {currentStatus}
                  </span>
                  <span className="support-toolbar-chip">{currentAgent}</span>
                  <span className="support-toolbar-chip">{currentQueue}</span>
                  <button
                    className="support-toolbar-button"
                    disabled={isWorking}
                    onClick={() => void handleRefresh()}
                    type="button"
                  >
                    Refresh
                  </button>
                </div>
              </header>

              {newTicketNotification ? (
                <div className="support-conversation-notice" role="status">
                  <span className="support-conversation-notice-dot" />
                  <span>{newTicketNotification}</span>
                </div>
              ) : null}

              <div className="support-thread-shell">
                <div className="support-thread-scroll" ref={threadScrollRef}>
                  <div className="support-thread-summary">
                    <div className="support-thread-summary-main">
                      <div className="support-avatar support-avatar-customer">{customerInitials}</div>
                      <div>
                        <div className="support-thread-summary-name">{customerDisplayName}</div>
                        <div className="support-thread-summary-copy">
                          {formatDisplayText(selectedTicket.customer_email, "No customer email")}
                        </div>
                      </div>
                    </div>
                    <div className="support-thread-summary-side">
                      <div className="support-thread-summary-copy">Updated {lastUpdatedLabel}</div>
                      <div className="support-thread-summary-stat">
                        <span>Messages</span>
                        <strong>{threadMessageCount}</strong>
                      </div>
                      <div className="support-thread-summary-stat">
                        <span>Notes</span>
                        <strong>{detailNoteCount}</strong>
                      </div>
                      <div className="support-thread-summary-stat">
                        <span>Files</span>
                        <strong>{threadAttachmentCount}</strong>
                      </div>
                    </div>
                  </div>

                  <div className="support-thread-messages">
                    {detail.messages.map((message) => {
                      const isCustomer = message.sender.toLowerCase() === "customer";

                      return (
                        <article
                          className={`support-thread-message${isCustomer ? " customer" : " agent"}`}
                          key={message.id}
                        >
                          <div
                            className={`support-avatar${isCustomer ? " support-avatar-customer" : " support-avatar-agent"}`}
                          >
                            {isCustomer ? customerInitials : agentInitials}
                          </div>

                          <div className="support-thread-bubble">
                            <div className="support-thread-message-meta">
                              <span className="support-thread-message-author">
                                {isCustomer ? customerDisplayName : "Help Desk"}
                              </span>
                              <span>{formatTicketTimestamp(message.created_at)}</span>
                            </div>
                            <div className="support-thread-message-text">
                              {message.message || "Attachment-only message"}
                            </div>

                            {message.attachments?.length ? (
                              <div
                                className={`support-thread-attachments${
                                  message.attachments.length === 1 ? " single" : ""
                                }`}
                              >
                                {message.attachments.map((attachment, index) => {
                                  const imageUrl = getMessageAttachmentImageUrl(attachment);

                                  if (!imageUrl) {
                                    return null;
                                  }

                                  return (
                                    <button
                                      className="support-thread-attachment"
                                      key={`${message.id}-${index}`}
                                      onClick={() =>
                                        setAttachmentPreview({
                                          alt: attachment.name ?? `attachment-${index}`,
                                          src: imageUrl
                                        })
                                      }
                                      type="button"
                                    >
                                      <img
                                        alt={attachment.name ?? `attachment-${index}`}
                                        className="support-thread-attachment-image"
                                        src={imageUrl}
                                      />
                                      <div className="support-thread-attachment-name">
                                        {attachment.name ?? `Image ${index + 1}`}
                                      </div>
                                    </button>
                                  );
                                })}
                              </div>
                            ) : null}
                          </div>
                        </article>
                      );
                    })}
                  </div>
                  <div className="support-reply-shell inside-thread">
                    <div className="support-reply-head">
                      <div className="support-reply-address">
                        <span className="support-reply-label">To</span>
                        <span>{formatDisplayText(selectedTicket.customer_email, "No customer email")}</span>
                      </div>
                      <div className="support-reply-copy">
                        Use a macro, adjust the draft, and keep the reply thread moving.
                      </div>
                    </div>

                    {suggestedMacros.length ? (
                      <div className="support-suggested-macros">
                        <span className="support-suggested-label">Suggested macros</span>
                        <div className="support-suggested-list">
                          {suggestedMacros.map((macro) => (
                            <button
                              className={`support-suggested-macro${
                                Number(macro.id) === Number(appliedMacroId) ? " active" : ""
                              }`}
                              key={macro.id}
                              onClick={() => applyMacroTemplate(macro)}
                              type="button"
                            >
                              {macro.name}
                            </button>
                          ))}
                        </div>
                      </div>
                    ) : null}

                    <div className="support-reply-toolbar">
                      <select
                        className="field-input support-console-input"
                        onChange={(event) => setSelectedMacroId(Number(event.target.value))}
                        value={selectedMacroId || ""}
                      >
                        {!orderedMacros.length ? (
                          <option value="">No macros available</option>
                        ) : null}
                        {orderedMacros.map((macro) => (
                          <option key={macro.id} value={macro.id}>
                            {macro.name}
                          </option>
                        ))}
                      </select>

                      <button
                        className="support-secondary-button"
                        disabled={!selectedMacro || !selectedTicket}
                        onClick={() => {
                          if (!selectedMacro) {
                            return;
                          }

                          applyMacroTemplate(selectedMacro);
                        }}
                        type="button"
                      >
                        Apply macro
                      </button>

                      {appliedMacroId ? (
                        <button
                          className="support-secondary-button"
                          onClick={clearAppliedMacro}
                          type="button"
                        >
                          Clear macro
                        </button>
                      ) : null}
                    </div>

                    <textarea
                      ref={replyTextareaRef}
                      className="field-textarea support-console-textarea support-reply-textarea"
                      onChange={(event) => setReply(event.target.value)}
                      onKeyDown={handleReplyKeyDown}
                      placeholder="Click here to reply, or send images with a short note."
                      rows={8}
                      value={reply}
                    />

                    <div className="support-reply-footer">
                      <label
                        className="support-upload-pill"
                        htmlFor={`reply-files-${selectedTicket.ticket_id}-${replyUploadVersion}`}
                      >
                        <span>Add attachments</span>
                        <small>
                          {replyFiles.length
                            ? `${replyFiles.length} file${replyFiles.length === 1 ? "" : "s"} ready`
                            : "PNG, JPG, JPEG, WEBP, GIF"}
                        </small>
                        <input
                          accept=".png,.jpg,.jpeg,.webp,.gif"
                          id={`reply-files-${selectedTicket.ticket_id}-${replyUploadVersion}`}
                          multiple
                          onChange={(event) => setReplyFiles(Array.from(event.target.files ?? []))}
                          type="file"
                        />
                      </label>

                      <div className="support-reply-actions">
                        <div className="support-reply-shortcut">Press Ctrl/Cmd + Enter to send</div>
                        <button
                          className="support-primary-button"
                          disabled={isWorking || (!reply.trim() && !replyFiles.length)}
                          onClick={() => void handleSendReply()}
                          type="button"
                        >
                          Send reply
                        </button>
                        <button
                          className="support-secondary-button"
                          disabled={isWorking}
                          onClick={() => void handleCloseTicket()}
                          type="button"
                        >
                          Close ticket
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </>
          )}
        </section>

        <aside className="support-console-details">
          {!visibleTickets.length ? (
            <PhotoEmptyState
              className="support-empty-state support-empty-panel support-empty-panel-detail"
              description="When a ticket matches this filter, the inspector will show tags, ownership, and customer context here."
              eyebrow="Ticket inspector"
              highlights={["Tags", "Ownership", "Customer context"]}
              title="No inspector for this view"
              variant="compact"
            />
          ) : !selectedTicket || !detail ? (
            <PhotoEmptyState
              className="support-empty-state support-empty-panel support-empty-panel-detail"
              description="Pick a conversation and the customer profile, tags, and workflow actions will appear in this rail."
              eyebrow="Ticket inspector"
              highlights={["Profile", "Workflow actions", "Ticket snapshot"]}
              title="Ticket details will load here"
              variant="compact"
            />
          ) : (
            <div className="support-details-scroll">
              <div className="support-details-header">
                <div className="support-details-header-copy">
                  <div className="support-details-kicker">Ticket details</div>
                  <h2 className="support-details-title">{customerDisplayName}</h2>
                  <div className="support-details-subtitle">{selectedTicket.ticket_id}</div>
                </div>

                <button
                  className="support-secondary-button support-secondary-button-small support-details-header-button"
                  onClick={() => setIsTagEditorOpen((current) => !current)}
                  type="button"
                >
                  Edit tags
                </button>
              </div>

              {isTagEditorOpen ? (
                <div className="support-details-card">
                  <div className="support-card-head">
                    <div className="support-card-title">Manage tags</div>
                    <div className="support-card-copy">
                      Keep automation tags and manual routing labels aligned.
                    </div>
                  </div>

                  {visibleTicketTags.length ? (
                    <div className="support-badge-cluster">
                      {visibleTicketTags.map((tag) => (
                        <span className="support-tag-chip" key={tag.id}>
                          <span
                            className="support-tag-chip-dot"
                            style={{ backgroundColor: tag.color || "#38bdf8" }}
                          />
                          {tag.name}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <div className="support-empty-inline">No tags assigned yet.</div>
                  )}

                  <input
                    className="field-input support-console-input"
                    onChange={(event) => setTagSearch(event.target.value)}
                    placeholder="Search tags by name..."
                    value={tagSearch}
                  />

                  <div className="support-tag-checklist">
                    {filteredAvailableTags.length ? (
                      filteredAvailableTags.map((tag) => {
                        const tagId = Number(tag.id);
                        const isRuleTag = ruleTagIds.has(tagId);
                        const isChecked = isRuleTag || selectedManualTagIds.includes(tagId);

                        return (
                          <label className="support-tag-check-row" key={tag.id}>
                            <input
                              checked={isChecked}
                              disabled={isRuleTag}
                              onChange={(event) => {
                                if (isRuleTag) {
                                  return;
                                }

                                setSelectedManualTagIds((current) =>
                                  event.target.checked
                                    ? [...current, tagId]
                                    : current.filter((value) => value !== tagId)
                                );
                              }}
                              type="checkbox"
                            />
                            <span className="support-tag-chip">
                              <span
                                className="support-tag-chip-dot"
                                style={{ backgroundColor: tag.color || "#38bdf8" }}
                              />
                              {tag.name}
                            </span>
                            {isRuleTag ? (
                              <small className="support-rule-tag-note">Applied automatically</small>
                            ) : null}
                          </label>
                        );
                      })
                    ) : (
                      <div className="support-empty-inline">No tags matched the search.</div>
                    )}
                  </div>

                  <button
                    className="support-primary-button support-primary-button-block"
                    disabled={isWorking}
                    onClick={() => void handleSaveTags()}
                    type="button"
                  >
                    Save tags
                  </button>
                </div>
              ) : null}

              <div className="support-details-card support-details-card-actions">
                <div className="support-card-head">
                  <div className="support-card-title">Quick actions</div>
                  <div className="support-card-copy">Move the ticket forward without opening more menus.</div>
                </div>
                <div className="support-status-actions">
                  <button
                    className="support-status-action amber"
                    disabled={isWorking || !quickActionState.canMoveToInProgress}
                    onClick={() => void handleStatusChange("In Progress")}
                    type="button"
                  >
                    In Progress
                  </button>
                  <button
                    className="support-status-action green"
                    disabled={isWorking || !quickActionState.canResolve}
                    onClick={() => void handleStatusChange("Resolved")}
                    type="button"
                  >
                    Resolve
                  </button>
                  <button
                    className="support-status-action blue"
                    disabled={isWorking || !quickActionState.canReopen}
                    onClick={() => void handleStatusChange("Open")}
                    type="button"
                  >
                    Reopen
                  </button>
                </div>
              </div>

              <div className="support-details-card">
                <div className="support-card-head">
                  <div className="support-card-title">Assignment</div>
                  <div className="support-card-copy">
                    Admin and owner can assign this ticket to an agent or clear the assignee.
                  </div>
                </div>

                <label className="support-field-block">
                  <span>Assign to agent</span>
                  <select
                    className="field-input support-console-input"
                    onChange={(event) => setSelectedAssignee(event.target.value)}
                    value={selectedAssignee}
                  >
                    <option value="">Unassigned</option>
                    {assignableAgents.map((agentName) => (
                      <option key={agentName} value={agentName}>
                        {agentName}
                      </option>
                    ))}
                  </select>
                </label>

                <div className="support-assignment-actions">
                  <button
                    className="support-primary-button"
                    disabled={isWorking || selectedAssignee === (selectedTicket.assigned_agent || "")}
                    onClick={() => void handleAssigneeUpdate(selectedAssignee)}
                    type="button"
                  >
                    {selectedAssignee ? "Assign ticket" : "Update assignee"}
                  </button>
                  <button
                    className="support-secondary-button"
                    disabled={isWorking || !selectedTicket.assigned_agent}
                    onClick={() => {
                      setSelectedAssignee("");
                      void handleAssigneeUpdate("");
                    }}
                    type="button"
                  >
                    Unassign
                  </button>
                </div>
              </div>

              <div className="support-details-card">
                <div className="support-card-title">Ticket snapshot</div>
                <dl className="support-detail-list">
                  <div><dt>Ticket ID</dt><dd>{selectedTicket.ticket_id}</dd></div>
                  <div><dt>Type</dt><dd>{formatDisplayText(selectedTicket.issue_type, "General")}</dd></div>
                  <div><dt>Priority</dt><dd>{formatDisplayText(selectedTicket.priority, "Low")}</dd></div>
                  <div><dt>Intent</dt><dd>{formatDisplayText(selectedTicket.intent_tag, "General Inquiry")}</dd></div>
                  <div><dt>Last updated</dt><dd>{formatTicketTimestamp(selectedTicket.updated_at)}</dd></div>
                </dl>
              </div>

              <div className="support-details-card">
                <div className="support-card-title">Customer context</div>
                <dl className="support-detail-list">
                  <div><dt>Email</dt><dd>{formatDisplayText(selectedTicket.customer_email, "N/A")}</dd></div>
                  <div><dt>Brand</dt><dd>{BRANDS[selectedBrandKey].label}</dd></div>
                  <div><dt>Assignee</dt><dd>{formatDisplayText(selectedTicket.assigned_agent, "Unassigned")}</dd></div>
                  <div><dt>Queue</dt><dd>{formatDisplayText(selectedTicket.queue_name, "General Queue")}</dd></div>
                  <div><dt>Route method</dt><dd>{formatDisplayText(selectedTicket.assignment_method, "Auto-Routed")}</dd></div>
                </dl>
              </div>

              <div className="support-details-card">
                <div className="support-card-head">
                  <div className="support-card-title">Customer profile</div>
                  <div className="support-card-copy">
                    Live Acrobuild lookup, order history, and subscription status.
                  </div>
                </div>

                <div className="support-profile-controls">
                  <label className="support-field-block">
                    <span>Brand</span>
                    <select
                      className="field-input support-console-input"
                      onChange={(event) => setSelectedBrandKey(event.target.value as BrandKey)}
                      value={selectedBrandKey}
                    >
                      {Object.entries(BRANDS).map(([brandKey, brandConfig]) => (
                        <option key={brandKey} value={brandKey}>
                          {brandConfig.label}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label className="support-field-block">
                    <span>Customer Email</span>
                    <input
                      className="field-input support-console-input"
                      onChange={(event) => setCustomerEmailQuery(event.target.value)}
                      value={customerEmailQuery}
                    />
                  </label>
                </div>

                {isLoadingCustomerContext ? (
                  <div className="support-empty-inline">Loading customer context...</div>
                ) : null}

                {!isLoadingCustomerContext && customerContextError ? (
                  <div className="support-inline-warning">{customerContextError}</div>
                ) : null}

                {!isLoadingCustomerContext && customerEmailQuery.trim() ? (
                  <>
                    <div className="support-profile-grid">
                      <div className="support-profile-metric">
                        <span>Name</span>
                        <strong>{formatDisplayText(customerProfile.name, "N/A")}</strong>
                      </div>
                      <div className="support-profile-metric">
                        <span>Phone</span>
                        <strong>{formatDisplayText(customerProfile.phone, "N/A")}</strong>
                      </div>
                      <div className="support-profile-metric">
                        <span>Total Orders</span>
                        <strong>
                          {formatDisplayText(customerProfile.total_orders, String(customerOrders.length))}
                        </strong>
                      </div>
                      <div className="support-profile-metric">
                        <span>Total Spent</span>
                        <strong>{formatDisplayText(customerProfile.total_spent, "N/A")}</strong>
                      </div>
                    </div>

                    <dl className="support-detail-list compact">
                      <div><dt>Source</dt><dd>{formatDisplayText(customerData?.source, "unknown")}</dd></div>
                      <div><dt>Subscriptions</dt><dd>{String(customerSubscriptions.length)}</dd></div>
                    </dl>
                  </>
                ) : null}
              </div>

              <div className="support-details-card">
                <div className="support-card-head">
                  <div className="support-card-title">Internal notes</div>
                  <div className="support-card-copy">
                    Capture refunds in progress, promised callbacks, and edge cases.
                  </div>
                </div>

                <textarea
                  className="field-textarea support-console-textarea support-note-textarea"
                  onChange={(event) => setNoteDraft(event.target.value)}
                  placeholder="Capture refunds in progress, promised callbacks, edge cases, or anything the next agent should know..."
                  rows={5}
                  value={noteDraft}
                />

                <div className="support-note-actions">
                  <button
                    className="support-primary-button"
                    disabled={isWorking}
                    onClick={() => void handleSaveNote()}
                    type="button"
                  >
                    Save note
                  </button>
                  <button
                    className="support-secondary-button"
                    disabled={!noteDraft.trim()}
                    onClick={() => setNoteDraft("")}
                    type="button"
                  >
                    Clear draft
                  </button>
                </div>

                {detail.notes.length ? (
                  <div className="support-note-list">
                    {detail.notes.map((note) => (
                      <article className="support-note-card" key={note.id}>
                        <div className="support-note-meta">
                          <span>{formatDisplayText(note.author, "Admin")}</span>
                          <span>{formatTicketTimestamp(note.created_at)}</span>
                        </div>
                        <div className="support-note-text">{formatDisplayText(note.note, "")}</div>
                      </article>
                    ))}
                  </div>
                ) : (
                  <div className="support-empty-inline">No internal notes yet.</div>
                )}
              </div>
            </div>
          )}
        </aside>
          </>
        ) : (
          <section className="support-console-workspace">
            <div className="support-workspace-body">{renderWorkspaceSurface()}</div>
          </section>
        )}
      </div>

      {attachmentPreview ? (
        <div
          aria-label="Attachment preview"
          aria-modal="true"
          className="support-image-lightbox"
          onClick={() => setAttachmentPreview(null)}
          role="dialog"
        >
          <div
            className="support-image-lightbox-frame"
            onClick={(event) => event.stopPropagation()}
          >
            <button
              aria-label="Close image preview"
              className="support-image-lightbox-close"
              onClick={() => setAttachmentPreview(null)}
              type="button"
            >
              Close
            </button>
            <img
              alt={attachmentPreview.alt}
              className="support-image-lightbox-image"
              src={attachmentPreview.src}
            />
            <div className="support-image-lightbox-caption">{attachmentPreview.alt}</div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export function AdminInboxPage() {
  return <SharedManagerInboxPage />;
}

export function OwnerInboxWorkspacePage() {
  return <SharedManagerInboxPage />;
}






















