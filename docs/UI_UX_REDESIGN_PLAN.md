# UI/UX redesign execution plan

This is the canonical execution roadmap for the remaining AcroBuild frontend
redesign. It is a planning document, not evidence that a future phase has been
implemented. Current source code is the final authority; inspect it again before
starting every phase because the inventory and risks below can drift.

Use this plan with the [frontend audit](UI_UX_FRONTEND_AUDIT.md), which contains
the detailed route, contract, state, and defect evidence, and the
[design-system foundation](DESIGN_SYSTEM.md), which records the approved design
tokens and reusable primitives.

## Status legend

- `[x]` Completed and present in repository history/source.
- `[ ]` Not started by this plan.
- `BLOCKED` Requires a product decision or unavailable evidence before its
  affected scope can be designed or implemented.
- `OUT OF SCOPE` Must not be added as part of the visual redesign.

## Design source and visual direction

The approved direction comes from the AcroBuild Figma Design System and
`docs/DESIGN_SYSTEM.md`. Implementations must use the code tokens and primitives
as their immediate source of truth:

- Plus Jakarta Sans.
- `#0055FF` primary blue, `#111827` text navy, and `#F9FAFB` off-white canvas.
- Approved `#FF8000` orange and `#10B981` green accents.
- `#D9A420` yellow remains **PROPOSED**, not approved for unrestricted use.
- Restrained accents, light surfaces, subtle borders, and subtle shadows.
- The real multi-color AcroBuild logo through the existing logo component.
- No heavy gradients, glassmorphism, or purple “AI” styling.

## Completed foundation

- [x] **Phase 0 — Frontend UI/UX audit.** Current routes, panels, contracts,
  styling, responsiveness, accessibility, and risk areas inventoried.
- [x] **Phase 0.5 — Audit verification.** Deeper staff-panel and agent-inbox
  review completed; reachability, logo, action, and evidence-shape questions
  resolved where source allowed.
- [x] **Phase 1 — Figma design-system foundations.** Foundations and component
  direction established in the AcroBuild Figma Design System.
- [x] **Phase 1.1 — Figma correction pass.** Orange `#FF8000` and green
  `#10B981` approved; yellow `#D9A420` retained as proposed; IconButton and
  Destructive Button added.
- [x] **Phase 2A — Design-system code foundation.** Tokens, self-hosted Plus
  Jakarta Sans, Button, IconButton, Input, Badge, Card, and design-system
  documentation implemented.
- [x] **Phase 2B — Login migration.** Existing staff Login page migrated to the
  design system with authentication, redirect, Remember me, password toggle,
  loading, error, role, and session behavior preserved.

## Current implementation snapshot

- One React/Vite application serves the public experience and authenticated
  staff workspace. Route and role behavior is defined in current source; see
  audit sections 3–6.
- The staff shell has a shared top bar, but its sidebar and inbox structure are
  duplicated between manager and agent implementations. Panel selection remains
  URL-query based.
- Customer chat is embedded in `CustomerHomePage` and uses streaming NDJSON
  with a non-streaming fallback and a final local article fallback. Conversation
  restoration, quick replies, and property selection depend on existing text,
  action, and storage contracts.
- Public header/layout patterns are duplicated. The home, help-centre,
  category/article, and customer-lookup surfaces have different current
  structures.
- Thirteen distinct staff surfaces are reachable. Several additional page
  components are dead or aliased and are not redesign scope unless explicitly
  authorized.
- Legacy global CSS remains active alongside the new design-system foundation.
  Page migration must therefore stay isolated until a deliberate consolidation
  phase is authorized.

## Global execution rules

These rules apply to every remaining phase:

1. Current source code is final authority. Reinspect the relevant source,
   contracts, feature flags, and tests immediately before implementation.
2. Implement one phase or explicitly named sub-phase at a time, then **STOP**
   for review. Completion does not authorize the next phase.
3. Do not invent property/project data, routes, APIs, fields, capabilities, or
   product decisions. Property facts must use the established live-data and
   grounding contracts.
