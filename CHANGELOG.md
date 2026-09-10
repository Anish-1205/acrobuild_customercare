# Changelog

Running log of deliberate changes to this repo. Newest first. Each entry:
what problem, the root cause, the exact files/functions touched, and how it
was verified.

Timestamps are local (Asia/Kolkata, +0530).

---

## 2026-09-10 18:30 — Bytecode reconstruction: Phases 1–2

**Context:** The original source for the two `*_runtime.pyc` modules is
unrecoverable. Rebuilding in phases; see `docs/RECONSTRUCTION_STATUS.md`.

**Phase 1 — documentation (read-only):** `DECOMPILED_MAP.md` — full function
inventory of both modules (26 + ~150 functions), module constants, entry-point
flow, and provenance (the big file was originally a food-catalogue bot). Baked-in
constants located to the bytecode line.

**Phase 2 — constant patch:** `scripts/patch_runtime_constants.py` rewrites two
constants inside `build_ai_support_answer` / `stream_ai_support_answer_events`:
- `temperature 0.35 → 0.1` on the property/factual generation call (reduces
  fabricated figures)
- `agent_mode "gemini" → "remote_llm"` (correct `AGENT_MODE_ENUM` value)

Output is `services/ai_agent_service_runtime.patched.pyc`; the original `.pyc` is
never written (md5 unchanged). `services/ai_agent_service.py` loads the patched
copy when present.

**Verification:** `pytest tests/` → **634 passed, 43 subtests** (identical to
baseline). `ruff` clean. Patched-module import confirms `0.35`/`"gemini"` gone,
`0.1`/`"remote_llm"` present.

---

## 2026-09-10 17:05 — Repeatable prompt evaluation + failure analysis

**Problem:** The only chatbot quality signal was a stale spreadsheet
(`...prompt_evaluation.xlsx`, 66.5% pass). The eval script couldn't be re-run —
`extract_cases()` read a PDF from a hardcoded path that exists on no current
machine.

**Changes:**
- `scripts/eval_prompts.json` (new) — the 200 prompts (id/category/prompt/
  expected), extracted from the cached results, version-controlled.
- `scripts/evaluate_chatbot_prompts.py` — `extract_cases()` now loads that JSON;
  dropped the `pypdf` dependency in this script. `API_URL`, worker count,
  timeout, and all paths are env-overridable (`EVAL_*`).
- `docs/EVAL_FINDINGS.md` (new) — analysis of the 67 failures.
- `SETUP_AND_USAGE.md` — "Running the prompt evaluation" section.

**Findings:** 41 of 67 failures were `ReadTimeout` (60 s) against the RunPod
*serverless* Sarvam endpoint — an infra/latency problem, not answer quality.
16 were wrong-document dumps, 4 wrong refusals, ~6 genuinely wrong — all in the
compiled-blob answer path, so blocked on `.pyc` source recovery. Priority order:
fix endpoint latency → re-measure → fix content.

**Verification:** `extract_cases()` returns 200 contiguous cases; `judge()` smoke
check passes; `ruff` clean. Full 200-prompt run not executed here (hits a paid
remote endpoint) — left for the owner to run once the provider latency is
addressed.

---

## 2026-09-10 16:20 — Dependency security triage

**Problem:** `pip-audit` reported 42 known vulnerabilities across 5 packages;
none had been triaged.

**Findings & actions** (full detail in `requirements/SECURITY_ADVISORIES.md`):
- `pip` (7) — dev tooling only. **Fixed:** upgraded venv pip 25.0.1 → 26.2.1.
- `ecdsa` PYSEC-2026-1325 — **not reachable**; auth uses HS256/HMAC
  (`services/auth_service.py:14`), the ECDSA path is never called. No upstream fix.
- `transformers` (~30), `accelerate`, `protobuf` — local-ML stack only, not on
  the live (remote-provider) request path. Nearly all require loading an
  attacker-controlled model; this app runs a fixed self-hosted Qwen. **Deferred
  on purpose:** bump + regression-test these alongside enabling the local
  fallback LLM.
- No package was found unused; nothing removed.

