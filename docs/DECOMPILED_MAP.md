# Compiled runtime map (Phase 1)

Read-only documentation of the two bytecode-only modules the app loads at import
time. No source was modified to produce this. Everything here is derived from the
marshalled code objects (function signatures, docstrings, string/number
constants, and bytecode disassembly).

**Status of both files: bytecode-only. No `.py` source exists.** See
`docs/RECONSTRUCTION_STATUS.md` for the running ledger of what has been converted.

---

## Provenance note (important)

The larger file (`ai_agent_service_runtime.pyc`) was **originally written for a
food / beverage catalogue support bot** and later repurposed for Acrobuild real
estate. Evidence, still present in its constants:

- `SNACK_PRODUCT_TERMS = {chip, popper, bites, ball, falafel, arancini, ...}`
- `DRINK_PRODUCT_TERMS = {juice, h2coco, kombucha, sparkling, h2juice}`
- `MEAL_QUERY_TERMS`, `BUNDLE_QUERY_TERMS`, `CATALOG_PRODUCT_PATTERN` matching
  `"<N> Cal ... Regular price $<price>"` (a Shopify-style product export)
- ~60 `*_local_product_feed_*` and `*_catalog_*` functions

This is why property-search prompts sometimes fall through to catalogue / verbatim
document handling and dump the raw company record — the retrieval-miss path was
built for a product menu, not a project portfolio.

---

## How they load

`services/ai_agent_service.py` and `graph/haystack_conversation_pipeline.py` are
thin loaders:

```python
with open("<name>_runtime.pyc", "rb") as f:
    validate_runtime_header(f.read(16))   # guard added 2026-09-10
    code = marshal.load(f)
exec(code, globals(), globals())          # every top-level name lands in module globals
```

Both `.pyc` files are **headerless marshal dumps** of a module code object,
compiled for **CPython 3.12** (magic `cb0d0d0a`). `services/ai_agent_service.py`
then adds ~470 lines of its own deterministic pre-handlers around
`build_company_api_direct_answer` (see "Wrapper layer" below).

---

# File 1 — `graph/haystack_conversation_pipeline_runtime.pyc`

~640 source lines, 26 top-level functions + 1 class. This is the **conversation
router**: decide small-talk vs property vs general, resolve "this / that / it"
against history, validate answers. **This is the Phase 3 reconstruction target.**

### Module constants

| Name | Value |
|---|---|
| `PROPERTY_SUPPORT_TERMS` | frozenset of ~52 terms: `acrobuild, address, amenities, apartment(s), availability, available, bhk, book(ing), complaint, configuration, construction, cost, document(s), flat(s), floor, handover, home(s), inventory, location, maintenance, payment, plot(s), possession, price, pricing, project(s), properties, property, rate(s), refund, rera, "site visit", size, "sq ft", "sq.ft", support, ticket, tower, unit(s), villa(s), wing` |
| `SMALL_TALK_PATTERNS` | 15 regexes: `^(?:hi\|hello\|hey\|good morning\|good afternoon\|good evening)[!. ]*$`, `\bhow are you\b`, `\bwhat are you doing\b`, `\bwhat(?:'s\| is) up\b`, `\b(?:tell\|share\|give) me (?:a )?joke\b`, `\bmake me laugh\b`, `\bwho are you\b`, `\bwhat can you do\b`, `\b(?:tell\|write) me (?:a )?story\b`, `\bfun fact\b`, `\bwhat do you think\b`, `\bcan we chat\b`, `\bwhat(?:'s\| is) your favorite\b`, `\bweather\b`, `^(?:thanks\|thank you\|bye\|goodbye\|okay\|ok)[!. ]*$` |
| `LIVE_INFORMATION_PATTERNS` | 3 regexes: `\b(?:today\|right now\|currently\|current\|latest\|live\|this week\|this month)\b`, `\b(?:weather\|temperature\|forecast\|score\|scores\|news\|stock price\|exchange rate)\b`, `\bwho is (?:the )?(?:current )?(?:president\|prime minister\|chief minister\|ceo)\b` |
| `HIGH_STAKES_PATTERNS` | 3 regexes: `\b(?:diagnose\|diagnosis\|dosage\|dose\|medicine\|medical emergency\|suicid)\w*\b`, `\b(?:legal advice\|lawsuit\|sue\|criminal charge\|court deadline)\b`, `\b(?:invest\|investment\|buy stock\|sell stock\|tax advice\|financial advice)\b` |
| `JOKE_RESPONSE` | `"Why did the building bring a ladder to the meeting? Because it wanted to take the discussion to the next level."` |
| `CONVERSATION_PIPELINE` | module-level singleton, `build_conversation_pipeline()` result |
| env at import | `os.environ.setdefault("HAYSTACK_TELEMETRY_ENABLED", "False")` |

