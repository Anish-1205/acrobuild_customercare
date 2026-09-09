# Changelog

Running log of deliberate changes to this repo. Newest first. Each entry:
what problem, the root cause, the exact files/functions touched, and how it
was verified.

Timestamps are local (Asia/Kolkata, +0530).

---

## 2026-09-09 19:29 — Fix: bot replied in romanised Tamil/Telugu instead of English

**Problem:** After heavy multilingual testing, the assistant answered plain
English questions ("what is the properties you offer?") in romanised Tamil
("Naanga residential properties offer panrom…").

**Root cause:** the conversation history sent to the LLM contained romanised
non-English turns (earlier test messages + the bot's own Tanglish replies). The
Sarvam model (Indian-multilingual) mirrors the conversation's dominant language.
`answer_matches_response_language` / `localize_ai_answer` (inside the
`ai_agent_service_runtime.pyc` blob) only detect non-Latin scripts, so
transliterated Tamil/Telugu slipped through unfixed.

**Changes — `graph/main_orchestrator.py`:**
- `_looks_english(text)` — new heuristic: non-Latin script, transliterated
  agglutination (`projects-a`, `Ambernath-la`), or ≥15 % romanised-Indic marker
  words → not English.
- `_recent_history(messages, current_issue)` — when the current message is
  English, drop non-English turns from the history handed to the model (full
  store untouched). Applied at all 5 LLM call sites.
- `_generation_issue(issue)` — appends
  `"[Note: the customer is writing in English. Reply in English.]"` to the issue
  passed to the answer-writing blob functions (`build_ai_support_answer`,
  `stream_ai_support_answer_events`) when the message is English.
- Added "reply in the user's language; English → English" to the two general-LLM
  system prompts.
- `LLM_HISTORY_TURNS` semantics unchanged.

**Verified:** `pytest` 625 pass · `ruff` clean. Repro (English question +
romanised-Tamil history) now answers in English; a romanised-Telugu question
still gets a Telugu reply (not force-converted); clean-English conversations
unaffected.

**Follow-ups:** blob answer-quality artifacts seen alongside this ("Here is the
relevant information:", repeated "mee question ki verified answer:") are
pre-existing and unrelated — need the blob source.

---

## 2026-09-09 — Session: run the app, fix login/chat, add logging, chatbot fixes

Three workstreams in one session. Nothing here was committed — all changes are
in the working tree.

### 1. Make the app run (blockers found while starting it)

**1a. Backend crashed on import (`WinError` access violation / exit 139)**
- Cause: the global interpreter is Python 3.14; `services/ai_agent_service.py`
  and `graph/haystack_conversation_pipeline.py` `marshal.load` a `.pyc`
  compiled for Python 3.12 (`ai_agent_service_runtime.pyc`,
  `haystack_conversation_pipeline_runtime.pyc`) with the version header
  stripped, so a mismatched interpreter segfaults instead of erroring.
- Fix: none in code — the project ships a working `.venv` (Python 3.12) with
  all deps. Run with `.venv/Scripts/python.exe -m uvicorn app:api --reload`.
- Documented the interpreter requirement; no file change.

**1b. `POST /auth/login` returned 500**
- Cause: `services/auth_service.py:51` raises
  `RuntimeError("AUTH_SECRET_KEY must be configured with at least 32 characters.")`
  and `AUTH_SECRET_KEY` was absent from `.env`.
- Fix: **`.env`** — added `AUTH_SECRET_KEY` (48-byte `secrets.token_urlsafe`)
  and `ACROBUILD_CORS_ORIGINS` (localhost + 127.0.0.1 for ports 5173–5175;
  default only trusted `:5173`).
- Seed logins: `owner@acrobuild.com` / `admin@acrobuild.com` /
  `agent@acrobuild.com`, password `demo@123` (from
  `services/database_service.py:2444`); only `status="Active"` rows can log in.

**1c. Stale Vite dev server served a blank page**
- Cause: an old `vite` process on `:5173` had a broken client runtime
  (`__SERVER_FORWARD_CONSOLE__ is not defined` in `@vite/client`).
- Fix: none in code — killed the stale process, restarted `npm run dev`.

### 2. Customer chat was broken (two real bugs)

**2a. Customer chat `POST /api/support/assist` → 403 for logged-in users**
- Cause: `api_context.py` middleware `enforce_admin_route_auth` ran a **global
  CSRF check on every non-GET request** whenever a `workspace_session` /
  `workspace_refresh` cookie was present. A staff member logged into the
  workspace who then opened the customer site could not use the public chat
  (the customer frontend correctly sends no `x-csrf-token`).
- Fix: **`api_context.py`** — CSRF enforcement scoped to workspace-mutating
  routes only: `path.startswith("/api/admin/")`, `"/admin/"`, or
  `path in {"/auth/logout", "/auth/refresh"}` (new `csrf_protected` guard).
  The Origin check stays global.
- Verified: `POST /api/support/assist` with a workspace cookie present →
  200 (was 403); admin routes still 403 without token, 422 with token.

**2b. Chat white-screened the whole page on a normal reply**
- Cause: `graph/main_orchestrator.py` streams `{"type": "progress",
  "stage": "generating"}`. `streamSupportAssist` in **`src/lib/api.ts`**
  treated **any** non-`delta` event as the terminal `done` event and read
  `.response` off it → `onDone(undefined)` → `assistResponse.answer` threw in
  `CustomerHomePage` → React unmounted the tree (no error boundary).
- Fix: **`src/lib/api.ts`** — `streamSupportAssist` only treats
  `type in {"done","error"}` **with** a `response` as terminal; other event
  types (e.g. `progress`) are ignored and streaming continues. Trailing-buffer
  parse guarded the same way.
- Verified: headless Chrome — typed "hi" on `/home`, assistant replied, no
  white screen.

### 3. Observability + chatbot correctness/perf

**3a. Structured logging system (new)**
- **`services/observability.py`** (new) — `configure_logging()` (idempotent,
  env-driven), a per-request `request_id` `ContextVar` + logging filter,
  plain + JSON formatters, console handler + `RotatingFileHandler`
  (`logs/chatbot.log`, 5 MB × 5), helpers `preview` / `mask_email` / `kv` /
  `StageTimer` / `get_logger`.
- **`api_context.py`** — calls `configure_logging()` at import; new outermost
  middleware `attach_request_id_and_log` stamps `X-Request-ID`, logs
  `request in` / `request out` for chatbot routes.
- **`routers/assist.py`** — `turn start` / `turn branch` / `turn done`
  per-turn logs with metadata; per-stream-event logging; rebinds `request_id`
  inside the streaming generator.
- **`graph/main_orchestrator.py`** — logs branch decision
  (`general_llm` / `property` / `rag_pipeline`), resolved-from-context issue.
- **`qwen.py`** — `llm call` / `llm reply` / `llm stream done` with provider,
  model, latency, size; warnings on failure.
- **`services/internal_api_log_service.py`** — every data-API call also emitted
  to the `chatbot.dataapi` logger (WARNING on failure).
- **`.env`** — `LOG_LEVEL`, `CHATBOT_LOG_LEVEL`, `LOG_FILE`, `LOG_JSON`.
- **`.vscode/launch.json`** + **`.vscode/settings.json`** (new) — "FastAPI:
  debug chatbot" debugpy config (`justMyCode=false`, forces DEBUG logs),
  "Pytest: current file"; interpreter pinned to `.venv`.
- **`.gitignore`** — added `logs/`.
- **`SETUP_AND_USAGE.md`** — "Debugging the Chatbot" section.

**3b. Seven defects found in live traces, all fixed**

| # | Problem (log evidence) | Fix — file |
|---|---|---|
| 1 | Hallucinated property facts passed through (`"Flat 1108 = ₹3,500/sqft"`, `matched_chunks=0`) | **`api_context.py`** `_enforce_live_property_data`: new `_PROPERTY_CLAIM_RE` / `_HEDGE_RE`; a property answer with specific figures and **no** `company_api` chunk (or a figure next to a hedge) is replaced with the live-data-unavailable message + `handoff_recommended=True`, `source_status="unverified"`. `property answer rejected` logged. |
| 2 | `/api/cs/company` + `/api/cs/projects` fetched 2–4× per turn | **`services/internal_api_log_service.py`**: `begin/end_data_api_trace` carry a `turn_cache` dict; `turn_cache_get/set` helpers. **`services/acrobuild_company_service.py`** `_cached_request`: identical `(path, params)` within one turn reuse the first live fetch (`cache_hit=True`, `response_summary.kind="turn_cache"`, 0 ms). `_enforce_live_property_data` `non_live_calls` filter updated to not treat turn-cache hits as "non-live". |
| 3 | LLM calls hung 60–70 s (httpx timeout is per-read, not wall-clock) | **`sarvam_client.py`**: `SARVAM_DEADLINE_SECONDS` (default 45) — `monotonic()` deadline in `.stream()` loop and per-call `timeout` on `.chat()`; `httpx.Timeout(total, connect=10)`. Overrun raises → existing fallback path. |
| 4 | `temperature=0.35` on factual property answers | Cannot fix directly — literal baked in `ai_agent_service_runtime.pyc` (no env). Mitigated by #1 gate + the hedge check. **See "Open items".** |
| 5 | Every turn `conversation_id=-`; history to model grew unbounded (`history_turns=32`, `+4600` char prompts) | **`src/pages/CustomerHomePage.tsx`**: `conversationIdRef = useRef(crypto.randomUUID())`, passed to `streamSupportAssist` + `getSupportAssist`, rotated on conversation reset. **`services/observability.py`**: `conversation_id` `ContextVar` + `set/get_conversation_id`, added to log filter + JSON formatter. **`routers/assist.py`**: binds it per turn. **`graph/main_orchestrator.py`**: `_recent_history()` + `LLM_HISTORY_TURNS` (default 10) — full 60-msg store kept for context resolution, only the model prompt is trimmed (applied to `_build_live_general_llm_response`, the stream Qwen call, and the `conversation_messages=` arg to the blob functions). |
| 6 | `agent_mode="gemini"` in telemetry (no Gemini configured) | **`services/observability.py`**: `normalize_agent_mode()` + `AGENT_MODE_ENUM` (`remote_llm` / `local_llm` / `retrieval` / `grounded` / `fallback` / `live_data_error`). Applied in `_enforce_live_property_data` and both orchestrator result assemblies (`graph/main_orchestrator.py`). |
| 7 | RAG step a black box when it returns nothing | **`graph/main_orchestrator.py`**: `_log_retrieval()` — DEBUG dump of `retrieval_mode`, matched chunk ids + scores from the payload; `WARNING "property turn retrieved no evidence"` when a property turn ends with zero chunks. |

- **`.env`** — `SARVAM_DEADLINE_SECONDS=45`, `SARVAM_TIMEOUT_SECONDS=120`,
  `LLM_HISTORY_TURNS=10`.
- **`SETUP_AND_USAGE.md`** — agent_mode enum table, new knobs, grep recipes.

### Verification (whole session)

- `ruff check .` clean · `tsc -p tsconfig.json --noEmit` clean ·
  `eslint` clean (1 pre-existing unrelated `any` warning in `src/lib/api.ts`).
- `pytest tests/` → **625 passed** (43 subtests). `npm test` → **3 passed**.
- Live curl + headless-Chrome checks per fix (documented above and in
  `.claude/plans/spicy-splashing-scroll.md`).

### Open items

- **`temperature=0.35` for property answers** cannot be changed without the
  source of `services/ai_agent_service_runtime.pyc` (a marshalled blob;
  `temperature=0.35` and the `"gemini"` label are literals inside it, no env
  override — confirmed by disassembly). The header says "Recovered runtime
  loader"; an earlier traceback referenced `E:\customer-support-agent`. If that
  source exists, un-blobbing the property-answer generator would also unlock
  real RAG-internal logging (#7) and remove the `gemini` literal at the root.
- Plan document for workstream 3: `.claude/plans/spicy-splashing-scroll.md`.

---

## Template for future entries

```
## YYYY-MM-DD HH:MM — <short title>

**Problem:** <what was wrong / what was requested>
**Root cause:** <if a bug>
**Changes:**
- `path/to/file.py` — <function/area>: <what changed and why>
**Verification:** <commands run + result>
**Follow-ups:** <anything deferred>
```
