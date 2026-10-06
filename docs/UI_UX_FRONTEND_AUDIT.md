# UI/UX frontend audit (Phase 0)

Audit date: 2026-10-05. Branch: `work/2026-10-01-phase1-chatbot-stabilization`.
Scope: inventory of the current frontend only. No product code was changed and
nothing here is a redesign proposal.

Evidence labels used throughout:

- **VERIFIED** — traced in current source.
- **PARTIAL** — skimmed or inferred from imports/markers; needs a full read before relying on it.
- **DOC ONLY / STALE** — stated in documentation but not matched by source.
- **NOT IMPLEMENTED** — no reachable implementation in current source.

The audit reflects the working tree, which had one uncommitted change in
`src/pages/CustomerHomePage.tsx` before the audit started. That change was
read as-is and not touched. It removes the `startProjectsFlow` call from the
welcome "Browse all projects" button, so the button now goes to the server
assist endpoint; this is why `startProjectsFlow` has no caller.

---

## 1. Executive summary

- One React 18 + Vite + react-router SPA serves the public site and the staff
  workspace. There is no UI library, no Tailwind, no CSS modules, and no icon
  package. Styling is global CSS, dominated by one 14,274-line `src/styles.css`.
- **37 route declarations**, of which only 15 render a screen (8 public paths,
  `/login`, 6 staff paths); the other 22 are redirects. Distinct screens: 7
  public, 1 login, 3 staff page components.
- The staff workspace is one component (`SharedManagerInboxPage` in
  `AdminInboxPage.tsx`) that swaps **13 distinct panel surfaces** by
  `?panel=` query string. Agents get a separate, near-duplicate inbox page.
- The sidebar is **not** part of the shell. `AppShell` is only a top bar; each
  inbox page renders its own sidebar. `/admin/automation` therefore has a top
  bar and no sidebar.
- Six page components are unreachable dead code (~6,900 lines), including the
  only UI for **workflow rules** and the modal-based knowledge base.
- The customer chat renders the server answer as plain text plus quick-reply
  buttons. It does not read `source_status`, evidence, or discovery fields, and
  it silently replaces a failed assist call with a locally generated article
  reply instead of an error state.
- A second, client-driven property flow (project → wing → floor → flat → price)
  exists alongside the server discovery flow and uses different endpoints.
- `SupportAssistResponse` lags the backend: `route`, `clarification_entity`,
  `pending_project_lookup`, `discovery_slots` and related fields are untyped,
  several enum unions are stale, and the evidence-chunk type does not match
  what property answers return.
- None of the chosen target tokens exist today: no Plus Jakarta Sans, no
  `#0055FF`, and `Inter` is declared but never loaded. Violet/purple and
  gradients are used widely (59 violet-family references, 210 gradients).

---

## 2. Source and authority notes

### Source read in full
`src/App.tsx`, `src/main.tsx`, `src/components/AppShell.tsx`,
`src/lib/api.ts`, `src/types.ts`, `src/contexts/RoleContext.tsx`,
`src/contexts/SearchContext.tsx`, `src/lib/roleNavigation.ts`,
`src/lib/conversationSession.ts`, `src/lib/widgetConfig.ts`,
`src/lib/apiActivity.ts`, `src/pages/CustomerHomePage.tsx`,
`src/pages/LoginPage.tsx`, `src/pages/AutomationPage.tsx`,
`src/pages/CSApiSettingsPage.tsx`, `src/pages/ApiActivityPage.tsx`,
`src/components/AcrobuildLogo.tsx`, `AttachmentPreview.tsx`,
`PhotoEmptyState.tsx`, `WorkspaceStatePanel.tsx`, `package.json`,
`index.html`, `vite.config.ts`, `vite.config.js`, `routers/properties.py`.

### Source read in part
`src/pages/AdminInboxPage.tsx` (constants, state, panel switch, full JSX),
`AIAgentPage.tsx` (imports, delete flow, full JSX), `CustomerLookupPage.tsx`
(component body), `DataApiLogsPage.tsx`, `src/lib/chatLanguage.ts`,
`routers/assist.py` (completion, both endpoints, history), `api_context.py`
(request models, authorization middleware, live-data guard),
`graph/main_orchestrator.py`, `services/discovery_slot_service.py`,
`services/property_clarification_service.py`,
`services/internal_api_log_service.py` (response builders only).

### Source scanned by pattern only (PARTIAL)
All CSS files (counted, not read rule by rule). `AgentInboxPage.tsx`,
`UsersPage.tsx`, `MacrosPage.tsx`, `ManageTagsPage.tsx`,
`BusinessHoursPage.tsx`, `ChatWidgetPage.tsx`, `TicketDashboardPage.tsx`,
`AdminAnalyticsPage.tsx` and `ArticlesPage.tsx` were read in full during the
Phase 0.5 pass (2026-10-05) and are now VERIFIED — see section 18.

### Docs read
`AGENTS.md`, `docs/README.md`, `docs/ARCHITECTURE.md`, `docs/CHAT_FLOW.md`,
`docs/PRODUCT_STATUS.md`.

### Missing or conflicting documentation

| Item | Finding |
| --- | --- |
| `docs/AI_CONTEXT.md`, `docs/PROJECT_MAP.md`, `docs/GAP_ANALYSIS.md` | **Confirmed (Phase 0.5):** none of the three exists under tracked `docs/`, which holds 9 Markdown files. A repo-wide filename search found exactly one hit — `data/merge-main/docs/AI_CONTEXT.md` — but `data/` is listed in `.gitignore` (`data/	data/merge-main`) and is not part of the tracked checkout; it is a local merge artifact, not current source. No `PROJECT_MAP*` or `GAP_ANALYSIS*` file exists anywhere in the working tree, tracked or not. |
| CHAT_FLOW: "`Browse all projects` creates a new conversation ID in the frontend" | True only for a server quick reply with `action: "browse_projects"`. The welcome-message button of the same name sends with reset disabled, and typing the phrase never rotates the ID on the client. |
| ARCHITECTURE: `roleNavigation.ts` "defines role-visible panels" | Incomplete. Sidebar membership is also hard-coded in `AdminInboxPage.tsx` (`workspacePanelItems`, `hiddenWorkspaceSidebarPanels`, and an inline admin-only filter). |
| PRODUCT_STATUS: staff workspace covers "workflow rules" | Backend routes and `api.ts` functions exist. No reachable UI renders them (section 4.4). |
| PRODUCT_STATUS: "Some frontend response types lag additive backend discovery fields" | Confirmed and broader than discovery (section 8). |
| ARCHITECTURE: conversation "browser-session scoped", history strips markers | Consistent with `conversationSession.ts` and the history endpoint. |
| `vite.config.js` | A transpiled twin of `vite.config.ts`. All npm scripts pass `--config vite.config.ts`; the `.js` copy is only picked up by `vite preview`, which passes no config flag. |

---

## 3. Frontend architecture map

### Stack
React 18.3, react-router-dom 7, Vite 8, TypeScript 5.6, Vitest 5 (jsdom).
Runtime dependencies are only `react`, `react-dom`, `react-router-dom`.
`@playwright/test` and `@axe-core/playwright` were added with the audit tooling;
no Playwright spec or config exists in the repository.

### Provider tree (`src/main.tsx`)
`RoleProvider` → `SearchProvider` → `BrowserRouter` → `App`. Three global
stylesheets are imported here for every route: `styles.css`,
`customer-home-refresh.css`, `customer-home-v2.css`.

### Routing (`src/App.tsx`)
All page components are `React.lazy`; the single `Suspense` fallback is
`<div className="app-loading">Loading page…</div>`.

- Public paths render with no layout route.
- `/login` renders `LoginPage`, or redirects an authenticated user to their role home.
- `/` is a layout route (`ProtectedAppShell` → `AppShell` + `<Outlet/>`).
  Unauthenticated access redirects to `/login`.

### State and data boundaries

| Boundary | Where | Persistence |
| --- | --- | --- |
| Staff session | `RoleContext` + HttpOnly cookies set by backend | `localStorage`: `supportConsole_authUser`, `supportConsole_userRole`, `rememberedEmail`. `supportConsole_accessToken` is actively removed. |
| Ticket search | `SearchContext` (query, suggestions, visible count) | Memory only. Written by inbox pages, read by `AppShell`. |
| Chat conversation ID, transcript, client property flow | `conversationSession.ts` | `sessionStorage`, 2-hour max age, keys `acrobuild.support.*.v1` |
| Chat widget appearance | `widgetConfig.ts` | `localStorage` `supportConsole_widgetConfig` — browser-local only, no backend |
| Chat request log | `apiActivity.ts` | `localStorage` `acrobuild-chat-api-activity-v1`, max 20 compacted records |
| Everything else | `useState` inside each page | None. No query cache, no global store. |

`src/lib/api.ts` is the only HTTP client. Every request sends
`credentials: "include"` and, when the `workspace_csrf` cookie exists, an
`X-CSRF-Token` header. A 401 on any non-auth path triggers one shared
`/auth/refresh` and a single retry.

---

## 4. Route, page and panel inventory

### 4.1 URL routes that render a screen

| Path | Component | Access | Notes |
| --- | --- | --- | --- |
| `/home` | `CustomerHomePage` (marketing variant) | Public | `isHomeDemoPage` branch |
| `/home/about` | `CustomerHomePage` (help-centre landing) | Public | The only path that renders search, popular questions, categories, get-support |
| `/home/categories/:categorySlug` | `CustomerHomePage` (category) | Public | |
| `/home/articles/:articleSlug` | `CustomerHomePage` (article) | Public | |
| `/home/project-support`, `/home/order-lookup` | `CustomerLookupPage` | Public | Same component on both paths |
| `/home/api-activity` | `ApiActivityPage` | **Public, unguarded** | Shows this browser's own chat request log |
| `/home/data-api-logs` | `DataApiLogsPage` | **Public, unguarded** | Same data source |
| `/login` | `LoginPage` | Public | |
| `/admin/workspace`, `/admin/inbox` | `AdminInboxPage` | admin | Same component; default panel differs |
| `/owner/inbox` | `OwnerInboxPage` → same shared component | owner | |
| `/agent/inbox` | `AgentInboxPage` | agent | Separate component |
| `/admin/automation`, `/owner/automation` | `AutomationPage` | admin / owner | No link to it anywhere in `src/`; URL only |

