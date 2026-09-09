import type {
  BusinessHoursProfile,
  CreateTicketResponse,
  CustomerLookupResponse,
  DataApiCallTrace,
  KnowledgeDocumentRecord,
  KnowledgeUrlImportResponse,
  KnowledgeUploadResponse,
  PropertyInventoryUnit,
  PropertyProject,
  PropertyTypology,
  PropertyWing,
  Macro,
  RuleAffectedTicket,
  SupportConversationMessage,
  SupportArticleRecord,
  SupportWorkspaceUser,
  SupportAssistResponse,
  Ticket,
  TicketDetailResponse,
  TicketTag,
  WorkflowRule,
  WorkflowRuleWindow
} from "../types";
import { beginApiActivity, failApiActivity, finishApiActivity } from "./apiActivity";

type ImportMetaWithOptionalEnv = ImportMeta & {
  env?: Record<string, string | undefined>;
};

const configuredBackendUrl = String((import.meta as ImportMetaWithOptionalEnv).env?.VITE_BACKEND_URL ?? "").trim().replace(/\/+$/, "");
const DEFAULT_STREAM_ACTIVITY_TIMEOUT_MS = 120000;
let refreshRequest: Promise<Response> | null = null;
const backendPorts = ["8000", "8001"];

type ApiAttemptError = Error & {
  recoverable?: boolean;
};

function createRecoverableApiError(message: string) {
  const error = new Error(message) as ApiAttemptError;
  error.recoverable = true;
  return error;
}

function isRecoverableApiError(error: unknown) {
  return error instanceof Error && Boolean((error as ApiAttemptError).recoverable);
}

function addUniqueApiBase(candidates: string[], value: string) {
  const normalizedValue = value.trim().replace(/\/+$/, "");

  if (!normalizedValue && candidates.includes("")) {
    return;
  }

  if (normalizedValue && candidates.includes(normalizedValue)) {
    return;
  }

  candidates.push(normalizedValue);
}

function buildApiBaseCandidates() {
  // One configured origin: never replay a mutation against another backend.
  return [configuredBackendUrl];
}

function buildApiUrl(path: string, baseUrl: string) {
  return baseUrl ? `${baseUrl}${path}` : path;
}

function buildRequestInit(init?: RequestInit, signal?: AbortSignal): RequestInit {
  const csrf = typeof document === "undefined" ? "" : document.cookie.split("; ").find(value => value.startsWith("workspace_csrf="))?.split("=")[1] ?? "";
  return {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(csrf ? { "X-CSRF-Token": decodeURIComponent(csrf) } : {}),
      ...(init?.headers ?? {})
    },
    ...(signal ? { signal } : {})
  };
}

function resolveApiErrorMessage(responseText: string, status: number) {
  let resolvedMessage = responseText || `Request failed: ${status}`;

  try {
    const parsedError = JSON.parse(responseText) as {
      detail?: string;
      message?: string;
    };

    resolvedMessage =
      parsedError.detail?.trim() ||
      parsedError.message?.trim() ||
      resolvedMessage;
  } catch {
    // Keep the plain text body when the response is not JSON.
  }

  return resolvedMessage;
}

function isHtmlResponse(responseText: string) {
  const normalizedResponse = responseText.trim().toLowerCase();

  return (
    normalizedResponse.startsWith("<!doctype") ||
    normalizedResponse.startsWith("<html")
  );
}

function isRecoverableHttpStatus(status: number) {
  return status === 404 || status >= 500;
}

