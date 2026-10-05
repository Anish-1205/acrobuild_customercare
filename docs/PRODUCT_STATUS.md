# Product status and limitations

This page describes current scope, not a roadmap commitment. Verify changing
facts with source and fresh tests before release decisions.

## Implemented product surface

- Public customer chat with streaming and JSON endpoints.
- Grounded project, location, amenity, home-type, wing, floor, flat, inventory,
  and base-rate answers from the configured AcroBuild CS API.
- Phase 1 discovery memory: configuration → eligible live area → budget → live
  project shortlist → selected-project detail. Discovery defaults on;
  `ACROBUILD_DISCOVERY_SLOTS=false` restores project-first behavior.
- Server-side pending selections and current-project context across short
  follow-ups and browser refresh within the retained conversation.
- Workspace knowledge ingestion/search and answer evidence.
- Local ticket, callback/human-contact, and site-visit request workflows.
- Authenticated staff workspace for tickets, articles, knowledge, users, tags,
  macros, workflow rules, business hours, and automation proposals.
- Sarvam generation through an OpenAI-compatible endpoint, plus optional local
  language/voice components.

## Grounding and data rules

Property facts must come from current CS API responses or an explicitly
identified allowed fallback. With `ACROBUILD_CS_API_LIVE_ONLY=true` (the
default), failed live reads do not use the local snapshot. When live-only mode
is disabled, snapshot fallback is permitted only for matching connection
configuration and must be disclosed by `source_status`.

The shared clarification contract lists real options and retains the original
request, scope, and retry query. Unknown customer text is never promoted to a
real locality or project. Estimated base amounts use listed per-square-foot
rates and saleable area and must retain their exclusion disclaimer.

## Unsupported or partial external capabilities

The CS API does not currently provide the data or write endpoints required for:

- complete cost sheets, price history, active offers, and payment plans;
- nearby places, distance, and travel time without an external maps provider;
- real external site-visit slot booking or revisit scheduling;
- CRM lead creation/update and CRM callback creation;
- verified customer, payment, and customer-document lookup;
- creating tickets in an external AcroBuild ticketing system.

Local request/ticket fallbacks exist for site visits, callbacks, and support
tickets. They must not be described as confirmed external bookings or CRM
updates. `POST /order/refund` and `POST /subscription/cancel` are retained
legacy endpoints that return HTTP 501.

## Current technical constraints

- `services/ai_agent_service.py` still depends on a Python 3.12 bytecode-only
  runtime. This limits reviewability and interpreter upgrades; see the
  [compiled runtime note](runtime/COMPILED_RUNTIME.md).
- Chat is anonymous. Its cookie scopes conversation history but does not verify
  customer identity. Ticket/site-visit creation is rate-limited but public.
  Customer lookup and feedback use separate email-OTP tokens.
- The live CS API has no retry policy. Broad catalogue queries may require one
  request per project and can be sensitive to upstream latency or partial
  failure.
- Discovery partial-source handling remains conservative: an unresolved live
  failure can replace a partly successful answer with the generic live-data
  fallback.
- Some frontend response types lag additive backend discovery fields. Runtime
  handling is in `src/lib/api.ts`; update types when changing those contracts.
- Knowledge, translation, speech, SMTP, CS API, and LLM features have separate
  configuration and failure modes.

## Verification status

The most recent committed broad manual acceptance record is dated 2026-10-01:
90 cases passed and one remained `BLOCKED_BY_LIVE_DATA`; it is retained under
[manual evidence](evidence/manual/acceptance-report-2026-10-01.md). Treat those
results and all live transcripts as historical snapshots.

Fresh verification should include task-specific automated tests, both assist
endpoints for routing changes, and the appropriate real-service acceptance
script. A passing unit suite is not evidence that Sarvam or the CS API is
currently reachable.

The local snapshot fallback test currently assumes an older nine-project
snapshot and can fail when the process has already observed a ten-project live
catalogue. Keep this distinct from application failures and do not rewrite the
snapshot or assertion during unrelated work.

## Deferred engineering work

These are known follow-ups, not authorization to implement a new phase:

- model partial property-read status without weakening the grounding gate;
- consolidate duplicated locality and text-cleaning helpers;
- align frontend assist-response types with all additive backend fields;
- decide whether to reconstruct the remaining answer-engine bytecode;
- add upstream APIs/providers before enabling blocked pricing, maps, CRM, or
  post-sales capabilities;
- retest dependency advisories before enabling or changing the local ML stack.

Dependency-specific rationale lives in
[requirements/SECURITY_ADVISORIES.md](../requirements/SECURITY_ADVISORIES.md).