The chat panel is mounted on every `CustomerHomePage` variant and opens by
default (`isChatOpen` starts `true`). It is **not** mounted on
`CustomerLookupPage`, `ApiActivityPage`, or `DataApiLogsPage`.

### 4.2 Redirect-only routes (22)
`/` (index), `/admin`, `/owner`, `/agent`, `/admin/api-activity`,
`/admin/data-api-logs`, `/admin/cs-api-settings`, `/ai-agent`,
`/business-hours`, `/admin/analytics`, `/articles`, `/knowledge-base`,
`/workflow-rules`, `/chat-widget`, `/macros`, `/manage-tags`,
`/ticket-dashboard`, `/customer-portal`, `/order-track`, `/users`, `/chat-ui`,
`*`. All resolve through `getRolePanelPath` / `getRoleHomePath`. Any unknown
path under `/` lands on the role home. There is no 404 screen.

### 4.3 Workspace panels (rendered inside `SharedManagerInboxPage`)

Panel is chosen by `?panel=`; an unknown or disallowed value falls back to the
default (`ai-agent` on `/admin/workspace`, otherwise `inbox`).

| Panel id | Surface rendered | In sidebar | Sidebar label | Roles |
| --- | --- | --- | --- | --- |
| `inbox` | Three-column inbox (inline JSX) | Yes | Inbox | admin, owner |
| `ai-agent` | `AIAgentPage` | Via "Teach AI" group button | Teach AI | admin, owner |
| `knowledge-base`, `products`, `rules`, `shopping-assistant`, `support-actions` | **Also `AIAgentPage`** (aliases) | Hidden | — | admin, owner |
| `chat-widget` | `ChatWidgetPage` | Hidden; reached from a button in `AIAgentPage` | — | admin, owner |
| `analytics` | `AdminAnalyticsPage` | Yes | Analytics | admin, owner |
| `ticket-dashboard` | `TicketDashboardPage` | Yes | Dashboard | admin, owner |
| `articles` | `ArticlesPage` | Yes | Articles | admin, owner |
| `business-hours` | `BusinessHoursPage` | Yes | Open Hours | admin, owner |
| `macros` | `MacrosPage` | Yes | Saved Replies | admin, owner |
| `manage-tags` | `ManageTagsPage` | Yes | Manage Tags | admin, owner |
| `users` | `UsersPage` | Yes | Users | admin, owner |
| `api-activity` | `ApiActivityPage basePath="/admin"` | Yes | API activity | admin |
| `data-api-logs` | `DataApiLogsPage basePath="/admin"` | Yes | Data APIs | admin |
| `cs-api-settings` | `CSApiSettingsPage embedded` | Yes | CS API settings | admin |
| `order-track` | Placeholder block | **Unreachable** | — | — |

Totals: 19 ids in `WorkspacePanelId`, 18 accepted by the page, **13 distinct
surfaces**. Sidebar entries: 12 for admin, 9 for owner.

`order-track` is a valid id in `roleNavigation.ts` but is absent from
`workspacePanelItems`, so `getWorkspacePanelId` rejects it and the placeholder
branch can never render.

Naming is inconsistent between sidebar label and page heading: "Open Hours" /
"Business Hours", "Saved Replies" / "Macros", "Dashboard" / "Ticket Dashboard",
"Articles" / "AI Training Workspace".

### 4.4 Unreachable components (VERIFIED by import search across `src/`)

| File | Lines | What is lost while it stays unreachable |
| --- | --- | --- |
| `pages/KnowledgeBasePage.tsx` | 2,134 | Modal-based knowledge document management (8 `role="dialog"` blocks) |
| `pages/RulesPage.tsx` | 1,436 | The only workflow-rule builder UI |
| `pages/TicketSearchPage.tsx` | 863 | The only `<table>`-based ticket view besides Automation |
| `pages/ShoppingAssistantPage.tsx` | 193 | — |
| `pages/ProductsPage.tsx` | 169 | — |
| `pages/SupportActionsPage.tsx` | 141 | — |
| `components/TrainUi.tsx` | 207 | Used only by the dead pages above |
| `components/RoleSelector.tsx` | 46 | — |

Consequences for the redesign brief:

- **Workflow rules: NOT IMPLEMENTED as reachable UI.** The `rules` panel
  renders the Teach AI page. `api.ts` still exports nine workflow-rule
  functions with no live caller.
- **Knowledge document management** is reachable only through the simplified
  Teach AI page (upload, URL import, link deletion). Edit and per-document
  views exist only in the dead page.
- `public/images/real-world/ai-training.png` is referenced only from dead code.

Dead code inside reachable files (VERIFIED in `CustomerHomePage.tsx`):
`startProjectsFlow`, `resetChatHome`, `homeDemoHeroImage`,
`homeDemoSceneCards`, `showBackControl`, `supportsSpeechRecognition`, and the
voice-call overlay (see section 14).

---

## 5. Role and navigation audit

### Roles
`admin`, `owner`, `agent` (`RoleId`). The role comes from the server session
(`/auth/me`, `/auth/login`). `setRole` refuses any value other than the
current user's own role, so there is no client-side role switching.

### Guards

| Guard | Behaviour |
| --- | --- |
| `ProtectedAppShell` | Not authenticated → `/login` |
| `RoleRoute` | Not authenticated → `/login`; wrong role → that role's home |
| `RoleRedirect` | Not authenticated → `/login`; else role panel path or role home |
| `LoginRoute` | Authenticated → role home |
| Panel access | `canRoleAccessPanel(role, panel)`; disallowed → default panel, no message shown |

### Home destinations

| Role | Home | Default panel |
| --- | --- | --- |
| admin | `/admin/workspace` | `ai-agent` (Teach AI) |
| owner | `/owner/inbox` | `inbox` |
| agent | `/agent/inbox` | inbox only |

### Role access matrix (frontend)

| Area | admin | owner | agent |
| --- | --- | --- | --- |
| Inbox | Shared manager inbox | Shared manager inbox | Separate agent inbox |
| Teach AI, Chat Box, Analytics, Dashboard, Articles, Open Hours, Saved Replies, Manage Tags, Users | Yes | Yes | No |
| API activity, Data APIs, CS API settings | Yes | No | No |
| Automation (URL only) | Yes | Yes | No |
| "Test Home" link in top bar | Yes | No | No |

`RolePermissions` in `RoleContext` (17 booleans) is exported but **no
component reads it** — `permissions` has no consumer in `src/`. Admin and
owner maps are identical. Real gating is `roleNavigation.ts` plus the server.

Backend authorization is stricter in places and looser in others
(`api_context.py` middleware): management prefixes allow admin and owner;
`DELETE`, `/reset` and `/restore-default` are admin only; agents are limited
to tickets assigned to them and cannot assign or tag. The frontend still shows
owners the delete controls for tags, macros and knowledge links, which the
server will reject (PARTIAL — controls seen by pattern scan, not exercised).

### Behaviour future shell work must preserve

1. Panel state lives in the URL query string and is replaced, not pushed
   (`navigate(..., { replace: true })`), so browser Back leaves the workspace.
2. `getRolePanelPath("admin", "rules")` deliberately returns
   `/admin/workspace` with no `panel` parameter.
3. Admin has two inbox-capable paths with different defaults
   (`/admin/workspace` → Teach AI, `/admin/inbox` → Inbox).
4. The sidebar has two modes: a compact inbox mode (filters, views, ticket
   list) and a workspace-menu mode. Entering any non-inbox panel forces menu
   mode; the "< Workspace" button switches from inbox mode to menu mode.
5. Session bootstrap is asynchronous. `isAuthenticated` is `false` until
   `/auth/me` resolves, so a hard refresh on a staff URL briefly routes to
   `/login` and then back to the role **home**, not the original URL.
6. Logout clears local state immediately, fires `/auth/logout` without
   waiting, then navigates to `/login`.
7. Failed login always shows "Invalid email or password", including for
   network failures (`login` swallows every error).

---

## 6. Current app shells

### Public
There is no shared public layout component. `CustomerHomePage` and
`CustomerLookupPage` each write their own `<header class="help-center-header">`
with different contents; `ApiActivityPage` and `DataApiLogsPage` have a third
header (`api-activity-topbar`) and no site navigation.

- Header (`CustomerHomePage`): logo, four nav links, and a "Sign in" /
  "Open workspace" link.
- Footer: only on `CustomerHomePage`. Shows a hard-coded "English (US)" label
  with no language switch behind it.
- Chat container: fixed floating panel plus round launcher
  (`store-chat-layer`), not part of the page flow.

### Staff
- `LoginPage`: standalone two-column page (image panel + form). Not inside `AppShell`.
- `AppShell`: top bar only — role-initial badge (not the AcroBuild logo),
  global ticket search with suggestion list, optional "Test Home" link,
  session name/email/role chip, "Log out". Content region is
  `<main class="page-shell support-console-page-shell">`.
- Sidebar: rendered separately inside `SharedManagerInboxPage` and again
  inside `AgentInboxPage`. `AppShell` locates it by DOM query
  (`document.querySelector(".support-console-sidebar")`) to position the
  search suggestions.

### Shared or duplicated

| Layer | State |
| --- | --- |
| Staff top bar | Shared (`AppShell`) |
| Staff sidebar | Duplicated in two page components |
| Staff inbox body | Duplicated: `AdminInboxPage` 2,514 lines vs `AgentInboxPage` 1,757 lines, same class names |
| Public header | Duplicated three ways |
| Public footer | Single use |

