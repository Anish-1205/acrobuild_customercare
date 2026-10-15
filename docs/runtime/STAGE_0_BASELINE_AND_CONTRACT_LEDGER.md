# Runtime Migration Stage 0: Baseline and Contract Ledger

Date: 9 October 2026  
Status: Stage 0 investigation complete; Stage 1 is not authorized

> Stage 1 update (9 October 2026): separate authorization resolved the plural
> `wings` regression, reduced the historical differential to 39 expected
> differences, made routing source-native, and removed the conversation runtime.
> See `STAGE_1_SOURCE_NATIVE_ROUTING.md`. The remainder of this document records
> the Stage 0 baseline as it existed before that work.

## 1. Executive summary

Stage 0 established a repeatable behavioral baseline without changing application behavior, runtime loading, Haystack integration, prompts, public contracts, or feature flags.

The historical differential count was not reproducible because the verifier randomly selected validation answers without a seed. After making the diagnostic tool deterministic, two consecutive runs produced **40 mismatches across 13,077 cases**. All 40 are assigned to four families:

| Family | Count | Classification |
| --- | ---: | --- |
| Safe relevance fallback copy | 27 | Intentional source evolution |
| Property-scoped pricing guard | 6 | Intentional source evolution; contextual follow-up coverage remains a gap |
| All explicit projects required | 4 | Intentional source evolution |
| Property term boundary routing | 3 | Two intentional false-positive fixes; one possible plural-`wings` regression |

The answer-engine binary remains a broad runtime dependency. It contains 152 top-level functions. Conservative recursive name analysis connects 146 to the five production entry points; a synthetic JSON/cache/stream scenario observed 71 functions executing. The six functions outside the conservative closure are not proven dead because dynamic references or external imports remain possible. The observed scenario also executed local-product/catalogue predicates, so that legacy domain cannot yet be removed solely on the prior assumption that it is dormant.

The supported behavior is well covered at the route, clarification, discovery, grounding, and action boundaries. The most important gaps are representative sanitized conversation-corpus comparison, live Sarvam verification, production latency, cache concurrency/isolation characterization, and an explicit product decision about `prefer_qwen_response=False` and legacy catalogue behavior.

Stage 1 is **conditionally ready**. Before removal of the Haystack runtime fallback, the plural `wings` routing difference must be resolved or explicitly accepted, the 40 source-evolution differences must be approved as the baseline, and the opt-out route must remain supported unless product ownership authorizes a contract change.

## 2. Scope, authority, and evidence classes

Current source is the implementation authority. The historical bytecode is comparison evidence, not an automatic specification. This stage made diagnostic/test/documentation changes only.

Evidence labels used below:

- **Source-confirmed:** directly established by current readable code.
- **Automated-mocked:** covered by tests with controlled dependencies; not proof of a live integration.
- **Synthetic-characterized:** exercised through sanitized stubs by `scripts/stage0_runtime_characterization.py`.
- **Static-potential:** found by conservative code-object name closure; not proof of execution.
- **Live-verified:** exercised against the configured external service in this stage.
- **Unverified:** not established by this stage.

No real customer data, secrets, tickets, callbacks, or site visits were used.

## 3. Current execution and response contracts

### 3.1 Entry paths

| Path | Current contract | Compiled dependency |
| --- | --- | --- |
| Startup | `app.py` imports `api_context.py`, which imports answer-engine exports. | `services/ai_agent_service.py` executes the patched runtime, or the original runtime as fallback, during import. Missing/incompatible bytecode blocks normal startup. |
| JSON | `POST /api/support/assist` prepares the turn, runs readable shortcuts or `run_support_orchestration()`, then finalizes once. | Applicable property/RAG turns call compiled `build_ai_support_answer()`. |
| NDJSON | `POST /api/support/assist/stream` prepares the same turn and consumes orchestration events. | Applicable property/RAG turns call compiled `stream_ai_support_answer_events()`. Property text is buffered until finalization. |
| Opt-out | `prefer_qwen_response=False` calls `run_conversation_pipeline()`. | The readable Haystack reconstruction invokes a support handler backed by compiled `build_ai_support_answer()`. |
| Cache invalidation | Both assist endpoints, content changes, and refresh paths clear answer cache. | `clear_assist_response_cache()` is compiled. |
| Finalization | Clarification, live-data enforcement, capability sanitization, localization, trace publication, and RAG evaluation. | Source-visible. The router intentionally does not use the compiled blob localizer. |

