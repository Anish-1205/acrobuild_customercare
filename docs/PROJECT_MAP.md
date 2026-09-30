# Project map (audit, 2026-09-30)

Audit snapshot of branch `work/2026-09-09-chatbot-fixes-observability`. Source code
was read directly; where behaviour lives only in compiled bytecode it is marked
**(blob)** and described from `docs/DECOMPILED_MAP.md` plus constant inspection.
"unverified" means not confirmed from source.

---

## 1. Repo tree

| Path | Purpose |
|---|---|
| `app.py` | Entry point (`uvicorn app:api`); includes every router except `sessions` (included in `api_context.py:340`). |
| `api_context.py` | FastAPI app, lifespan (DB init + migrations), middleware (CORS, admin auth/CSRF, request-id logging), all shared Pydantic request models, grounded router shortcuts, `_enforce_live_property_data`. |
| `qwen.py` | Legacy-named LLM facade → Sarvam only. |
| `sarvam_client.py` | httpx client for an OpenAI-compatible `/v1/chat/completions`. |
| `routers/` | HTTP endpoints: `assist`, `automation`, `cs_api_settings`, `customer`, `health`, `knowledge`, `properties`, `sessions`, `workspace`. |
| `graph/main_orchestrator.py` | Turn preparation, routing, general LLM chat, call-booking/human-contact flows, localization. |
| `graph/haystack_conversation_pipeline.py` | Loader: execs `haystack_conversation_pipeline_source.py` (hand reconstruction) or the `.pyc`, then wraps functions. |
| `graph/haystack_conversation_pipeline_source.py` | Reconstructed Haystack router / contextual resolver / relevance guard. |
| `graph/workflow.py` | Ticket creation pipeline `run_workflow()` (plain function, not a graph). |
| `services/ai_agent_service.py` | Loader for `ai_agent_service_runtime(.patched).pyc` **(blob, ~10k lines)** + ~470 lines of source pre-handlers. |
| `services/acrobuild_company_service.py` | CS API client, caching, snapshot fallback, project matching, company knowledge chunks. |
| `services/property_clarification_service.py` | Project/wing/floor/flat/home-type clarification contract. |
| `services/project_home_type_service.py` | BHK / configuration builders. |
| `services/amenity_search_service.py` | Live amenity index and reverse amenity search. |
| `services/conversation_store_service.py` | Server-side chat history (`conversation_turns`) + hidden state markers. |
| `services/turn_analysis_service.py` | LLM turn classifier (intent, language, script, English rendering). |
| `services/knowledge_index_service.py` / `knowledge_ingestion_service.py` | Workspace RAG index / document + URL ingestion. |
| `services/database_service.py` | SQLite (`support_system.db` at repo root) schema + CRUD. |
| `services/migration_service.py` | Versioned SQLite migrations (indexes, sessions, audit, conversation turns). |
| `services/otp_service.py`, `auth_service.py`, `session_service.py` | Customer email OTP; staff JWT + session rotation. |
| `services/request_security_service.py` | Body-size limit, per-IP rate limits, audit events. |
| `services/provider_resilience_service.py` | LLM circuit breaker. |
| `services/rag_evaluation_service.py`, `answer_evidence_service.py` | Per-turn proxy RAG metrics. |
| `services/ticket_metadata_service.py`, `intent_service.py`, `admin_settings_service.py`, `macro_service.py`, `workflow_automation_service.py` | Ticket tagging/queues, tags/rules/business hours, macros, escalation. |
| `services/indic_translation_service.py`, `indic_tts_service.py`, `reply_language.py`, `tenglish_rewriter_service.py` | Language detection, TTS; translation model warm-up only; Tenglish rewriter is not imported anywhere. |
| `src/` | React/Vite app: customer home + chat (`pages/CustomerHomePage.tsx`), staff workspace pages, `lib/api.ts`, `types.ts`. |
| `tests/` | 44 pytest files (see §14). `src/**/*.test.ts(x)`: 2 frontend tests. |
| `scripts/` | Live acceptance checks, eval runners, bytecode tools, demo seed. `check_live_property_data.py` is untracked. |
| `docs/` | Architecture, CS API docs, audits, live-check JSON results. |
| `data/` (git-ignored) | RAG index JSON, company snapshot, uploads, `merge-main/` (a stale code copy). |
| `resources/` | Evaluation CSV/XLSX, reference company text. |

---

## 2. Backend routes

All routers have no prefix unless noted. "—" = no body model.