### Functions

| Function | Signature | Behaviour (from bytecode + literals) |
|---|---|---|
| `ConversationState` | `TypedDict(total=False)` | Keys: `issue`, `conversation_messages`, `route`, `response`, `support_handler`. |
| `normalize_text` | `(value)` | `" ".join(str(value).split()).strip()` — collapse whitespace. |
| `is_property_support_message` | `(issue) -> bool` | Lowercase+normalize; True if any `PROPERTY_SUPPORT_TERMS` token present, OR regex `\b(?:do you have\|show me\|find\|looking for\|need)\s+(?:anything\|something\|options?)\s+(?:in\|near\|around)\b`, OR `\b[1-6]\s*bhk\b\|\bfloor\s*\d+\b\|\b\d{3,5}\s*sq`. |
| `is_small_talk_message` | `(issue) -> bool` | Any `SMALL_TALK_PATTERNS` regex matches (IGNORECASE). |
| `matches_live_company_context` | `(issue) -> bool` | Extracts word tokens; calls `search_company_knowledge("all projects")`, reads the `acrobuild-cs-projects` chunk's `project_names`; True if a project name appears in the issue, or the issue names a place after `\b(?:in\|near\|around\|at)\b` and any project `body_text`/`excerpt` mentions it. Guarded by `try/except Exception`. `4` = min token length. |
| `_latest_bot_message` | `(conversation_messages)` | Last message whose `sender`≈`"bot"`; returns its `text`. |
| `_conversation_project_name` | `(conversation_messages)` | Scans messages newest-first; returns the first live project name (`get_live_project_names()`) found in any message text. |
| `_selected_wing_from_context` | `(issue, conversation_messages)` | Detects an explicitly chosen wing. Regexes: `\b(?:go with\|go for\|choose\|select\|take\|pick)\s+(?:the\s+)?(?:wing\s+)?([a-z0-9]+(?:\s+[a-z0-9]+)?)\b` in the issue; in the last bot message, bullet list `(?m)^\s*[-*]\s*([^:\n]+)(?::\|$)` and `(?:\bWing:\s*\|\bin\s+\|\bGot it\s*-\s*)([A-Za-z0-9-]+...)\s+wing\b`. |
| `resolve_contextual_support_issue` | `(issue, conversation_messages) -> str` | **The "this/that/it" resolver.** If the issue is a contextual property reply, rewrites it to a concrete query using the project name + wing from history. Templates: `"Show verified details for <...>"`, `"Show verified construction status for <...>"`. Reference regexes for `this/that/selected/same/recommended + project\|wing\|floor\|flat\|home\|unit\|option` and bare `it/this/that`; `\bexplore\s+(.+?)(?:\?\|$)`. Returns the original issue unchanged when there's nothing to resolve. |
| `is_contextual_property_reply` | `(issue, conversation_messages) -> bool` | True when the issue is short/pronoun-only (`\b(?:this\|that\|it)\b` …), or `\b(?:go with\|choose\|…)\s+…`, or `explore`, **and** the last bot message looks property-related (`is_property_support_message` / `matches_live_company_context`). |
| `classify_conversation_route` | `(state) -> "support"\|"conversation"` | `"support"` if `is_property_support_message` or `matches_live_company_context` or `is_contextual_property_reply`, else `"conversation"`. Writes `state["route"]`. |
| `select_route` | `(state)` | `state.get("route", "support")`. |
| `is_live_information_question` | `(issue) -> bool` | Any `LIVE_INFORMATION_PATTERNS` match. |
| `is_high_stakes_general_question` | `(issue) -> bool` | Any `HIGH_STAKES_PATTERNS` match. |
| `is_unclear_general_message` | `(issue) -> bool` | Fewer than 1 real word after stripping `" .!?"` and tokenising `[a-z0-9]+`. (i.e. empty/punctuation-only) |
| `validate_general_answer` | `(issue, answer) -> str` | If answer empty → `"I could not form a reliable answer. Could you rephrase the question with a little more detail?"`. If answer mentions `acrobuild` but the issue did not → `"I do not have reliable information connecting that subject to Acrobuild. …"`. Else returns the answer. |
| `build_deterministic_conversation_answer` | `(issue) -> str \| None` | Canned replies for small talk. `is_unclear_general_message` → `"Could you add a little more detail…"`. `is_live_information_question` or `is_high_stakes_general_question` → `"I do not have live internet access…"`. `prabhas` → (name handling). `how are you` → `"I'm doing well, thank you! …"`. `what are you doing` / `what's up` → `"I'm here and ready to chat…"`. joke regex → `JOKE_RESPONSE`. `who are you` → `"I'm the Acrobuild Assistant. …"`. `what can you do` → `"I can have a normal conversation and also check live Acrobuild project details…"`. greeting → `"Hi! It's nice to hear from you. How can I help?"` / `"<Title>! How can I help?"`. `thanks` → `"You're welcome!"`. `bye` → `"Goodbye! Have a great day."`. `okay` → `"Okay. What would you like to discuss next?"`. Returns `None` when nothing matches. |
| `build_local_conversation_answer` | `(issue, conversation_messages) -> str` | `build_deterministic_conversation_answer(issue)` first; else `generate_qwen_chat_response(..., temperature=0.2)` over the last `-10` messages, passed through `validate_general_answer`; on `Exception` returns `"I'm happy to chat. I may not have reliable real-time information for that topic…"`. |
| `conversation_node` | `(state) -> state` | Runs the two above; sets `state["response"]` with `agent_mode="conversation_haystack"`, `confidence_label="high"`, `source_label="Local conversational model"`, `source_status="conversation"`. |
| `support_node` | `(state) -> state` | Calls `state["support_handler"]()` (raises `RuntimeError("Haystack conversation support handler is unavailable.")` if missing/not callable); stores under `state["response"]`. |
| `get_live_project_names` | `() -> list[str]` | `search_company_knowledge("all projects")` → `acrobuild-cs-projects` chunk → `project_names`. `try/except Exception → []`. |
| `validate_support_answer` | `(issue, answer) -> list[str]` | Returns a list of **unmet-requirement descriptions**. Checks: empty answer; answer just echoes the question; BHK count in the issue (`\b([1-6])\s*bhk\b`) not reflected; floor number (`\b(?:floor\s*)?(\d{1,3})(?:st\|nd\|rd\|th)?\s*floor\b`) missing; sq-ft (`\b(\d{3,5})\s*(?:sq…ft)`) missing; requested project name absent; lowest/highest-price comparison, "one recommended option", pricing, wing-details, availability intent not addressed. Empty list = answer passes. |
| `validate_support_node` | `(state) -> state` | If `validate_support_answer` is non-empty, replaces the response with a clarification: `"I could not verify one live answer that matches all of your requested details: <joined>. I will not substitute unrelated project or property data. …"`, `confidence_label="low"`, `source_label="Conversation relevance guard"`, adds `relevance_clarification`. |
| `ConversationOrchestrator` | Haystack `@component`, `.run(issue, conversation_messages, support_handler)` | Orchestrates: `classify_conversation_route` → `select_route` → `conversation_node` or (`support_node` → `validate_support_node`). Output type `{response: dict}`. |
| `build_conversation_pipeline` | `()` | Haystack `Pipeline()` with one component `"orchestrator"`. |
| `run_conversation_pipeline` | `(issue, conversation_messages, support_handler) -> dict` | Runs `CONVERSATION_PIPELINE`, returns `result["orchestrator"]["response"]`. |