### 3.2 Public response invariants

The final JSON object and the terminal NDJSON `done.response` preserve the same core fields where applicable:

- `answer`, `route`, `agent_mode`, `retrieval_mode`, `source_label`, `source_status`;
- `used_llm`, `confidence_label`, `handoff_recommended`;
- `matched_chunks`, `articles`, `knowledge_documents`;
- sanitized `data_api_calls` and `rag_evaluation`;
- language metadata and additive quick-reply, clarification, discovery, or unsupported-capability fields.

Server-only pending-selection markers are persisted but removed before public serialization. Property streaming may emit progress/route events internally, but customer-visible property answer text is buffered until clarification, live-data enforcement, localization, and evaluation finish. A successful stream has exactly one terminal `done` response. The synthetic answer-engine stream emitted `delta` then `done`; route-level endpoint tests cover public event shaping and error fallback.

The finalization order is a contract:

1. property clarification;
2. CS API/live-source enforcement;
3. terminal action/next-step policy;
4. capability sanitization for LLM output;
5. localization with protected facts;
6. sanitized trace and RAG evaluation;
7. conversation persistence/public serialization.

## 4. Differential mismatch classification

The verifier now uses a fixed selection seed and reports family counts. The reported 48 and observed 49 from earlier runs were sampling artifacts in `validate_support_node`; the stable Stage 0 baseline is 40.

### 4.1 Property term boundary routing: 3

| Cases | Difference | Classification and impact | Evidence |
| --- | --- | --- | --- |
| `show me the wings` | Bytecode: property; source: non-property. | **Possible regression.** Source uses whole-word matching but the term set contains `wing`, not `wings`. The primary turn analyzer is expected to recognize wings; its heuristic fallback calls this function, so an LLM-analysis failure may misroute this phrase. Resolve before fallback deletion. | `graph/haystack_conversation_pipeline_source.py`; `services/turn_analysis_service.py`; no direct plural-wings regression test. |
| Two deterministic fuzz strings containing embedded property substrings | Bytecode: property; source: non-property. | **Intentional source evolution.** Whole-word matching prevents unrelated words such as `united` from matching `unit`. No customer-facing regression is indicated. | `tests/test_company_context_matching.py` covers the boundary behavior. |

### 4.2 All explicit projects required: 4

All four cases use `compare Skyline Residency and Green Valley` with an answer mentioning only one requested project. Bytecode accepts the partial comparison; source returns `requested project`.

Classification: **intentional source evolution**. The current validator resolves every explicitly named project and requires all of them in a comparison answer, including suffix-aware matching. Customer impact is positive: incomplete or cross-project answers are rejected instead of presented as full comparisons. Covered by `tests/test_project_home_type_followups.py`.

### 4.3 Property-scoped pricing guard: 6

All six cases use the bare phrase `how much is this` with non-price or echoed answers. Bytecode always treats it as a property price request; source adds the `pricing` failure only when property context is present.

Classification: **intentional source evolution with a coverage gap**. This prevents a general cost question from being forced into property clarification. Current context resolution should establish property scope for real property follow-ups, but direct opt-out-path coverage for a bare contextual phrase should be added before changing that path. The source rule is covered by `tests/test_pricing_validation_guard.py`.

### 4.4 Safe relevance fallback copy: 27

All 27 cases have identical routing, status, confidence, and `used_llm=False`; only the answer text differs. Bytecode exposes internal validator constraints and asks which detail to relax. Source gives a generic unavailable/retry/callback response.