| Method | Path | Request model | Handler | File |
|---|---|---|---|---|
| POST | `/api/support/assist` | `SupportAssistRequest` | `get_support_assist` | routers/assist.py:414 |
| POST | `/api/support/assist/stream` | `SupportAssistRequest` | `stream_support_assist` | routers/assist.py:502 |
| POST | `/api/support/voice/synthesize` | `VoiceSynthesisRequest` | `synthesize_support_voice` | routers/assist.py:479 |
| DELETE | `/api/support/conversations/{conversation_id}` | — | `delete_conversation` | routers/assist.py:653 |
| GET | `/api/admin/automation/escalations` | — | `escalations` | routers/automation.py |
| GET | `/api/admin/automation/capacity` | — | `capacity` | routers/automation.py |
| POST | `/api/admin/automation/proposals` | `ProposalRequest` | `propose` | routers/automation.py |
| POST | `/api/admin/automation/proposals/{proposal_id}/confirm` | `ConfirmationRequest` | `confirm` | routers/automation.py |
| POST | `/api/support/feedback` | `FeedbackRequest` (+Bearer OTP token) | `feedback` | routers/automation.py |
| GET / PUT | `/api/admin/cs-api-settings` | — / `CSApiSettingsRequest` | `get_settings` / `update_settings` | routers/cs_api_settings.py (prefix; `require_admin_user`) |
| POST | `/create_ticket` | `TicketRequest` | `create_ticket` | routers/customer.py |
| GET | `/customer` | query `email` | `get_customer` | routers/customer.py |
| POST | `/auth/otp/request` | `OtpRequest` | `request_otp` | routers/customer.py |
| POST | `/auth/otp/verify` | `OtpVerifyRequest` | `verify_otp` | routers/customer.py |
| GET | `/auth/me` | — | `workspace_me` | routers/customer.py |
| GET | `/customer/verified` | query `email` + Bearer | `get_verified_customer` | routers/customer.py |
| GET | `/orders` | query `email` | `get_orders` | routers/customer.py (legacy) |
| POST | `/ticket/message` | `TicketMessageRequest` | `add_ticket_message` | routers/customer.py |
| POST | `/order/refund` | `RefundRequest` | `refund_order` (501) | routers/customer.py (legacy) |
| POST | `/subscription/cancel` | `SubscriptionCancelRequest` | `cancel_subscription` (501) | routers/customer.py (legacy) |
| GET | `/` | — | `home` | routers/health.py |
| GET | `/api/health` | — | `api_health` | routers/health.py |
| GET | `/api/admin/provider-health` | — | `get_provider_health` | routers/health.py |
| GET | `/api/local-product-feeds`, `/local-data/products/{feed_key}.csv`, `/local-data/products/{feed_key}` | — | `get_local_product_feeds_api`, `get_local_product_feed_csv_api`, `get_local_product_feed_html_api` | routers/health.py (legacy food feed) |
| GET/POST | `/api/admin/articles` (+ `/admin/articles`) | — / `SupportArticleCreateRequest` | `get_admin_articles_api` / `create_admin_article_api` | routers/knowledge.py |
| PUT | `/api/admin/articles/{article_id}` (+ `/admin/…`) | `SupportArticleUpdateRequest` | `update_admin_article_api` | routers/knowledge.py |
| GET/POST | `/api/admin/knowledge-documents` (+ `/admin/…`) | — / `KnowledgeDocumentCreateRequest` | `get_admin_knowledge_documents_api` / `create_admin_knowledge_document_api` | routers/knowledge.py |
| POST | `/api/admin/knowledge-documents/upload` (+ `/admin/…`) | `KnowledgeDocumentUploadRequest` | `upload_admin_knowledge_documents_api` | routers/knowledge.py |
| POST | `/api/admin/knowledge-documents/import-url` (+ `/admin/…`) | `KnowledgeDocumentUrlImportRequest` | `import_admin_knowledge_url_api` | routers/knowledge.py |
| PUT | `/api/admin/knowledge-documents/{document_id}` (+ `/admin/…`) | `KnowledgeDocumentUpdateRequest` | `update_admin_knowledge_document_api` | routers/knowledge.py |
| POST | `/api/admin/knowledge-documents/delete` (+ `/admin/…`) | `KnowledgeDocumentDeleteRequest` | `delete_admin_knowledge_documents_api` | routers/knowledge.py |
| POST | `/api/admin/knowledge-documents/reset` (+ `/admin/…`) | — | `reset_admin_workspace_knowledge_api` | routers/knowledge.py |
| GET | `/api/property-flow/projects` | — | `property_flow_projects` | routers/properties.py |
| GET | `/api/property-flow/projects/{project_id}/wings` | — | `property_flow_wings` | routers/properties.py |
| GET | `/api/property-flow/wings/{wing_id}/typologies` | — | `property_flow_typologies` | routers/properties.py |
| GET | `/api/property-flow/wings/{wing_id}/inventory` | query `available_only` | `property_flow_inventory` | routers/properties.py |
| POST | `/api/site-visits` | `SiteVisitRequest` | `create_site_visit` | routers/properties.py |
| POST | `/auth/login` | `LoginRequest` | `login` | routers/sessions.py (prefix `/auth`) |
| POST | `/auth/refresh` | — | `refresh` | routers/sessions.py |
| POST | `/auth/logout` | — | `logout` | routers/sessions.py |
| GET | `/admin/all-tickets` | query limit/offset | `get_admin_tickets` | routers/workspace.py |
| PUT | `/admin/tickets/{ticket_id}/assign`, `/api/admin/tickets/{ticket_id}/assign` | `UpdateTicketAgentRequest` | `assign_ticket_to_agent`, `update_admin_ticket_assignee` | routers/workspace.py |
| PUT | `/admin/tickets/{ticket_id}/status`, `/api/admin/tickets/{ticket_id}/status` | `UpdateTicketStatusRequest` | `update_ticket_status_endpoint`, `update_admin_ticket_status` | routers/workspace.py |
| GET | `/api/admin/tickets` | query limit/offset/status/search | `get_admin_tickets_api` | routers/workspace.py |
| GET/POST/PUT | `/api/admin/users` (+ `/admin/users`), `/api/admin/users/{user_id}` | — / `SupportUserCreateRequest` / `SupportUserUpdateRequest` | `get_admin_users_api`, `create_admin_user_api`, `update_admin_user_api` | routers/workspace.py |
| GET | `/api/admin/tickets/{ticket_id}/detail` | — | `get_admin_ticket_detail` | routers/workspace.py |
| POST | `/api/admin/tickets/{ticket_id}/messages` | `AdminTicketMessageRequest` | `post_admin_ticket_message` | routers/workspace.py |
| POST | `/api/admin/tickets/{ticket_id}/reply` | `AdminTicketReplyRequest` | `post_admin_ticket_reply` | routers/workspace.py |
| POST | `/api/admin/tickets/{ticket_id}/read` | — | `mark_admin_ticket_read` | routers/workspace.py |
| POST | `/api/admin/tickets/{ticket_id}/notes` | `AdminTicketNoteRequest` | `create_admin_ticket_note` | routers/workspace.py |
| POST | `/api/admin/tickets/{ticket_id}/close` | — | `close_admin_ticket` | routers/workspace.py |
| GET | `/api/admin/tickets/{ticket_id}/recommended-macros` | — | `get_admin_recommended_macros` | routers/workspace.py |
| GET | `/api/admin/attachment` | query `path` | `get_admin_attachment` | routers/workspace.py |
| GET/POST/PUT/DELETE | `/api/admin/tags`, `/api/admin/tags/{tag_id}`, POST `/api/admin/tags/merge`, PUT `/api/admin/tickets/{ticket_id}/tags` | `TagRequest`, `TagMergeRequest`, `TicketTagUpdateRequest` | `get_admin_tags`, `create_admin_tag`, `update_admin_tag`, `delete_admin_tag`, `merge_admin_tags`, `update_admin_ticket_tags` | routers/workspace.py |
| GET/POST/PUT/DELETE | `/api/admin/macros[/{macro_id}]`, POST `…/duplicate`, POST `…/archive` | `MacroRequest`, `MacroArchiveRequest` | `get_admin_macros`, `get_admin_macro`, `create_admin_macro`, `update_admin_macro`, `duplicate_admin_macro`, `archive_admin_macro`, `delete_admin_macro` | routers/workspace.py |
| GET/POST/PUT/DELETE | `/api/admin/workflow-rules[/{rule_id}]`, `/windows`, `/{rule_id}/affected`, `/{rule_id}/duplicate`, `/restore-default` | `WorkflowRuleUpdateRequest` | `get_admin_workflow_rules` … `restore_admin_default_workflow_rule` | routers/workspace.py |
| GET/POST/PUT/DELETE | `/api/admin/business-hours/profiles[/{profile_id}]`, GET `/api/admin/business-hours/default` | `BusinessHoursProfileRequest` | `get_admin_business_hours_profiles` … `delete_admin_business_hours_profile` | routers/workspace.py |