---

# File 2 — `services/ai_agent_service_runtime.pyc`

~10,400 source lines, ~150 top-level functions. This is the **answer engine**:
retrieval-miss handling, the live-CS-API answer builder, catalogue/product-feed
logic (dormant for real estate), prompt construction, localisation, the LLM call.

**Too large to hand-reconstruct.** Phase 4 will spike a chunk of the big function
with a decompiler and report before proceeding.

### Module constants

| Name | Value / meaning |
|---|---|
| `RISKY_SUPPORT_TERMS` | `{lawyer, cancel, replacement, complaint, damaged, escalate, late, chargeback, missing, urgent, refund}` — trigger handoff bias. |
| `CATALOG_PRODUCT_PATTERN` | regex: `\b\d+\s+Cal\b.*?\bF\s+(?P<name>…)…\s+Regular price` (food-menu export) |
| `PRICE_LINE_PATTERN` | `\bRegular price\s+\$(?P<price>\d+(?:\.\d{1,2})?)\b` |
| `LOCAL_PRODUCT_FEED_PATH_PATTERN` | `/local-data/products/(?P<feed_key>[a-z0-9_-]+)(?:\.csv)?/?$` |
| `DRINK_QUERY_TERMS` | `{juice, juices, beverage(s), kombucha(s), drink(s)}` |
| `SNACK_PRODUCT_TERMS` | `{chip(s), popper(s), bites, bite, ball(s), falafel, arancini}` |
| `DRINK_PRODUCT_TERMS` | `{juice, h2coco, kombucha, sparkling, h2juice}` |
| `MEAL_QUERY_TERMS` | `{menu(s), product(s), item(s), dish(es), meal(s)}` |
| `BUNDLE_QUERY_TERMS` | `{plan(s), pack(s), bundle(s)}` |
| `SIDE_QUERY_TERMS` / `EXTRA_QUERY_TERMS` | `{side(s)}` / `{extra(s), snack(s)}` |
| `CONTEXT_REFERENCE_TOKENS` | `{it, its, one, ones, that, these, they, same, their, those, this, them}` |
| `LOW_SIGNAL_QUERY_TOKENS` | ~50 stopwords (`a, an, and, are, be, … your`) |
| `FOLLOW_UP_QUERY_PREFIXES` | `("and ", "also ", "how about", "what about", "what if")` |
| `VERBATIM_SOURCE_TYPES` | `{url, upload, macro, article}` |
| `AGENT_OPERATING_MANUAL` | large canned text, built by `build_agent_operating_manual` |
| `ASSIST_RESPONSE_CACHE` / `_LOCK` / `_TTL_SECONDS` | in-process response cache (module-level dict + `Lock`) |

