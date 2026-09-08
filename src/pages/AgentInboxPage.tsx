import {
  startTransition,
  type KeyboardEvent as ReactKeyboardEvent,
  useDeferredValue,
  useEffect,
  useMemo,
  useRef,
  useState
} from "react";
import { PhotoEmptyState } from "../components/PhotoEmptyState";
import { useSearch } from "../contexts/SearchContext";
import type { TicketSearchSuggestion } from "../contexts/SearchContext";
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
  updateAdminTicketTags,
  updateAdminTicketStatus
} from "../lib/api";
import {
  formatTicketTimestamp,
  getStatusColor
} from "../lib/ticketPresentation";
import type {
  CustomerLookupResponse,
  Macro,
  Ticket,
  TicketDetailResponse,
  TicketTag
} from "../types";

type Badge = {
  color: string;
  label: string;
};

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
type AttachmentPreview = {
  alt: string;
  src: string;
};
type TicketViewPreset = {
  id: TicketViewId;
  label: string;
};

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

function getTicketBadges(ticket: Ticket, tags: TicketTag[]) {
  const badges: Badge[] = [];
  const seen = new Set<string>();

  const addBadge = (label: string, color: string) => {
    const cleanLabel = label.trim();
    if (!cleanLabel) return;

    const normalized = cleanLabel.toLowerCase();
    if (seen.has(normalized)) return;

    seen.add(normalized);
    badges.push({ color, label: cleanLabel });
  };

  addBadge(ticket.issue_type, "#2dd4bf");
  addBadge(
    `${ticket.priority} Priority`,
    ticket.priority === "High" ? "#ef4444" : ticket.priority === "Medium" ? "#f59e0b" : "#38bdf8"
  );
  addBadge(ticket.intent_tag, "#8b5cf6");
  addBadge(ticket.queue_name, "#14b8a6");

  for (const tag of tags) {
    addBadge(tag.name, tag.color || "#38bdf8");
  }

  return badges;
}