4. Respect `source_status`, live-data boundaries, and established safe failure
   behavior. Never replace unavailable data with plausible values.
5. Preserve authentication, CSRF, role authorization/navigation, session
   behavior, feature flags, and frontend/backend API contracts.
6. Preserve streaming and non-streaming assist paths, conversation/state
   continuity, reset semantics, and restore behavior.
7. Site visits, callbacks, and tickets are request workflows unless current
   source proves otherwise. Never imply confirmed bookings or unsupported
   availability.
8. Do not enable dead or unreachable functionality unless the user explicitly
   requests re-enablement after resolving the applicable product decision.
9. Do not expand into backend rewrites, dependency upgrades, unrelated
   refactors, or later roadmap phases.
10. Add or update appropriate tests for behavior changes. Prefer underlying
    fixes over example-specific workarounds.
11. Keep changes reversible, narrowly scoped, accessible, responsive, and
    production-grade. Preserve unrelated work in the repository.

## Known defects and constraints to track

These are current findings, not automatic authorization to fix them in an
unrelated phase. Full evidence is in audit sections 8, 13–15, and 20–24.

- Chat stream errors and total API failure can appear as normal assistant
  answers; there is no retry control.
- Server-only conversation restore can lose terminal action buttons, while the
  local transcript and server history use different restoration capabilities.
- Chat response types lag current backend fields and values. Property evidence
  does not match the knowledge-chunk type used by the Teach AI preview.
- The public activity/data-log routes are unguarded, and the intended product
  visibility is unresolved.
- Staff navigation, public headers, analytics/dashboard patterns, and the two
  inbox implementations contain duplication and inconsistent naming.
- Some owner-visible destructive controls are rejected by server authorization.
- Several reachable inputs and controls lack labels or complete listbox/dialog
  semantics; staff surfaces can also produce nested `<main>` elements.
- Mobile navigation is incomplete, the Automation table lacks an overflow
  strategy, and focus/contrast/reduced-motion coverage is incomplete.
- Some public copy and retail-shaped staff/customer fields are not confirmed as
  AcroBuild product truth.

## Remaining roadmap

### [x] Phase 3 — Staff application shell

**Goal:** Establish the reusable authenticated layout before migrating staff
surface content.

**Scope:** `AppShell`, the reachable staff sidebar/navigation, utility header,
search anchoring, responsive navigation, and shared layout slots. Include admin,
owner, and agent variants; do not redesign panel content.

**Current relevant behavior:** The top bar is shared, while sidebars are owned
by the inbox pages. The shell queries `.support-console-sidebar` to position
search suggestions. `SearchContext`, URL `?panel=` selection, compact inbox mode,
two admin entry paths, asynchronous session bootstrap, logout, and role guards
all participate in navigation (audit sections 5–6 and 17).

**Desired result:** A design-system shell with the real AcroBuild logo,
consistent sidebar and utility header, explicit responsive navigation, and
stable content slots across every reachable staff route.

**Constraints:** Preserve role-visible destinations, URL values, default-panel
fallbacks, replace-vs-push history behavior, search behavior, guards, session
bootstrap, and logout. Do not merge the agent and manager inbox implementations
or activate hidden panels in this phase.

**High-risk regression areas:** `.support-console-sidebar` DOM coupling,
`SearchContext` suggestion positioning, `?panel=` values, the admin `rules`
special case, `/admin/workspace` versus `/admin/inbox`, role access, and refresh
redirect behavior.

**Acceptance criteria:** All currently authorized destinations remain reachable
for the same roles; active and compact/menu states remain correct; keyboard and
mobile navigation are usable; no panel content or backend contract changes; no
dead surface becomes reachable.

**Verification expectations:** Targeted navigation/role tests, direct URL and
refresh checks for all roles, search-suggestion behavior, logout, desktop/mobile
browser coverage, accessibility smoke, build, lint, full frontend tests, and
`git diff --check`.

**STOP boundary:** Stop after the shared shell and responsive navigation are
verified. Do not migrate Inbox, Teach AI, or another staff surface.