### Function inventory (grouped)

**Text / normalisation:** `normalize_ai_text`, `normalize_ai_multiline_text`,
`normalize_floor_number`, `format_floor_location`, `strip_import_note_prefix`,
`normalize_verbatim_source_text`, `join_ai_answer_terms`, `dedupe_preserving_order`,
`truncate_assist_context_text`, `strip_voice_instruction_metadata`,
`normalize_llm_response_content`.

**Intent detectors (`is_*`):** `is_company_name_question`,
`is_document_requirement_question`, `is_construction_update_question`,
`is_project_location_question`, `is_site_visit_booking_request`,
`is_site_visit_fee_question`, `is_support_contact_question`,
`is_workspace_capability_question`, `is_site_operations_overview_question`,
`is_price_question`, `is_count_question`, `is_total_products_question`,
`is_context_dependent_issue`, `is_lowest_property_value_request`,
`is_highest_property_value_request`, `has_global_project_scope`,
`is_cross_project_floor_comparison_request`,
`is_cross_project_flat_count_comparison_request`, `is_model_answer_echo`.

**Deterministic answer builders (`build_*_answer` / `build_*_line`):**
`build_document_requirement_answer`, `build_construction_update_answer`,
`build_unknown_clarification_answer`, `build_project_location_answer`,
`build_site_visit_booking_answer`, `build_company_identity_answer`,
`build_company_name_guidance_line`, `build_support_contact_guidance_line`,
`build_site_operations_overview_answer`, `build_site_visit_fee_answer`,
`build_workspace_capability_guidance_line`, `build_product_fact_guidance_line`,
`build_direct_workspace_answer`, `build_catalog_guidance_line`,
`build_guidance_line_from_chunk`, `build_chunk_guidance_text`,
`build_company_value_proposition_answer`, `build_conversational_small_talk_answer`,
`build_offline_conversation_answer`, `build_fallback_assist_answer`.