Classification: **intentional source evolution**. The readable copy avoids exposing internal validation mechanics or implying that unsupported constraints may be relaxed. `tests/test_haystack_conversation_pipeline.py::test_irrelevant_best_option_answer_is_rejected` explicitly requires the new behavior and rejects the old phrase.

### 4.5 Unresolved mismatch decision

No mismatch remains unclassified. One behavior remains unresolved: whether `show me the wings` must be restored as a property heuristic in the readable pipeline. The current product/property vocabulary strongly suggests yes, but Stage 0 does not change business logic.

## 5. Compiled runtime dependency map

### 5.1 Reachability classes

| Class | Evidence | Result |
| --- | --- | --- |
| Confirmed production entry | Source imports/call sites | `build_ai_support_answer`, `stream_ai_support_answer_events`, and `clear_assist_response_cache` are actively called. `answer_matches_response_language` and `localize_ai_answer` are imported; route finalization deliberately uses readable localization instead. |
| Synthetic observed | Instrumented sanitized JSON/cache/stream scenario | 71 runtime-defined top-level functions executed, spanning retrieval assembly, direct-answer selection, context/prompt construction, LLM facade calls, cache, confidence/handoff, localization helpers, and response assembly. |
| Static potential | Recursive `co_names` closure from five production entry points | 146 of 152 top-level functions are conservatively connected. This over-approximates reachability and includes mutually exclusive branches. |
| Outside conservative closure | Direct-name analysis only | Six: `add_butler_politeness`, `create_butler_english_response`, `create_mixed_language_response`, `create_telugu_english_response`, `get_language_greeting`, `normalize_llm_response_content`. They are **not verified unreachable**. |

### 5.2 Responsibility map

| Responsibility | Reachability conclusion | Migration evidence needed |
| --- | --- | --- |
| Startup/module assembly | Confirmed active | Source-only import/startup test after a future seam exists. |
| JSON answer generation | Confirmed active | Fixture comparison through final public payload. |
| Streaming generation | Confirmed active | Shared-decision and exactly-one-terminal-result tests. |
| Opt-out route | Confirmed active API branch | Product decision or preserved parity. |
| Retrieval/RAG assembly | Observed and static-potential | Deterministic workspace/company fixtures plus live acceptance. |
| Deterministic builders | Observed subset; broad static potential | Scenario-by-scenario handler coverage. |
| Prompts/Sarvam invocation | Observed with stub; live unverified | Live Sarvam acceptance without customer data. |
| Cache | Confirmed/observed | Scope, expiry, concurrency, invalidation, and PII tests. |
| Confidence/handoff | Observed/static-potential | Policy matrix and action-semantics tests. |
| Localization | Legacy helpers observed; public finalizer is readable | Protected-fact multilingual parity. |
| Failure/fallback | Observed subset/static-potential | CS API, LLM, sparse retrieval, and stream-error matrix. |
| Local product/catalogue logic | Some predicates/builders observed; most statically connected | Product ownership decision and targeted reachability. Do not silently omit. |

## 6. Supported-behavior ledger

Risk is migration risk, not current defect severity.