### [x] Phase 4 — Customer AI assistant and chat UX — HIGH RISK

**Status:** Complete.

Completed sub-phases:

- [x] Phase 4A — Chat contract/type stabilization.
- [x] Phase 4B — Core chat visual migration.
- [x] Phase 4C — Supported property discovery presentation.
- [x] Phase 4D1 — Ticket/site-visit form visual migration.
- [x] Phase 4D2 — Failure/retry/restore UX.

**Known limitation:** Retry metadata remains in memory. After a page refresh,
the failure state remains explicit and honest, but the retry control is not
reconstructed. This limitation remains open and is not fixed by Phase 4.

**Goal:** Apply the design system to the customer assistant while preserving its
current routing, live-data, action, streaming, and continuity semantics.

**Scope:** Message presentation, typing/loading states, quick replies, supported
property-discovery presentation, supported error/retry states, ticket and
site-visit request forms, launcher/panel responsiveness, and conversation
restore/reset presentation. Resolve contract defects only when required and
explicitly within the approved sub-phase.

**Current relevant behavior:** `CustomerHomePage` consumes NDJSON deltas and a
final payload, falls back to non-streaming assist, then may generate a local
article response. Raw bot text supports display truncation and numbered/named
selection. Quick-reply actions can reset the conversation or open request forms.
Server discovery and the client wing/floor/flat flow are separate state machines
(audit sections 8 and 15).

**Desired result:** Structured, accessible chat presentation that makes
supported loading, source, failure, retry, quick-reply, discovery, and request
states understandable without changing what the system can do or claim.

**Constraints:** Preserve both assist paths, exact quick-reply values/actions,
`browse_projects` reset behavior, raw selection text, `visibleMessageText`,
`isRestoringChat`, transcript fields, conversation ID rotation, localization,
feature flags, and live grounding. Do not expose server-only pending state. Do
not unify the two property flows until Open Product Decision 5 is resolved.

**High-risk regression areas:** NDJSON partial failure, quick-reply dispatch,
conversation reset/restore, numbered and named project selection, transcript
length and exact matching, client vs server property state, silent fallback,
scroll selectors, request wording, and stale frontend response types.

**Acceptance criteria:** Streaming and non-streaming transcripts preserve
content and actions; short and named selections still work; unavailable live
data stays honest; refresh/reset continuity is unchanged or deliberately fixed
with regression coverage; request forms retain their exact effects; desktop and
mobile chat remain keyboard accessible.

**Verification expectations:** Unit tests for response/action rendering and
state transitions; both assist endpoints; restore/reset and repeated-failure
tests; named/numbered selection cases; feature-flag coverage; ticket/site-visit
form tests; browser accessibility/responsive checks; required real API/LLM
acceptance when live-data semantics change; build, lint, full tests, and
`git diff --check`.

**STOP boundary:** Stop after chat-specific acceptance. Do not redesign the
surrounding public site, staff Inbox, or unsupported property capabilities.

### [x] Phase 5 — Public customer experience

**Status:** Complete for the authorized scope.

Completed sub-phases:

- [x] Phase 5A — `/home` migration and shared `PublicShell` header/footer.
- [x] Phase 5B — `/home/about`, category, article, and not-found/empty states.
- [x] Phase 5C — Customer lookup (`/home/project-support`, `/home/order-lookup`).

**Verification outcome:** Build, lint (no errors), and the full frontend suite
pass. A desktop (1440px) and mobile (390px) browser matrix covered all eight
public routes, shared navigation/footer, the mobile menu, chat mount boundaries,
article-to-chat actions, and the lookup keyboard/focus flow; the lookup routes
have no serious automated accessibility findings. The lookup OTP flow, chat
restore, and assist responses were verified with **MOCKED** responses only. Live
OTP delivery, live `/customer/verified` data, and live chat/LLM behavior are
**BLOCKED/UNVERIFIED** because the backend was not running during verification.

**Known limitations:**