**Company name extraction:** `extract_explicit_company_name_from_text`,
`extract_company_name_from_source_name`, `select_company_name_source_match`,
`infer_company_name_from_chunks`, `should_return_company_name_source_answer`.

**Verbatim / direct-source answering:** `build_verbatim_source_text`,
`get_verbatim_source_priority`, `get_chunk_title_overlap_counts`,
`select_preferred_verbatim_chunk`, `should_return_verbatim_source_answer`,
`select_direct_workspace_answer_chunk`, `build_direct_workspace_source_label`,
`get_selected_source_domain`. — **This is the path that dumps a raw document
("Here is the relevant information: …") on a retrieval miss.**

**Local product feed (dormant for real estate — ~35 functions):**
`extract_local_product_feed_key`, `is_local_product_feed_source_name`,
`get_local_product_feed_summary_*`, `get_workspace_local_product_feed_keys`,
`summarize_local_product_feed_description`, `*_vendor_*`, `score_*`, `rank_*`,
`find_local_product_feed_product_match`, `build_local_product_feed_product_reply`,
`parse_local_product_feed_price_value`, `format_local_product_feed_currency`,
`get_local_product_feed_recommendation_rows`, `build_local_product_feed_guidance_line`, …

**Catalogue (also food-origin):** `detect_catalog_query_kind`,
`extract_catalog_products`, `select_catalog_source_name`,
`get_catalog_source_texts`, `extract_catalog_count_label`,
`extract_catalog_label_count`, `format_catalog_preview_names`,
`filter_catalog_products_for_issue`, `build_includes_snacks_line`,
`wants_combined_snack_total`, `build_combined_products_and_snacks_line`.

**Product price extraction:** `extract_product_reference_from_issue`,
`get_product_reference_search_tokens`, `get_product_price_line_score`,
`extract_product_price_match`.

**Query building / context:** `build_assist_cache_key`,
`get_cached_assist_response`, `store_cached_assist_response`,
`clear_assist_response_cache`, `get_customer_display_name`,
`build_conversation_transcript`, `build_contextual_assist_query`,
`resolve_assist_issue_type`, `mentions_wing_reference`, `build_context_sections`,
`build_system_prompt`, `build_user_prompt`, `should_use_fast_retrieval_reply`,
`should_use_llm_generation`.

**Confidence / handoff:** `classify_confidence`, `has_sufficient_guidance`,
`should_recommend_handoff`, `ensure_handoff_language`.

**Localisation (Tenglish / Indic):** `extract_voice_response_language`,
`answer_matches_response_language`, `localize_cached_response`,
`get_language_greeting`, `create_butler_english_response`, `add_butler_politeness`,
`create_mixed_language_response`, `create_telugu_english_response`,
`localize_ai_answer`.

**LLM:** `generate_support_chat_response(system_prompt, user_prompt,
conversation_messages, model_name, temperature)` → thin wrapper over
`generate_qwen_chat_response`. `stream_support_chat_response` → wrapper.

### The three entry points the app calls

| Function | `@src` | Locals | Called from |
|---|---|---|---|
| `build_company_api_direct_answer(issue, matched_chunks, conversation_messages)` | L4875 | 283 | wrapped by `services/ai_agent_service.py` (see below), then `graph/main_orchestrator.py` via `build_ai_support_answer` |
| `build_ai_support_answer(issue, customer_name, customer_email, business_hours_tag, issue_type, article_hint_url, conversation_messages, limit, prefer_fast_response, prefer_qwen_response)` | L9883 | 37 | `graph/main_orchestrator.py` non-stream + RAG-pipeline `support_handler` |
| `stream_ai_support_answer_events(...same args...)` | L10387 | 39 | `graph/main_orchestrator.py` property-stream branch |

**`build_ai_support_answer` flow (from bytecode):**
1. Cache check (`build_assist_cache_key` → `get_cached_assist_response` →
   `localize_cached_response`).
