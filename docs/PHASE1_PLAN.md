# Phase 1 plan: discovery slot memory + typed CS API tool layer

Status: Steps 1–7b implemented; fresh Step 7/7b live acceptance passed on both assist endpoints on 2026-10-01. Step 8 applied: discovery defaults **true**; `ACROBUILD_DISCOVERY_SLOTS=false` disables it. Source code is authoritative; "unverified" marks unconfirmed facts.

## Activation gate (2026-10-01)

- Before changing the default, `scripts/live_disambiguation_check.py --discovery`
  passed T1–T12 on JSON and streaming (24 endpoint transcripts, 72 turns) using
  the real configured CS API and Sarvam with live-only property reads. Every
  discovery turn had `source_status=live_api`; name/estimate and leak checks passed.
- After activation, the same 24 transcripts and 72 turns passed again with the
  flag **unset**, exercising the new default and T11's explicit false opt-out.
  Live checks used the real application through `TestClient`; a browser `/home`
  walkthrough was not performed in this run.
- Step 7b was already implemented. T7 confirmed a live locality search replaces
  inherited project scope; T8 confirmed the deterministic bare reset and reset
  with a new BHK request. No discovery behavior defect needed a fix.
- The live catalogue supplied 9 customer-facing projects and 305 typologies,
  all with `Rate Per Sq.Ft.`. Missing localities used live city values. Typology
  images remain content-unverified. A city absent from offered area options and
  an unpriced 3BHK project were not present in this catalogue; those branches and
  repeated API failures are covered by automated regression tests.
- Focused regression: **767 passed + 16 subtests** before activation;
  **769 passed + 16 subtests** after adding default-on endpoint coverage. Explicit
  false/off values still preserve the prior response and stored-marker behavior.
- Full backend regression after activation: **1617 passed + 136 subtests,
  1 pre-existing snapshot test failure**. The legacy snapshot test assumes nine
  records and the old server; the configured server differs, and in the live
  full-suite run the test observes ten records from the turn cache. No snapshot
  or cache behavior was changed for activation. A network-permission error in
  the initial sandbox run and temporary-directory permission errors in the
  first elevated run were resolved by rerunning with network access and a
  writable system-temp parent outside the repository (no `--basetemp`).
- Changed Python files pass Ruff; configured mypy checks pass. Repo-wide Ruff
  still reports two pre-existing F821 diagnostics in the restricted
  `graph/haystack_conversation_pipeline.py` loader (`get_live_project_names`,
  `_conversation_project_name`, populated by its exec-loaded source).

The results file retains a `phase1_activation.pre_activation` summary and the
latest full `discovery` transcript. The checker now records timestamps, checks
live grounding and exits nonzero on a failed transcript. Set the flag to false
to roll back activation. The original step table below is retained as history;
its Step 5/6 default-false settings describe the pre-activation rollout.

## Corrections after implementation

Where the code differs from the plan below, the code is right:

- (a) After a project tap, "and 2 BHK?" goes to the tapped project
  (`current_project` wins), not to locality reuse. Plan A3 was wrong there.
  Locality and budget are reused for a new configuration only while no
  project is in scope (for example right after the shortlist).
- (b) Discovery pending selections carry `"source": "discovery"`. The area
  question also carries `purpose: "discovery"`; the shortlist keeps
  `purpose: "home_type_search"`.
- (c) Discovery payloads set `catalogue_home_type_search`, so one matching
  project never sets `current_project`.
- (d) On discovery payloads, `skipped[]` entries keep just the project name.
  All public `data_api_calls[].error` values now use a shared generic message;
  the full text stays in the server log.
- (e) The contract's own re-ask (`build_unmatched_selection_answer()`) has no
  "Any area" button. Discovery handles place-like replies first, so it is
  reached only for non-place replies such as "A1".
- (f) The cleaning rule (U+2063 removed, control characters as spaces,
  whitespace collapsed) is duplicated in three modules and pinned by a test:
  `property_clarification_service._clean_option_text()`,
  `property_tools_service.clean_place_text()` and `discovery_slot_service._clean()`.
  A fourth, length-capped variant validates marker values in
  `conversation_store_service._clean_slot_text()`; that test does not pin it.
- (g) Additive response fields on discovery payloads: `discovery_kind`,
  `options`, `skipped`, `discovery_slots`, `catalogue_home_type_search`,
  `discovery_prompt` (budget question only) and `source` inside
  `pending_project_lookup`.
- (h) Turn 1 reads `property_tools_service.search_projects(config, "any")`, not
  `list_localities()`, so a typed city that is not an option is still
  accepted. The budget question reuses that turn's read; there is no second
  live read per turn.