| Behavior | Owner and dependency | Scenarios and observable contract | Grounding/state/security | Existing evidence | Missing evidence | Risk / confidence |
| --- | --- | --- | --- | --- | --- | --- |
| General conversation | `turn_analysis_service`, `main_orchestrator`; source routing plus compiled fallback/generation | Greeting, thanks, capability, small talk; general route and safe answer | No property facts; retain language intent | `test_haystack_conversation_pipeline.py`, `test_free_chat_language.py`, `test_general_local_llm.py` | Live Sarvam and broader prose sampling | Medium / high |
| Project discovery | `discovery_slot_service`, `routers/assist`; source-visible | Locality -> budget -> shortlist; wildcard/reset/correction; flag-off bypass | Live locality/city only; catalogue is not checked inventory; server marker retains intent | Discovery service/flow/slot/live-fix/review-fix suites, both endpoints | Live endpoint parity remains environment-dependent | High / high |
| BHK/configuration | `project_home_type_service`, router shortcuts; source-visible, compiled fallback for uncovered turns | Single/multiple BHK, project comparison, short follow-up | Live project/home-type records; all explicit projects preserved | `test_project_home_type_followups.py`, `test_property_question_variants.py` | Replacement-engine handler trace | High / high |
| Project/locality/wing/floor/flat/home-type clarification | `property_clarification_service`; source-visible mandatory finalizer | Ambiguous, missing, suffix match, short selection, repeated API failure | Fetch real options; never invent or silently choose; preserve original question/scope/options/retry | Clarification, locality, ambiguous-project, pending lookup, project-field tests; endpoint coverage | Add plural `wings` heuristic regression | Very high / high |
| Multi-turn context | `conversation_store_service`, `prepare_turn`, selection markers; source-visible plus compiled contextual query | Pronouns, short selections, restored state, explicit new question | Server-only markers; bounded history/session; no intent derived from translated prose | Clarification/discovery/history/failed-new-intent suites | Sanitized corpus comparison and concurrent sessions | Very high / medium-high |
| Inventory/availability | Router/property services plus compiled property fallback | Available/unavailable, wing/floor/flat scope | CS API is authority; catalogue does not prove inventory | Property tools, unsupported capability, grounded-failure, question-variant tests | Live partial-failure matrix | Very high / high |
| Pricing/estimates | Source shortcuts/final guards plus compiled fallback | Price/base-cost estimate, inclusions/exclusions, ambiguous scope | Live facts only; label estimate and exclusions; safe failure | Pricing guard, contextual flat cost, unsupported-capability endpoint tests | Bare contextual opt-out case | Very high / high |
| Amenities/construction | Amenity/home/property services; source-visible shortcuts, compiled fallback | Project amenities, general catalogue, reverse amenity search, construction status | Live or approved workspace source; preserve project scope | Amenity catalogue/regression/shortlist/reverse search/project amenity tests | Live construction-update sample | High / high |
| Workspace knowledge/RAG | `knowledge_index_service`, company retrieval, compiled assembly | Documents, policies, direct/verbatim source, sparse retrieval | Do not expose raw unsafe content; retain source metadata and prompt-injection controls | Knowledge-index and thin-retrieval/RAG evaluation tests | Full prompt/context equivalence and live generation | Very high / medium |
| Multilingual input/output | `turn_analysis_service`, `reply_language`, readable final localization; compiled generation helpers | English, native script, romanized input; protected names/numbers | Preserve facts, scripts, names, amounts, layouts | Free-chat language, localization/property follow-up tests | Live Sarvam language set; romanized quality sampling | High / medium-high |
| Tickets/callback/human contact/site visit | `workflow`, router/action services; source-visible routing plus answer hints | Create/request/continue/cancel; avoid duplicate side effects | Confirm only completed local workflow; never claim CRM booking | Call booking, callback expansion, human contact, site visit and terminal-next-step tests | External CRM/booking integration is not implemented/live | Very high / high for local contract |
| Feature flags | Discovery and request configuration; source-visible | `ACROBUILD_DISCOVERY_SLOTS=false` bypasses discovery; answer preference branch preserved | Read flags at documented boundary; no implicit enablement | Discovery slot/flow tests | Deployment configuration audit | High / high |
| CS API failure/snapshot | Property tools and `_enforce_live_property_data`; source-visible | Success, partial/total failure, disclosed snapshot, unverified | Never invent facts; sanitize trace errors; recommend handoff as defined | Property tools, snapshot, public trace, grounded shortcut failure tests | Current live failure/latency run | Very high / high |
| LLM failure | Qwen/Sarvam facade plus compiled engine and readable finalizers | Timeout/error/empty/echo/invalid response | Safe deterministic fallback; no unsupported confirmation | Pipeline validation, unsupported and general LLM tests | Live outage behavior and exact streaming failure timing | High / medium |
| JSON delivery | `routers/assist.py`; source-visible wrapper, compiled core on applicable turns | One finalized object with additive fields | Auth/rate/session boundaries unchanged | Broad endpoint suite | Formal schema snapshot/versioning | High / high |
| NDJSON delivery | `routers/assist.py`; source-visible wrapper, compiled stream core | Progress/delta and exactly one terminal response; property text buffered | No unvalidated property delta or duplicate action | Discovery, amenities, home-type, unsupported, trace endpoint tests | Concurrency/disconnect/backpressure characterization | Very high / medium-high |
| Cache | Compiled answer engine; readable invalidation call sites | Hit/miss/clear; response equivalence | Must isolate customer/conversation/data scope; bounded TTL; no PII logging | Synthetic timing and existing cache-related suite coverage | Dedicated key/isolation/expiry/concurrency contract tests | Very high / medium-low |

