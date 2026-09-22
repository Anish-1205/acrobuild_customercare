# Project assessment — Acrobuild customer support agent

Whole-project review as of 2026-09-10. Honest read of strengths and weaknesses.

**One-line summary:** a working, reasonably well-tested support chatbot +
admin workspace for one company, held back by two unmodifiable compiled blobs,
several oversized files, and no production deployment story.

---

## The stack

- **Backend:** FastAPI + SQLite, ~29k lines Python. Chat orchestration in
  `graph/`, business logic in `services/`, HTTP in `routers/` + `api_context.py`.
- **Frontend:** React + Vite admin workspace + customer chat widget, ~23k lines TS/TSX.
- **AI:** local Qwen or remote Sarvam (swappable), Haystack RAG, sentence-transformers
  search, AI4Bharat translation + TTS for Indian languages.
- **CI:** GitHub Actions runs pytest, ruff, mypy, pip-audit, and the frontend
  build/lint/format/audit on every push and PR.

---

## Positives

### Product / behaviour
- **It works end to end.** Customer widget → streaming answer → admin inbox →
  ticketing, all runnable locally.
- **Grounding guardrails.** Property answers with specific figures but no live-data
  citation are replaced with a safe message + handoff flag
  (`_enforce_live_property_data`). Reduces confident hallucination.
- **Honest RAG metrics.** `rag_evaluation_service` reports `not_available` instead
  of inventing recall/MRR numbers it can't compute online.
- **Multilingual handling** including romanised Tamil/Telugu ("Tanglish") detection
  and language-matching fixes.
- **Durable conversation history** — SQLite-backed, cookie-scoped, 2h retention,
  survives worker restarts.

### Engineering
- **Good test breadth on the backend** — 634 tests + 43 subtests, covering chat
  routing, entity resolution, security boundaries, migrations, RAG scoring.
- **Real CI gate**, not just local scripts.
- **Structured observability** — request IDs, per-turn logs, provider/latency
  metadata, rotating log files, JSON option.
- **Numbered transactional migrations** with indexes (`migration_service.py`).
- **Security baseline in place** — cookie sessions + CSRF on mutating routes,
  global Origin check, request size limits, rate limiting, HMAC-signed auth,
  fail-closed upload scanning hook.
- **Provider abstraction** — swap local/remote LLM by env var; fallback + latency
  routing wired.
- **Documentation discipline** — `AGENTS.md`, `CHAT_FLOW.md` (with diagram),
  `SETUP_AND_USAGE.md`, a strict `CHANGELOG.md`, an upgrade ledger.
- **Secrets not committed** — `.env`, `*.db`, `data/` all gitignored.

---

## Negatives

### Critical
- **Two compiled `.pyc` blobs with no source.**
  `services/ai_agent_service_runtime.pyc` (322 KB) and
  `graph/haystack_conversation_pipeline_runtime.pyc` hold core answer-generation
  logic. They are committed on purpose because the source is lost.
  Consequences:
  - Can't review, audit, or security-scan the most important code path.
  - Can't change baked-in constants — e.g. `temperature=0.35` on factual property
    answers (a hallucination risk) and a stray `"gemini"` telemetry label.
  - Hard-locks the whole app to **exactly Python 3.12**. A guard now fails
    cleanly instead of segfaulting, but the constraint remains.
  - This is the single biggest risk in the project.

### High
- **No deployment story.** No Dockerfile, no container, no process manager, no
  worker config. "Running it" means `uvicorn --reload` and a VS Code launch
  config. Nothing is production-shaped yet.
- **SQLite is the only datastore.** One 8 MB file, `BEGIN IMMEDIATE` write locks
  serialise all writers. Fine for a demo or a handful of agents; it will not hold
  up under real concurrent support-desk load.
- **Type checking is effectively off.** `mypy` is configured to check just 2
  files, with `follow_imports = skip` and `ignore_missing_imports`. ~52k lines
  are unchecked.
- **Lint is syntax-only.** `ruff` selects just `E9/F63/F7/F82` — undefined names
  and broken syntax. No bug-class, style, or security lint (no `S` rules, no bandit).

### Medium
- **Oversized files.** `services/database_service.py` 3077 lines,
  `api_context.py` 1352 lines (middleware + business logic + 30-odd functions in
  one module), `src/pages/CustomerHomePage.tsx` 3865 lines,
  `AdminInboxPage.tsx` 2481, `KnowledgeBasePage.tsx` 2134. Slow to read, review,
  and test; easy place for bugs to hide.
- **Frontend has almost no tests.** 3 tests against ~23k lines of TSX. The big
  pages have zero component coverage.
- **Local ML dependency stack carries ~35 known advisories**
  (`transformers`, `accelerate`, `protobuf`). Documented and not on the live
  path today, but must be cleared before any local-model production use.
- **Malware scanning not configured.** Uploads are blocked in production until
  ClamAV + definitions are installed.
- **Single-tenant and bespoke.** Hardcoded to one company, a 1.1 MB
  `acrobuild_all_company_data.txt` checked into the repo, a fixed CS API. This is
  a custom deployment, not a reusable product.

### Low
- **Repo bloat.** Compiled blobs, a logo PNG, a 47 KB xlsx, the 1.1 MB data file —
  all in git history.
- **Seed credentials in code.** `demo@123` for seeded users in
  `database_service.py`. Fine for dev, must not reach production.
- **Auth is basic.** HS256 JWT + cookies, three roles, no MFA for staff, no
  visible password-rotation policy.
- **Large uncommitted surface.** Several sessions of work sit in the working tree;
  `CHANGELOG` notes many changes were never committed. Risk of loss.

---

## If this were going to production, in order

1. Recover or reconstruct the two `.pyc` sources (or accept them as a permanent,
   documented black box with extra integration tests around them).
2. Containerise + add a real process/worker setup and a deploy pipeline.
3. Decide the datastore: keep SQLite only if load is genuinely small, else move
   to Postgres.
4. Turn on real `mypy` coverage and a meaningful `ruff`/security ruleset; fix the
   fallout.
5. Clear the ML dependency advisories and stand up ClamAV.
6. Break up the top 5 largest files; add frontend component tests for the widget
   and the inbox.
7. Rotate all seed credentials; review the staff auth model.

---

## Bottom line

Solid prototype-to-pilot quality. The recent work (observability, security
baseline, durable history, provider fallback, migrations) genuinely moved it
forward and it is well-tested on the backend. It is **not** production-ready,
and the lost `.pyc` source is a structural problem that limits everything
downstream of it.