- (i) The forced-property rule covers an awaited `budget` or `locality`
  (pending selection absent, not call booking/human contact, `is_slot_reply()`
  true). "start over, <new request>" starts from empty slots and stores the
  new ones.

## Phase 2 follow-ups

- (a) Teach `_enforce_live_property_data()` a "partial" status, so "N
  project(s) could not be checked" can reach the customer instead of the
  generic outage message.
- (b) Public response redaction of CS API error text in `data_api_calls` is
  implemented for discovery, non-discovery, streaming and property-flow paths.
- (c) Consolidate the duplicate locality helpers (`api_context._known_localities`,
  `property_clarification_service._project_locality_values`, the discovery and
  tool helpers) and the copies of the cleaning rule.
- (d) Fix the `src/types.ts` drift, including the new additive fields.
- (e) While an area is awaited, a short non-place reply such as "good night"
  gets the not-found reply once before the question lapses.

## Context

`docs/GAP_ANALYSIS.md` ranks two gaps high:

- **Slot memory (Inquiry to Sales §28).** "Show me 3 BHK" asks for a *project*, then forgets the configuration, locality and budget.
- **No typed tool layer (§33).** Property calls go straight to `services/acrobuild_company_service.py` from many builders. Some calls also run inside the compiled blob.

Phase 1 adds:

- **(A)** a server-side `discovery_slots` marker and a discovery flow (config → locality → budget → matching projects).
- **(B)** an additive tool module that wraps the 7 CS API endpoints already in use, with one return shape that carries `source_status`.

Everything must keep the property clarification contract in `AGENTS.md`.

**Decisions (confirmed by the user):**

1. Turn 1 asks for **locality**. This adds a new `locality` entity to the clarification contract, with options taken from live values. The question is skipped when only one locality applies.
2. The **budget** question is asked and can be skipped ("any budget"). Matching uses an estimated base amount (min rate × saleable area) with a disclaimer.
3. The tool layer is **additive only**. Existing builders keep calling `acrobuild_company_service` and migrate in a later phase.

---

## A) Discovery slot memory

### A1. Marker design

This lives in `services/conversation_store_service.py`, next to `build_current_project_marker` / `get_current_project_context`.

- New prefix: `_DISCOVERY_SLOTS_PREFIX = f"{_MARKER_CHAR}discovery_slots:"`. It uses the same base64-JSON and U+2063 framing as the existing markers.
- New functions:
  - `build_discovery_slots_marker(slots: dict) -> str`. An empty dict writes an explicit **clear** marker.
  - `get_discovery_slots(message_text) -> dict | None`. Parses and **validates** the marker. Unknown keys are dropped, types are coerced, and anything invalid is discarded.
  - `latest_discovery_slots(messages) -> dict`. Scans stored bot messages newest-first. The first marker found wins; `{}` means none or cleared.

**Fields (v1):**

| Field | Type | Rule |
|---|---|---|
| `v` | int | `1` |
| `config` | list[str] | BHK numbers `"1"`–`"6"`, taken from `project_home_type_service.requested_home_types()` |
| `locality` | str | Only a value copied from a live project's `locality`/`city`, or `"any"` (set only by the "Any area" quick reply or an equivalent phrase such as "any area" / "anywhere"; see A2). Never the customer's raw text. |
| `budget_max_inr` | int \| null | 1 ≤ value ≤ 10¹⁰; `null` = not asked or "any" |
| `budget_label` | str | Customer's wording ("1.5 crore"), for copy only; max 40 chars |
| `awaiting` | `"locality"` \| `"budget"` \| null | Which slot the last discovery reply asked for |
| `origin_issue` | str | The full original discovery question, max 500 chars |

**Project slot.** The project is **not duplicated** here. The single source of truth stays `current_project` (`build_current_project_marker`, read by `_conversation_project_name` in `graph/haystack_conversation_pipeline_source.py`).

**Storage.** `routers/assist.py::_conversation_state_marker()` gets a new optional parameter, `slots=None`, and appends `_discovery_slots_marker(response_payload, slots)`:

- If the payload has a `discovery_slots` key, write it; `{}` clears.
- Else, if `slots.awaiting` is set and this turn was not a slot reply, write `{**slots, "awaiting": None}` so the stale question lapses.
- Else write nothing; the backward scan keeps the previous value.

The marker is only appended to the **stored** copy in `ConversationSession.append`, the same as the other markers.

**Restore.** `routers/assist.py::_prepare_lookup_turn()` calls `latest_discovery_slots(request.conversation_messages)`. Both endpoints already load the server history into `conversation_messages` before this runs. The return signature stays a 4-tuple, because `tests/test_chat_quick_replies.py` unpacks it. Endpoints read the slots once and pass them to `_grounded_property_shortcut(..., slots=...)` as a new keyword argument defaulting to `None`. `tests/test_grounded_shortcut_cs_api_failure.py` calls it with 2 arguments.