async function requestJsonFromUrl<T>(
  path: string,
  init: RequestInit | undefined,
  baseUrl: string
): Promise<T> {
  const requestUrl = buildApiUrl(path, baseUrl);
  let response: Response;

  try {
    response = await fetch(requestUrl, buildRequestInit(init));
    if (response.status === 401 && !["/auth/login", "/auth/refresh", "/auth/logout"].includes(path)) {
      refreshRequest ??= fetch(buildApiUrl("/auth/refresh", baseUrl), buildRequestInit({ method: "POST" })).finally(() => { refreshRequest = null; });
      const refreshed = await refreshRequest;
      if (refreshed.ok) response = await fetch(requestUrl, buildRequestInit(init));
    }
  } catch {
    throw createRecoverableApiError(
      `Could not reach the backend at ${requestUrl}.`
    );
  }

  const responseText = await response.text();

  if (!response.ok) {
    const resolvedMessage = resolveApiErrorMessage(responseText, response.status);

    if (isRecoverableHttpStatus(response.status)) {
      throw createRecoverableApiError(resolvedMessage);
    }

    throw new Error(resolvedMessage);
  }

  try {
    return JSON.parse(responseText) as T;
  } catch {
    if (isHtmlResponse(responseText)) {
      throw createRecoverableApiError(
        "The workspace received an HTML page instead of backend data. Restart the frontend and backend servers."
      );
    }

    throw createRecoverableApiError(
      "The workspace received an invalid JSON response from the backend."
    );
  }
}

async function apiRequest<T>(
  path: string,
  init?: RequestInit
): Promise<T> {
  let lastError: unknown;

  for (const baseUrl of buildApiBaseCandidates()) {
    try {
      return await requestJsonFromUrl<T>(path, init, baseUrl);
    } catch (error) {
      lastError = error;

      if (!isRecoverableApiError(error)) {
        throw error;
      }
    }
  }

  if (lastError instanceof Error) {
    throw lastError;
  }

  throw new Error("Unable to reach the backend.");
}

export type WorkspaceSessionUser = {
  id: number;
  email: string;
  name: string;
  role: "admin" | "owner" | "agent";
  status: string;
  team: string;
};

export function loginWorkspace(email: string, password: string) {
  return apiRequest<{ user: WorkspaceSessionUser }>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password })
  });
}

export function logoutWorkspace() {
  return apiRequest("/auth/logout", { method: "POST" });
}

export function getWorkspaceSession() {
  return apiRequest<{ user: WorkspaceSessionUser }>("/auth/me");
}

async function apiRequestWithFallback<T>(
  primaryPath: string,
  fallbackPath: string,
  init?: RequestInit
): Promise<T> {
  try {
    return await apiRequest<T>(primaryPath, init);
  } catch (error) {
    const message = error instanceof Error ? error.message.trim().toLowerCase() : "";

    if (message !== "not found") {
      throw error;
    }

    try {
      return await apiRequest<T>(fallbackPath, init);
    } catch (fallbackError) {
      const fallbackMessage =
        fallbackError instanceof Error ? fallbackError.message.trim().toLowerCase() : "";
      const isKnowledgeBaseRoute =
        primaryPath.includes("/knowledge-documents") || fallbackPath.includes("/knowledge-documents");

      if (isKnowledgeBaseRoute && fallbackMessage === "not found") {
        throw new Error(
          "The Knowledge Base backend routes are not loaded yet. Restart the FastAPI server on 127.0.0.1:8000 or 127.0.0.1:8001 and refresh this page."
        );
      }

      throw fallbackError;
    }
  }
}

async function openStreamResponse(
  path: string,
  init: RequestInit,
  timeoutMs = DEFAULT_STREAM_ACTIVITY_TIMEOUT_MS
) {
  let lastError: unknown;

  for (const baseUrl of buildApiBaseCandidates()) {
    const requestUrl = buildApiUrl(path, baseUrl);
    const controller = new AbortController();
    const timeoutId = globalThis.setTimeout(() => {
      controller.abort();
    }, timeoutMs);

    try {
      const response = await fetch(requestUrl, buildRequestInit(init, controller.signal));
      globalThis.clearTimeout(timeoutId);

      if (!response.ok) {
        const responseText = await response.text();
        const resolvedMessage = resolveApiErrorMessage(responseText, response.status);

        if (isRecoverableHttpStatus(response.status)) {
          throw createRecoverableApiError(resolvedMessage);
        }

        throw new Error(resolvedMessage);
      }

      if (!response.body) {
        throw createRecoverableApiError("The support stream did not include a response body.");
      }

      return {
        controller,
        response
      };
    } catch (error) {
      globalThis.clearTimeout(timeoutId);
      lastError = error;

      if (error instanceof DOMException && error.name === "AbortError") {
        lastError = createRecoverableApiError(
          `The backend at ${requestUrl} took too long to start replying.`
        );
      }

      if (!isRecoverableApiError(lastError)) {
        throw lastError;
      }
    }
  }

  if (lastError instanceof Error) {
    throw lastError;
  }

  throw new Error("Unable to open the support stream.");
}