### 6.1 Product status boundaries

- **Implemented:** current local chat, discovery, clarification, property-tool grounding, workspace retrieval, multilingual finalization, local ticket/callback/human-contact/site-visit request flows, and both delivery endpoints, subject to external availability.
- **Partial:** CRM/confirmed external booking semantics; live-generation language quality; cache contract documentation; legacy opt-out behavior as a long-term product commitment.
- **Missing or unresolved:** product approval to omit inherited food/local-product catalogue behavior; formal decision on `prefer_qwen_response=False`; representative approved conversation corpus.
- **Blocked/unverified:** live Sarvam acceptance, production traffic latency, and full live CS API failure/latency benchmarking in this Stage 0 run.

## 7. Regression and comparison matrix

| Scenario family | Normal cases | Edge/failure cases | Current protection | Stage 3-5 comparison target |
| --- | --- | --- | --- | --- |
| Routing | General/property/action/knowledge | Analysis failure, ambiguous short text, plural `wings` | Pipeline and turn-analysis tests | Route, handler, state markers |
| Discovery | Locality, budget, shortlist | Unknown place, any area, reset, flag off, API failure | Discovery suites on both endpoints | Options, prompt state, zero extra live reads |
| Clarification | Every supported entity | Multiple matches, suffixes, empty catalogue, repeated failures | Mandatory contract suites | Original question, scope, options, retry query |
| Property facts | Inventory, price, amenities, construction | Snapshot, unavailable, partial/total failure | Tool/guard/endpoint tests | Facts, source status, trace, no invention |
| Context | Pronoun and short selection | Refresh/restore, new intent replaces pending | Conversation/clarification tests | Server marker and final intent |
| Knowledge/RAG | Direct and generated answer | Sparse retrieval, echo, unsafe/irrelevant answer | Retrieval/validation tests | Evidence selection, `used_llm`, confidence/handoff |
| Language | English/native/romanized | Translation echo, changed number/name/layout | Language/localization tests | Protected facts and requested script |
| Actions | Ticket/callback/site visit request | Cancellation, malformed data, retries | Workflow/action suites | No duplicate side effect; honest confirmation |
| Delivery | JSON and NDJSON | Stream exception/disconnect/fallback | Cross-endpoint tests | Same terminal payload decisions |
| Cache | Miss, hit, clear | Scope collision, expiry, concurrency | Synthetic baseline only | Exact key policy and isolation tests |

The characterization script uses only sanitized synthetic fixtures. It does not write evidence, call external services, or trigger actions.

## 8. Performance and cache baseline

Five local runs on this checkout, CPython environment, with stubbed retrieval and LLM:

| Measure | Result |
| --- | ---: |
| Cold import median | 1,428.556 ms |
| Cold import samples | 1,542.226; 1,387.612; 1,428.556; 1,457.814; 1,409.134 ms |
| Cold import peak allocation median (`tracemalloc`) | 21.634 MiB |
| Cache miss median | 10.228 ms |
| Cache miss samples | 234.721; 12.965; 10.228; 9.786; 8.857 ms |
| Cache hit median | 0.541 ms |
| Cache hit samples | 0.716; 0.542; 0.541; 0.447; 0.433 ms |
| Synthetic stream first event/delta | 9.316 ms |
| Synthetic stream terminal `done` | 9.774 ms |