2. `build_contextual_assist_query`, then `search_workspace_knowledge` +
   `search_company_knowledge`; if the issue matches
   `\b(?:projects?|properties)\b.*\bin\s+`, also `get_company_projects` and
   inserts a synthetic `acrobuild-cs-projects` chunk.
3. `get_customer_context(customer_email, timeout_seconds=0.6)`.
4. `resolve_assist_issue_type`; risky-term check against `RISKY_SUPPORT_TERMS`.
5. Routes to `build_company_api_direct_answer` (property/company), or
   `build_document_requirement_answer` / `build_project_location_answer` /
   `build_site_visit_booking_answer` / workspace-capability / small-talk /
   `build_company_value_proposition_answer`, or
   `build_fallback_assist_answer` (retrieval miss).
6. `localize_ai_answer`, `classify_confidence`, `should_recommend_handoff`.
7. Assembles the result dict. **`agent_mode` is the string literal `"gemini"`**
   (bytecode L10338; L10909 in the stream version). `temperature=0.35` is passed
   to `generate_support_chat_response` (bytecode L10316; L10869 in stream). Both
   are baked-in constants with no env override — **Phase 2 target.**
8. `store_cached_assist_response`.

### Wrapper layer — `services/ai_agent_service.py` (this part IS source)

The loader file adds ~470 lines of deterministic pre-handlers that run **before**
the blob's `build_company_api_direct_answer` (aliased `_legacy_…`):

- `_build_contextual_flat_cost_answer` — computes a referenced flat's base cost
  from chat history (`area × rate` range).
- `_build_contextual_same_price_floor_answer` — finds same-config units on a
  requested floor.
- `_is_project_count_question` / `_build_project_count_answer`
- `_is_portfolio_overview_question` / `_build_portfolio_overview_answer`
- `_is_project_catalogue_question` / `_build_project_catalogue_answer`
- `_build_acrobuild_overview`
- `_is_vague_project_recommendation` / `_build_project_recommendation_clarification`
- `_is_budget_project_recommendation` / `_build_budget_project_recommendation`
- `_is_multi_bhk_budget_recommendation` / `_build_multi_bhk_budget_recommendation`
- `_build_recommendation_budget_follow_up`
- `_is_shop_availability_question` / `_build_shop_availability_answer`
- `_find_requested_project` / `_sanitize_project_location_answer`

Only if none of these fire does it call `_legacy_build_company_api_direct_answer`
(the blob) and post-process with `_sanitize_project_location_answer`.

---

## Baked-in constants of interest

| Constant | Location (bytecode) | Effect | Fixable without full decompile? |
|---|---|---|---|
| `temperature=0.35` | `build_ai_support_answer` ~L10316, `stream_ai_support_answer_events` ~L10869 — the `generate_support_chat_response(...)` call | Property/factual answers generated with sampling temperature 0.35 → invented figures | **Yes** — swap the code constant (Phase 2) |
| `agent_mode="gemini"` | same two functions, result dict ~L10338 / ~L10909 | Wrong provider label in telemetry/logs (no Gemini is configured); `normalize_agent_mode()` in the orchestrator masks it downstream | **Yes** — swap the code constant (Phase 2) |
| `temperature=0.2` | `build_local_conversation_answer` (pipeline file) | General-chat generation temperature | leave as-is |
| `temperature` param default `0.1` | `generate_support_chat_response` signature | only used if caller omits it (callers pass 0.35) | n/a |
| `get_customer_context(..., timeout_seconds=0.6)` | both entry points | 600 ms budget for customer-context lookup | leave as-is |

---

## Phase 1 result

- Both files fully enumerated: **26 + ~150 functions**, all module constants,
  all baked-in literals of interest located to the bytecode line.
- Provenance identified (food-catalogue origin).
- Confirmed the two Phase-2 constants (`0.35`, `"gemini"`) are plain `LOAD_CONST`
  in `build_ai_support_answer` / `stream_ai_support_answer_events` — patchable.
- Pipeline file is well-scoped for Phase 3 reconstruction; agent file needs the
  Phase 4 decompiler spike.
- Nothing was modified.