async function readStreamChunk(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  controller: AbortController,
  timeoutMs = DEFAULT_STREAM_ACTIVITY_TIMEOUT_MS
) {
  let timeoutId = 0;

  try {
    return await Promise.race([
      reader.read(),
      new Promise<never>((_, reject) => {
        timeoutId = globalThis.setTimeout(() => {
          controller.abort();
          reject(
            new Error("The assistant took too long to reply. Switching to a faster fallback.")
          );
        }, timeoutMs);
      })
    ]);
  } finally {
    if (timeoutId) {
      globalThis.clearTimeout(timeoutId);
    }
  }
}

export function getTicketPage(limit = 100, offset = 0, status = "", search = "") {
  const query = new URLSearchParams({ limit: String(limit), offset: String(offset), status, search });
  return apiRequest<{ tickets: Ticket[]; total: number; limit: number; offset: number }>(`/api/admin/tickets?${query}`);
}

export async function getAdminTickets() {
  // Compatibility for aggregate dashboards; individual inboxes can use getTicketPage.
  const first = await getTicketPage(500);
  const tickets = [...first.tickets];
  for (let offset = 500; offset < first.total; offset += 500) {
    tickets.push(...(await getTicketPage(500, offset)).tickets);
  }
  return { tickets };
}

type PropertyFlowResponse<T> = {
  data_api_calls?: DataApiCallTrace[];
  items: T[];
};

async function getPropertyFlow<T>(endpoint: string, issue: string) {
  const request = { issue };
  const activityId = beginApiActivity({ endpoint, method: "GET", request, transport: "json" });
  try {
    const response = await apiRequest<PropertyFlowResponse<T>>(endpoint);
    finishApiActivity(activityId, response);
    return response;
  } catch (error) {
    failApiActivity(activityId, error);
    throw error;
  }
}

export function getPropertyProjects() {
  return getPropertyFlow<PropertyProject>("/api/property-flow/projects", "Browse live projects");
}

export function getPropertyWings(projectId: number) {
  return getPropertyFlow<PropertyWing>(
    `/api/property-flow/projects/${projectId}/wings`,
    `Load wings for project ${projectId}`
  );
}

export function getPropertyTypologies(wingId: number) {
  return getPropertyFlow<PropertyTypology>(
    `/api/property-flow/wings/${wingId}/typologies`,
    `Load pricing for wing ${wingId}`
  );
}

export function getPropertyInventory(wingId: number) {
  return getPropertyFlow<PropertyInventoryUnit>(
    `/api/property-flow/wings/${wingId}/inventory?available_only=true`,
    `Load available flats for wing ${wingId}`
  );
}