**Clear / override rules:**

- A new value replaces the old one for that slot only (e.g. "2 BHK" replaces `config`; a new live locality replaces `locality`).
- "start over", "reset", "new search", and "clear my preferences" write `{}`.
- `build_project_browse_response` payloads and a new `conversation_id` ("Browse all projects") start empty.
- `DELETE /api/support/conversations/{id}` removes everything.
- Rows expire with `conversation_turns` (`RETENTION_SECONDS = 7200`).
- General, callback and human-contact turns keep the slots. `awaiting` only lapses as described above.
- Slots are re-validated on use: `locality` must still appear in live data, or it's treated as unset.

**Coexistence with `pending_project_lookup`:**

1. The pending selection still has **priority** for short replies (`continues_selection`, the narrowing helpers). The discovery flow also *uses* the contract's pending state:
   - Locality question: `entity: "locality"`, `purpose: "discovery"`, `original_issue` = the full original question.
   - Result shortlist: `entity: "project"`, `purpose: "home_type_search"`, `original_issue` = a composed query that contains the BHK text. The existing `resume_selection()` branch turns this into `"Show 3BHK details in project X"`.
2. `discovery_slots.awaiting` is a **backup** for when the pending state is dropped. For example, "Wakad lo" matches `_NEW_REQUEST_RE` ("lo"), so `continues_selection()` returns False. It is also the only state for the budget question, which is free text with no options and no pending selection.
3. The marker never stores options; the pending state never stores budget.
4. A project in scope wins: if `current_project` or a named project resolves, discovery does not start. The existing `build_project_home_type_answer` path answers, as covered by `test_real_selection_sequence_and_bare_followup`.

### A2. Contract extension (the `locality` entity)

These changes go in `services/property_clarification_service.py`:

- `clarification_entity()` accepts the explicit value `"locality"`.
- `live_options()` gets a new first branch: `if entity == "locality": return "locality", list_localities(config from requested_home_types(issue)).data, {}`.
- The label maps in `apply_clarification_contract` / `build_unmatched_selection_answer` get `{"locality": "area"}`, so the question reads "Which area should I check?\n- …".
- **"Any area" quick reply (addendum decision).** `build_discovery_answer()` appends `{"label": "Any area", "value": "Any area"}` to the locality question's `quick_replies`. It is **not** added to `pending_project_lookup.options`, which stay real live names only. When the customer taps it or types "any area" / "anywhere", `continues_selection()` finds no option match, and `build_discovery_answer()` (which runs before `build_unmatched_selection_answer`) sets `locality="any"`. The next step is then the budget question with no locality filter.
- `apply_clarification_contract()` gets an early return for payloads with `discovery_prompt` (the budget question). This stops the prose detector from misreading budget copy.
- `AGENTS.md` changes the entity list to `project, wing, floor, flat, home_type, locality`.

### A3. Trace: "Show me 3 BHK" → "Wakad" → "1.5 crore"

This runs with the feature flag `ACROBUILD_DISCOVERY_SLOTS=true`.

**Turn 1 — "Show me 3 BHK"**

1. The flow is the same as today up to `_prepare_lookup_turn()`:
   - `prepare_turn()`: `_HARD_PROPERTY_SIGNAL_RE` sets `intent="property"`, and the text becomes "Show me 3BHK".
   - `resolve_contextual_support_issue()` appends nothing, because no project is in history.
2. `_prepare_lookup_turn()`: no pending state, `slots={}`.
3. `_grounded_property_shortcut(..., slots={})`. The chain order becomes `build_grounded_site_visit_document_assist` → **`discovery_slot_service.build_discovery_answer(issue, turn, slots, pending)`** → the existing chain.
4. `build_discovery_answer()`:
   1. `is_discovery_request()` is True: a config is present; no project in the issue or in "Requested project:"; not a recommendation or quantity phrasing (see Risks); not a wing/floor/flat/amenity/location/documents request.
   2. `extract_discovery_slots()` gives `config=["3"]`.
   3. `property_tools_service.list_localities(["3"])` runs.
   4. If there are 2 or more localities, it calls `apply_clarification_contract({"clarification_entity": "locality"}, issue, history)` and adds `pending_project_lookup.purpose="discovery"` and `discovery_slots={config:["3"], awaiting:"locality", origin_issue}`.
   5. Other cases: exactly 1 locality means `locality` is set automatically and the budget question comes next. 0 localities returns the honest copy "None of the projects in the latest catalogue list 3BHK" and clears `awaiting`.