The first miss includes process/service warm-up and is retained rather than hidden. These numbers measure local runtime overhead only. They are **not** live CS API, Sarvam, browser, production, throughput, or end-to-end latency evidence. Network retrieval/generation timing, production p50/p95, first-token latency from Sarvam, concurrent cache behavior, and steady-state memory remain unverified.

## 9. Migration blockers and decisions

| Item | Type | Required resolution |
| --- | --- | --- |
| Plural `wings` heuristic difference | Possible regression | Add/approve expected routing behavior before retiring the fallback. |
| `prefer_qwen_response=False` | Product/API decision | Preserve until ownership explicitly removes or redefines it. |
| Local-product/catalogue helpers | Product and reachability uncertainty | Decide whether any behavior is supported; add targeted traces before omission. |
| Broad 146-function static closure | Technical uncertainty | Use per-handler characterization; static reachability is not a porting checklist by itself. |
| Six functions outside closure | Evidence limitation | Do not call dead until dynamic/import references and representative traffic are checked. |
| No approved sanitized production corpus | Coverage limitation | Obtain representative sanitized turns before replacement comparison. |
| Cache key/isolation semantics | Security/contract gap | Add dedicated customer/conversation/source/expiry/concurrency tests before moving cache ownership. |
| Live Sarvam not exercised | External verification gap | Run approved live acceptance before cutover, without recording secrets/customer data. |
| Current live CS API performance/failure matrix not run | External verification gap | Run isolated live acceptance before deletion gates. |
| `docs/AI_CONTEXT.md` absent | Documentation gap | Restore an approved current map or remove the stale instruction; do not invent it. |

## 10. Stage 0 verification

### Diagnostic and targeted results

- Deterministic differential: **expected non-zero exit; 40/13,077 classified differences**, identical on repeated runs.
- Characterization: **passed**, five iterations; 152 functions inventoried, 146 conservative-static, 71 synthetic-observed; stream shape `delta`, `done`.
- Targeted characterization/routing/property tests: **100 passed, 6 subtests passed, 1 deprecation warning**.
- Full backend suite in the network sandbox: **1,906 passed, 182 subtests passed, 1 setup error**. The error was `WinError 10013` when the configured CS API test attempted a network connection; it was an environment restriction, not a test assertion failure.
- The single blocked CS API-backed test rerun outside the network sandbox: **1 passed, 4 subtests passed, 1 deprecation warning**. This is live CS API evidence for that test only.
- Ruff on all Stage 0 Python changes: **passed**.

### Evidence boundaries

- Differential and static analysis: local source/bytecode evidence.
- Characterization and most regression coverage: mocked/synthetic, not live.
- Live Sarvam, frontend build/browser acceptance, production load, and live external-action integration: not run and not claimed.

## 11. Acceptance and Stage 1 readiness

| Stage 0 criterion | Status |
| --- | --- |
| Mismatches reproduced and classified | Met: stable 40; earlier 48/49 explained as nondeterministic sampling |
| Unresolved differences documented | Met: plural `wings` candidate regression |
| Active/uncertain bytecode mapped | Met, with explicit evidence limits |
| Supported-behavior ledger available | Met: this document |
| JSON/stream characterized | Met through current source/tests and sanitized synthetic engine scenario |
| Regression scenarios established | Met; remaining gaps listed |
| Performance/cache baseline | Partially met: local synthetic measured; live/production unverified |
| Technical/product blockers identified | Met |
| Application behavior unchanged | Met: only diagnostics, tests, and documentation changed |

**Stage 0 status: complete.**

**Stage 1 status: conditionally ready, not authorized.** Approval should explicitly accept the 40-difference readable-source baseline and resolve the plural `wings` case. The opt-out branch must remain intact unless separately changed by product decision. Stage 1 must not infer that the AI runtime, catalogue helpers, Haystack framework, or later migration work is authorized.

## STOP

No runtime file, loader, Haystack integration, business rule, prompt, public API, dependency, or feature flag was changed. Do not begin Stage 1 without explicit authorization.
