export type ApiActivityStatus = "pending" | "completed" | "failed";

export interface ApiActivityRecord {
  completedAt?: string;
  durationMs?: number;
  endpoint: string;
  error?: string;
  id: string;
  method: string;
  request: unknown;
  response?: unknown;
  startedAt: string;
  status: ApiActivityStatus;
  transport: "json" | "stream";
}

const STORAGE_KEY = "acrobuild-chat-api-activity-v1";
const ACTIVITY_EVENT = "acrobuild-api-activity";
const MAX_RECORDS = 20;

function readRecords(): ApiActivityRecord[] {
  if (typeof window === "undefined") return [];
  try {
    const parsed = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "[]");
    if (!Array.isArray(parsed)) return [];

    const compacted = (parsed as ApiActivityRecord[])
      .filter((record) => !String(record.error || "").toLowerCase().includes("exceeded the quota"))
      .slice(0, MAX_RECORDS)
      .map(compactRecord);

    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(compacted));
    } catch {
      window.localStorage.removeItem(STORAGE_KEY);
    }

    return compacted;
  } catch {
    try {
      window.localStorage.removeItem(STORAGE_KEY);
    } catch {
      // Corrupt activity history must not affect the chatbot.
    }
    return [];
  }
}

function compactRequest(request: unknown) {
  const value = (request || {}) as Record<string, unknown>;
  return {
    article_hint_url: value.article_hint_url ?? "",
    conversation_id: value.conversation_id ?? "",
    issue: value.issue ?? "",
    issue_type: value.issue_type ?? "",
    limit: value.limit ?? 3,
    prefer_fast_response: value.prefer_fast_response ?? false,
    prefer_qwen_response: value.prefer_qwen_response ?? true
  };
}

function compactDataApiCalls(calls: unknown) {
  if (!Array.isArray(calls)) return [];
  return calls.slice(0, 30).map((call) => {
    const value = (call || {}) as Record<string, unknown>;
    return {
      cache_hit: value.cache_hit ?? false,
      duration_ms: value.duration_ms ?? 0,
      endpoint: value.endpoint ?? "",
      error: value.error ?? "",
      id: value.id ?? "",
      method: value.method ?? "GET",
      params: value.params ?? {},
      provider: value.provider ?? "",
      response_summary: value.response_summary ?? {},
      status: value.status ?? "completed"
    };
  });
}

function compactResponse(response: unknown) {
  const value = (response || {}) as Record<string, unknown>;
  return {
    agent_mode: value.agent_mode ?? "",
    answer: value.answer ?? "",
    assist_error: value.assist_error ?? "",
    confidence_label: value.confidence_label ?? "",
    data_api_calls: compactDataApiCalls(value.data_api_calls),
    rag_evaluation: value.rag_evaluation,
    retrieval_mode: value.retrieval_mode ?? "empty",
    source_label: value.source_label ?? "",
    source_status: value.source_status ?? "fallback",
    used_llm: value.used_llm ?? false
  };
}

function compactRecord(record: ApiActivityRecord): ApiActivityRecord {
  return {
    ...record,
    request: compactRequest(record.request),
    response: record.response === undefined ? undefined : compactResponse(record.response)
  };
}

function writeRecords(records: ApiActivityRecord[]) {
  if (typeof window === "undefined") return;

  const compacted = records.slice(0, MAX_RECORDS).map(compactRecord);
  const recordLimits = [MAX_RECORDS, 10, 5, 1];
  let saved = false;

  for (const limit of recordLimits) {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(compacted.slice(0, limit)));
      saved = true;
      break;
    } catch {
      // Retry with fewer compact records when the browser storage quota is full.
    }
  }

  if (!saved) {
    try {
      window.localStorage.removeItem(STORAGE_KEY);
    } catch {
      // Activity persistence is optional and must never break the chat request.
    }
  }

  window.dispatchEvent(new CustomEvent(ACTIVITY_EVENT));
}

export function getApiActivity() {
  return readRecords();
}

export function beginApiActivity(input: Pick<ApiActivityRecord, "endpoint" | "method" | "request" | "transport">) {
  const id = `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
  const record: ApiActivityRecord = {
    ...input,
    id,
    startedAt: new Date().toISOString(),
    status: "pending"
  };
  writeRecords([record, ...readRecords()]);
  return id;
}

export function finishApiActivity(id: string, response: unknown) {
  const completedAt = new Date();
  writeRecords(readRecords().map((record) => record.id === id ? {
    ...record,
    completedAt: completedAt.toISOString(),
    durationMs: completedAt.getTime() - new Date(record.startedAt).getTime(),
    response: compactResponse(response),
    status: "completed"
  } : record));
}

export function failApiActivity(id: string, error: unknown) {
  const completedAt = new Date();
  writeRecords(readRecords().map((record) => record.id === id ? {
    ...record,
    completedAt: completedAt.toISOString(),
    durationMs: completedAt.getTime() - new Date(record.startedAt).getTime(),
    error: error instanceof Error ? error.message : String(error),
    status: "failed"
  } : record));
}

export function clearApiActivity() {
  writeRecords([]);
}

export function subscribeToApiActivity(listener: () => void) {
  if (typeof window === "undefined") return () => undefined;
  window.addEventListener(ACTIVITY_EVENT, listener);
  window.addEventListener("storage", listener);
  return () => {
    window.removeEventListener(ACTIVITY_EVENT, listener);
    window.removeEventListener("storage", listener);
  };
}