### Safest seam for a later unified shell (observation, not a prescription)
The `/` layout route in `App.tsx` already wraps every staff screen, and
`AppShell` is the only place that sees all of them. The public side has no
equivalent seam: the eight public routes are siblings with no layout route.
The coupling to watch is `AppShell`'s DOM query for the sidebar and the
`SearchContext` handshake between the top bar and the inbox pages.

---

## 7. API usage map by frontend area

| Area | Endpoints |
| --- | --- |
| Customer chat | `POST /api/support/assist/stream`, `POST /api/support/assist`, `GET /api/support/conversations/{id}/history` |
| Client property flow | `GET /api/property-flow/projects`, `/projects/{id}/wings`, `/wings/{id}/inventory?available_only=true`, `/wings/{id}/typologies` |
| Site visit form | `POST /api/site-visits` |
| Support ticket form | `POST /create_ticket` |
| Voice playback (unreachable UI) | `POST /api/support/voice/synthesize` |
| Help-centre articles | `GET /api/admin/articles` (see note) |
| Customer lookup | `POST /auth/otp/request`, `POST /auth/otp/verify`, `GET /customer/verified` |
| Session | `POST /auth/login`, `GET /auth/me`, `POST /auth/refresh`, `POST /auth/logout` |
| Inbox (manager and agent) | `GET /api/admin/tickets` (paged, 500 per page, all pages), ticket `detail`, `read`, `reply`, `notes`, `status`, `assign`, `close`, `tags`, `recommended-macros`; `GET /api/admin/tags`; `GET /api/admin/macros`; `GET /customer`; `GET /orders` |
| Teach AI | `GET/POST /api/admin/articles`, `GET /api/admin/knowledge-documents`, `.../upload`, `.../import-url`, `.../delete`, `POST /api/support/assist` |
| Articles panel | articles CRUD, plus assist preview (PARTIAL) |
| Users / Tags / Macros / Business hours | Matching `/api/admin/*` CRUD (PARTIAL) |
| Analytics / Dashboard | `GET /api/admin/tickets` only; all metrics are computed client-side (PARTIAL) |
| Chat Box panel | None — browser `localStorage` only |
| API activity / Data APIs | None — browser `localStorage` only |
| CS API settings | `GET/PUT /api/admin/cs-api-settings` |
| Automation | `GET /api/admin/automation/escalations`, `/capacity`, `POST /proposals`, `POST /proposals/{id}/confirm` |

Notes:

- **Public page calls a staff endpoint.** `CustomerHomePage` calls
  `getAdminArticles()`. The backend requires a workspace session for
  `/api/admin/*`, so anonymous visitors get an error, which is swallowed, and
  the page falls back to the static `knowledgeArticles` list in
  `src/lib/articleAssist.ts`. Published workspace articles appear on the
  public site only when the same browser holds a staff session. VERIFIED.
- Both inbox pages poll on a 5-second interval (PARTIAL — interval seen, not
  the exact call set).
- `apiRequestWithFallback` retries a legacy `/admin/*` path only when the
  error message is exactly "not found".
- Exported but with no reachable caller: all workflow-rule functions,
  `getAdminMacro`, `postAdminTicketMessage`, `updateAdminKnowledgeDocument`,
  `createAdminKnowledgeDocument` (PARTIAL — checked against reachable pages'
  import lists).

---

## 8. SupportAssist / chat contract map

### Request (`SupportAssistRequest`, `api_context.py`)
The frontend always sends all twelve fields. Values the UI controls:

| Field | Sent by chat |
| --- | --- |
| `issue` | The customer text, unmodified |
| `conversation_id` | From `sessionStorage`; rotated only on reset |
| `conversation_messages` | Entire visible transcript, including client-only property-flow and form confirmation messages. Server caps the list at 60 items; the client does not trim. Once a stored conversation exists the server replaces this with its own history. |
| `customer_email` | Set only after a ticket or site-visit form supplied one |
| `issue_type` | Client keyword guess (`inferIssueType`) |
| `article_hint_url` | Only for "Open in chat" on an article |
| `limit` | 2 (6 in voice mode) |
| `prefer_fast_response` | `true` (false in voice mode) |
| `language_hint` | Only in voice mode with a non-English voice |

`customer_name` and `business_hours_tag` are always empty.

### Stream protocol (`POST /api/support/assist/stream`, NDJSON)

| Event | Backend | Frontend (`streamSupportAssist`) |
| --- | --- | --- |
| `{type:"delta", text}` | Deterministic and property answers emit exactly one delta holding the full final answer. Only non-property LLM turns stream incrementally. | Appends to the bot bubble; hides the typing dots |
| `{type:"done", response}` | Final payload | `onDone`, then stops reading |
| `{type:"error", response}` | Emitted on server exception with a full fallback payload (`source_status: "fallback"`, `handoff_recommended: true`) | **Handled identically to `done`.** The UI shows the apology text as a normal answer with no error styling or retry. |
| Any other type | Non-property orchestration events are forwarded as-is; `route` is filtered server-side | Ignored. No progress UI exists. |

Timeouts: 120 s to open the stream and 120 s between chunks, then abort.

### Failure ladder in `queueBotResponse` (VERIFIED)

1. Stream fails after some text arrived → the partial text is finalised as the
   answer. Quick replies and `serverTurn` are dropped.