function getCustomerFirstName(email: string) {
  const localPart = email.split("@")[0] ?? "Customer";
  const normalized = localPart.replace(/[._-]+/g, " ").trim();
  const first = normalized.split(" ")[0] ?? "Customer";
  return first.charAt(0).toUpperCase() + first.slice(1);
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

function getMessageAttachmentImageUrl(attachment: {
  absolute_path?: string;
  mime_type?: string;
  path?: string;
  url?: string;
}) {
  const url = attachment.url ?? attachment.path ?? attachment.absolute_path;
  if (!url) return undefined;
  return attachment.mime_type?.startsWith("image/") ? url : undefined;
}

function formatTicketButtonTitle(ticket: Ticket) {
  return `${formatDisplayText(ticket.issue_type, "General")} ${ticket.ticket_id}`;
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

function buildAgentSearchSuggestions(tickets: Ticket[]) {
  const seen = new Set<string>();
  const suggestions: TicketSearchSuggestion[] = [];

  for (const ticket of tickets) {
    const ticketId = ticket.ticket_id.trim();

    if (!ticketId) {
      continue;
    }

    const normalizedId = ticketId.toLowerCase();

    if (seen.has(normalizedId)) {
      continue;
    }

    seen.add(normalizedId);
    suggestions.push({
      id: `ticket:${normalizedId}`.replace(/[^a-z0-9:-]+/g, "-"),
      kind: "ticket",
      primary: ticketId,
      secondary: `${formatDisplayText(ticket.issue_type, "General")} â€¢ ${formatDisplayText(ticket.status, "Open")}`,
      searchText: normalizedId,
      value: ticketId
    });
  }

  return suggestions;
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

export function AgentInboxPage() {
  const {
    ticketSearchQuery,
    setSearchSuggestions,
    setVisibleTicketCount
  } = useSearch();
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [detail, setDetail] = useState<TicketDetailResponse | null>(null);
  const [availableTags, setAvailableTags] = useState<TicketTag[]>([]);
  const [allMacros, setAllMacros] = useState<Macro[]>([]);
  const [recommendedMacros, setRecommendedMacros] = useState<Macro[]>([]);
  const [selectedTicketId, setSelectedTicketId] = useState("");
  const [activeTicketView, setActiveTicketView] = useState<TicketViewId>("tickets");
  const [sortBy, setSortBy] = useState<SortMode>("Newest Activity");
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [selectedMacroId, setSelectedMacroId] = useState(0);
  const [appliedMacroId, setAppliedMacroId] = useState<number | null>(null);
  const [reply, setReply] = useState("");
  const [replyFiles, setReplyFiles] = useState<File[]>([]);
  const [replyUploadVersion, setReplyUploadVersion] = useState(0);
  const [noteDraft, setNoteDraft] = useState("");
  const [selectedBrandKey, setSelectedBrandKey] = useState<BrandKey>("nufoodz");
  const [customerEmailQuery, setCustomerEmailQuery] = useState("");
  const [customerData, setCustomerData] = useState<CustomerLookupResponse | null>(null);
  const [customerContextError, setCustomerContextError] = useState("");
  const [tagSearch, setTagSearch] = useState("");
  const [selectedManualTagIds, setSelectedManualTagIds] = useState<number[]>([]);
  const [isTagEditorOpen, setIsTagEditorOpen] = useState(false);
  const [attachmentPreview, setAttachmentPreview] = useState<AttachmentPreview | null>(null);
  const [isBootstrapping, setIsBootstrapping] = useState(true);
  const [isLoadingCustomerContext, setIsLoadingCustomerContext] = useState(false);
  const [isWorking, setIsWorking] = useState(false);
  const [error, setError] = useState("");
  const [successMessage, setSuccessMessage] = useState("");
  const threadScrollRef = useRef<HTMLDivElement | null>(null);
  const replyTextareaRef = useRef<HTMLTextAreaElement | null>(null);
  const deferredTicketSearch = useDeferredValue(ticketSearchQuery);
  const deferredCustomerEmail = useDeferredValue(customerEmailQuery);

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
  const viewerAssignmentLabel = "Help Desk";
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
          ticket.ticket_id.toLowerCase().includes(deferredTicketSearch.trim().toLowerCase())
      ),
    [sidebarCandidateTickets, deferredTicketSearch]
  );
  const visibleTickets = useMemo(
    () =>
      candidateTickets.filter(
        (ticket) =>
          !deferredTicketSearch.trim() ||
          ticket.ticket_id.toLowerCase().includes(deferredTicketSearch.trim().toLowerCase())
      ),
    [candidateTickets, deferredTicketSearch]
  );
  const ticketSearchSuggestions = useMemo(
    () =>
      buildAgentSearchSuggestions(
        sidebarCandidateTickets
      ),
    [sidebarCandidateTickets]
  );

  const visibleTicketTags = getVisibleTags(detail?.tags ?? []);
  const availableVisibleTags = getVisibleTags(availableTags);
  const ticketBadges = selectedTicket ? getTicketBadges(selectedTicket, visibleTicketTags) : [];
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
  const filteredAvailableTags = availableVisibleTags.filter((tag) =>
    tag.name.toLowerCase().includes(tagSearch.trim().toLowerCase())
  );
  const customerProfile = customerData?.customer ?? {};
  const customerOrders = customerData?.orders ?? customerData?.data?.orders ?? [];
  const customerSubscriptions = customerData?.subscriptions ?? [];
  const currentStatus = formatDisplayText(selectedTicket?.status, "Open");
  const quickActionState = getQuickActionState(currentStatus);
  const currentQueue = formatDisplayText(selectedTicket?.queue_name, "No team");
  const currentAgent = formatDisplayText(selectedTicket?.assigned_agent, "Unassigned");
  const customerDisplayName = formatDisplayText(
    customerProfile.name,
    selectedTicket ? getCustomerFirstName(selectedTicket.customer_email) : "Customer"
  );
  const suggestedMacros = orderedMacros.slice(0, 4);
  const customerInitials = getInitials(customerDisplayName, "CU");
  const agentInitials = getInitials(currentAgent.replace(/^Agent\s+/i, ""), "HD");

  useEffect(() => {
    setVisibleTicketCount(sidebarTickets.length);
  }, [setVisibleTicketCount, sidebarTickets.length]);

  useEffect(() => {
    setSearchSuggestions(ticketSearchSuggestions);

    return () => {
      setSearchSuggestions([]);
    };
  }, [setSearchSuggestions, ticketSearchSuggestions]);

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

  async function loadTickets(preferredTicketId?: string) {
    const response = await getAdminTickets();
    setTickets(response.tickets);

    if (!response.tickets.length) {
      setSelectedTicketId("");
      setDetail(null);
      return;
    }

    const visibleIds = new Set(response.tickets.map((ticket) => ticket.ticket_id));
    const nextTicketId =
      preferredTicketId && visibleIds.has(preferredTicketId)
        ? preferredTicketId
        : selectedTicketId && visibleIds.has(selectedTicketId)
          ? selectedTicketId
          : response.tickets[0].ticket_id;

    setSelectedTicketId(nextTicketId);
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
          current ? { ...current, ticket: readResponse.ticket } : current
        );
        setTickets((current) =>
          current.map((ticket) =>
            ticket.ticket_id === ticketId
              ? { ...ticket, unread_count: 0 }
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

        if (cancelled) return;

        setTickets(ticketsResponse.tickets);
        setAvailableTags(tagsResponse.tags);
        setAllMacros(macrosResponse.macros);
        setSelectedTicketId(ticketsResponse.tickets[0]?.ticket_id ?? "");
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

    async function pollTickets() {
      if (document.visibilityState === "hidden") {
        return;
      }

      try {
        const response = await getAdminTickets();

        if (cancelled) {
          return;
        }

        setTickets(response.tickets);

        if (!response.tickets.length) {
          setSelectedTicketId("");
          setDetail(null);
          return;
        }

        if (!response.tickets.some((ticket) => ticket.ticket_id === selectedTicketId)) {
          setSelectedTicketId(response.tickets[0].ticket_id);
        }
      } catch {
        // Keep background refresh quiet; direct actions already surface errors.
      }
    }

    const intervalId = window.setInterval(() => {
      void pollTickets();
    }, 5000);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [isBootstrapping, selectedTicketId]);

  useEffect(() => {
    let cancelled = false;

    async function hydrateSelectedTicket() {
      if (!selectedTicketId) {
        setDetail(null);
        setRecommendedMacros([]);
        return;
      }

      try {
        setError("");
        await loadSelectedTicketWorkspace(selectedTicketId);
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
  }, [selectedTicketId]);

  useEffect(() => {
    setAppliedMacroId(null);
    setReply("");
    setReplyFiles([]);
    setReplyUploadVersion((current) => current + 1);
    setNoteDraft("");
    setTagSearch("");
    setIsTagEditorOpen(false);
    setAttachmentPreview(null);

    if (selectedTicket) {
      setSelectedBrandKey(getBrandKeyFromTicket(selectedTicket));
      setCustomerEmailQuery(selectedTicket.customer_email || "");
      setCustomerContextError("");
    } else {
      setCustomerEmailQuery("");
      setCustomerData(null);
      setCustomerContextError("");
    }
  }, [selectedTicket?.ticket_id]);

  useEffect(() => {
    setSelectedManualTagIds(manualTagIds);
  }, [selectedTicket?.ticket_id, detail?.tags]);

  useEffect(() => {
    if (!visibleTickets.length) return;

    if (!visibleTickets.some((ticket) => ticket.ticket_id === selectedTicketId)) {
      setSelectedTicketId(visibleTickets[0].ticket_id);
    }
  }, [selectedTicketId, visibleTickets.map((ticket) => ticket.ticket_id).join("|")]);

  useEffect(() => {
    let cancelled = false;

    async function hydrateCustomerContext() {
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
        const customerResponse = await getAdminCustomerByEmail(email, brandConfig.apiBaseUrl);

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
  }, [deferredCustomerEmail, selectedBrandKey]);

  useEffect(() => {
    if (!detail?.messages.length || !threadScrollRef.current) {
      return;
    }

    const threadElement = threadScrollRef.current;
    const animationFrame = window.requestAnimationFrame(() => {
      threadElement.scrollTop = threadElement.scrollHeight;
    });

    return () => {
      window.cancelAnimationFrame(animationFrame);
    };
  }, [detail?.messages.length, selectedTicket?.ticket_id]);

  useEffect(() => {
    if (!attachmentPreview) return;

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
    if (!selectedTicket) return;

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
    if (!selectedTicket) return;

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
    if (!selectedTicket) return;

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

  async function handleRefresh() {
    if (!selectedTicket) return;

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
        author: formatDisplayText(selectedTicket.assigned_agent, "Agent"),
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

  return (
    <div className="support-console-page">
      <div className="support-console-toast-stack">
        {error ? <div className="banner-error support-console-banner">{error}</div> : null}
        {successMessage ? (
          <div className="banner-success support-console-banner">{successMessage}</div>
        ) : null}
      </div>

      <div className="support-console-grid">
        <aside className="support-console-sidebar">
          <div className="support-sidebar-panel">
            <div className="support-sidebar-top">
              <div className="support-sidebar-home">NS</div>
              <div className="support-sidebar-heading">
                <div className="support-sidebar-title-row">
                  <div className="support-sidebar-title">Inbox</div>
                  <span className="support-sidebar-title-count">{tickets.length}</span>
                </div>
                <div className="support-sidebar-copy">
                  {tickets.length} tickets / {getActiveTicketCount(tickets)} active / {getUnreadTicketCount(tickets)} unread
                </div>
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
                  description="We are pulling your latest ticket list, unread counts, and queue updates."
                  eyebrow="Agent queue"
                  highlights={["Queue sync", "Unread counts"]}
                  title="Loading tickets"
                  variant="compact"
                />
              ) : null}
              {!isBootstrapping && !sidebarTickets.length ? (
                <PhotoEmptyState
                  className="support-empty-state sidebar"
                  description="Try another shared view or wait for the next routed ticket to arrive in your queue."
                  eyebrow="Agent queue"
                  highlights={["Shared views", "Next routed ticket"]}
                  title="No tickets match this view"
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
                    <span
                      className="support-ticket-dot"
                      style={{ backgroundColor: getStatusColor(ticket.status) }}
                    />
                    <span className="support-ticket-subject">{formatTicketButtonTitle(ticket)}</span>
                    {Number(ticket.unread_count || 0) > 0 ? (
                      <span className="support-ticket-counter">{ticket.unread_count}</span>
                    ) : null}
                  </div>
                </button>
              ))}
            </div>
          </div>
        </aside>

        <section className="support-console-main">
          {!visibleTickets.length ? (
            <PhotoEmptyState
              className="support-empty-state support-empty-panel support-empty-panel-main"
              description="Your active queue is clear right now, so there is no conversation waiting in the main workspace."
              eyebrow="Conversation workspace"
              highlights={["Assigned queue", "Unread replies", "Fresh handoffs"]}
              title="No tickets in your queue"
              variant="compact"
            />
          ) : !selectedTicket || !detail ? (
            <PhotoEmptyState
              className="support-empty-state support-empty-panel support-empty-panel-main"
              description="Pick a ticket from the left column to open the thread, suggested replies, and customer context."
              eyebrow="Conversation workspace"
              highlights={["Thread history", "Suggested replies", "Customer context"]}
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
                    <div className="support-thread-summary-copy">
                      Updated {formatTicketTimestamp(selectedTicket.updated_at)}
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

                                  if (!imageUrl) return null;

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
              description="As soon as a routed ticket appears, this rail will show ownership, tags, and customer details."
              eyebrow="Ticket details"
              highlights={["Ownership", "Tags", "Customer details"]}
              title="No ticket details available"
              variant="compact"
            />
          ) : !selectedTicket || !detail ? (
            <PhotoEmptyState
              className="support-empty-state support-empty-panel support-empty-panel-detail"
              description="Select a conversation and this panel will fill with the customer profile, actions, and notes."
              eyebrow="Ticket details"
              highlights={["Profile", "Actions", "Notes"]}
              title="Ticket details will load here"
              variant="compact"
            />
          ) : (
            <div className="support-details-scroll">
              <div className="support-details-header">
                <div>
                  <div className="support-details-kicker">Ticket details</div>
                  <h2 className="support-details-title">{customerDisplayName}</h2>
                  <div className="support-details-subtitle">{selectedTicket.ticket_id}</div>
                </div>

                <button
                  className="support-secondary-button support-secondary-button-small"
                  onClick={() => setIsTagEditorOpen((current) => !current)}
                  type="button"
                >
                  Edit tags
                </button>
              </div>

              <div className="support-details-card">
                <div className="support-badge-cluster">
                  {ticketBadges.map((badge) => (
                    <span className="support-tag-chip" key={badge.label}>
                      <span
                        className="support-tag-chip-dot"
                        style={{ backgroundColor: badge.color }}
                      />
                      {badge.label}
                    </span>
                  ))}
                </div>
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

              <div className="support-details-card">
                <div className="support-card-title">Quick actions</div>
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
                    Live Acrobuild lookup so agents can answer with current customer context.
                  </div>
                </div>

                <label className="field-block">
                  <span>Customer Email</span>
                  <input
                    className="field-input support-console-input"
                    onChange={(event) => setCustomerEmailQuery(event.target.value)}
                    value={customerEmailQuery}
                  />
                </label>

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
                        <strong>{formatDisplayText(customerProfile.total_orders, String(customerOrders.length))}</strong>
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
                    Capture important context for other agents.
                  </div>
                </div>

                <textarea
                  className="field-textarea support-console-textarea support-note-textarea"
                  onChange={(event) => setNoteDraft(event.target.value)}
                  placeholder="Add an internal note..."
                  rows={4}
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
                          <span>{formatDisplayText(note.author, "Agent")}</span>
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

