- The lookup result labels ("Buyer profile", "Project records", "Portfolio
  value", "Plans and schedules", "Next review") and USD formatting are preserved
  unchanged from the pre-migration page. They are not confirmed AcroBuild
  terminology and remain subject to Open Product Decision 7.
- The Phase 5 `/home` guide-number contrast regression is corrected with the
  approved primary-action token. Automated scans still report the pre-existing
  orange caption below AA contrast on `/home/about`, and two findings inside the
  Phase 4 chat (`.store-chat-online` ARIA usage and the "Automated" note
  contrast). Those pre-existing findings are left for Phase 7.
- On mobile the chat opens full-screen on first load and covers the page until
  closed; this is existing Phase 4 behavior.
- Legacy `.customer-lookup-*` rules remain in `styles.css` unused, pending the
  deliberate stylesheet consolidation.

**Outside completed scope:** `/home/api-activity` and `/home/data-api-logs` were
not changed and remain unresolved under Open Product Decision 3. Open Product
Decisions 2, 4, 7, and 8 are also untouched.

**Goal:** Create a coherent public AcroBuild experience around the existing,
reachable public routes.

**Scope:** `/home`, `/home/about`, category and article views, customer lookup,
shared public navigation/footer, responsive structure, and removal of
internal/demo-looking presentation where supported by confirmed copy and data.
Public activity/data-log routing remains blocked by Open Product Decision 3.

**Current relevant behavior:** Public pages use three header patterns and only
`CustomerHomePage` has a footer. `/home` is a marketing branch, `/home/about` is
the help-centre landing, customer lookup is shared by two paths, and chat is
mounted only on `CustomerHomePage` variants (audit sections 4, 6, and 14).

**Desired result:** Shared design-system navigation and footer with consistent
page hierarchy, content states, responsive behavior, and clearly customer-facing
presentation across existing routes.

**Constraints:** Preserve route/access behavior, article/category lookup,
customer OTP flow, existing chat mount boundaries, and all API contracts. Do not
publish workspace articles, correct unknown contact details, expose unsupported
buyer data, or change route visibility without a resolved product decision.

**High-risk regression areas:** Duplicated header selectors, global stylesheet
order, public/staff endpoint boundaries, hard-coded contact copy, customer lookup
types, article links, and interaction with the floating chat layer.

**Acceptance criteria:** Existing public routes retain their behavior; shared
navigation and footer work at desktop/mobile widths; loading/empty/error states
are explicit; confirmed AcroBuild copy replaces demo/internal presentation only
where source exists; staff-only data is not exposed.

**Verification expectations:** Route and link tests, article/category states,
customer lookup without destructive or real-customer actions, chat coexistence,
responsive and accessibility browser checks, build, lint, full tests, and
`git diff --check`.

**STOP boundary:** Stop after the named public routes. Do not alter chat internals
from Phase 4 or begin staff workspace migration.

### [x] Phase 6A — Staff Inbox

**Status:** Complete. Committed in `dcc69a4` ("feat: complete Phase 6 staff
workspace redesign"). `src/pages/StaffInbox.css` and
`src/pages/StaffInbox.test.tsx` cover both inbox implementations; role
ownership, polling, and endpoint behavior are unchanged.

**Goal:** Migrate the manager and agent inbox experiences to the design system
without changing ticket operations or authorization boundaries.

**Scope:** Ticket lists, filters, thread, composer, details rail, assignment,
tags, status, internal notes, customer context, macros, attachments, polling,
loading/empty/error feedback, and responsive layout for both implementations.

**Current relevant behavior:** Admin/owner share one inbox implementation while
agents use a near-duplicate with fewer controls and five-second visibility-aware
polling. Server permissions remain authoritative (audit sections 5 and 18).

**Desired result:** Consistent, accessible inbox presentation and states for all
roles, using the Phase 3 shell and approved primitives.

**Constraints:** Preserve ownership rules, polling, ticket selection, unread
behavior, message sending, macro substitution, attachments, assignment/tag
restrictions, status transitions, and current endpoints. Consolidation of the
two inboxes is blocked by Open Product Decision 11.

**High-risk regression areas:** Role-specific actions, polling races, selected
ticket continuity, SearchContext, macro variables, attachment preview focus,
tag rules, Ctrl/Cmd+Enter, and duplicated shared selectors.

**Acceptance criteria:** Every currently supported ticket action produces the
same request and state transition; forbidden actions remain unavailable or are
handled consistently with server policy; empty/loading/error states and
responsive navigation are usable; no retail-shaped copy is replaced without
confirmed AcroBuild language.

**Verification expectations:** Role-matrix tests, mocked API transition tests,
polling/visibility checks, composer/macro/attachment tests, keyboard and mobile
browser coverage, build, lint, full tests, and `git diff --check`.

**STOP boundary:** Stop after both reachable inboxes pass. Do not migrate other
staff panels or decide whether their implementations should merge.

### [x] Phase 6B — Teach AI and Articles

**Status:** Complete. Committed in `dcc69a4`, covered by
`src/pages/Phase6Knowledge.test.tsx`. Teach AI and Articles/Training Documents
workflows, APIs, and role checks are unchanged.

**Goal:** Migrate the two reachable knowledge/content-management surfaces while
preserving their distinct current workflows.

**Scope:** Teach AI upload, URL import, typed-answer creation, assist test, and
integrated-link list; Articles and Training Documents directories, editors,
uploads, filters, and assist preview.

**Current relevant behavior:** Teach AI is a simplified reachable surface.
Articles has parallel article/document workflows and repeated editor markup.
Property evidence currently does not match the preview’s knowledge-chunk shape
(audit sections 8 and 18).

**Desired result:** Clear design-system content workflows with consistent form,
directory, progress, empty, error, success, and preview presentation.

**Constraints:** Preserve APIs, role checks, source labels, upload/import
behavior, article/document distinctions, and destructive confirmations. Do not
enable the dead Knowledge Base, Rules, Products, Shopping Assistant, or Support
Actions pages. Do not invent evidence metadata.

**High-risk regression areas:** File handling, admin-only deletion, native
confirmation replacement, non-streaming assist previews, mismatched evidence
shapes, parallel editor state, and long-running progress feedback.

**Acceptance criteria:** Existing create/update/upload/import/delete/test flows
remain behaviorally equivalent; evidence renders only fields actually supplied;
role restrictions hold; every async state is visible and accessible; no dead
surface becomes reachable.

**Verification expectations:** Targeted form and API tests for both surfaces,
role/destructive-action coverage, evidence variants, keyboard/focus and
responsive browser checks, build, lint, full tests, and `git diff --check`.

**STOP boundary:** Stop after Teach AI and Articles. Do not implement workflow
rules or redesign the remaining staff panels.

### [x] Phase 6C — Staff configuration and libraries

**Status:** Complete. Committed in `dcc69a4`, covered by
`src/pages/Phase6Configuration.test.tsx`. Chat Box, Open Hours, Saved Replies,
Manage Tags, Users, and CS API Settings retain their persistence destinations,
secret boundaries, and role authorization.

**Goal:** Standardize the remaining editable staff libraries and configuration
forms without expanding their capabilities.

**Scope:** Chat Box, Open Hours, Saved Replies, Manage Tags, Users, and CS API
Settings, migrated in that order only if each preceding surface is accepted.

**Current relevant behavior:** Chat Box is browser-local; Open Hours edits one
selected profile; Saved Replies, Tags, and Users use distinct list/editor
patterns; some Users controls are local-only messages; CS API Settings has
write-only secret handling and stronger existing form semantics (audit section
18).

**Desired result:** Consistent directories, editors, validation, state feedback,
destructive controls, responsive layouts, and accessible labels using shared
design-system patterns.

**Constraints:** Preserve `localStorage` behavior, API requests, secret
boundaries, role authorization, timezone fallback, macro tokens, and current
save semantics. Do not turn local-only controls into backend behavior or treat
Chat Box as deployable product functionality without a decision.

**High-risk regression areas:** Widget configuration persistence, unsupported
external snippet host, business-hour ranges/timezones, macro token drift,
owner-visible destructive actions, native color input, user status/save
semantics, and API-key confidentiality.

**Acceptance criteria:** Every current persisted action writes to the same
destination; local-only actions remain clearly local; secrets are never exposed;
authorization remains enforced; forms are labelled, keyboard usable, and
responsive; unsupported capabilities are not implied.

**Verification expectations:** Per-surface state and persistence tests,
role/authorization cases, validation and secret-display checks, browser
keyboard/mobile coverage, build, lint, full tests, and `git diff --check` after
each accepted surface.

**STOP boundary:** Stop after the explicitly authorized surface or batch. Do not
advance automatically through the list or begin reporting/automation work.

### [x] Phase 6D — Staff reporting, diagnostics, and Automation

**Status:** Complete. Committed in `dcc69a4`, covered by
`src/pages/Phase6Reporting.test.tsx`. Analytics, Dashboard, API Activity, Data
APIs, and Automation retain their calculation inputs, local-only trace scope,
route reachability, and proposal confirmation flow. Automation remains
URL-only and unlinked.

**Goal:** Migrate Analytics, Dashboard, API Activity, Data APIs, and Automation
without inventing metrics, diagnostics, or automation outcomes.

**Scope:** Existing KPI/filter/chart/list views, local request traces, data-call
details, automation escalation/capacity/proposal workflows, tables, and all
loading/empty/error states.

**Current relevant behavior:** Analytics and Dashboard derive metrics from the
ticket list in memory. Activity and Data APIs are browser-local traces.
Automation is URL-only, uses a propose/confirm flow, and is not linked in the
sidebar (audit sections 4 and 18).

**Desired result:** Accurate, accessible design-system reporting and diagnostic
surfaces with readable responsive data presentation and explicit state/status
feedback.

**Constraints:** Preserve calculation inputs, filters, local-only trace scope,
route reachability, role access, API contracts, and proposal confirmation. Do
not link Automation, change public visibility, or add analytics fields without
separate authorization and resolved product decisions.

**High-risk regression areas:** Full-list client metrics, filter parity,
Analytics/Dashboard duplication, trace sanitization, table overflow, proposal
expiry/confirmation, nested landmarks, and public diagnostic routes.

**Acceptance criteria:** Displayed metrics remain derivable from current data;
trace fields stay sanitized; proposal actions preserve their two-step behavior;
all tables/charts have accessible alternatives and mobile handling; route and
role visibility are unchanged.

**Verification expectations:** Calculation/filter tests, trace privacy checks,
proposal state-transition tests, role/direct-route checks, responsive and
accessibility browser coverage, build, lint, full tests, and `git diff --check`.

**STOP boundary:** Stop after the explicitly authorized reporting/diagnostic
batch. Do not expose private diagnostics or link previously URL-only features.

### [x] Phase 7 — Responsive, accessibility, and UX consistency pass

**Status:** Complete for the authorized consistency and defect scope.

**Verification outcome:** A reusable Playwright/axe suite now covers the public,
login, admin, owner, and agent route variants with deterministic API responses.
The responsive matrix uses 1440px, 1280px, 768px, 390px, and 320px widths;
reachable surfaces have no measured horizontal page overflow, and the automated
WCAG A/AA smoke has no serious or critical axe findings. Browser checks also
cover mobile staff navigation focus/Escape behavior, chat focus restoration,
role redirects, reduced motion, and a non-default supported widget accent.

**Corrections:** Approved tokens now provide sufficient contrast for staff
navigation labels, ticket-count metadata, inbox empty-state eyebrows, the public
"Fast answer lanes" caption, and the chat "Automated" note. The chat online
indicator now exposes visible text without invalid ARIA, staff-shell motion is
suppressed under `prefers-reduced-motion`, and the reporting surfaces consistently
use the source-supported term "customer". No route, role, API, chat, or property
behavior changed.

**Limitations:** Browser evidence is MOCKED, not LIVE. Arbitrary administrator
widget colors still have no automatic contrast-selection contract; the tested
non-default blue is accessible, but every possible custom value cannot be
certified. Public diagnostic visibility and the other open product decisions
remain unchanged. Live release verification remains Phase 8 work.

**Goal:** Verify and close cross-screen usability gaps after all approved page
migrations, without redesigning product behavior.

**Scope:** Breakpoint consistency, navigation, overflow, typography, spacing,
focus order/visibility, labels, landmarks, headings, live regions, dialogs,
contrast, motion preferences, state language, and reusable-pattern consistency.

**Current relevant behavior:** The audit found desktop-first breakpoint sprawl,
incomplete mobile navigation, missing labels/semantics, nested landmarks,
limited focus management, unmeasured contrast risks, and no automated
accessibility run (audit sections 20–21).

**Desired result:** Every migrated reachable surface meets an agreed responsive
matrix and practical WCAG-oriented keyboard, semantics, focus, and contrast
baseline with consistent feedback patterns.

**Constraints:** This is a consistency and defect pass, not permission to add
features, alter copy requiring product approval, rewrite APIs, or enable dead
screens. Keep widget-configurable colors and content variability in test cases.

**High-risk regression areas:** CSS source order, lazy-loaded CSS persistence,
focus restoration, chat scrolling, fixed-position layers, tables, listbox
semantics, auto-dismiss feedback, configured colors, and mobile browser chrome.

**Acceptance criteria:** No horizontal overflow at supported widths; keyboard
flows are complete; visible focus and accessible names are present; landmark and
heading structure is valid; contrast and reduced-motion behavior meet the
agreed baseline; shared states and terminology are consistent.

**Verification expectations:** Cross-route viewport matrix, keyboard-only
walkthroughs, automated accessibility scans plus manual review, contrast checks,
reduced-motion checks, full frontend tests/build/lint, and `git diff --check`.

**STOP boundary:** Stop after recording and resolving only redesign-introduced or
explicitly authorized cross-screen issues. Do not start final release changes.

### [x] Phase 8 — Final regression, visual consistency, and production readiness

**Status:** Complete for the authorized verification scope. READY FOR RELEASE
DECISION WITH BLOCKERS (see the Phase 8 readiness report for the full
breakdown).

**Verification outcome:** Fresh evidence gathered against the current working
tree: 183/183 frontend unit tests pass; production build and `tsc --noEmit`
succeed; ESLint reports 0 errors (7 pre-existing `no-explicit-any` warnings,
outside redesign scope); `git diff --check` is clean; the 7-test Playwright/axe
suite (`tests/e2e/phase7-accessibility.spec.ts`) passes with MOCKED browser
responses, covering the public/login/admin/owner/agent route and role matrix
at five viewports with no serious/critical axe findings and no horizontal
overflow; backend `ruff check` and the scoped `mypy` run are clean; backend
pytest passes 1828 of 1866 collected tests, with the remaining 38 failing only
on a Windows shared-temp-directory `PermissionError` unrelated to any redesign
change; a fresh, unmocked run of `scripts/live_disambiguation_check.py`
against the real Sarvam LLM and real CS API passed every live assertion and
regenerated `docs/evidence/live/disambiguation.json`. Live backend auth
boundaries were independently smoke-checked (`/api/admin/tickets` and
`/admin/all-tickets` return 401 without a session).

**Known gaps:** `tests/e2e/` and `playwright.config.ts` remain uncommitted, so
Phase 7/8 browser evidence currently depends on local working-tree files, not
repository history. Full manual live chat/staff-workflow/OTP verification
against a browser was not performed in this pass; see the readiness report for
what is BLOCKED versus PASS.

**Constraints:** Verification does not authorize fixes outside the approved
redesign scope, deployment, real customer actions, fabricated live data, or
changes to backend behavior. Unavailable evidence is BLOCKED, never PASS.

**Goal:** Produce fresh evidence that the approved redesign is behaviorally safe,
visually consistent, and ready for the user’s release decision.

**Scope:** All reachable migrated routes and role variants; design-token and
component consistency; auth/navigation; chat paths and continuity; staff
workflows; public workflows; responsive/accessibility coverage; documentation
accuracy; final change inventory.

**Current relevant behavior:** Earlier audit and test results are historical
snapshots. Live property, LLM, session, and browser behavior require fresh,
separately classified evidence.

**Desired result:** A traceable PASS/FAIL/BLOCKED report that distinguishes
static, mocked, disposable, and live verification and identifies any remaining
release blockers without masking them.

**Constraints:** Verification does not authorize fixes outside the approved
redesign scope, deployment, real customer actions, fabricated live data, or
changes to backend behavior. Unavailable evidence is BLOCKED, never PASS.

**High-risk regression areas:** Role/session boundaries, CSRF, direct routes,
stream/non-stream parity, live-data failure, conversation restore, property
selection, request workflows, local storage, CSS leakage, mobile navigation,
and external-service availability.

**Acceptance criteria:** All approved phase criteria have fresh evidence;
reachable screens use the design system consistently; no unrelated screen or
backend contract changed; failures and blockers are documented; open product
decisions remain unresolved unless the user supplied decisions.

**Verification expectations:** Full automated frontend suite, build/lint/type
checks, route/role browser matrix, accessibility and responsive regression,
targeted API/integration checks, required live chat/property acceptance with no
mocks, documentation/link review, `git diff --check`, and final git status.

**STOP boundary:** Stop with the readiness report and artifacts. Do not deploy,
merge, push, or begin unapproved remediation.

## Open Product Decisions

These questions remain unresolved. Do not answer them through implementation:

1. Which long-term sidebar/panel set is intended: the reachable simplified
   Teach AI surface, or the dead Knowledge Base, Rules, Products, Shopping
   Assistant, and Support Actions implementations?
2. Should `/home/about` remain and be linked as the help-centre landing, or is
   `/home` intended to replace it?
3. Should `/home/api-activity` and `/home/data-api-logs` remain public?
4. Should published workspace articles be visible to anonymous visitors?
5. Should the client-driven wing → floor → flat flow remain alongside server
   discovery?
6. Is voice conversation in scope, given that its UI has no reachable entry
   point?
7. What AcroBuild buyer data does `/customer/verified` actually return?
8. What are the correct public phone number, support hours, and timezone?
9. Is the browser-local Chat Box panel a real product surface, and what should
   replace or validate its external installation host?
10. Does the CS API provide confirmed image, price, or configuration fields
    that may support property cards?
11. Should the agent inbox remain a separate implementation?
12. What values can the compiled runtime emit for `source_status`,
    `agent_mode`, and `retrieval_mode`?

Any phase affected by one of these questions must exclude that scope or stop as
`BLOCKED` until the user provides a decision or authoritative source evidence.

## Explicitly out of scope

- Re-enabling dead/unreachable screens, voice UI, placeholder panels, or hidden
  navigation items.
- New routes, APIs, backend capabilities, data fields, analytics, booking flows,
  SSO, sign-up, password reset, or confirmed-availability experiences.
- Backend or database rewrites, dependency upgrades, deployment, and broad
  refactors unrelated to the authorized phase.
- Invented property imagery, prices, configurations, inventory, availability,
  possession, offers, locations, or other project facts.
- Treating request workflows as confirmed site visits, callbacks, tickets
  resolved by a human, or bookings.
- Resolving the Open Product Decisions without explicit user direction.

## Phase handoff checklist

Before each implementation phase:

- [ ] Confirm the exact authorized phase/sub-phase and STOP boundary.
- [ ] Re-read current relevant source, tests, feature flags, and audit sections.
- [ ] Check git status and preserve unrelated work.
- [ ] Identify behavior contracts and create a regression plan before styling.
- [ ] Confirm required product decisions are resolved or exclude blocked scope.

Before reporting a phase complete:

- [ ] Verify every acceptance criterion with the appropriate evidence type.
- [ ] Run targeted tests and justified broader checks.
- [ ] Confirm no unrelated route or screen was restyled.
- [ ] Record PASS, FAIL, and BLOCKED results honestly.
- [ ] Run `git diff --check`, report git status, and STOP for review.