2. Stream fails with no text → one call to `POST /api/support/assist`.
3. That fails too → `buildDemoBotResponse` produces a **local** reply from the
   article list ("Based on "<article>", …" or "I could not find the right help
   article…"). No error is shown and nothing marks the reply as offline.
4. If the widget setting `aiResponsesEnabled` is off in this browser's
   `localStorage`, step 3's local reply is used for every message and no
   backend call is made.

There is no retry control anywhere in the chat.

### Response fields

Status key: A aligned · L loosely typed · M missing from frontend types ·
S stale frontend definition · V needs deeper verification.

| Backend field | Frontend representation | Status | Frontend consumers | Risk if redesigned first |
| --- | --- | --- | --- | --- |
| `answer` | `answer: string` | A | Chat bubble, Teach AI test, API activity | Low |
| `quick_replies[].label/value` | Typed | A | Chat buttons, history restore | Low |
| `quick_replies[].action` — backend emits `browse_projects`, `site_visit`, `ticket` | `SupportAssistResponse` union is `"ticket" \| "site_visit" \| "call"`; `browse_projects` appears only in three other inline copies of the type | S + M | Chat click handler branches on all four | A typed component built on `SupportAssistResponse` would not accept `browse_projects`. **Confirmed (Phase 0.5):** `"action": "call"` does not occur anywhere in `.py` source — not in `routers/assist.py`, `graph/main_orchestrator.py`, `services/discovery_slot_service.py`, or `services/property_clarification_service.py`. It is typed and tolerated client-side but has no backend emitter; safe to drop from a redesign's type contract. |
| `quick_replies[].project_name` | Typed optional | A | Prefills the site-visit project | Low |
| `offer_action_menu` | Typed optional | A | Shows the two-button action menu | Low |
| `reply_language`, `reply_script` | Typed optional | A | Switches the language of client-side flow labels | Medium — localisation depends on it |
| `source_status` | 10-value union | S / V | **Not read by the customer chat.** Stored in API activity. | Backend values seen in source: `live_api`, `snapshot`, `failed`, `unavailable`, `workspace`, `fallback`; `error` is tested for in the router. `live`, `unverified`, `conversation`, `clarification` have no emitter in the source read (the compiled runtime was not inspectable). |
| `route` (`property`, `general`, `call_booking`, `human_contact`) | — | M | None | A design that distinguishes callback or contact turns has nothing typed to key on |
| `clarification_entity` | — | M | None | Clarification-specific UI cannot be typed |
| `pending_project_lookup` | — | M | None | Returned in the payload by `routers/assist.py` without being stripped (verified in that file only). Must never be echoed back or used as client state. |
| `discovery_slots`, `discovery_kind`, `options`, `skipped`, `catalogue_home_type_search` | — | M / V | None | Present on discovery drafts and passed through by the router. Exact final shape not traced end to end. |
| `phone_rejection_reason` | Typed optional | A | None | Low |
| `agent_mode` | Union `"fallback" \| "qwen" \| "retrieval"` | S | API activity (as string) | Every deterministic builder read emits `"knowledge_retrieval"` |
| `retrieval_mode` | Union `"empty" \| "lexical" \| "semantic"` | S | API activity (as string) | Backend emits `"live_project_records"` and `"none"` |
| `matched_chunks[]` | `SupportAssistChunkMatch` (requires `chunk_id`, `record_id`, `excerpt`, `score`, `source_name`, `source_type`, `url`, `category`) | S | Teach AI test card: React key `${record_id}-${chunk_id}`, label `source_name \|\| source_type` | **Confirmed (Phase 0.5):** every property-evidence chunk builder read in `api_context.py` and `services/acrobuild_company_service.py` sets `record_kind: "company_api"`, `source_key`, `title`, `score`, `excerpt`, and one of `project` / `project_name` / `projects` / `amenities_matched`. None set `chunk_id`, `record_id`, `source_name`, `source_type`, `url`, or `category`. Rendering a property-evidence chunk through the Teach AI test card with the current type produces an `undefined-undefined` React key and a blank `source_name \|\| source_type` label — this is a real, reproducible defect, not just a type gap. The current `SupportAssistChunkMatch` shape matches only the knowledge-article/document retrieval path, not property evidence. |
| `data_api_calls[]` | `DataApiCallTrace` | A | Data APIs page | Public trace fields match. `error` is replaced server-side with a generic string. `apiActivity` drops `created_at` when compacting. |
| `rag_evaluation` | `RagEvaluation` | V | API activity page | Service not read |
| `articles`, `knowledge_documents` | Required arrays | L | Not rendered in customer chat | Discovery drafts omit both; the live-data guard clears `articles` |
| `source_label`, `support_base_url` | **Required** strings | S | `source_label` shown in Teach AI | `support_base_url` is absent from every deterministic builder read; `source_label` is absent from discovery drafts |
| `assist_error`, `confidence_label`, `handoff_recommended`, `model`, `used_llm`, `last_synced_at`, `sync_error` | Typed optional | A / L | `handoff_recommended` in Teach AI only | Low |

The quick-reply item type is declared inline in four places
(`types.ts`, `api.ts` `ConversationHistory`, `CustomerHomePage` `ChatMessage`,
`conversationSession.ts` `RestorableMessage`) and they already disagree.

### Conversation identity and continuity

- ID is created on first load and stored per tab in `sessionStorage`.
- Reset (`replaceConversation()`) happens in exactly three places: a quick
  reply with `action: "browse_projects"`, "Open in chat" on an article page,
  and `handleChatFlowSelect` (which has no reachable caller).
- On reload the page calls the history endpoint and disables the composer and
  quick replies until it resolves (`isRestoringChat`). If the local snapshot
  matches server history it is used, including client-only messages and the
  client property flow. Otherwise server history is shown.
- **Server-only restore loses terminal actions.** The history endpoint
  rebuilds quick replies only for a pending selection (plus "Any area") or a
  pending budget ("Any budget"). After a reload without a matching snapshot,
  the Browse / Site visit / Ticket buttons on the last answer do not return.
- Restore failure shows "Your earlier chat could not be loaded. Refresh to try
  again." and leaves the composer enabled.
- Project continuity and discovery slots are entirely server-side. The client
  holds no copy and shows no indicator of the current project, area or budget.

---

## 9. `api.ts` + `types.ts` gap analysis beyond chat

Only items proven from source are listed.

| Item | Finding | Status |
| --- | --- | --- |
| `ConversationHistory` | Matches the history endpoint (`exists`, `messages`, `quick_replies`) | A |
| `PropertyFlowResponse<T>` | `{ items, data_api_calls? }`; produced by `_cs_api_response`, which was not read | V |
| `createSiteVisit` payload | Matches `SiteVisitRequest` field for field | A |
| `createSiteVisit` / `createSupportTicket` return | Typed as `CreateTicketResponse`; both return `run_workflow(...)` output, not read | V |
| `CSApiSettings` | Read returns `company_id: string`; save sends `number` | A (as coded) |
| `Order`, `OrderItem`, `SubscriptionRecord`, `CustomerProfileRecord` | Index signatures typed `any`; retail-shaped (orders, line items, subscriptions) | L |
| `getOrdersByEmail` | Returns `{ orders: any[] }` | L |
| `postAdminTicketReply` return | `message: unknown` | L |
| `WorkflowRule*` types, nine rule functions | No reachable consumer | S (unused) |
| `SupportArticleMatch`, `KnowledgeDocumentMatch` | Typed; never rendered in customer chat | L |
| `backendPorts`, `addUniqueApiBase` in `api.ts` | Declared, unused | S |
| `generateIndicVoiceAudio` | Bypasses `apiRequest` (no credentials, no CSRF header) | Note |

Ticket, tag, macro, user, article, business-hours and knowledge-document
shapes were not compared against `services/database_service.py` in this
phase — **V**.

---

## 10. Styling architecture

| Aspect | Finding |
| --- | --- |
| Approach | Global, hand-written CSS with prefixed class names. No CSS modules, Tailwind, CSS-in-JS, or preprocessor. |
| Files | `styles.css` 14,274 lines; `customer-home-v2.css` 455; `customer-home-refresh.css` 247; `api-activity.css` 207; `pages/CSApiSettingsPage.css` 8; `automation.css` 6 |
| Loading | First three load globally from `main.tsx`. The other three load with their lazy page chunk and then stay applied. |
| Layering | `styles.css` is the base; `customer-home-refresh.css` then `customer-home-v2.css` are successive overrides of the same `help-center-*` and `store-chat-*` selectors. Later blocks inside `styles.css` also re-declare earlier ones (for example `--legacy-details-width` is set four times). |
| Custom properties | 167 `var(--…)` uses against 1,285 literal hex colours. Seven unrelated variable families: `:root`, `--support-shell-*`, `--train-ui-*`, `--ai-agent-*`, `--teach-ai-*`, `--legacy-*`, `--home-*`, `--v2-*`. |
| Inline styles | 41 `style={{…}}` uses in 12 files, mostly dynamic colours (status dots, tag colours, chart bars, widget accent). |
| `!important` | 12 |

`:root` in `styles.css` defines a **dark navy** palette (`--bg-canvas:
#07111f`, `--text-main: #f7fbff`). Most current screens are light, so they
override rather than consume those root values.

---

## 11. Typography, colour, spacing, radius and shadow findings

Descriptive only.

- **Typeface.** `--font-body` and `--font-heading` both name `"Inter"` with a
  system fallback. Inter is not loaded: no `<link>` in `index.html`, no
  `@import`, no `@font-face`. Rendering therefore depends on whether Inter is
  installed locally. Two rules use `Georgia, "Trebuchet MS", serif`. The chat
  panel sets its own font inline from widget config (default Inter stack).
  Plus Jakarta Sans appears nowhere.
- **Colour.** No single primary. Role-specific accents exist on the staff
  shell (admin blue `#2563eb`, owner amber `#b45309`, agent green `#059669`).
  The public pages use coral, mint and lime (`--home-*`, `--v2-*`). Teach AI
  uses gold/amber. The chat bubble default accent is `#1f2937`. `#0055FF`,
  `#111827` and `#F9FAFB` each have zero or near-zero matches as tokens.
- **Violet / purple.** 49 matches in `styles.css` plus accents named `violet`
  in five components (`--accent-violet: #8b5cf6`, `accent-violet` cards).
- **Gradients.** 210 gradient declarations (195 in `styles.css`).
- **Glass effects.** 17 `backdrop-filter` declarations.
- **Shadows.** 191 `box-shadow` declarations; named shadows are large
  (`0 28px 54px …`, `0 18px 36px …`).
- **Radius.** 424 `border-radius` declarations with no scale; large values are
  common (`--legacy-panel-radius: 30px`).
- **Spacing.** No spacing variables. Values are literal per rule.
- **Breakpoints.** 46 media queries using 22 different widths between 500px
  and 1500px (980px, 900px, 720px and 640px are the most repeated), plus one
  `max-height: 900px`. All are `max-width`; nothing is mobile-first.
- **Z-index.** 19 declarations, ad hoc values `-1` to `120`
  (60, 80, 120 are the top layers).
- **Focus.** 26 `:focus` / `:focus-visible` matches and 7 `outline: none`
  across 14,000+ lines; most interactive classes have no explicit focus style.

---

## 12. Reusable component inventory

Shared components that exist today:

| Component | Reused by | Notes |
| --- | --- | --- |
| `AppShell` | All staff routes | Top bar only |
| `AcrobuildLogo` | Public header and footer, login, customer lookup | Not used in the staff shell |
| `AttachmentPreview` | Both inboxes | The only modal with focus handling |
| `PhotoEmptyState` | Both inboxes | Empty and loading share one visual |
| `WorkspaceStatePanel` | Analytics, Dashboard | Loading and empty variants |
| `AnalyticsCharts` | Analytics, Dashboard | Hand-built charts, no chart library (PARTIAL) |
| `chat/ChatIcons` | `CustomerHomePage` only | 15 inline SVG icons |

Everything else is page-local markup. By category:

| Category | Reusable today? | Variants found | Behaviour mixed into markup? | Extraction candidate |
| --- | --- | --- | --- | --- |
| Buttons | No | About 90 distinct `*-button` rule blocks; primary alone exists as `primary-button`, `support-primary-button`, `teach-ai-primary-button`, `help-center-inline-button-solid`, `sign-in-button`, `customer-lookup-submit`, `store-chat-visit-submit`, `api-activity-button` | No | Yes |
| Icon buttons | No | Chat send, chat close, feedback thumbs, view toggles | No | Yes |
| Text inputs | No | `field-input`, `form-input`, `teach-ai-input`, `support-console-input`, `store-chat-message-input`, `store-chat-email-input`, `customer-lookup-input`, bare unclassed inputs in Automation and CS API settings | No | Yes |
| Select | No | Native `<select>` with the input classes above | No | Yes |
| Textarea | No | `field-textarea`, `teach-ai-textarea`, `support-console-textarea`, `store-chat-compose-input` | No | Yes |
| Checkbox / radio | No | Native, unstyled or card-wrapped (`support-check-card`, `remember-me`); "radio" in customer lookup is two buttons | Yes (lookup mode) | Yes |
| Badges / chips | No | `support-toolbar-pill`, `support-toolbar-chip`, `support-tag-chip`, `teach-ai-file-chip`, `photo-empty-state-chip`, `help-center-hero-chip`, `api-activity-pill` | Colour often inline | Yes |
| Cards | No | `support-details-card`, `teach-ai-card`, `help-center-*-card`, `customer-lookup-*-card`, metric cards per page | No | Yes |
| Tables | No | Real `<table>` only in Automation (and dead Ticket Search). Lists elsewhere are stacked buttons or cards. | — | Later |
| Tabs | No | `api-view-tabs` is two router links; category grid/list toggle | Yes (routing) | Later |
| Modal / dialog | One | `AttachmentPreview`; otherwise `window.confirm` (Teach AI delete) and inline expanding sections | Yes | Yes |
| Drawer | None | — | — | — |
| Toast / banner | No | `support-console-toast-stack` with `banner-error` / `banner-success`; `teach-ai-feedback`; `store-chat-error`; plain `<p role="alert">` | Auto-dismiss timers inline (2.5 s success) | Yes |
| Loading | No | Text ("Loading page…", "Loading settings…", "…"), `WorkspaceStatePanel`, `PhotoEmptyState`, chat typing dots. No skeletons. | No | Yes |
| Empty state | Partly | `PhotoEmptyState`, `WorkspaceStatePanel`, `help-center-empty-state`, `teach-ai-empty-state`, `api-activity-empty`, `support-empty-inline`, `customer-lookup-empty` | No | Yes |
| Error / retry | No | Error banners per page. An explicit Retry button exists only in CS API settings. | — | Yes |
| Pagination | None in UI | `getAdminTickets` loads every page before render | — | — |
| Search / filter | No | Top-bar search with suggestions, sidebar search, help-centre search, tag search | Yes (`SearchContext`) | Careful |
| Page header | No | Each panel writes its own `<h2>` block | No | Yes |
| Sidebar | No | Duplicated in both inboxes | Yes (ticket list, views, nav) | Careful |
| Property / result cards | **None** | Property data is shown as text plus list buttons | — | Not available today |
| Quick replies | No | `store-chat-guided-button` grid, one visual for every option type | Yes (action dispatch inline) | Careful |
| Chat messages | No | Inline in `CustomerHomePage`; staff thread uses separate `support-thread-*` | Yes | Careful |
| Form sections | No | Per page | — | Yes |

---

## 13. Duplicate and inconsistent pattern inventory

1. Two inbox implementations totalling 4,271 lines with shared class names
   and separately maintained logic.
2. Six dead page components (section 4.4) still carry about 4,000 lines of
   CSS-backed markup; their selectors remain in `styles.css`.
3. Four competing "Teach AI" style namespaces in CSS (`train-ui`, `ai-agent`,
   `teach-ai`, `knowledge-*`) for one reachable page.
4. Three layered public stylesheets overriding each other.
5. Three different public headers.
6. Primary button implemented at least eight times (section 12).
7. Feedback messaging implemented five ways (section 12, toast row).
8. Quick-reply type declared four times with diverging unions.
9. Two property browsing mechanisms in chat (section 14).
10. Legacy retail vocabulary in a property product: `BrandKey = "nufoodz"`,
    a hard-coded private IP base URL for customer lookup in
    `AdminInboxPage.tsx`, "Total Orders", "Total Spent", "Subscriptions",
    "Courier Queries" and "Sent tracking" views, `TrackOrderIcon`,
    `CancelOrderIcon`, Teach AI placeholders such as "My order is late" and
    "Shipping page", and install-snippet host `config.support-agent.chat`.
11. Default assignable agents are hard-coded names
    (`Agent Michael`, `Agent Sarah`, `Agent John`, `Agent Anika`).
12. Sidebar label and page title disagree for four panels (section 4.3).

---

## 14. Public customer experience audit

### `/home` (marketing variant)
Hero (headline, two buttons, three metric cards, local hero image), a
lifecycle section (three cards), featured categories (up to three), and a
"support operations" section. Findings:

- The three metric cards show counts of **articles, categories and quick
  paths**, zero-padded. For anonymous visitors these count the static fallback
  list, not workspace content.
- Seven distinct images are hot-linked from `images.unsplash.com`. They are
  generic stock photos, not AcroBuild property imagery.
- Two body paragraphs are internal build notes shown to customers: "The
  landing page now mirrors how premium construction brands present trust…"
  and "The visual upgrade just presents them with more polish."
- "Explore with us" calls `openContactMode("")`, which opens the **ticket
  follow-up form** inside chat, not property discovery.
- "Browse support guides" and "Open full help center" link to `/home`, the
  page the user is already on.

### Navigation defects (VERIFIED)
`helpCenterArticlesPath` and `helpCenterHomePath` are both `/home`. The header
links "Popular questions", "All articles" and "Get support" point to
`/home#popular-questions`, `/home#more-information`, `/home#get-support`, but
those anchors are rendered only on `/home/about`. **No link in the app
navigates to `/home/about`**, so the help-centre landing (search, popular
questions, all categories, contact cards) is reachable only by typing the URL.
Breadcrumb "All articles" has the same problem.

### `/home/about` (help-centre landing)
Search with live match count, three "lane" cards, popular questions, three
action cards, category grid with grid/list toggle, and a get-support section.

- Action cards "Book site visit", "Request pricing" and "Report site issue"
  all navigate to `/home/project-support` (the OTP lookup page). None opens
  the site-visit form.
- The "Call us" card shows `+61 1800 592 299` and "Monday to Friday, 9:00 AM -
  5:00 PM AEST" — an Australian number and timezone, hard-coded.

### Category and article pages
Breadcrumbs, compact search, grid/list toggle, article body split by line,
related articles, and two actions: "Open in chat" (starts a **new**
conversation seeded with the article) and "Need more help" (opens the ticket
form). Missing article shows a not-found block.

### `/home/project-support` (customer lookup)
Email OTP request → six-digit verify → profile, "project records" and "plans
and schedules". The SMS option is selectable but always returns "SMS OTP is
not configured yet." The result labels are property-flavoured but the data
shape is retail (`orders`, `subscriptions`, `total_spent` shown as "Portfolio
value"). PRODUCT_STATUS lists verified customer lookup as unsupported by the
CS API; what real data this page can return was not verifiable from source.

### `/home/api-activity`, `/home/data-api-logs`
Developer-oriented diagnostics for this browser's own chat requests: question,
endpoint, duration, answer, RAG metric cards, raw JSON, and per-call property
lookups. Public and unlinked from the public navigation; the staff top bar's
"Test Home" link goes to `/home`, not here.

---

## 15. AI assistant UX and state audit

### Layout
Fixed panel with a header (close chevron, initial avatar, "Acrobuild
Assistant / Property support", online dot), scrolling body, single-line
composer, optional error strip, and a round launcher. Width comes from widget
config (default 340px, capped to the viewport). The panel is open on first
load.

### Message rendering
- One bubble per message; bot bubbles show "Acrobuild Support" and an
  "Automated" note. Customer bubble colour comes from widget config.
- Text is rendered as plain text (`store-chat-message-text`). No Markdown,
  links, lists, tables or cards.
- `visibleMessageText`: when a message has quick replies and **none** carries
  an `action`, everything from the first bullet line onward is cut from the
  displayed (and spoken) text, because the buttons repeat those options.
- A date label shows today's date in `en-US` format regardless of chat language.

### Controls under the latest completed bot message
Only the most recent completed bot message shows controls, and none while the
site-visit form is open. Priority order:

1. Server `quick_replies`
2. Client property-flow buttons
3. The welcome "Browse all projects" button
4. `offer_action_menu` → "Raise a ticket" and "Book a site visit"

Quick-reply click dispatch:

| `action` | Result |
| --- | --- |
| `ticket` | Opens the ticket follow-up form |
| `site_visit` | Loads projects if needed, opens the site-visit form with `project_name` preselected |
| `browse_projects` | New conversation ID, transcript cleared, sends `value` |
| anything else, including `call` | Sends `value` as a normal message in the same conversation |

Quick-reply buttons are disabled while a reply is pending or history is restoring.

### Composer interception order (typed text)
Before text reaches the backend the submit handler tries, in order:
client property-flow selection → named project match in recent bot text →
numbered project match (both skipped when the last bot message has server
quick replies) → site-visit phrase (`visit` + book/schedule/arrange/request)
→ short helpfulness reply → backend. Any restyle of bot text that changes
numbered-list formatting (`1. Name` / `1) Name`) affects the two text-matching
steps.

### Two property flows

| | Server discovery / clarification | Client property flow |
| --- | --- | --- |
| Driver | `/api/support/assist*` | `/api/property-flow/*` called from the page |
| Steps | configuration → area → budget → shortlist → project → details (server-side) | project → wing → floor → flat → flat price |
| Options shown as | `quick_replies` | Buttons built from fetched lists |
| State | Server markers | `PropertyFlowState` in `sessionStorage` |
| Entry | Any typed question or quick reply | Typing a project name/number from a prior bot list when no server quick replies are present |
| Text language | Server-localised | `FLOW_TEXT[chatLanguage]` client table |
| Ends with | Terminal quick replies | "Book a site visit" button |

`startProjectsFlow` (client project list) has no caller, so the client flow is
entered only at the wing step. Client-flow messages are not sent as server
turns but are included in `conversation_messages`.

### Forms
- **Site visit** (inline card in the transcript): name, email, phone, project
  select, date (min today), time, notes. Client validation message is a single
  combined sentence. Submits to `POST /api/site-visits`, which creates a
  **local ticket**. Success text reads "Your site visit request has been
  submitted. Ticket X is assigned to Y." The form heading says "Book your
  preferred visit" and the footnote says the site team will "confirm the
  correct project and visit slot" — wording that must stay a request, not a
  confirmed booking.
- **Support ticket** (inline card): email and message; submits to
  `POST /create_ticket`; success shows ticket id, assignee and queue in a
  small card. The card's helper text is written for staff ("after the customer
  enters an email", "Add the customer's remaining question here…").
- **Callback / human contact**: there is no form. It is a server-driven
  conversation (`route: call_booking` / `human_contact`) that collects phone,
  time or name in free text and creates a local ticket. The UI shows it as
  ordinary bubbles.

### States

| State | Current treatment |
| --- | --- |
| Waiting for reply | Three animated dots; composer and quick replies disabled |
| Streaming | Text grows in the bubble (only for non-property LLM turns) |
| Restoring history | Composer and quick replies disabled; no visible indicator |
| Client-flow fetch failure | Localised bot message plus raw error text in the red strip |
| Assist failure | Silent local article reply (section 8) |
| Server `error` event | Shown as a normal answer |
| Form validation / submit failure | Red strip under the composer; cleared on next action |
| Live data unavailable | Whatever text the server returns; no visual distinction |
| Empty option list | Server text only |

### Mobile
The panel width is `min(widgetWidth, 100vw - 1rem)`. Site-visit date and time
sit in a two-column row. No full-screen mobile mode was found in the JSX;
CSS-level behaviour was not traced rule by rule (PARTIAL).

### Capability separation (mandatory)

**A. Backend capability exists and the frontend renders it**
- Answer text, streaming deltas, final payload.
- Quick replies for project, locality, wing, floor, flat, home-type, "Any
  area", "Any budget".
- Terminal actions: Browse all projects (new conversation), Book a site visit
  (with project prefill), Raise a support ticket.
- Confusion action menu (`offer_action_menu`).
- Reply language driving client flow labels.
- Conversation restore after reload.
- Site-visit and ticket request forms creating local tickets.

**B. Backend capability exists but the frontend does not represent it well**
- `source_status` (live / snapshot / failed / unavailable) — never shown.
- `error` stream events — indistinguishable from answers.
- `handoff_recommended`, `confidence_label` — unused in chat.
- `matched_chunks` property evidence, `data_api_calls` — visible only on the
  diagnostics pages.
- Current project, selected area, budget — no indicator; server-side only.
- Skipped projects in a shortlist (`skipped`) — only as text in the answer.
- Estimated base amount and its exclusion disclaimer — plain text, no
  structure.
- Terminal quick replies after a server-only restore — not rebuilt.
- Progress events — forwarded for non-property turns, ignored.
- `phone_rejection_reason`, `route` — unused.
- Server reset phrases ("start over") clear server slots but the client keeps
  the same conversation ID and transcript.

**C. Frontend contains UI but the backend contract is weaker or different**
- Voice call overlay: full UI and logic exist, but nothing sets it active —
  `handleVoiceToggle` is only wired to "End call". **Unreachable.** Two of its
  strings are also mis-encoded (`â€”`, `â€œ`).
- Contact-mode intake (email card + "Type your support question") and the
  empty "menu mode": gated on an empty transcript, which the page never
  produces in normal use. **Effectively unreachable.**
- Helpful / not-helpful thumbs: rendered only when `showHelpfulPrompt` is
  true, and every code path sets it to `false`. Feedback is local state only;
  `POST /api/support/feedback` exists but has no client function.
- `quick_replies[].action: "call"` — typed and tolerated, no emitter found.
- Local "demo" answers (`buildDemoBotResponse`) — present a canned article
  reply as if it were the assistant.
- Chat Box settings (name, intro, accent, logo, widths, AI on/off, install
  snippet) — saved to this browser only. The intro message and chat title are
  not shown in the reachable chat; the install snippet points at a host this
  repository does not serve.
- Related-article suggestions under answers — field always set to `[]`.

**D. Desired future concept, NOT CURRENTLY IMPLEMENTED**
- Property or project cards (image, price, configuration, location).
- Property imagery of any real AcroBuild project. The CS project type exposes
  only `id`, `projectName`, `city`, `locality`, `projectType` to the client.
- A visual stepper for configuration → area → budget → shortlist → project.
- Shortlist comparison, favourites, maps, distance, nearby places.
- Structured budget input (slider or chips beyond "Any budget").
- Cost sheets, offers, payment plans, price history.
- Confirmed site-visit slots, calendar availability, rescheduling.
- A dedicated callback form or CRM confirmation.
- Retry button, offline banner, per-message error state.
- Source badges ("Live data", "Snapshot").
- Assistant embedded in page content rather than a floating panel.
- Typed language switcher.

---

## 16. Staff login audit

- Standalone two-column layout: image panel (`workspace-ops.png`, headline,
  three pills, two text "stats") and form panel (logo, kicker, title, intro).
- Fields: email, password with a text "Show/Hide" toggle, "Remember me".
- States: idle, submitting ("Signing in…", button disabled), single generic
  error. No field-level errors, no lockout or rate-limit message.
- "Remember me" stores only the email. `getRememberedEmail` rewrites any
  remembered local part `admin`, `agent` or `owner` to `@acrobuild.com`.
- No forgot-password flow ("Need a reset? Contact your workspace owner."),
  no SSO, no sign-up, no link back to the public site.
- The error block has no `role="alert"`.

---

## 17. Staff workspace shell audit

- Top bar (`AppShell`): described in section 6. The brand mark is the first
  two letters of the role label ("AD", "OW", "AG") with "<Role> Experience";
  the AcroBuild logo is absent from the staff workspace.
- Global search is always visible but only functional on the inbox: other
  panels publish no suggestions, and typing filters nothing there. The ticket
  count beside it appears only when it is above zero.
- Search suggestions are a `role="listbox"` of `<button>` elements with
  arrow-key, Enter and Escape handling on the input.
- Sidebar header shows a role-initial home link, the active tool name, and a
  count. In workspace mode that count is `workspacePanelItems.length` (18) —
  a constant, not a meaningful number.
- The Teach AI group button always displays "1 page".
- Role theming: `support-console-shell-<role>` changes accent variables.
- No collapse control, no user menu, no notifications, no breadcrumbs, no
  help link, no environment or connection indicator.
- Feedback: a toast stack at the top of the inbox page for error and success;
  a "new ticket" notice inside the thread header for 5 seconds.

---

## 18. Staff panel inventory

All rows below are now VERIFIED by a full read of the component (Phase 0.5,
2026-10-05), except Automation and API activity/Data APIs/CS API settings,
already VERIFIED in the Phase 0 pass.

| Panel | Purpose and primary actions | Key APIs | Key states | Styling / reuse risk |
| --- | --- | --- | --- | --- |
| **Inbox** (manager) | Sidebar: search, sort (3 options), unread-only, 3 default + 8 shared views with counts, ticket list. Main: breadcrumb, status pill, assignee/queue chips, Refresh, thread with image attachments, suggested macros (4), macro select/apply/clear, reply textarea (Ctrl/Cmd+Enter), attachments, Send, Close ticket. Details rail: tag editor (rule tags locked), quick status actions, assignment, ticket snapshot, customer context, customer profile lookup, internal notes. | `getAdminTickets` (paged, all pages), `getAdminTicketDetail`, `getAdminRecommendedMacros`, `markAdminTicketRead`, `postAdminTicketReply`, `updateAdminTicketStatus/Assignee/Tags`, `closeAdminTicket`, `createAdminTicketNote`, `getAdminTags`, `getAdminMacros`, `getAdminCustomerByEmail`, `getOrdersByEmail` | Loading, no match, no selection, working, error/success toasts, customer-context loading/warning | `support-*` classes shared only with agent inbox; hard-coded `BRANDS.nufoodz` base URL |
| **Inbox** (agent) | Same three-column layout, separate component (`AgentInboxPage.tsx`, 1,758 lines). No assignment or tag-edit controls (server forbids for agents); badge cluster instead of a tag editor on the details card top. Polls `getAdminTickets` every 5 s via `window.setInterval`, paused when `document.visibilityState === "hidden"`. | Same ticket/macro/tag/customer endpoints as manager inbox, minus `updateAdminTicketAssignee`/`updateAdminTicketTags` | Same shape as manager inbox; `viewerAssignmentLabel` is the fixed string `"Help Desk"` | Near-duplicate of `AdminInboxPage.tsx`'s inbox branch; `BRANDS` and retail field names (`Total Orders`, `Subscriptions`) duplicated verbatim |
| **Teach AI** | Hero with flow illustration and four stat cards; four numbered cards: upload files, add URL, type an answer (saved as an article), ask the AI (non-streaming `getSupportAssist`, shows answer, source label, handoff note, matched-chunk chips); list of integrated links (grouped by source type + hostname) with select-all and delete (native `confirm`). | `getAdminArticles`, `getAdminKnowledgeDocuments`, `uploadAdminKnowledgeDocuments`, `importAdminKnowledgeUrl`, `deleteAdminKnowledgeDocuments`, `createAdminArticle`, `getSupportAssist` | Loading ("…", "Syncing"), per-action busy labels, inline error/success, empty link list | Four separate CSS namespaces (section 13); test card's `matchedChunks` rendering keys on `chunk_id`/`record_id`, fields property chunks do not carry (section 8) |
| **Chat Box** | Appearance form (title, assistant name, intro, logo URL, font, widget key, width/launcher sliders), a "Reply Behavior" checklist (AI on/off, one checkbox permanently checked+disabled, feedback toggle), manual-install steps, copyable snippet, and a live preview pane that renders a static two-turn mock conversation. | None — reads/writes only `localStorage` via `loadWidgetConfig`/`saveWidgetConfig` | Snippet-copy success/failure toast (1.8 s) | Entirely local; "Open test home" link to `/home` is the only cross-page wiring; install snippet host (`config.support-agent.chat`) is not this repo |
| **Analytics** | Filter toolbar (search, status, priority, queue) plus Refresh/Clear filters; 4 KPI cards; status/queue/agent distribution and a 7-day trend bar chart; "Recent tickets" and "Needs attention" lists. All computed client-side from the full ticket list. | `getAdminTickets` only | `WorkspaceStatePanel` loading and empty variants, error banner | No pagination; every metric recomputes from the full in-memory ticket array on each filter change |
| **Dashboard** | Same ticket-metrics pattern as Analytics with a different KPI set (Active/High priority/Closed) and an "Operational focus" card (active/waiting/queues-covered). No agent filter (Analytics has one; Dashboard does not). | `getAdminTickets` only | Same `WorkspaceStatePanel` loading/empty, error banner | Near-duplicate logic and markup of `AdminAnalyticsPage.tsx`; both files import the same `AnalyticsCharts`/`analyticsPresentation` helpers |
| **Articles** (heading: "AI Training Workspace") | Two parallel CRUD libraries — Articles and Training Documents — each with its own search/category/status filters, directory grid, and a full-page editor surface; file upload (multi-file, base64) and single-file text import into a draft; a third section runs a non-streaming `getSupportAssist` preview and shows source label, model, retrieval mode, confidence, handoff flag, matched knowledge docs/articles. | `getAdminArticles`, `createAdminArticle`, `updateAdminArticle`, `getAdminKnowledgeDocuments`, `createAdminKnowledgeDocument`, `updateAdminKnowledgeDocument`, `uploadAdminKnowledgeDocuments`, `getSupportAssist` | Working flags per action, inline error/success banners, "Thinking..." on preview | Three-surface state machine (`list`/`manage-article`/`manage-document`) duplicates most of the editor-grid markup between the two record types |
| **Open Hours** | Single schedule editor: profile select, timezone select, description, per-day time-range rows (add/remove, minimum one range), Save. No create/delete-profile or multi-profile directory UI — explicitly removed per in-page copy. | `getBusinessHoursProfiles`, `updateBusinessHoursProfile` | Saving (button disabled), error banner, empty-profile fallback card | Relies on `Intl.supportedValuesOf("timeZone")` with a ~11-zone hard fallback for older browsers |
| **Saved Replies** (Macros) | Library view (search, language/category/active-archived filters, directory grid) and an editor surface (name, language, response template, category, auto-status, subject, description, quick-tag picker, extra-tags input, live token-substituted preview, duplicate/archive/delete). | `getAdminMacros`, `createAdminMacro`, `updateAdminMacro`, `duplicateAdminMacro`, `archiveAdminMacro`, `deleteAdminMacro`, `getAdminTags` | Working flags, error banner, empty-library card | Preview token set (`{{ agent_first_name }}` etc.) is a separate hard-coded dictionary from the one used in the inbox (`buildMacroVariables`) — can drift |
| **Manage Tags** | Library (search, directory grid with ticket counts) and a create/edit surface (name, native colour picker, description, live chip preview, delete). | `getAdminTags`, `createAdminTag`, `updateAdminTag`, `deleteAdminTag` | Working flags, error banner, empty-library card | Simplest CRUD panel in the workspace; good baseline pattern for the others |
| **Users** | Directory list (search, role filter, status pill, Manage button) plus separate Invite and Manage surfaces; Manage includes role/status/team edit, resend-invite/reset-link and suspend/reactivate actions that only set local toast text (no corresponding API calls), and a static role-permission reference grid. | `getAdminUsers`, `createAdminUser`, `updateAdminUser` | Error banner, inline success banner (no auto-dismiss) | "Resend invite", "Send reset link" and suspend/reactivate-status-only actions do not call the backend — status changes are saved only via the general "Save changes" button |
| **API activity / Data APIs** | Section 14; embedded with `/admin` links | — (local only) | Empty list, no selection | VERIFIED (Phase 0) |
| **CS API settings** | Base URL, company ID, API key (write-only; shows whether one is configured), Save | `GET/PUT /api/admin/cs-api-settings` | Loading, load failure with Retry, saving (fieldset disabled), alert/status messages | VERIFIED (Phase 0) |
| **Automation** (route, not panel) | Overdue ticket table, team capacity list, propose assignment or resolution, confirm/cancel a proposal that expires in 10 minutes | `/api/admin/automation/escalations`, `/capacity`, `/proposals`, `/proposals/{id}/confirm` | Busy, alert, status; no loading state; errors print as `Error: …` | VERIFIED (Phase 0) |

Automation and CS API settings remain visibly unstyled relative to the rest
(6-line and 8-line stylesheets, bare elements). Analytics and Dashboard are
confirmed near-duplicates of each other, not just structurally similar as the
Phase 0 pass inferred.

---

## 19. Forms, modals and workflow inventory

| # | Workflow | Type | Location | Backend effect |
| --- | --- | --- | --- | --- |
| 1 | Site-visit request | Inline form in chat | `CustomerHomePage` | Local ticket via `run_workflow` |
| 2 | Support ticket follow-up | Inline form in chat | `CustomerHomePage` | Local ticket |
| 3 | Callback / human contact | Conversational, no form | Server-driven | Local ticket |
| 4 | Customer email OTP lookup | Page form, two steps | `CustomerLookupPage` | OTP + verified read |
| 5 | Staff login | Page form | `LoginPage` | Session cookies |
| 6 | Ticket reply with macro and attachments | Inline composer | Inboxes | Message + optional macro/status |
| 7 | Internal note | Inline form | Inboxes | Note |
| 8 | Ticket tags | Inline expanding card | Manager inbox | Tag set |
| 9 | Assignment and status | Inline controls | Manager inbox | Ticket update |
| 10 | Customer profile lookup | Inline fields | Manager inbox | Read only |
| 11 | Attachment preview | **Modal** (`role="dialog"`, focus moved and restored, Esc closes) | Inboxes | — |
| 12 | Teach AI: upload, URL, answer, test | Four inline card forms | `AIAgentPage` | Knowledge docs / article |
| 13 | Delete integrated links | Native `window.confirm` | `AIAgentPage` | Delete (admin only server-side) |
| 14 | Article editor and preview | Inline | `ArticlesPage` | Article CRUD |
| 15 | User invite and edit | Inline | `UsersPage` | User CRUD |
| 16 | Macro editor | Inline | `MacrosPage` | Macro CRUD |
| 17 | Tag editor | Inline | `ManageTagsPage` | Tag CRUD |
| 18 | Business-hours editor | Inline | `BusinessHoursPage` | Profile update |
| 19 | Chat Box settings | Inline | `ChatWidgetPage` | `localStorage` only |
| 20 | CS API settings | Page form | `CSApiSettingsPage` | Persisted connection override |
| 21 | Automation propose → confirm | Two-step inline | `AutomationPage` | Ticket change after confirmation |

Reachable true modals: **one** (attachment preview). Drawers: none.
Unreachable: voice-call overlay, contact-mode intake, eight knowledge-base
dialogs, rule builder.

---

## 20. Responsive behaviour audit

- All breakpoints are desktop-first `max-width` overrides; 22 distinct widths
  (section 11).
- The inbox is a three-column grid driven by `--legacy-sidebar-width`,
  `--legacy-sidebar-width-compact` and `--legacy-details-width`; the details
  width becomes `100%` under 900px.
- No hamburger or off-canvas navigation exists in JSX for either the public
  header or the staff sidebar. How the four public nav links and the staff
  sidebar behave under 640px was not traced rule by rule (PARTIAL).
- The only `<table>` in reachable UI (Automation) has no overflow wrapper.
- Chat panel width is clamped to the viewport; launcher size is inline from
  widget config.
- `AppShell` positions the suggestion list with fixed coordinates
  recalculated on resize and scroll.
- No container queries, no `prefers-reduced-motion`, no
  `prefers-color-scheme` handling were found (PARTIAL — pattern search only
  covered the properties listed in section 11).

---

## 21. Accessibility baseline

Observed, not fixed.

**Semantics**
- Public pages have one `<main>`, `<header>`, `<footer>` and a labelled `<nav>`.
- Staff pages nest `<main>` inside `<main>` when `ApiActivityPage`,
  `DataApiLogsPage` or `AutomationPage` render under `AppShell`.
- Panel headings are `<h2>` with no `<h1>` on most workspace panels; the
  inbox uses `<h1>` for the ticket title.
- Customer lookup uses `role="radiogroup"` containing buttons with
  `aria-pressed` rather than radios.
- The chat panel is a `<section>` with no accessible name and no live region
  for incoming messages. Typing dots have no text alternative.
- Suggestion list is `role="listbox"` but its children are buttons without
  `role="option"`; the input lacks `aria-controls` and `aria-activedescendant`.

**Labels**
- No label or `aria-label`: both chat composers (placeholder only), inbox
  sidebar search and sort select, macro select, reply textarea, note textarea,
  tag search, top-bar search input.
- Grid/list toggle buttons contain only an icon and have no `aria-label`.
- The help-centre "clear search" button shows a literal "x".
- 28 `aria-label` attributes exist across the whole app, 18 of them in
  `CustomerHomePage`.

**Keyboard and focus**
- Controls are native buttons, links and inputs, so they are reachable by Tab.
- Opening the site-visit or ticket form does not move focus into it (the
  ticket form does, via `setTimeout` focus; the site-visit form does not).
- Chat open/close does not move or restore focus.
- `AttachmentPreview` traps Tab by always refocusing the Close button and
  restores focus on close. It is the only focus-managed surface.
- `window.confirm` is used for a destructive action.
- Focus visibility: few explicit focus styles and 7 `outline: none`
  (section 11). Per-component contrast of focus rings not measured.

**Contrast risks (not measured)**
- Customer bubble background is a configurable colour with fixed text colour.
- Muted text tokens on light surfaces (`#8da4c3`, `#64748b`-family).
- Status conveyed by colour dots alone in ticket lists and activity rows.
- Launcher falls back to a white background when a logo URL is set.

**Other**
- Error messages are `role="alert"` only in Automation and CS API settings.
- Decorative images mostly have empty `alt`; content images have descriptive `alt`.
- Auto-dismissing success toast (2.5 s) and new-ticket notice (5 s).
- No automated accessibility test runs (axe is installed, unused).

---

## 22. Asset inventory

| Asset | Location | Used by |
| --- | --- | --- |
| AcroBuild logo (PNG) | `public/Acrobuild_logo.png` | `AcrobuildLogo` (with cache-busting query, `?v=20260730-2`). Rendered as a small mark beside a text "ACROBUILD" wordmark and subtitle. **This is the canonical, only in-app logo file.** |
| AcroBuild logo copy | `docs/assets/Acrobuild_logo.png` | `docs/README.md` only — confirmed byte-identical to `public/Acrobuild_logo.png` (`cmp` match, same size: 324×340 RGBA PNG, 18,287 bytes). It is a documentation copy, not a second asset. |
| `public/logo.svg` | `public/` | No reference in `src/` or `index.html` |
| Favicon | — | None declared in `index.html` |
| Page title | `index.html` | "Customer Support Agent" |
| `property-support-hero-v2.png` | `public/images/real-world/` | `/home` hero |
| `help-center-support.png` | same | Help-centre hero panel; unreachable order-track placeholder |
| `workspace-ops.png` | same | Login; dead `RulesPage` |
| `ai-training.png` | same | Dead `TrainUi` only |
| `guided-property-consultation-v2.png`, `pricing-home-details-card.png`, `projects-available-homes-card.png`, `site-visit-buyer-support-card.png` | same | No reference found in `src/` (may be referenced from CSS — not confirmed) |
| Stock photos | `images.unsplash.com` (7 URLs) | `/home` lifecycle, sector and command sections |
| Icons | `src/components/chat/ChatIcons.tsx` | 15 inline SVG components, chat and help centre only. Staff UI uses text and HTML entities (`&#9906;`, `<`, `→`, `x`). |
| Fonts | — | None bundled or linked |

**Confirmed (Phase 0.5):** the logo was opened and inspected. It is a
multi-colour raster mark (not a monochrome icon) — the single PNG referenced
by `AcrobuildLogo.tsx` is the real, multi-colour AcroBuild logo the target
direction calls for. No vector (SVG) version of the actual logo exists in the
checkout; `public/logo.svg` is a separate, unreferenced file and was not
confirmed to contain the same mark.

---

## 23. Design-system readiness

**Suitable to reuse (behaviour and structure are sound)**
- `AttachmentPreview` focus handling.
- `AcrobuildLogo` as the single logo entry point.
- `conversationSession.ts`, `apiActivity.ts`, `chatLanguage.ts`,
  `roleNavigation.ts`, `api.ts` request layer.
- `WorkspaceStatePanel` and `PhotoEmptyState` as the loading/empty contract.
- CS API settings form semantics (labels, `fieldset disabled`, alert/status).

**Should be standardised later (many variants, low behavioural risk)**
- Buttons, inputs, selects, textareas, chips, cards, page headers, banners,
  empty states, loading indicators.
- Staff panel headers and action bars.
- Public headers and footer.
- Colour, radius, shadow, spacing, breakpoint and z-index scales.

**Should be replaced visually while preserving behaviour**
- Staff sidebar and top bar.
- Login page.
- `/home` marketing content (stock images, internal copy, wrong phone number).
- Teach AI page (single-column cards today; no split pane exists).
- Analytics and Dashboard visuals.
- Automation and CS API settings (currently near-unstyled).

**Behaviour-sensitive / high risk**
- `CustomerHomePage` chat: `queueBotResponse`, quick-reply dispatch, composer
  interception, `visibleMessageText`, restore flow, both forms.
- `SharedManagerInboxPage`: panel switching, `SearchContext` handshake,
  polling, macro rendering, tag rules.
- `AgentInboxPage` as a parallel copy.
- `RoleContext` bootstrap and the redirect guards.

---

## 24. High-risk regression zones for later phases

1. **Quick-reply dispatch.** The four-way `action` branch and the reset
   semantics of `browse_projects`. Moving buttons into cards must keep the
   exact `value` sent and the reset flag.
2. **Bot text truncation.** `visibleMessageText` cuts bullet lists only when
   no option has an `action`. Rich rendering must not reintroduce or
   double-display options.
3. **Numbered-list parsing.** `getNumberedProjectSelection` and
   `getNamedProjectSelection` read the raw bot text. Reformatting lists breaks
   typed selection.
4. **`.store-chat-message.customer` selector** is queried from JS for scroll
   positioning.
5. **`.support-console-sidebar` selector** is queried from `AppShell`.
6. **Transcript persistence shape.** `saveTranscript` whitelists fields; any
   new message field needed after reload must be added there, and
   `matchingTranscript` compares server turns by exact JSON equality.
7. **`conversation_messages` length.** The client sends the whole visible
   transcript; the server model caps it at 60. Adding more client-only
   messages (cards, system notes) raises the chance of a validation failure,
   which the UI would mask as a local article reply.
8. **Silent fallback.** Any work on error states must account for the
   three-stage failure ladder, or real outages stay invisible.
9. **`isRestoringChat` gating** of composer and quick replies.
10. **Client property flow vs server discovery.** A unified property UI must
    decide per interaction which contract it is driving; today they are not
    interchangeable and store state in different places.
11. **Request/site-visit wording.** Copy must remain "request"; the backend
    creates a local ticket only.
12. **Panel URLs.** `?panel=` values, the admin `rules` special case, and the
    two admin entry paths.
13. **Role bootstrap flash** on reload and the generic login error.
14. **Global CSS.** Three public stylesheets and `styles.css` override each
    other by source order; removing or reordering imports changes unrelated
    screens. Lazy-loaded page CSS stays applied after first visit.
15. **Widget config in `localStorage`** changes chat appearance and can
    disable backend calls per browser.
16. **Type drift.** Building typed components on today's
    `SupportAssistResponse` bakes in the stale unions listed in section 8.

---

## 25. Open questions and genuine blockers

Only items that current source cannot answer.

1. Which sidebar/panel set is intended long term: the simplified Teach AI
   page (reachable) or the separate Knowledge Base, Rules, Products,
   Shopping Assistant and Support Actions pages (dead)? This decides whether
   "workflow rules" and "knowledge management" are redesign targets or
   re-enablement work.
2. Should `/home/about` (help-centre landing) be linked, or is `/home`
   intended to replace it?
3. Are `/home/api-activity` and `/home/data-api-logs` meant to stay public?
4. Should published workspace articles be visible to anonymous visitors?
   Today they are not, because the public page calls a staff endpoint.
5. Is the client-driven wing → floor → flat flow meant to survive next to
   server discovery?
6. Is voice conversation in scope? The UI exists with no entry point. The
   pre-audit change in `CustomerHomePage.tsx` does not touch voice, so the
   entry point is already absent in the committed code.
7. What does `/customer/verified` actually return for AcroBuild buyers?
   Types are retail-shaped and PRODUCT_STATUS marks verified customer lookup
   as unsupported upstream.
8. Correct public phone number, hours and timezone.
9. Is the Chat Box (widget) panel a real product surface? It persists only to
   one browser and references an external host.
10. Does the CS API expose any image, price or configuration fields per
    project that could back property cards? The client project type has five
    text fields; the upstream schema was not inspected.
11. Is the agent inbox expected to stay a separate implementation?
12. Values the compiled runtime can emit for `source_status`, `agent_mode`
    and `retrieval_mode` (not inspectable as source).

Resolved in the Phase 0.5 pass (no longer open): the 9 PARTIAL staff panels
and the agent inbox are now fully read (section 18); the docs-path question
is answered (section 2, finding above); the logo asset is confirmed as the
real multi-colour mark (section 22); and the `action: "call"` /
`matched_chunks` type questions (section 8) are confirmed from readable
source — `call` has no backend emitter anywhere in `.py` source, and property
evidence chunks never carry `chunk_id`/`record_id`/`source_name`/`source_type`,
confirmed as a reproducible rendering defect, not just a type gap.

---

## 26. Recommended Phase 1 inputs

Extract from Figma, and nothing beyond this list, so that Phase 1 output maps
onto surfaces that exist:

**Foundations**
- Colour styles with names and hex values: primary blue, text navy, surface
  off-white, borders, the orange/green/yellow accents, and semantic
  success / warning / error / info.
- Type styles for Plus Jakarta Sans: family, weights used, size, line height
  and letter spacing per named style.
- Spacing scale, radius scale, border widths, shadow styles, and the
  breakpoint/frame widths the designs were drawn at.
- Icon set name and sizes.
- Logo usage: variants, clear space, minimum size, and which file is canonical.

**Component specs (with every state drawn)**
- Button (primary, secondary, ghost, destructive, icon), input, select,
  textarea, checkbox, radio, chip/badge, card, banner/toast, modal, empty
  state, loading state, error-with-retry state, tabs, table row, page header.
- Staff sidebar (expanded and collapsed) and utility header.
- Public top navigation and footer.
- Chat: bot bubble, customer bubble, typing indicator, quick-reply group,
  action group, inline form card, ticket confirmation card, error strip.

**Frames to map against the current inventory**
One frame per existing surface, labelled with the id from section 4: `/home`,
help-centre landing, category, article, customer lookup, login, inbox, Teach
AI, Chat Box, Analytics, Dashboard, Articles, Open Hours, Saved Replies,
Manage Tags, Users, API activity, Data APIs, CS API settings, Automation.

**For each chat or property frame, record which of these it depends on**
`answer` text only · `quick_replies` · `action` values · `project_name` ·
`offer_action_menu` · `source_status` · `matched_chunks` · project list
fields (`projectName`, `city`, `locality`, `projectType`) · wing, typology
and inventory fields from `src/types.ts`. Any frame element that needs data
outside this list should be flagged in Phase 1 as section 15-D (not
implemented), not designed around.

**Explicitly flag in Phase 1, do not extract as buildable**
Property cards with imagery or prices, discovery stepper, split-pane Teach
AI, workflow-rule builder, booking confirmations, analytics beyond ticket
counts.

---

## Appendix: baseline checks

Run on 2026-10-05 against the working tree, after this document was written.

| Command | Result |
| --- | --- |
| `npm run lint` | Exit 0. 0 errors, 7 `no-explicit-any` warnings (`src/lib/api.ts`, `src/types.ts`, `src/pages/BusinessHoursPage.tsx`). Pre-existing. |
| `npm test` | Exit 0. 5 files, 124 tests passed. |
| `npm run build` | Exit 0. `tsc --noEmit` clean; 66 modules. Main CSS bundle 240 kB (42 kB gzip). Output goes to ignored `dist/`. |

Vitest collects five files, not three: the three under `src/` plus stale
copies under ignored `data/merge-main/src/` (`RoleContext.test.tsx`,
`chatLanguage.test.ts`). The Vitest config sets no `include`/`exclude`, so the
reported test count includes those duplicates.