export function createSiteVisit(payload: {
  customer_name: string;
  customer_email: string;
  customer_phone: string;
  project_name: string;
  preferred_date: string;
  preferred_time: string;
  wing_name?: string;
  typology_name?: string;
  unit_number?: string;
  notes?: string;
}) {
  return apiRequest<CreateTicketResponse>("/api/site-visits", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}
export function createSupportTicket(payload: {
  customer_email: string;
  issue: string;
}) {
  return apiRequest<CreateTicketResponse>("/create_ticket", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function getSupportAssist(payload: {
  article_hint_url?: string;
  business_hours_tag?: string;
  conversation_id?: string;
  conversation_messages?: SupportConversationMessage[];
  customer_email?: string;
  customer_name?: string;
  issue: string;
  issue_type?: string;
  limit?: number;
  prefer_fast_response?: boolean;
  prefer_qwen_response?: boolean;
}) {
  const request = {
    article_hint_url: payload.article_hint_url ?? "",
    business_hours_tag: payload.business_hours_tag ?? "",
    conversation_id: payload.conversation_id ?? "",
    conversation_messages: payload.conversation_messages ?? [],
    customer_email: payload.customer_email ?? "",
    customer_name: payload.customer_name ?? "",
    issue: payload.issue,
    issue_type: payload.issue_type ?? "",
    limit: payload.limit ?? 3,
    prefer_fast_response: payload.prefer_fast_response ?? false,
    prefer_qwen_response: payload.prefer_qwen_response ?? true
  };
  const activityId = beginApiActivity({ endpoint: "/api/support/assist", method: "POST", request, transport: "json" });

  try {
    const response = await apiRequest<SupportAssistResponse>("/api/support/assist", {
      method: "POST",
      body: JSON.stringify(request)
    });
    finishApiActivity(activityId, response);
    return response;
  } catch (error) {
    failApiActivity(activityId, error);
    throw error;
  }
}

export async function streamSupportAssist(
  payload: {
    article_hint_url?: string;
    business_hours_tag?: string;
    conversation_id?: string;
    conversation_messages?: SupportConversationMessage[];
    customer_email?: string;
    customer_name?: string;
    issue: string;
    issue_type?: string;
    limit?: number;
    prefer_fast_response?: boolean;
    prefer_qwen_response?: boolean;
  },
  handlers: {
    onDelta?: (text: string) => void;
    onDone: (response: SupportAssistResponse) => void;
  }
) {
  const request = {
    article_hint_url: payload.article_hint_url ?? "",
    business_hours_tag: payload.business_hours_tag ?? "",
    conversation_id: payload.conversation_id ?? "",
    conversation_messages: payload.conversation_messages ?? [],
    customer_email: payload.customer_email ?? "",
    customer_name: payload.customer_name ?? "",
    issue: payload.issue,
    issue_type: payload.issue_type ?? "",
    limit: payload.limit ?? 3,
    prefer_fast_response: payload.prefer_fast_response ?? false,
    prefer_qwen_response: payload.prefer_qwen_response ?? true
  };
  const activityId = beginApiActivity({ endpoint: "/api/support/assist/stream", method: "POST", request, transport: "stream" });

  try {
    const { controller, response } = await openStreamResponse("/api/support/assist/stream", {
      method: "POST",
      body: JSON.stringify(request)
    });
    const streamBody = response.body;
    if (!streamBody) throw new Error("The support stream did not include a response body.");

    const reader = streamBody.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await readStreamChunk(reader, controller);
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";

      for (const line of lines) {
        const trimmedLine = line.trim();
        if (!trimmedLine) continue;
        const event = JSON.parse(trimmedLine) as
          | { type: "delta"; text: string }
          | { type: "done" | "error"; response: SupportAssistResponse }
          | { type: string; [key: string]: unknown };
        if (event.type === "delta") {
          handlers.onDelta?.((event as { text?: string }).text ?? "");
        } else if ((event.type === "done" || event.type === "error") && (event as { response?: unknown }).response) {
          const finalResponse = (event as { response: SupportAssistResponse }).response;
          finishApiActivity(activityId, finalResponse);
          handlers.onDone(finalResponse);
          return;
        }
        // Other event types (e.g. "progress") are informational — keep reading.
      }
    }

    if (buffer.trim()) {
      const event = JSON.parse(buffer.trim()) as { response?: SupportAssistResponse; type: string };
      if (event.response) {
        finishApiActivity(activityId, event.response);
        handlers.onDone(event.response);
        return;
      }
    }
    throw new Error("The support stream ended before a final response arrived.");
  } catch (error) {
    failApiActivity(activityId, error);
    throw error;
  }
}
export function getAdminTicketDetail(ticketId: string) {
  return apiRequest<TicketDetailResponse>(`/api/admin/tickets/${ticketId}/detail`);
}

export function markAdminTicketRead(ticketId: string) {
  return apiRequest<{ ticket: Ticket }>(`/api/admin/tickets/${ticketId}/read`, {
    method: "POST"
  });
}

export function getAdminRecommendedMacros(ticketId: string) {
  return apiRequest<{ macros: Macro[] }>(`/api/admin/tickets/${ticketId}/recommended-macros`);
}

export function requestEmailOtp(email: string) {
  return apiRequest<{ expires_in: number; message: string; resend_after: number }>("/auth/otp/request", {
    method: "POST",
    body: JSON.stringify({ email })
  });
}

export function verifyEmailOtp(email: string, code: string) {
  return apiRequest<{ access_token: string; expires_in: number; message: string }>("/auth/otp/verify", {
    method: "POST",
    body: JSON.stringify({ email, code })
  });
}

export function getVerifiedCustomerByEmail(email: string, accessToken: string, apiBaseUrl?: string) {
  const params = new URLSearchParams({
    email
  });

  if (apiBaseUrl) {
    params.set("api_base_url", apiBaseUrl);
  }

  return apiRequest<CustomerLookupResponse>("/customer/verified?" + params.toString(), { headers: { Authorization: `Bearer ${accessToken}` } });
}
export function getAdminCustomerByEmail(email: string, apiBaseUrl?: string) {
  const params = new URLSearchParams({
    email
  });

  if (apiBaseUrl) {
    params.set("api_base_url", apiBaseUrl);
  }

  return apiRequest<CustomerLookupResponse>(`/customer?${params.toString()}`);
}

export function getOrdersByEmail(email: string, apiBaseUrl?: string) {
  const params = new URLSearchParams({
    email
  });

  if (apiBaseUrl) {
    params.set("api_base_url", apiBaseUrl);
  }

  return apiRequest<{ orders: any[] }>(`/orders?${params.toString()}`);
}

export function updateAdminTicketStatus(ticketId: string, status: string) {
  return apiRequest<{ ticket: Ticket }>(`/api/admin/tickets/${ticketId}/status`, {
    method: "PUT",
    body: JSON.stringify({ ticket_id: ticketId, status })
  });
}

export function updateAdminTicketAssignee(ticketId: string, agentName: string) {
  return apiRequest<{ ticket: Ticket }>(`/api/admin/tickets/${ticketId}/assign`, {
    method: "PUT",
    body: JSON.stringify({ ticket_id: ticketId, agent_name: agentName })
  });
}

export function closeAdminTicket(ticketId: string) {
  return apiRequest<{ ticket: Ticket }>(`/api/admin/tickets/${ticketId}/close`, {
    method: "POST"
  });
}

export function postAdminTicketMessage(ticketId: string, message: string) {
  return apiRequest<{ ticket: Ticket }>(`/api/admin/tickets/${ticketId}/messages`, {
    method: "POST",
    body: JSON.stringify({ message, sender: "admin" })
  });
}

export function postAdminTicketReply(
  ticketId: string,
  payload: {
    applied_macro_id?: number | null;
    attachments?: Array<{
      content_base64: string;
      mime_type: string;
      name: string;
    }>;
    message: string;
    sender?: string;
  }
) {
  return apiRequest<{
    applied_macro: Macro | null;
    message: unknown;
    tags: TicketTag[];
    ticket: Ticket;
  }>(`/api/admin/tickets/${ticketId}/reply`, {
    method: "POST",
    body: JSON.stringify({
      applied_macro_id: payload.applied_macro_id ?? null,
      attachments: payload.attachments ?? [],
      message: payload.message,
      sender: payload.sender ?? "admin"
    })
  });
}

export function createAdminTicketNote(
  ticketId: string,
  payload: {
    author?: string;
    note: string;
  }
) {
  return apiRequest<{ notes: TicketDetailResponse["notes"]; ticket: Ticket }>(
    `/api/admin/tickets/${ticketId}/notes`,
    {
      method: "POST",
      body: JSON.stringify(payload)
    }
  );
}

export function getAdminUsers() {
  return apiRequestWithFallback<{ users: SupportWorkspaceUser[] }>(
    "/api/admin/users",
    "/admin/users"
  );
}

export function getAdminArticles() {
  return apiRequestWithFallback<{ articles: SupportArticleRecord[] }>(
    "/api/admin/articles",
    "/admin/articles"
  );
}

export function createAdminArticle(payload: {
  body: string;
  category: string;
  keywords: string[];
  status: SupportArticleRecord["status"];
  summary: string;
  title: string;
  url?: string;
}) {
  return apiRequestWithFallback<{ article: SupportArticleRecord }>(
    "/api/admin/articles",
    "/admin/articles",
    {
      method: "POST",
      body: JSON.stringify({
        ...payload,
        url: payload.url ?? ""
      })
    }
  );
}

export function updateAdminArticle(
  articleId: number,
  payload: {
    body: string;
    category: string;
    keywords: string[];
    status: SupportArticleRecord["status"];
    summary: string;
    title: string;
    url?: string;
  }
) {
  return apiRequestWithFallback<{ article: SupportArticleRecord }>(
    `/api/admin/articles/${articleId}`,
    `/admin/articles/${articleId}`,
    {
      method: "PUT",
      body: JSON.stringify({
        ...payload,
        url: payload.url ?? ""
      })
    }
  );
}

export function getAdminKnowledgeDocuments() {
  return apiRequestWithFallback<{ documents: KnowledgeDocumentRecord[] }>(
    "/api/admin/knowledge-documents",
    "/admin/knowledge-documents"
  );
}

export function createAdminKnowledgeDocument(payload: {
  body: string;
  category: string;
  source_name?: string;
  source_type?: string;
  status: KnowledgeDocumentRecord["status"];
  summary: string;
  tags: string[];
  title: string;
}) {
  return apiRequestWithFallback<{ document: KnowledgeDocumentRecord }>(
    "/api/admin/knowledge-documents",
    "/admin/knowledge-documents",
    {
      method: "POST",
      body: JSON.stringify({
        ...payload,
        source_name: payload.source_name ?? "",
        source_type: payload.source_type ?? "manual"
      })
    }
  );
}

export function updateAdminKnowledgeDocument(
  documentId: number,
  payload: {
    body: string;
    category: string;
    source_name?: string;
    source_type?: string;
    status: KnowledgeDocumentRecord["status"];
    summary: string;
    tags: string[];
    title: string;
  }
) {
  return apiRequestWithFallback<{ document: KnowledgeDocumentRecord }>(
    `/api/admin/knowledge-documents/${documentId}`,
    `/admin/knowledge-documents/${documentId}`,
    {
      method: "PUT",
      body: JSON.stringify({
        ...payload,
        source_name: payload.source_name ?? "",
        source_type: payload.source_type ?? "manual"
      })
    }
  );
}

export function deleteAdminKnowledgeDocuments(documentIds: number[]) {
  return apiRequestWithFallback<{ deleted_count: number; deleted_ids: number[] }>(
    "/api/admin/knowledge-documents/delete",
    "/admin/knowledge-documents/delete",
    {
      method: "POST",
      body: JSON.stringify({
        document_ids: documentIds
      })
    }
  );
}

export function uploadAdminKnowledgeDocuments(payload: {
  category: string;
  files: Array<{
    content_base64: string;
    mime_type: string;
    name: string;
  }>;
  source_name?: string;
  status: KnowledgeDocumentRecord["status"];
  tags: string[];
}) {
  return apiRequestWithFallback<KnowledgeUploadResponse>(
    "/api/admin/knowledge-documents/upload",
    "/admin/knowledge-documents/upload",
    {
      method: "POST",
      body: JSON.stringify({
        category: payload.category,
        files: payload.files,
        source_name: payload.source_name ?? "",
        status: payload.status,
        tags: payload.tags
      })
    }
  );
}

export function importAdminKnowledgeUrl(payload: {
  body_note?: string;
  category: string;
  status: KnowledgeDocumentRecord["status"];
  summary?: string;
  source_type?: string;
  tags: string[];
  title_prefix?: string;
  url: string;
}) {
  return apiRequestWithFallback<KnowledgeUrlImportResponse>(
    "/api/admin/knowledge-documents/import-url",
    "/admin/knowledge-documents/import-url",
    {
      method: "POST",
      body: JSON.stringify({
        body_note: payload.body_note ?? "",
        category: payload.category,
        status: payload.status,
        summary: payload.summary ?? "",
        source_type: payload.source_type ?? "url",
        tags: payload.tags,
        title_prefix: payload.title_prefix ?? "",
        url: payload.url
      })
    }
  ).catch((error) => {
    const message = error instanceof Error ? error.message.trim().toLowerCase() : "";

    if (message === "method not allowed" || message === "not found") {
      throw new Error(
        "The URL import backend route is not loaded yet. Restart the FastAPI server on 127.0.0.1:8000 and try again."
      );
    }

    throw error;
  });
}

export function createAdminUser(payload: {
  email: string;
  name: string;
  role: SupportWorkspaceUser["role"];
  status?: SupportWorkspaceUser["status"];
  team: string;
}) {
  return apiRequestWithFallback<{ user: SupportWorkspaceUser }>(
    "/api/admin/users",
    "/admin/users",
    {
      method: "POST",
      body: JSON.stringify({
        ...payload,
        status: payload.status ?? "Invited"
      })
    }
  );
}

export function updateAdminUser(
  userId: number,
  payload: {
    name: string;
    role: SupportWorkspaceUser["role"];
    status: SupportWorkspaceUser["status"];
    team: string;
  }
) {
  return apiRequestWithFallback<{ user: SupportWorkspaceUser }>(
    `/api/admin/users/${userId}`,
    `/admin/users/${userId}`,
    {
      method: "PUT",
      body: JSON.stringify(payload)
    }
  );
}

export function getAdminTags(searchTerm = "") {
  const suffix = searchTerm ? `?search_term=${encodeURIComponent(searchTerm)}` : "";
  return apiRequest<{ tags: TicketTag[] }>(`/api/admin/tags${suffix}`);
}

export function createAdminTag(payload: {
  color: string;
  description: string;
  name: string;
}) {
  return apiRequest<{ tag: TicketTag | null }>("/api/admin/tags", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function updateAdminTag(
  tagId: number,
  payload: {
    color: string;
    description: string;
    name: string;
  }
) {
  return apiRequest<{ tag: TicketTag | null }>(`/api/admin/tags/${tagId}`, {
    method: "PUT",
    body: JSON.stringify(payload)
  });
}

export function deleteAdminTag(tagId: number) {
  return apiRequest<{ deleted: boolean; tag_id: number }>(`/api/admin/tags/${tagId}`, {
    method: "DELETE"
  });
}

export function mergeAdminTags(targetTagId: number, sourceTagIds: number[]) {
  return apiRequest<{ merged: boolean; target_tag_id: number }>("/api/admin/tags/merge", {
    method: "POST",
    body: JSON.stringify({
      source_tag_ids: sourceTagIds,
      target_tag_id: targetTagId
    })
  });
}

export function updateAdminTicketTags(ticketId: string, tagIds: number[]) {
  return apiRequest<{ tags: TicketTag[] }>(`/api/admin/tickets/${ticketId}/tags`, {
    method: "PUT",
    body: JSON.stringify({ tag_ids: tagIds })
  });
}

export function getAdminMacros(options?: {
  category?: string;
  includeArchived?: boolean;
  language?: string;
  searchTerm?: string;
  tagName?: string;
}) {
  const params = new URLSearchParams();

  if (options?.searchTerm) {
    params.set("search_term", options.searchTerm);
  }

  if (options?.language) {
    params.set("language", options.language);
  }

  if (options?.category) {
    params.set("category", options.category);
  }

  if (options?.tagName) {
    params.set("tag_name", options.tagName);
  }

  if (options?.includeArchived) {
    params.set("include_archived", "true");
  }

  const query = params.toString();
  const suffix = query ? `?${query}` : "";

  return apiRequest<{ macros: Macro[] }>(`/api/admin/macros${suffix}`);
}

export function getAdminMacro(macroId: number) {
  return apiRequest<{ macro: Macro }>(`/api/admin/macros/${macroId}`);
}

export function createAdminMacro(payload: {
  category: string;
  description: string;
  language: string;
  name: string;
  response_text: string;
  set_status: string;
  subject_template: string;
  tag_names: string[];
}) {
  return apiRequest<{ macro: Macro }>("/api/admin/macros", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function updateAdminMacro(
  macroId: number,
  payload: {
    category: string;
    description: string;
    language: string;
    name: string;
    response_text: string;
    set_status: string;
    subject_template: string;
    tag_names: string[];
  }
) {
  return apiRequest<{ macro: Macro }>(`/api/admin/macros/${macroId}`, {
    method: "PUT",
    body: JSON.stringify(payload)
  });
}

export function duplicateAdminMacro(macroId: number) {
  return apiRequest<{ macro: Macro }>(`/api/admin/macros/${macroId}/duplicate`, {
    method: "POST"
  });
}

export function archiveAdminMacro(macroId: number, isArchived: boolean) {
  return apiRequest<{ macro: Macro | null }>(`/api/admin/macros/${macroId}/archive`, {
    method: "POST",
    body: JSON.stringify({ is_archived: isArchived })
  });
}

export function deleteAdminMacro(macroId: number) {
  return apiRequest<{ deleted: boolean; macro_id: number }>(`/api/admin/macros/${macroId}`, {
    method: "DELETE"
  });
}

export function getBusinessHoursProfiles() {
  return apiRequest<{ profiles: BusinessHoursProfile[] }>("/api/admin/business-hours/profiles");
}

export function updateBusinessHoursProfile(profile: BusinessHoursProfile) {
  return apiRequest<{ profile: BusinessHoursProfile }>(
    `/api/admin/business-hours/profiles/${profile.id}`,
    {
      method: "PUT",
      body: JSON.stringify({
        description: profile.description,
        is_default: Boolean(profile.is_default),
        name: profile.name,
        ranges: profile.ranges,
        timezone_name: profile.timezone
      })
    }
  );
}

export function createBusinessHoursProfile(profile: {
  description: string;
  is_default?: boolean;
  name: string;
  ranges: BusinessHoursProfile["ranges"];
  timezone_name: string;
}) {
  return apiRequest<{ profile: BusinessHoursProfile }>("/api/admin/business-hours/profiles", {
    method: "POST",
    body: JSON.stringify(profile)
  });
}

export function deleteBusinessHoursProfile(profileId: number) {
  return apiRequest<{ deleted: boolean; profile_id: number }>(
    `/api/admin/business-hours/profiles/${profileId}`,
    {
      method: "DELETE"
    }
  );
}

export function getWorkflowRules() {
  return apiRequest<{ rules: WorkflowRule[] }>("/api/admin/workflow-rules");
}

export function getWorkflowRuleWindows() {
  return apiRequest<{ windows: WorkflowRuleWindow[] }>("/api/admin/workflow-rules/windows");
}

export function getWorkflowRuleAffectedTickets(ruleId: number) {
  return apiRequest<{ tickets: RuleAffectedTicket[] }>(
    `/api/admin/workflow-rules/${ruleId}/affected`
  );
}

export function createWorkflowRule() {
  return apiRequest<{ rule: WorkflowRule | null }>("/api/admin/workflow-rules", {
    method: "POST"
  });
}

export function updateWorkflowRule(
  ruleId: number,
  payload: {
    builder_mode?: string | null;
    config?: Record<string, unknown> | null;
    description: string;
    false_tag_id: number | null;
    is_enabled: boolean;
    name: string;
    true_tag_id: number | null;
  }
) {
  return apiRequest<{ rule: WorkflowRule | null }>(`/api/admin/workflow-rules/${ruleId}`, {
    method: "PUT",
    body: JSON.stringify(payload)
  });
}

export function duplicateWorkflowRule(ruleId: number) {
  return apiRequest<{ rule: WorkflowRule | null }>(
    `/api/admin/workflow-rules/${ruleId}/duplicate`,
    {
      method: "POST"
    }
  );
}

export function deleteWorkflowRule(ruleId: number) {
  return apiRequest<{ deleted: boolean; rule_id: number }>(
    `/api/admin/workflow-rules/${ruleId}`,
    {
      method: "DELETE"
    }
  );
}

export function restoreDefaultWorkflowRule() {
  return apiRequest<{ rule: WorkflowRule | null }>(
    "/api/admin/workflow-rules/restore-default",
    {
      method: "POST"
    }
  );
}
export async function generateIndicVoiceAudio(text: string, language = "", description = "") {
  let lastError: Error | null = null;

  for (const baseUrl of buildApiBaseCandidates()) {
    try {
      const response = await fetch(buildApiUrl("/api/support/voice/synthesize", baseUrl), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, description, language })
      });

      if (!response.ok) {
        const message = resolveApiErrorMessage(await response.text(), response.status);
        throw new Error(message);
      }

      return await response.blob();
    } catch (error) {
      lastError = error instanceof Error ? error : new Error("Voice synthesis failed.");
    }
  }

  throw lastError ?? new Error("Voice synthesis failed.");
}