**Verification:** `pip-audit` re-run shows the 7 `pip` findings cleared; the
remaining findings are documented with reachability analysis.

---

## 2026-09-10 15:40 — Validation of pending-upgrade batch

**Problem:** The durable-history, runtime-guard, provider-fallback, and
workflow-UI changes were in the tree but their verification lines still read
"pending" / "in progress".

**Verification (run 2026-09-10):**
- `pytest tests/` → **634 passed**, 43 subtests (was 625; +9 in
  `tests/test_pending_upgrades.py` covering browser isolation, retention, size
  cap, deletion, HTTP restore/delete integration, incompatible runtime header,
  provider-fallback metadata, and stream provider-stability).
- `ruff check .` clean.
- `tsc --noEmit` clean · `eslint` clean (7 pre-existing `any` warnings, none new)
  · `vitest run` → 3 passed · `vite build` succeeded
  (`dist/assets/index-*.js` 495.90 kB / 130.41 kB gzip).

**Still outside the repo:** original source recovery for the two `.pyc`
runtimes; a ClamAV binary + definitions on the host (`CLAMSCAN_PATH`); Python
dependency-advisory triage; a live remote-provider fallback endpoint. All are
documented as fail-closed / config-gated above.

---

## 2026-09-10 — Knowledge-import scan coverage

**Problem:** Remote PDFs and HTML bypassed the scanner hook because validation ran only in the generic-file branch.

**Changes:** `services/knowledge_ingestion_service.py` scans remote content before any parser, including PDF/HTML, and validates PDFs selected by MIME type. The automation page is now linked from the manager toolbar.

**Verification:** Scanner failure-path and PDF-signature tests added below; no ClamAV executable was found on PATH. Production remains fail-closed until an administrator supplies `CLAMSCAN_PATH` and virus definitions.

---

## 2026-09-10 — Workflow review UI

**Changes:** `src/pages/AutomationPage.tsx`, `src/automation.css`, `src/lib/api.ts`, and `src/App.tsx` expose overdue tickets, available agent capacity, and explicit preview/confirm actions at `/admin/automation` and `/owner/automation`. Server-side role checks, proposal expiry, and changed-ticket rejection remain authoritative.

**Verification:** `tsc`/`eslint`/`vite build` pass; existing `vitest` suite (3) still green. Dedicated interaction tests not yet added. This is a review workflow, not unattended scheduling or execution of refunds.

---

## 2026-09-10 — Configurable provider fallback

**Changes:** `services/provider_resilience_service.py`, `qwen.py`, and `services/answer_evidence_service.py` now support a configured alternate provider, routing based on previously observed latency, and explicit actual-provider/fallback metadata. Streaming never switches providers after emitting text.

**Configuration:** `LLM_FALLBACK_PROVIDER=qwen|sarvam`; optional `LLM_FALLBACK_LATENCY_MS`. An unset alternate preserves the configured provider. Both providers must be installed/configured to enable fallback.

**Verification:** `tests/test_pending_upgrades.py::test_fallback_reports_actual_provider` and `::test_stream_does_not_mix_providers` pass (mocked provider failure, actual-provider metadata, stream provider-stability). No remote endpoint was provisioned or changed.

---

## 2026-09-10 — Pending upgrades: durable history and runtime compatibility

**Problem:** Conversation state had no durable implementation, and loading the recovered bytecode with another Python version could crash the process.

**Changes:**
- `services/conversation_store_service.py` — cookie-scoped SQLite history, two-hour retention, a 60-message cap, atomic appends, and conversation deletion.
- `services/runtime_compatibility_service.py`, both runtime loaders — validate the Python bytecode header before unmarshalling.

**Integration:** `routers/assist.py` restores history for both chat endpoints, stores verified final replies, sets an HttpOnly conversation cookie, and exposes cookie-scoped deletion. No history is restored using a conversation ID alone.

**Verification:** `tests/test_pending_upgrades.py` (9 tests) passes — browser isolation, restoration, retention, size limits, deletion, HTTP restore/delete integration, and incompatible runtime headers. `conversation_turns` table + expiry index added as migration 3. Original source restoration remains pending; the compatibility guard is not source recovery.

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