5. `_complete_payload()` then runs:
   - The contract returns early (the pending state is a dict).
   - `_enforce_live_property_data()` returns `live_api` (GET projects + typologies were called).
   - `localize_response()` keeps the locality bullets verbatim.
6. Persisted: the pending marker (entity locality), the `current_project` marker `""`, and the discovery marker.

**Turn 2 — "Wakad"**

- **(a) "Wakad" is a live option:**
  1. `continues_selection()` returns True, then `_resume_project_lookup_request()` → `resume_selection()`. The effective question becomes "Show me 3BHK. Selected locality: Wakad" and `scope.locality="Wakad"`.
  2. `build_discovery_answer()` takes the locality from `pending.scope`, runs `list_localities` again (a live read, which also avoids the no-call trap in Risks), and returns the **budget question**: "What's your approximate budget for a 3BHK in Wakad? You can say 'any budget'."
  3. That payload has `discovery_prompt="budget"`, `quick_replies=[{"label": "Any budget", "value": "any budget"}]`, `discovery_slots={…, locality:"Wakad", awaiting:"budget"}`, and no pending state.
- **(b) "Wakad" is not in live data:** `is_unmatched_selection_reply()` returns True, the pending state is kept, and the text is unchanged. `build_discovery_answer()` runs **before** `build_unmatched_selection_answer` in the chain and returns:
  > "I couldn't find any current 3BHK projects in 'Wakad'. Projects with 3BHK are listed in: - Thane - Pune"
  - The options come from a fresh contract call. `slots.locality` stays unset (the customer's text is echoed in quotes and **never stored**), and `awaiting` stays `"locality"`.
  - If the reply names a live locality that has no 3BHK projects, the copy says so and lists the localities that do.
  - Nothing reaches the LLM or the search step with an unknown place.

**Turn 3 — "1.5 crore"**

1. `_prepare_lookup_turn()`: no pending state. `slots.awaiting == "budget"` and `discovery_slot_service.is_slot_reply()` is True (`parse_budget_inr("1.5 crore")` = 15,000,000). The turn is forced to `intent="property", unsure=False`, which overrides a possible "general" or "unsure" label from the analyzer.
2. `build_discovery_answer()` calls `property_tools_service.search_projects(config=["3"], locality="Wakad", budget_max_inr=15_000_000)`. The result lists projects within budget (from INR x.xx crore), then over-budget ones, then ones with no listed price. It includes a disclaimer (base estimate only; taxes, registration, floor rise and parking are excluded).
3. The payload uses `clarification_entity="project"` and a pending state with `entity:"project"`, `purpose:"home_type_search"`, `options` = within-budget + unpriced names, and `original_issue` = "Show me 3BHK in Wakad within about INR 1.50 crore". `discovery_slots` = `{config, locality, budget_max_inr, budget_label, awaiting:null}`. Tool evidence goes into `matched_chunks` (`record_kind="company_api"`), so the INR figures pass the check in `_enforce_live_property_data`.
4. **Turn 4 (project tapped):** the existing `resume_selection()` `home_type_search` branch runs, then `build_project_home_type_answer()` checks live availability. `current_project` is set and the slots are kept. A later "and 2 BHK?" updates `config` only; locality and budget are reused.

**One-shot:** "3 BHK in Thane under 1.5 crore" fills every slot and goes straight to step 2 of Turn 3.

**Failures:**

- On a failure while listing localities, the existing contract returns an honest retry message plus a pending state with `options: []`.
- On a failure while searching, `build_discovery_answer` returns `source_status="failed"` and a pending state (`entity:"project"`, `options:[]`, `original_issue` = composed query).
- In both cases `_project_lookup_marker` re-stores the state with no retry cap, and "retry" resumes it. The slots are unchanged.

---

## B) Typed tool layer

### B1. The §33 tool map

The 7 endpoints in use are: company, projects, project amenities, project wings, project typologies, wing typologies, and wing inventory (paths under `/api/cs/{companyId}/`).

**BLOCKED** means the tool needs a new AcroBuild endpoint (or an external provider).

| §33 tool | Status | Wrapper today (`acrobuild_company_service`) | Endpoint(s) / note |
|---|---|---|---|
| search_projects | Buildable | `get_company_projects`, `build_project_record_index`, `filter_project_index` | projects + project typologies |
| get_project_details | Buildable | `get_company_projects`, `get_project_wings` | projects, wings. `GET /projects/{id}` is documented but not wrapped or verified live (unverified). |
| get_developer_details | Partial | `search_company_knowledge` (contact chunk) | company (contact fields only). History and awards are BLOCKED or come from the knowledge base. |
| get_project_history | Partial | — | projects (`estimatedStartDate`/`EndDate`). Phase/tower launch dates are BLOCKED. |
| search_inventory | Exists (per wing) | `get_wing_inventory`, `get_project_wings` | wings + inventory |
| get_unit_details | Partial | `get_wing_inventory` | inventory (unit, floor, typology, areas, status). Facing, view, parking and unit price are BLOCKED. |
| get_live_price | Partial | `get_project_typologies`, `get_wing_typologies` | typology `min/maxBasePrice`, `rateType`. Per-unit price is BLOCKED. |
| calculate_cost_sheet | BLOCKED | — | needs a pricing-engine endpoint |
| get_price_history | BLOCKED | — | — |
| get_active_offers | BLOCKED | — | — |
| get_payment_plan | BLOCKED | — | — |
| get_amenities | Exists | `get_project_amenities` | amenities |
| get_construction_status | Partial | `get_project_wings` | wing `constructionStatus`. Percentages and dated updates are BLOCKED. |
| get_possession | Partial | `get_project_wings` | wing `expectedPossesionDate`. Unit-level and revised dates are BLOCKED. |
| get_project_documents | Partial | — | typology `imageUrl`: what it contains is **unverified** (`docs/cs-api.md` labels it "Floor plan / image"). It must not be presented as a floor plan until live data is checked (step 7). Brochure, master plan and RERA documents are BLOCKED. |
| get_location_details | Buildable | `get_company_projects` | project address, locality, city, lat/long |
| get_nearby_places / get_distance / get_travel_time | BLOCKED (external maps provider) | — | — |
| get_available_site_visit_slots / schedule_revisit | BLOCKED | — | — |
| schedule_site_visit | BLOCKED in AcroBuild | local: `routers/properties.create_site_visit` → `run_workflow` | local ticket only |
| create_lead / update_lead | BLOCKED | — | — |
| request_callback | BLOCKED in AcroBuild | local: `main_orchestrator._build_call_booking_response` | local ticket only |
| get_customer_details / get_payment_status / get_documents | BLOCKED | — | needs customer identity + post-sales APIs |
| create_ticket | Local only | `graph/workflow.run_workflow` | AcroBuild tickets are BLOCKED |

The helper `list_localities(config=None)` is not in §33 but is needed by A2.

### B2. Module, signatures, return shape

**New file: `services/property_tools_service.py`.** It depends only on `services/acrobuild_company_service` and `services/internal_api_log_service`.

- It calls through the module (`company_service.get_company_projects()`), so tests that patch `services.acrobuild_company_service.*` still work.
- Section comments use the house style `# -----------------------------------`.

```python
class ToolResult(TypedDict):
    tool: str
    status: str          # "ok" | "empty" | "partial" | "unavailable" | "blocked" | "invalid"
    source_status: str   # "live_api" | "snapshot" | "failed" | "unavailable"
    data: Any            # list | dict, tool-specific
    evidence: list[dict] # record_kind="company_api" chunks, ready for matched_chunks
    skipped: list[dict]  # [{"project": name, "error": msg}] for honest partial coverage
    error: str

def list_localities(config: list[str] | None = None) -> ToolResult
def search_projects(config: list[str] | None = None, locality: str = "", budget_max_inr: int | None = None) -> ToolResult
def get_project_details(project_id: int) -> ToolResult
def get_developer_details() -> ToolResult
def get_project_history(project_id: int) -> ToolResult
def search_inventory(project_id: int, config: list[str] | None = None, floor: int | None = None, available_only: bool = True) -> ToolResult
def get_unit_details(project_id: int, unit_number: str) -> ToolResult
def get_live_price(project_id: int, config: list[str] | None = None) -> ToolResult
def get_amenities(project_id: int) -> ToolResult
def get_construction_status(project_id: int) -> ToolResult
def get_possession(project_id: int) -> ToolResult
def get_project_documents(project_id: int) -> ToolResult
def get_location_details(project_id: int) -> ToolResult
BLOCKED_TOOLS: dict[str, str]   # tool name -> required AcroBuild/external endpoint
def blocked(tool: str) -> ToolResult   # status="blocked", no network call
```

**`search_projects` logic:**

1. Take customer-facing projects.
2. Keep those whose `city` or `locality` equals the locality, or whose `address`/`location` contains it. This is the same rule as `narrow_project_choice_by_locality`.
3. Build `build_project_record_index(get_project_typologies)` over the filtered projects only.
4. Match config with `requested_home_types(typologyName|typologyType)`.
5. Estimate `minBasePrice × saleableArea`, but only when `rateType` mentions sq. ft. The live values of `rateType` are unverified; the test fixture uses "Rate Per Sq.Ft.". Other projects go to `unpriced`.
6. Return `data = {matches, over_budget, unpriced}` plus `skipped`.

It does **not** fetch inventory. Availability is confirmed after selection.

**`source_status`** is derived from the `get_current_data_api_logs()` entries added during the call:

- Any failed live call not covered by a snapshot gives `failed`.
- Any `snapshot` provider gives `snapshot`.
- Otherwise `live_api`.

`_enforce_live_property_data()` stays the **final authority**, working from `data_api_calls`. Builders must never set `source_status="live_api"` when a tool returned `unavailable`. Builders must also always put the tool `evidence` into `matched_chunks`.

**Error behaviour:**

- `RuntimeError` / `TimeoutError` from the CS layer is caught and returned as `status="unavailable"`, `source_status="failed"`, `error=str(e)`. Tools never raise to routers.
- Bad ids return `status="invalid"`.
- Per-project failures in an index return `status="partial"` plus `skipped`, and the builder discloses "N project(s) could not be checked".
- Blocked tools return `status="blocked"` with no network call. Builders say the data isn't available and never ask the LLM to fill the gap.

### B3. Compiled paths the tool layer must NOT touch

- `services/ai_agent_service_runtime.pyc`, `services/ai_agent_service_runtime.patched.pyc`, `graph/haystack_conversation_pipeline_runtime.pyc`.
- The `exec` loader blocks in `services/ai_agent_service.py` and `graph/haystack_conversation_pipeline.py`. No globals get injected or monkeypatched there.
- Blob entry points `build_ai_support_answer`, `stream_ai_support_answer_events`, `build_company_api_direct_answer`, `_legacy_build_company_api_direct_answer`, and the orchestrator's `existing_support_handler` property branch.
- `scripts/patch_runtime_constants.py` must not be run. `graph/haystack_conversation_pipeline_source.py` is not edited in Phase 1.

---

## Files to change

**New:**

- `services/property_tools_service.py`
- `services/discovery_slot_service.py`, containing:
  - `is_discovery_request`, `extract_discovery_slots`, `parse_budget_inr`, `is_slot_reply`, `build_discovery_answer`
  - `DISCOVERY_ENABLED` (from `ACROBUILD_DISCOVERY_SLOTS`)
- `tests/test_property_tools_service.py`, `tests/test_discovery_slots.py`, `tests/test_discovery_flow.py`

**Modify:**

- `services/conversation_store_service.py`: marker helpers.
- `services/property_clarification_service.py`: the `locality` entity, the `discovery_prompt` early return, label maps.
- `routers/assist.py`: `_prepare_lookup_turn`, `_grounded_property_shortcut` (keyword argument + chain position), `_conversation_state_marker` (keyword argument), and the call sites in `get_support_assist` and `stream_support_assist`.
- `scripts/live_disambiguation_check.py`: discovery transcripts.
- Docs: `AGENTS.md` (entity list, slot rules), `docs/CHAT_FLOW.md`, `docs/AI_CONTEXT.md` (file map), `docs/PROJECT_MAP.md` §5/§10.
- `.env.example`: Step 6 planned `ACROBUILD_DISCOVERY_SLOTS=false`; Step 8 now sets it to `true` and documents the explicit false opt-out.

**Out of scope / do not touch (addendum):**

- `docs/cs-api.md`: the user will rotate the key and clean up the file.
- `docs/Inquiry to Sales.pdf`, `docs/Sales to Handover Ai chatbot.pdf`: never commit or stage these.
- `get_project_documents()` code comments must mark the `imageUrl` content as "unverified" and must not call it a floor plan.

**Not changed:** `api_context.py`, `graph/main_orchestrator.py`, all `.pyc` files, and `src/` (quick replies are generic; `src/types.ts` drift is left for Phase 2).

## Tests to add (per AGENTS.md)

The pattern follows `tests/test_project_home_type_followups.py`: a fake `Session`, a monkeypatched `analyze_turn`, and `@pytest.mark.parametrize("endpoint", ["/api/support/assist", "/api/support/assist/stream"])`. Run without `--basetemp`.

**`test_property_tools_service.py`:**

- Each tool's shape, plus the `unavailable` result on `RuntimeError`.
- `partial` with `skipped`.
- Blocked tools make **no** CS call.
- Evidence uses `record_kind="company_api"`.
- A payload built from tool evidence is classified `live_api` by `_enforce_live_property_data`, and `failed` on failure.
- An AST check that the module does not import `services.ai_agent_service`.

**`test_discovery_slots.py`:**

- Marker round trip, validation of forged or out-of-range values, and that the latest marker wins.
- An explicit clear works, and the marker survives long answers (mirrors `test_selection_metadata_survives_long_stored_answers`).
- It coexists with the pending and `current_project` markers in the same stored text.
- `parse_budget_inr` handles "1.5 crore", "1.5cr", "150 lakh", "80L", "90 lacs", "₹1,50,00,000", "any budget"; a bare "1.5" returns None.
- The locality is only accepted from live values.

**`test_discovery_flow.py`** (both endpoints):

- **Named options.** The locality question lists every live locality with 3BHK as `- X` bullets and quick replies, with `clarification_entity="locality"`. The result shortlist lists all matching projects and never auto-selects one.
- **Short follow-up.** Covers "Thane" → budget question → "1.5 crore" → shortlist → a project tap → "Home types in …". Also covers a one-shot query, and "any budget".
- **Unknown locality.** "Wakad" (absent from the fixture) gets the honest not-found copy with live options re-offered, and no `locality` in the stored marker.
- **Any area.** The locality question includes an "Any area" quick reply that is not in `pending_project_lookup.options`. Tapping it (or typing "anywhere") stores `locality="any"` and moves to the budget question. The search then runs with no locality filter.
- **Repeated API failures.** 3× `RuntimeError` at the locality step and at the search step. Each turn fails honestly, the pending state and slots are kept (no expiry), and a later "retry" succeeds.
- **Intent preservation.** After results, "2 BHK?" (with scope cleared) reuses the locality and budget. A new locality overrides the old one. A digression (an amenities question) keeps the slots. A current project in scope bypasses discovery.
- **Flag off.** Behaviour is identical to today (the project list).
- **Localization.** With a non-English analysis and a mocked translator, the locality names survive verbatim.

**Existing suites to re-run** (possible interactions): `test_property_clarification_contract`, `test_project_home_type_followups`, `test_chat_quick_replies`, `test_global_recommendation`, `test_budget_project_recommendation`, `test_grounded_shortcut_cs_api_failure`, `test_pending_project_lookup`, then the full suite.

## Risks

1. **Behaviour change for bare BHK questions.** Existing expectations (e.g. live check transcripts) show a project list. Mitigation: the flag, updated transcripts.
2. **Collision with the budget recommenders in `services/ai_agent_service.py`** (`_is_budget_project_recommendation`, `_is_multi_bhk_budget_recommendation`, `_build_recommendation_budget_follow_up`; phrasing in `test_global_recommendation`). `is_discovery_request` must exclude recommend/suggest/best/cheapest/affordable, quantity phrasing ("two 2BHK flats"), and "is it sufficient".
3. **The no-call trap in `_enforce_live_property_data`.** A property-route payload with no CS call becomes `failed`. Every discovery payload, including the budget question, must perform a live read and carry `company_api` evidence.
4. **CS API load and latency.** `list_localities(config)` and `search_projects` each make 1+N serial calls (2.5 s timeout each; there is no cross-turn cache when `ACROBUILD_CS_API_LIVE_ONLY=true`). Mitigation: filter by locality before fetching typologies. Parallelising is deferred.
5. **`rateType` coverage.** The activation run verified `Rate Per Sq.Ft.` in the current live catalogue. Budget maths remains limited to per-sq-ft rates; other rate types are reported as "pricing not listed" and covered by regression fixtures.
6. **Locality data quality.** `locality` may be empty or inconsistent, and the catalogue may not contain "Wakad" at all. Fall back to `city`. Unknown places are handled honestly.
7. **Forged markers.** When no `conversation_id` is sent, markers can come from client-supplied history (the pending marker already has this risk). Validate on read and re-check `locality` against live data.
8. **Analyzer labels.** "1.5 crore" may be labelled general or unsure. Covered by the forced-property rule, which only applies when `is_slot_reply` parses the reply.
9. **Duplicate helpers.** The new locality helpers duplicate `api_context._known_localities` and `property_clarification_service._project_locality_values`. Consolidate in Phase 2.

## Step order (each step keeps the suite green)

| # | Step | Verify | Rollback |
|---|---|---|---|
| 0 | Baseline: run the full pytest suite and ruff/mypy; record counts | counts recorded | — |
| 1 | Add `property_tools_service.py` + `test_property_tools_service.py` (unused by the app) | new tests + full suite | delete both files |
| 2 | Marker helpers in `conversation_store_service.py` + marker tests | `test_discovery_slots.py`, `test_pending_project_lookup` | revert the file (no callers yet) |
| 3 | `discovery_slot_service.py` (extraction, budget parser, builder) + unit tests | new tests | delete the module and tests |
| 4 | Contract: the `locality` entity + `discovery_prompt` guard | `test_property_clarification_contract` + new contract tests | revert `property_clarification_service.py` |
| 5 | Wire `routers/assist.py` behind `ACROBUILD_DISCOVERY_SLOTS` (default **false**) | `test_discovery_flow.py` (both endpoints, flag on/off) + full suite | set the flag to false; revert `assist.py` if needed |
| 6 | Docs: AGENTS.md, CHAT_FLOW.md, AI_CONTEXT.md, PROJECT_MAP.md; append `ACROBUILD_DISCOVERY_SLOTS=false` to `.env.example` (approved) | review | revert the doc files; remove the one `.env.example` line |
| 7 | Live acceptance: extend `scripts/live_disambiguation_check.py`; check `rateType`, locality and typology `imageUrl` values (describe `imageUrl` only after this check); write results to `docs/live_disambiguation_results.json` | real LLM/API transcripts | revert the script and results |
| 8 | Default the flag to **true** after step 7 passes | full suite + manual chat (`uvicorn app:api --reload`, `npm run dev`) | flip the default back to false |

## Verification

- `.venv/Scripts/python.exe -m pytest tests/test_property_tools_service.py tests/test_discovery_slots.py tests/test_discovery_flow.py`, then the full `tests/`.
- ruff + mypy (config in `pyproject.toml`; caches under `data/`).
- `scripts/live_disambiguation_check.py` against the real CS API and Sarvam: "Show me 3 BHK" → <live locality> → "1.5 crore" → project tap, plus an unknown locality and a one-shot query.
- Manual check in the customer chat (`/home`) on both the streaming and JSON fallback paths.

## Summary

1. Phase 1 adds discovery slot memory (§28) and an additive, typed CS API tool layer (§33).
2. Slots (config, locality, budget, awaiting, origin) live in a new `discovery_slots` marker in `conversation_store_service`. The project stays in `current_project`.
3. The locality question uses a new `locality` entity in the clarification contract, with options from live data only.
4. The budget question is free text, can be skipped, is guarded from the contract's prose detector, and always does a live read.
5. The results reuse the `home_type_search` pending selection, so a tap resumes the existing BHK answer.
6. Unknown localities are named back honestly, never stored, and live options are re-offered.
7. `services/property_tools_service.py` returns `ToolResult` with `source_status`. `_enforce_live_property_data` remains the final authority.
8. Of the 29 §33 tools: 2 exist, 10 are buildable or partial from the 7 endpoints, and 17 are BLOCKED. Of the blocked ones, 3 need an external maps provider, and 3 (site visit, callback, ticket) have local-ticket fallbacks only.
9. No `.pyc`, loader or blob entry point is touched. Routing changes sit behind `ACROBUILD_DISCOVERY_SLOTS`.
10. There are 8 reversible steps, 3 new test files covering both endpoints, and a live acceptance run before the flag is enabled.

## Corrections after Step 7

Live acceptance (Step 7) passed 11 of 12 transcripts on both endpoints. T7 and T8 exposed two defects, fixed in Step 7b (flag on only; with the flag off, answers, routes, quick replies and stored markers match `routers/assist.py` at git HEAD, pinned by a test that loads that file from HEAD).

1. **A live place in the customer's own words beats the project in context.** "3 BHK in Thane" with a Pune project in context was answered "Home types in <that project>". `explicit_locality_search_text()` strips the resolver's trailing `Requested project:` line and, when the remaining text is a discovery request naming a live locality or city, `_discovery_answer()` answers that text. The response sets `catalogue_home_type_search`, so `current_project` is cleared. Stored slots are kept and the stated locality overrides.
2. **A bare "start over" is a fixed reply.** With slots stored it now returns `RESET_ANSWER` from `build_reset_answer()`: no LLM, no place, configuration or figure from history, route `general` (a `property` route with no live read is downgraded by `_enforce_live_property_data`), quick reply `browse_projects`. Slots are cleared as before. A reset also skips the pending-choice amenity/area read.
3. **Defaults chosen.** The place equal to the current project's own locality still runs discovery. A project named in the customer's own text still wins. "3 BHK in this project in Thane" and a place that is not live ("3 BHK in Kharadi") keep today's routing (the project in context answers). A bare "2 BHK?" stays on the project in context. Only an exact reset phrase is intercepted; "reset my password" and "start over, show me 2 BHK" are not. A bare reset with no stored slots is unchanged. The project in context survives a reset.
4. **Known and accepted.** A second consecutive "start over" has no slots and goes to the general route as before. Turn preparation still makes its one cached catalogue read (`graph/main_orchestrator.py`) and the turn analysis still runs. A non-English customer's fixed reply is localized by the existing `localize_response()`.