Every `/api/admin/*` and `/admin/*` path is additionally gated by `enforce_admin_route_auth` (api_context.py:389).

---

## 3. Request traces

### a) "What amenities does <project> have?"

1. **Frontend**: `CustomerHomePage.tsx:1632` → `streamSupportAssist()` (`src/lib/api.ts:495`) → `POST /api/support/assist/stream` (Vite proxy). On stream failure the page falls back to `getSupportAssist()` (`api.ts:452`, JSON endpoint).
2. **Route**: `stream_support_assist()` (routers/assist.py:502) → `ConversationSession(cookie, conversation_id).load()` replaces client history with server history → `event_stream()`.
3. `clear_assist_response_cache()` → `begin_data_api_trace()` → `_prepare_lookup_turn()` → `prepare_turn()` (main_orchestrator.py:98) → `_merge_conversation()` → `analyze_turn()` (**LLM call #1**, turn_analysis_service.py:257) → `resolve_contextual_support_issue()` (haystack wrapper) → `TurnContext`.
4. Back in `_prepare_lookup_turn()`: `_pending_project_lookup()` → `get_pending_project_lookup()`; the issue contains `amenit`, so intent is forced to `property` (assist.py:296).
5. `_is_broad_project_request()` → False; `turn.analysis.unsure` → False.
6. `_grounded_property_shortcut()` (assist.py:130), evaluated in order:
   `build_grounded_site_visit_document_assist` → None ·
   `build_catalogue_home_type_answer` → None · `build_project_home_type_answer` → None ·
   `build_generic_home_type_answer` → None ·
   `build_grounded_amenity_search_assist` → builds `live_amenity_index()` (**GET projects + GET amenities for every project**) then returns None because no specific amenity is named ·
   `narrow_project_choice_by_locality` → None · `build_inventory_selection_answer` → None ·
   **`build_grounded_project_amenities_assist`** (api_context.py:1032) → `get_company_projects()` → `_customer_facing_projects()` → `_resolve_project_selection()` → `resolve_project_candidates_from_text()` → one match → `get_project_amenities(id)`.
7. **External**: `GET {base}/api/cs/{companyId}/projects/{id}/amenities` via `_cached_request()` → `_cached_configured_request()` → `_request_json()` (header `apiKey`); logged by `log_data_api_call()`.
8. **Shaping**: deterministic bullet list of `iconName` values + "Would you like to raise a support ticket, book a site visit, or request a call?"; `route="property"` added. `_complete_payload()` (assist.py:369): `apply_clarification_contract()` (no-op) → `_enforce_live_property_data()` → `source_status="live_api"` → next-step `quick_replies` (Browse all projects / Book a site visit / Raise a support ticket) → `localize_response()` (LLM translation only if non-English) → `evaluate_rag_response()`.
9. **Persist**: `session.append(issue, answer, marker=_conversation_state_marker(...))` → `current_project` marker = project name.
10. **Stream events**: one `{"type":"delta","text":<full answer>}` then `{"type":"done","response":{...}}`. The UI's `onDelta` / `onDone` handlers render it. No LLM call is used for the answer itself.
   - 0 matches → `build_amenity_project_choices()` (projects with listed amenities as quick replies); >1 → `_build_ambiguous_project_response()`.

### b) "Show me 3 BHK" (ambiguous → clarification)

1–3. Same as (a). In `prepare_turn()` `_HARD_PROPERTY_SIGNAL_RE` (`\b[1-6]\s*bhk\b…`) forces `intent="property"`; the text is normalised to `3BHK`. `resolve_contextual_support_issue()` appends `"\nRequested project: X"` **only if** a live project name appears in history (`_conversation_project_name`); otherwise, it passes the text through to the legacy resolver.
4. `_grounded_property_shortcut()`: site-visit docs → None; `build_catalogue_home_type_answer` → None (`is_catalogue_home_type_query` needs "projects"/"which project"); **`build_project_home_type_answer`** (project_home_type_service.py) → `resolve_project_candidates_from_text()` finds 0 → `apply_clarification_contract({"clarification_entity": "project"}, issue, history)`.
5. `apply_clarification_contract()` → `clarification_entity()` = `project` → `live_options()` → `get_company_projects()` (**GET /api/cs/{companyId}/projects**) → `customer_facing_projects()` → `_scope()` (issue, then customer history) → no match → all live names → `build_project_choice_answer(options, "", issue)` → "Which project should I check?\n- …".
6. Payload: `pending_project_lookup = {kind:"selection", original_issue, entity:"project", options:[…], scope:{}}`, `clarification_entity="project"`, `quick_replies=[names]`, `source_status="live_api"`.
7. `_complete_payload()`: the contract returns early (pending is a dict) → `_enforce_live_property_data()` (live_api) → no next-step replies (pending set) → `localize_response()` (bullet names must survive verbatim, §12).
8. Persist: `_project_lookup_marker()` → `build_pending_project_lookup_marker(state)`; `_current_project_marker()` → `build_current_project_marker("")` (clears scope). Stream: one `delta` + `done`.
9. **Next turn** ("<Project A>" tap): `_prepare_lookup_turn()` → `continues_selection()` (exact option) → `_resume_project_lookup_request()` → `resume_selection()` → effective issue `"Show me 3BHK. Selected project: <Project A>"` → `build_project_home_type_answer()` → `get_project_typologies()` (GET `/projects/{id}/typologies`), `get_project_wings()` (GET `/projects/{id}/wings`), `get_wing_inventory()` per wing (GET `/wings/{id}/inventory?availableOnly=true`) → "Home types in …" with counts, areas, base-rate range.
   - The spec (Inquiry to Sales §28) expects "Which location?" → "Budget?"; the code asks for **project** only (see GAP_ANALYSIS).

---

## 4. Orchestrator decisions

**Router level** (routers/assist.py, both endpoints, in this order):
1. `if _is_broad_project_request(processing_issue, turn.property_issue)` → `build_project_browse_response()`.
2. `elif turn.analysis.unsure and turn.analysis.intent not in {"call_booking", "human_contact"}` → `build_confusion_response()`.
3. `_grounded_property_shortcut(...)`, which starts `if not turn.analysis.is_property: return None` (the "shortcut" layer).
4. Otherwise `run_support_orchestration()` / `stream_support_orchestration_events()`.

**Intent promotion** (`prepare_turn`, main_orchestrator.py:122):
`if analysis.intent not in {"property", "call_booking", "human_contact"} and _has_hard_property_signal(english_issue, resolved_issue): analysis = replace(analysis, intent="property")`.
`_has_hard_property_signal` is True if the resolver rewrote the issue, `_HARD_PROPERTY_SIGNAL_RE` matches (`\b[1-6]\s*bhk\b|\b\d{3,5}\s*sq|\brera\b|\bsite\s+visits?\b|\bacrobuild\b`), or a live project name appears.
`call_booking` / `human_contact` come from regexes in `_parse_analysis()` / `analyze_turn()`, not from the LLM.

**Orchestrator** (`run_support_orchestration`, main_orchestrator.py:878; the stream version is identical):
```python
if analysis.intent == "call_booking":            # _build_call_booking_response
elif analysis.intent == "human_contact":         # _build_human_contact_response
elif prefer_qwen_response and not analysis.is_property:   # general LLM
elif prefer_qwen_response:                       # property path: build_ai_support_answer (blob) → _finalize_property_response
else:                                            # Haystack: run_conversation_pipeline
```
The Haystack branch is only reachable when `prefer_qwen_response=False`; the frontend always sends `true` (`api.ts` default). Inside Haystack, `classify_conversation_route()` picks `"support"` if `is_property_support_message` / `matches_live_company_context` / `is_contextual_property_reply`, otherwise `"conversation"`.

**Streaming behaviour**: only the general-LLM branch streams token deltas. Property events are buffered and re-emitted as one delta (assist.py:604–614), because validation, the live-data guard and localization can replace the draft.

---

## 5. Property clarification

- **Entities**: `project`, `wing`, `floor`, `flat`, `home_type`, `locality` (`clarification_entity()`, property_clarification_service.py:156). An English-prose detector catches builders that don't set it; `locality` is explicit only. Its options come from `locality_options()` (live project locality, else city, cleaned; same values and order as the discovery question), labelled "area" in the copy. Locality states carry `purpose: "discovery"`.
- **Contract**: `apply_clarification_contract(payload, issue, history)` → `live_options()` re-reads live CS API options, then writes `answer`, `quick_replies`, `pending_project_lookup`, `clarification_entity`, `source_status="live_api"`. A CS failure produces an honest retry message plus a pending state with `options: []`.
- **`pending_project_lookup` fields**: `kind` (`"selection"`, or legacy `"amenities" | "pricing" | "location"` + `selector` + `retry_count`), `original_issue`, `entity`, `options`, `scope` (`project`/`wing`/`floor`/`flat`/`home_type`), optional `purpose` (`explore_project`, `amenity_search`, `home_type_search`, `project_details`), and `effective_issue` (set on resume).
- **Stored**: `build_pending_project_lookup_marker()` base64-JSON wrapped in U+2063 markers, appended only to the **stored** bot text in the `conversation_turns` table (`ConversationSession.append`). A separate `current_project` marker is stored too (`build_current_project_marker`).
- **Restored**: `_pending_project_lookup()` → `get_pending_project_lookup(last bot message)` in `_prepare_lookup_turn()` (both endpoints). Narrowing replies are handled by `_narrows_selection_by_amenity`, `_narrows_selection_by_locality`, `project_detail_followup`, and `is_unmatched_selection_reply`.
- **Cleared**: a new turn stores no marker when `_project_lookup_marker()` returns `""`. `pending` is dropped when the intent is call_booking/human_contact or when the reply neither continues nor narrows the selection (`continues_selection()`: `cancel`/`stop`/`never mind`, `_NEW_REQUEST_RE`, or free text matching no option). On failure (`source_status` in failed/unavailable/error) the state is re-stored with no retry cap. A catalogue search writes an empty `current_project` marker.
- **Contract guards**: `apply_clarification_contract()` returns a payload unchanged when it already carries a pending-selection dict or a `discovery_prompt` (the discovery budget question), so discovery drafts cause no second live read.
- **Discovery pending selections** (flag `ACROBUILD_DISCOVERY_SLOTS`): the area question uses `entity: "locality"`, `purpose: "discovery"`; the shortlist uses `entity: "project"`, `purpose: "home_type_search"`. `routers/assist.py::_discovery_answer()` adds `source: "discovery"` to both. The "Any area" quick reply is never in `options`.
- **`discovery_slots` marker**: `build_discovery_slots_marker()` / `get_discovery_slots()` / `latest_discovery_slots()` in `services/conversation_store_service.py`. Base64 JSON with the same U+2063 framing, appended after the pending and `current_project` markers. Fields: `config`, `locality` (live value or `"any"`), `budget_max_inr` (present with `null` = any budget; absent = not asked), `budget_label`, `awaiting` (`locality`/`budget`/null), `origin_issue`. Validated on write and read; the last marker in a bot text wins; customer text is never read. Written by `_discovery_slots_marker()` (routers/assist.py:205) via `_turn_marker()` for both endpoints; `{}` clears it.

---

## 6. CS API layer (`services/acrobuild_company_service.py`)

| Method + path (company-scoped by `_company_scoped_path` → `/api/cs/{companyId}/…`) | Params | Wrapper |
|---|---|---|
| GET `/api/cs/company` | — | `search_company_knowledge()`, `export_all_company_data_to_text()` (direct `_cached_request`) |
| GET `/api/cs/projects` | — | `get_company_projects()`; also `search_company_knowledge()` |
| GET `/api/cs/projects/{id}/amenities` | — | `get_project_amenities()` |
| GET `/api/cs/projects/{id}/wings` | — | `get_project_wings()`; `search_company_knowledge()` |
| GET `/api/cs/projects/{id}/typologies` | — | `get_project_typologies()`; `search_company_knowledge()` |
| GET `/api/cs/wings/{id}/typologies` | — | `get_wing_typologies()` |
| GET `/api/cs/wings/{id}/inventory` | `availableOnly=true/false` | `get_wing_inventory()` (ttl 30 s); `search_company_knowledge()` when inventory terms are present |

- **Not called**: `GET /api/cs/projects/{projectId}` (documented in both CS API docs).
- **Auth/transport**: `urllib` GET, header `apiKey`, proxies disabled, timeout `ACROBUILD_CS_API_TIMEOUT_SECONDS` (default 2.5 s). Non-company responses must be a list of dicts, otherwise `RuntimeError`.
- **Config**: `_cs_api_config()` reads the admin override in the `cs_api_settings` table (`get_cs_api_settings`), falling back to env defaults.
- **Caching**: a per-turn memo (`turn_cache_get/set`, keyed by config hash + path + params) always applies. With `ACROBUILD_CS_API_LIVE_ONLY` **true (default)** every turn calls live with no TTL cache and no snapshot fallback. When false: in-process `_CACHE` with TTL `ACROBUILD_CS_API_CACHE_TTL_SECONDS` (300 s), and on failure `_load_snapshot_fallback()` (`data/acrobuild_all_company_data.json`, same base URL + company only) or the stale cache.
- **Retries**: none in the client. Retries are user-driven (pending marker + "retry").
- **Errors**: HTTPError (uses `errorMessage`), URLError, timeout and bad JSON are all logged as `failed` and raised as `RuntimeError`. Callers: `_grounded_property_shortcut` falls through; the clarification contract says "could not fetch… kept your request"; `_enforce_live_property_data` replaces the answer with "Live property data is unavailable right now…" (`source_status="failed"`) or "couldn't verify…" (`unverified`).
- **Cross-check with docs**: `docs/cs-api.md` documents un-scoped paths (`/api/cs/projects`) and is **stale**. `docs/cs-api updated.md` documents `/api/cs/{companyId}/…`, which matches the code. `docs/cs-api.md:466` contains an API key value → **[REDACTED]** (see §16).

---

## 7. LLM layer

- **Chain**: caller → `qwen.generate_qwen_chat_response()` → `provider_resilience_service.guarded_generation()` (circuit opens after 3 failures for 30 s) → `_generate_sarvam_chat_response()` → `build_qwen_messages()` → `sarvam_client.generate_sarvam_chat_response()` → `SarvamClient.chat()` → `POST {RUNPOD_BASE_URL}/v1/chat/completions`. Streaming: `qwen.stream_qwen_chat_response()` → `SarvamClient.stream()`; this path has **no circuit breaker**.
- **Limits**: `max_tokens = SARVAM_MAX_TOKENS (300) + SARVAM_REASONING_TOKENS (1536)`; per-call deadline `SARVAM_DEADLINE_SECONDS` (45 s); client timeout `SARVAM_TIMEOUT_SECONDS` (120 s); `<think>` is stripped by `strip_reasoning()`. No retries.
- **Prompts in use**:
  - `_ANALYZER_SYSTEM_PROMPT` + `FREECHAT_TYPO_POLICY` — `analyze_turn()`, temperature 0, **every turn**.
  - `_general_chat_system_prompt()` + `CONCISE_REPLY_RULES` + `LANGUAGE_CAPABILITY` + `FREECHAT_TYPO_POLICY` — general chat, temperature 0.
  - Translator prompt in `_localize_answer()` — temperature 0, then 0.3.
  - **(blob)** `build_system_prompt` / `build_user_prompt` → `generate_support_chat_response` inside `build_ai_support_answer` / `stream_ai_support_answer_events` — temperature patched 0.35→0.1.
  - Haystack `build_local_conversation_answer` — temperature 0.2 (Haystack branch only).
  - `intent_service.classify_structured_intent` — only if `SUPPORT_LLM_CLASSIFICATION=true`.
- **Live-data enforcement**: `_enforce_live_property_data()` (api_context.py:191, called from `_complete_payload`) checks that price/area/flat claims (`_PROPERTY_CLAIM_RE`) are backed by `company_api` chunks and flags hedge contradictions (`_HEDGE_RE`). Also `validate_support_node()` (relevance guard) in `_finalize_property_response()`, the clarification contract, and the general prompt's "do not invent Acrobuild facts" plus its no-fake-ticket rule.

---

## 8. RAG

- **Ingest**: `upload_admin_knowledge_documents_api` → `ingest_uploaded_knowledge_files()` (`.csv .docx .htm .html .json .md .markdown .pdf .txt`; text split into documents ≤ 4000 chars). `import_admin_knowledge_url_api` → `ingest_url_knowledge_source()` (public URL validation, crawl ≤ 200 pages, ≤ 10 MB, ≤ 5 redirects). Manual create/update. Rows go in `knowledge_documents`; articles in `support_articles`.
- **Index**: `build_workspace_records()` = Published knowledge docs + Published articles + non-archived macros → `build_chunk_entries()` (`MAX_CHARS_PER_CHUNK = 900`) → `data/ai_index/workspace_knowledge_index.json` (schema v2, fingerprinted). Edits call `refresh_support_assist_state()` → `mark_workspace_index_dirty()`; rebuilt lazily by `ensure_workspace_index()`, or at startup if `ACROBUILD_REFRESH_INDEX_ON_STARTUP`.
- **Retrieve**: `search_workspace_knowledge(query, limit, article_hint_url)`. **Lexical only**: `is_semantic_search_enabled()` returns False. Token synonyms/aliases, `MAX_SEARCH_RESULTS = 8`. Called from **(blob)** `build_ai_support_answer`, together with `search_company_knowledge()` (CS API data turned into chunks).
- **Chunk metadata**: `chunk_id, record_id, record_kind, source_key, source_name, source_type, status, title, summary, category, url, tag_terms, title_terms, content_terms, excerpt, body_text, search_text, dedupe_key, record_body, record_summary`. No project/tower/unit tags on knowledge chunks.
- **Eval**: `evaluate_rag_response()` adds online proxy metrics to every response (`rag_evaluation`).

---

## 9. Tickets and workflow

- **`graph/workflow.py::run_workflow(issue, customer_email, attachments)`**: `get_customer_context()` (HTTP to `NUFOODZ_API_BASE_URL/api/customer`, a legacy food API; defaults if unset) → `classify_structured_intent()` (LLM only if `SUPPORT_LLM_CLASSIFICATION=true`) or `classify_issue()` → `set_priority()` → `build_ticket_metadata()` → `get_default_agent()` → `database_service.create_ticket()` → returns `ticket_id` + metadata.
- **Callers**: `POST /create_ticket`, `POST /api/site-visits`, `_build_call_booking_response`, `_build_human_contact_response`. The chat "Raise a support ticket" quick reply calls `createSupportTicket()` → `/create_ticket` from the UI (`CustomerHomePage.tsx:1471`). Tickets are **local SQLite only** and are not pushed to AcroBuild.
- **Statuses** (`TicketStatus`): Open, Pending, Waiting on Customer, Resolved, Closed.
- **Schema** (SQLite `support_system.db`):
  - `tickets`: ticket_id PK, issue, customer_email, issue_type, priority, status, assigned_agent, unread_count, brand_tag, intent_tag, business_hours_tag, queue_name, assignment_method, created_at, updated_at
  - `ticket_counters`: name PK, next_value
  - `messages`: id, ticket_id, sender, message, created_at, attachments_json
  - `ticket_notes`: id, ticket_id, author, note, created_at
  - `support_users`: id, name, email UNIQUE, role, team, status, password (DEFAULT literal **[REDACTED]**), created_at, updated_at
  - `support_articles`: id, title, category, status, summary, body, keywords_json, url, created_at, updated_at
  - `knowledge_documents`: id, title, category, status, summary, body, tags_json, source_name, source_type, created_at, updated_at
  - `tags`, `ticket_tag_links`, `business_hours_profiles`, `business_hour_ranges`, `workflow_rules`, `business_hours_rule_windows` (admin_settings_service.py)
  - `cs_api_settings`: id=1, base_url, api_key, company_id
  - `email_otp_records`, `email_access_tokens`, `otp_request_audit` (otp_service.py)
  - Migrations: `security_sessions`, `refresh_sessions`, `request_limits`, `audit_events`, `action_proposals`, `ticket_feedback`, `conversation_turns`, `schema_migrations`

---

## 10. Conversation memory

| Remembered across turns? | Status | Where |
|---|---|---|
| Chat transcript (60 msgs, 2 h TTL, per cookie + conversation_id) | Yes | `conversation_turns`, `ConversationSession` |
| Current project | Yes | `current_project` marker; `_conversation_project_name()`; `_scope()` history scan |
| Pending selection (entity, options, scope, original question) | Yes | `pending_project_lookup` marker |
| Wing / floor / flat / home type | Only inside a pending selection's `scope` | property_clarification_service |
| Configuration (BHK) | Yes (flag) — `discovery_slots.config`; with the flag off, re-parsed from the current text (+ `resume_selection` from `original_issue`) | `discovery_slots` marker (conversation_store_service.py) |
| Location / locality | Yes (flag) — `discovery_slots.locality`, a live value or `"any"`, re-checked against live data on use; with the flag off, used only to narrow a pending project choice | `discovery_slots` marker; `narrow_project_choice_by_locality` |
| Budget | Yes (flag) — `discovery_slots.budget_max_inr` + `budget_label`; with the flag off, `_build_recommendation_budget_follow_up()` re-reads history text | `discovery_slots` marker; ai_agent_service.py:630 |
| Phone / time / name (callback, human contact) | Re-extracted from the last 6 messages; `pending_call_booking` / `pending_human_contact` markers | main_orchestrator.py |
| Customer identity | No | — |
| LLM history window | Last `LLM_HISTORY_TURNS` (10) turns | `_recent_history()` |

`_remember_response()` is a no-op and `_CONVERSATION_MEMORY` is unused.

"Yes (flag)" means only when `ACROBUILD_DISCOVERY_SLOTS` is true (default false). The project is deliberately not a discovery slot; `current_project` stays its single source of truth, and discovery answers never set it.

---

## 11. Frontend

- **Chat UI**: `src/pages/CustomerHomePage.tsx` (the only customer chat; routes `/home…`). It streams via `streamSupportAssist`, falls back to `getSupportAssist`, and handles quick replies: `action` `ticket` → ticket flow, `site_visit` → site-visit form → `createSiteVisit()` (`:2072`), `browse_projects` → new conversation (`:3421–3425`). `ChatWidgetPage.tsx` is only an admin widget-snippet configurator. `AIAgentPage.tsx` and `ArticlesPage.tsx` call the JSON `getSupportAssist` for staff previews.
- **Stream parsing** (`api.ts:495`): reads `response.body` with `TextDecoder`, splits on `\n`, and `JSON.parse`s each NDJSON line. `delta` → `onDelta(text)`; `done` or `error` with `response` → `onDone(response)` and return; other types (e.g. `progress`) are ignored. A leftover buffer is parsed at the end; it throws if no final response arrives.
- **Types** (`src/types.ts:373–449`): `SupportConversationMessage`, `SupportAssistChunkMatch`, `DataApiCallTrace`, `RagEvaluation(Metric)`, `SupportAssistResponse`. Drift from the backend: `agent_mode` typed `fallback|qwen|retrieval`, but the backend sends `knowledge_retrieval`, `live_remote_llm`, `live_data_error`, …; `source_status` is typed `live|fallback|workspace`, but the backend also sends `live_api|snapshot|failed|unverified`; `retrieval_mode` is missing `live_project_records|none|knowledge_base`; the `quick_replies.action` union lacks `browse_projects` (declared locally in CustomerHomePage.tsx:95); `pending_project_lookup` / `clarification_entity` / `route` are not typed.

---

## 12. Localization

- **Detect**: `analyze_turn()` returns `reply_language`, `script`, `english`, adjusted by `reply_language.py` heuristics (`strong_reply_language`, `guess_romanized_language`, `detect_script_language`) and `language_hint` (voice).
- **Generate in English**: property paths run on `turn.property_issue` (English rendering), and the blob gets `reply_language=ENGLISH`.
- **Translate last**: `localize_response()` in `_complete_payload()` (and `_localize_answer()` inside `_finalize_property_response()`, so the orchestrator path is localized twice; the second pass usually no-ops via `_needs_localization`). General chat is generated directly in the target language via `build_reply_language_directive`.
- **Protecting option names**: the translator prompt says to keep names, numbers, RERA and terms verbatim. `_localize_answer()` **rejects** a translation unless every `- ` bullet item appears unchanged, every number survives, and a one-line answer stays one line; otherwise it keeps the English. `quick_replies` labels/values are never translated, and clarification answers are built before localization.
- **Unused**: `tenglish_rewriter_service.py` (no importers); `indic_translation_service` is only warmed; the blob's `localize_ai_answer` is imported in api_context but not called by the chat path.

---

## 13. Auth

- **Staff**: `POST /auth/login` → `issue_session()` → cookies `workspace_session` (JWT, 900 s), `workspace_refresh` (7 d, rotated in `refresh_sessions`), `workspace_csrf`. `require_workspace_user()` accepts the cookie or Bearer and checks `active_session()` + role ∈ {owner, admin, agent}. `enforce_admin_route_auth` enforces CSRF, role tiers (destructive = admin; management = admin/owner), and agent ticket ownership. The JWT secret is `AUTH_SECRET_KEY`.
- **Customer**: email OTP only. `POST /auth/otp/request` sends a 6-digit code via SMTP (rate-limited per IP/account) → `POST /auth/otp/verify` → opaque `access_token` (hashed with `OTP_SECRET`). The token is accepted by `/customer/verified`, `/customer`, `/ticket/message`, `/api/support/feedback` (used by `CustomerLookupPage`).
- **Chat identity**: **none**. `/api/support/assist*` are anonymous (cookie `support_conversation_session` scopes history only). `customer_email`/`customer_name` in `SupportAssistRequest` are unverified free text; they flow into `get_customer_context()` and ticket rows. `/create_ticket` and `/api/site-visits` are unauthenticated (rate-limited 10/min/IP). No mobile OTP and no link to an AcroBuild customer/booking record. `_authorize_customer_identity` is imported in routers/customer.py but never called.

---

## 14. Tests

| File | Covers |
|---|---|
| conftest.py | Shared isolation fixtures |
| test_ambiguous_project_clarification | Multi-match project prompts |
| test_amenities_conversation_regression, test_project_amenities, test_general_amenity_catalogue, test_reverse_amenity_search | Amenity builders, reverse search |
| test_backend_startup | App boots |
| test_budget_project_recommendation, test_global_recommendation, test_project_recommendation_clarification | Budget/recommendation pre-handlers |
| test_call_booking_intent, test_human_contact_intent, test_malformed_phone_explanation | Callback/human-contact flows and ticket creation |
| test_chat_quick_replies, test_terminal_answer_next_steps | Quick replies, next-step gate |
| test_company_context_matching, test_company_value_proposition, test_portfolio_overview | Company/catalogue answers |
| test_contextual_flat_cost | Flat cost estimate from history |
| test_conversational_scope, test_free_chat_language, test_general_local_llm, test_llm_provider_switch | General chat routing, language, provider |
| test_cs_api_company_scope, test_cs_api_settings | Company-scoped paths; admin CS settings |
| test_disambiguation_copy_contract, test_property_clarification_contract, test_pending_project_lookup | Clarification contract and markers |
| test_fake_project_record_filter, test_project_entity_resolution_500, test_project_field_filter | Project matching/filtering |
| test_grounded_shortcut_cs_api_failure, test_snapshot_property_fallback | CS failures, snapshot |
| test_haystack_conversation_pipeline, test_thin_retrieval_guard | Reconstructed pipeline, fallback guard |
| test_location_known_locality_resolution | Location shortcut |
| test_pricing_validation_guard | Live-data claim guard |
| test_project_home_type_followups, test_property_question_variants, test_shop_availability | BHK/home-type, phrasing variants, shops |
| test_rag_evaluation_service | RAG proxy metrics |
| test_security_boundaries, test_upgrade_security, test_pending_upgrades | Auth/CSRF/security |
| test_seed_demo_tickets | Demo seed script |
| src/contexts/RoleContext.test.tsx, src/lib/chatLanguage.test.ts | Frontend role context, language helper |

**Gaps**: no tests for knowledge ingestion/indexing, `sarvam_client` streaming/`<think>` stripping, the circuit breaker, the NDJSON client parser (`streamSupportAssist`), OTP flows (unverified — may be inside test_security_boundaries), `/api/site-visits` payload validation (unverified), localization rejection rules, or post-sales features (none exist). Live behaviour is only covered by `scripts/live_*_check.py`.

---

## 15. Env var names (names only)

| Service / file | Env vars |
|---|---|
| CS API (`acrobuild_company_service.py`) | ACROBUILD_CS_API_BASE_URL, ACROBUILD_CS_API_KEY, ACROBUILD_CS_API_COMPANY_ID, ACROBUILD_CS_API_TIMEOUT_SECONDS, ACROBUILD_CS_API_CACHE_TTL_SECONDS, ACROBUILD_CS_API_LIVE_ONLY, ACROBUILD_COMPANY_DATA_PATH |
| LLM (`sarvam_client.py`, `llm_service.py`, orchestrator) | RUNPOD_BASE_URL, RUNPOD_API_KEY, MODEL_NAME, SARVAM_TIMEOUT_SECONDS, SARVAM_DEADLINE_SECONDS, SARVAM_MAX_TOKENS, SARVAM_REASONING_TOKENS, LLM_HISTORY_TURNS |
| App / security | ACROBUILD_ENV, ACROBUILD_CORS_ORIGINS, AUTH_SECRET_KEY, OTP_SECRET, UPLOAD_STORAGE_QUOTA_BYTES, CLAMSCAN_PATH |
| Email (OTP) | SMTP_SENDER_EMAIL, SMTP_APP_PASSWORD, SMTP_HOST, SMTP_PORT |
| Startup | ACROBUILD_REFRESH_INDEX_ON_STARTUP, ACROBUILD_WARM_LOCAL_AI_MODELS |
| Articles (`support_article_service.py`) | ACROBUILD_SUPPORT_BASE_URL, ACROBUILD_SUPPORT_CACHE_TTL_MINUTES, ACROBUILD_SUPPORT_MAX_ARTICLES, ACROBUILD_SUPPORT_TIMEOUT_SECONDS |
| Tickets | SUPPORT_LLM_CLASSIFICATION, SUPPORT_DEFAULT_BRAND, SUPPORT_TIMEZONE, SUPPORT_BUSINESS_HOURS_START, SUPPORT_BUSINESS_HOURS_END, NUFOODZ_API_BASE_URL, NUFOODZ_API_TIMEOUT_SECONDS (legacy) |
| Retrieval | ASSIST_FALLBACK_MIN_SCORE, HAYSTACK_TELEMETRY_ENABLED |
| Translation / TTS / Tenglish | INDIC_TRANSLATION_MODEL, INDIC_TTS_MODEL, INDIC_TTS_DEVICE, HUGGINGFACE_TOKEN, HF_TOKEN, HF_MODULES_CACHE, GEMMA_TENGLISH_MODEL, GEMMA_TENGLISH_TIMEOUT, OLLAMA_BASE_URL |
| Logging (`observability.py`) | LOG_LEVEL, CHATBOT_LOG_LEVEL, LIB_LOG_LEVEL, LOG_JSON, LOG_FILE, LOG_COLOR |
| Eval scripts | EVAL_API_URL, EVAL_CACHE_PATH, EVAL_MAX_WORKERS, EVAL_OUTPUT_PATH, EVAL_PROMPTS_PATH, EVAL_TIMEOUT_SECONDS, CI |

---

## 16. Known risks

- **Secret in repo**: `docs/cs-api.md:466` ("# Api key" section) holds a CS API key value **[REDACTED]**, committed in `1166969`. Rotate it and purge it from history.
- **Default credential literal**: `services/database_service.py:1277` `support_users.password DEFAULT '[REDACTED]'`.
- **Core logic in bytecode**: `services/ai_agent_service_runtime(.patched).pyc` (~150 functions incl. `build_ai_support_answer`, prompts, RAG assembly) has no source; it was originally a food-catalogue bot (`docs/DECOMPILED_MAP.md`). It can't be code-reviewed and is locked to CPython 3.12.
- **Stale docs**: `docs/cs-api.md` (paths without `{companyId}`); `docs/CHAT_FLOW.md` mermaid omits the browse/confusion steps before the shortcuts; the snapshot/TTL cache described in AI_CONTEXT/CHAT_FLOW only runs when `ACROBUILD_CS_API_LIVE_ONLY=false`; `docs/ONBOARDING.md` is flagged stale by AI_CONTEXT.
- **Dead / legacy code**: `_remember_response`, `_CONVERSATION_MEMORY`, `_MEMORY_LOCK`, `_MEMORY_TTL_SECONDS` (main_orchestrator.py); `workspace_login` and imports never referenced in app code: `answer_matches_response_language`, `localize_ai_answer`, `build_ai_support_answer`, `stream_ai_support_answer_events` (api_context.py; tests may import them from there, unverified); `_authorize_customer_identity` import (customer.py); `get_llm_client` (llm_service.py); `refresh_company_data_snapshot_async`; `tenglish_rewriter_service.py`; food/e-commerce leftovers (`/orders`, `/order/refund`, `/subscription/cancel`, `/local-data/products/*`, `NUFOODZ_*`, `DEFAULT_CUSTOMER_CONTEXT.ndis_enabled`); both `vite.config.js` and `vite.config.ts` tracked; `data/merge-main/` duplicates source (ignored, but pollutes grep).
- **Performance**: `build_grounded_amenity_search_assist` builds `live_amenity_index()` (1 + N project calls) for any message containing does/has/have… before checking for an amenity name. `build_project_home_type_answer` fetches inventory for every wing. With LIVE_ONLY on, there is no cross-turn cache. `analyze_turn` is an extra LLM round-trip on every turn.
- **Resilience**: no CS API retries; the Sarvam stream path skips the circuit breaker.
- **Security/identity**: anonymous chat with an unverified `customer_email` that reaches tickets and the customer-context lookup; unauthenticated ticket/site-visit creation.
- **Types**: frontend `SupportAssistResponse` has drifted from backend payloads (§11).
- **Untracked/uncommitted**: `scripts/check_live_property_data.py`; working-tree edits in README.md, api_context.py, acrobuild_company_service.py, tests/test_cs_api_company_scope.py; root-level `live_*_run.log` files (not read).
- **TODO/FIXME/XXX/HACK**: none found in `*.py`, `*.ts`, `*.tsx` (excluding `.venv`, `node_modules`, `data`, `dist`).
