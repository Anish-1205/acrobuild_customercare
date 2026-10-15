# Runtime Dependency Elimination and Developer Maintainability Feasibility Study

Date: 9 October 2026; focused Stage 5 continuation updated 12 October 2026  
Status: planning baseline; Stages 1 through 4 are complete and Stage 5 remains partial under separate authorizations; Stage 6 is not authorized

## 1. Executive summary

AcroBuild can realistically remove all three source-less application runtime files and, separately, the Haystack framework. A full translation of every historical bytecode function is neither necessary nor the safest route. The recommended solution is a staged hybrid migration: retire the already-obsolete Haystack bytecode fallback, replace the active answer-engine orchestration with readable Python around existing source-visible services, reconstruct only verified business rules that are still reachable, and delete the original and patched answer-engine runtimes only after route, failure, and live-integration gates pass.

Implementation update: Stage 1 imported the readable conversation pipeline normally, fixed the verified plural `wings` routing regression, and removed `graph/haystack_conversation_pipeline_runtime.pyc`. Stage 2 replaced the one-component Haystack shell with a native Python adapter and removed the `haystack-ai` dependency. Stage 3 introduced a typed readable answer-engine boundary. Stage 4 completed an independent source-visible engine for cache, retrieval, dispatch, prompting/Sarvam generation, policy, and response assembly while leaving production on the compiled backend. It classified 57 historical retail-specific helpers as unrelated product residue, deliberately excludes that domain from the future readable engine, and preserves the real-estate project catalogue. Both answer-engine runtimes remain in place.

The production dependency remains material but is now lazy. Stage 4 removed the eager `services.ai_agent_service` import from normal application assembly and moved the remaining contextual property calculations into readable source. A clean `import app` therefore does not load the compiled service. The production-selected `LegacyCompiledAnswerEngine` still imports `services.ai_agent_service` when a property/RAG answer is requested; that module selects the patched runtime when present, unmarshals it, and executes it into module globals. Production answers therefore remain tied to matching CPython 3.12 bytecode until a separately authorized cutover.

The Haystack situation was different. Stage 1 removed the historical conversation `.pyc` fallback and made the readable source a normal import. Stage 2 then removed the framework decorators and `Pipeline`, replacing their single synchronous step with a small native Python adapter that retains the prior `.run()` input/output shape. The historical module and `conversation_haystack` response label remain as compatibility names; neither requires the Haystack package.

Fresh investigation found an important documentation discrepancy. The initial differential run reported 48 mismatches across 13,077 cases, while `docs/runtime/COMPILED_RUNTIME.md` still says the reconstruction historically had zero mismatches. Stage 0 subsequently found that answer selection was unseeded; the deterministic baseline is **40 mismatches across 13,077 cases**, classified in `docs/runtime/STAGE_0_BASELINE_AND_CONTRACT_LEDGER.md`. The active source has continued to evolve through source-visible fixes. The historical `.pyc` is consequently not a behaviorally equivalent rollback and should not be treated as the desired parity oracle.

The answer-engine runtime contains 152 top-level code objects and covers retrieval assembly, response caching, direct/deterministic answers, prompt construction, LLM calls, confidence and handoff decisions, localization, and both JSON and streaming response construction. However, the repository already provides readable implementations for the external CS API, workspace retrieval, Sarvam calls, routing, clarification, discovery, live-data enforcement, localization, conversation state, support actions, and many current property answer builders. The migration should rebuild the supported orchestration contract from these components, not reproduce dormant food/product-catalogue code or every obsolete bytecode branch.

Recommended feasibility: **high, with moderate-to-high engineering effort**. A realistic planning range is **8-13 engineer-weeks for implementation and verification**, plus **1-2 weeks of release observation/stabilization**, assuming one experienced backend engineer with review support and no newly discovered product contract hidden only in bytecode. A full function-for-function reconstruction would likely take **16-24+ engineer-weeks** and still provide a worse long-term architecture.

## 2. Current dependency map

### Startup and imports

| Layer | Current path | Compiled/Haystack dependency |
| --- | --- | --- |
| FastAPI assembly | `app.py` -> `api_context.py` | Uses the readable Stage 3 interface and lazy compatibility exports. Clean application import does not load `services.ai_agent_service`. |
| Answer-engine loader | `services/ai_agent_service.py` | The production-selected legacy adapter imports it on first use; it prefers `ai_agent_service_runtime.patched.pyc`, falls back to `ai_agent_service_runtime.pyc`, validates the header, unmarshals, and executes the module. Missing or incompatible runtime prevents legacy answer execution, not clean application import. |
| Answer-engine integration seam | `services/answer_engine_service.py` | Readable typed request, backend protocol, JSON/stream/cache entry points, and non-sensitive execution tracing. The active adapter delegates to the compiled loader. |
| Conversation routing | `graph/haystack_conversation_pipeline.py` | Imports readable source, installs the existing compatibility overrides, and rebuilds the native pipeline adapter. No conversation bytecode or Haystack framework dependency remains. |
| Historical Haystack compatibility names | `graph/haystack_conversation_pipeline.py`, `graph/haystack_conversation_pipeline_source.py` | Module names and the `conversation_haystack` response value remain for caller/schema compatibility only. `haystack-ai` is no longer declared or imported. |

The original investigation found three tracked application `.pyc` files. After authorized Stage 1 work, two answer-engine runtimes remain:

- `services/ai_agent_service_runtime.pyc` (329,488 bytes)
- `services/ai_agent_service_runtime.patched.pyc` (329,583 bytes)

Ordinary generated `__pycache__` files are not part of this finding.

### Provenance and documentation gaps

Git history first shows both original runtime files in commit `2b12d04374d3f66e19ed8e82dde066635c3ff9f8` dated 8 September 2026, authored as `cleanup <cleanup@local>` with subject `Snapshot before dead-code cleanup`. That establishes repository entry, not original authorship or pre-Git source provenance. No original readable answer-engine implementation was found in the inspected Git history.

The repository instructions also identify `docs/AI_CONTEXT.md` as a current architecture map, but that file is absent from this checkout. This investigation therefore used `docs/ARCHITECTURE.md`, `docs/CHAT_FLOW.md`, current source, tests, runtime documentation, and relevant Git history. The missing file should be resolved as documentation maintenance, not reconstructed from assumptions.

### Request-to-response execution

Both public endpoints share preparation and finalization but enter different answer-engine functions:

| Path | Active flow | Where bytecode executes |
| --- | --- | --- |
| JSON | `routers/assist.py:624` -> router shortcuts or `run_support_orchestration()` (`graph/main_orchestrator.py:989`) -> `build_ai_support_answer()` | Property/RAG turns that are not satisfied by a readable router shortcut enter the compiled answer engine. |
| NDJSON | `routers/assist.py:723` -> router shortcuts or `stream_support_orchestration_events()` (`graph/main_orchestrator.py:1060`) -> `stream_ai_support_answer_events()` | The property stream enters the compiled streaming engine. Property deltas are buffered until final grounding/localization. |
| Legacy opt-out mode | request `prefer_qwen_response=False` (`api_context.py:717`) -> `run_conversation_pipeline()` | The source-visible native conversation pipeline calls a support handler backed by compiled `build_ai_support_answer()`. Stage 2 did not remove the answer-engine bytecode dependency. |
| Shared completion | `routers/assist.py:572-620` | Readable clarification, live-data enforcement, capability sanitization, localization, and RAG evaluation run after the draft. |

The browser explicitly sends `prefer_qwen_response: true`; the API default is also true. The native compatibility pipeline therefore is not the normal current route, but its opt-out path remains an API-supported branch until deliberately retired or reimplemented.

### What the answer-engine bytecode owns

Marshalled-code inspection found 152 top-level code objects. The two active public entry points depend on runtime globals for:

- response cache keying, reads, writes, and clearing;
- contextual query construction;
- `search_workspace_knowledge()` and `search_company_knowledge()` orchestration;
- customer context and issue-type resolution;
- deterministic company, document, location, site-visit, workspace, small-talk, and fallback answers;
- the large direct company/property answer dispatcher;
- prompt/context section construction;
- LLM versus deterministic selection;
- confidence and handoff decisions;
- model answer validation and echo detection;
- non-streaming and streaming Sarvam calls;
- legacy localization helpers;
- final result-object assembly.

The original and patched runtimes have the same function inventory. Structural comparison found only the expected constant substitutions in `build_ai_support_answer` and `stream_ai_support_answer_events`: `0.35 -> 0.1` and `"gemini" -> "remote_llm"`. The patch script encodes exactly those four substitutions (`scripts/patch_runtime_constants.py:27-33`) and writes the patched binary (`scripts/patch_runtime_constants.py:91`).

### Haystack runtime versus Haystack framework

These are materially different removals:

1. Stage 1 removed `haystack_conversation_pipeline_runtime.pyc`; the application now imports the readable reconstruction normally.
2. Stage 2 removed `haystack-ai` and replaced the one-component execution wrapper with a normal Python class call while preserving routing and validation logic.
3. Neither removal eliminates `ai_agent_service_runtime*.pyc`; that requires the answer-engine migration.

## 3. Existing readable code

The end state can reuse substantial production code instead of rebuilding the chatbot from zero.

| Responsibility | Readable source available now | Reuse assessment |
| --- | --- | --- |
| HTTP contracts, auth, rate limits, session boundaries | `api_context.py`, `routers/assist.py`, security/session services | Reuse unchanged. |
| Shared JSON/stream turn preparation | `graph/main_orchestrator.py` | Reuse, while replacing its two compiled engine calls behind one interface. |
| Intent/language analysis | `services/turn_analysis_service.py`, `services/reply_language.py` | Reuse. |
| Conversation state and pending markers | `services/conversation_store_service.py` | Reuse; preserve 60-message/two-hour behavior and server-only markers. |
| Clarification | `services/property_clarification_service.py:285` | Mandatory reuse before validation/localization/persistence. |
| Discovery | `services/discovery_slot_service.py:56-57,651` | Reuse with `ACROBUILD_DISCOVERY_SLOTS` read per call and current locality -> budget -> shortlist contract. |
| Live property reads | `services/acrobuild_company_service.py:547-580`, `services/property_tools_service.py` | Reuse; these are the grounding authority. |
| Workspace retrieval | `services/knowledge_index_service.py:1466` | Reuse. |
| Company/property retrieval assembly | `services/acrobuild_company_service.py:580` | Reuse, but move orchestration ownership out of bytecode. |
| Sarvam generation | `qwen.py:108,144`, `sarvam_client.py` | Reuse for both non-streaming and streaming. |
| Live-data enforcement | `api_context.py:193`, called from `routers/assist.py:572-620` | Reuse; preserve failure and snapshot semantics. |
| Response localization and protected facts | `graph/main_orchestrator.py` | Reuse; the router deliberately does not use the blob-only localizer. |
| Property/home-type/amenity/discovery shortcuts | `services/project_home_type_service.py`, `services/amenity_search_service.py`, `services/discovery_slot_service.py`, `routers/assist.py` | Reuse; these already bypass large portions of legacy behavior. |
| Ticket, callback, human handoff, site-visit request workflows | `graph/workflow.py`, readable routes/services | Reuse and preserve local-request semantics. |
| Source-visible answer engine | `services/answer_engine_service.py`, `services/readable_answer_engine.py` | Stage 4 implements cache, retrieval, deterministic dispatch, prompts/Sarvam generation, confidence/handoff, and result/event assembly for isolated readable mode. Constructed scenario, mapped upstream, no-legacy, and live integration checks pass. Production still selects the compiled adapter pending a separately authorized Stage 5/cutover. |
| Native conversation routing | `graph/haystack_conversation_pipeline_source.py` plus compatibility facade | Stage 1 removed runtime `exec()`/bytecode fallback and Stage 2 removed the Haystack shell; retain current readable behavior. |

The compiled answer engine is not wholly avoidable today. Even though a historical 200-prompt proxy recorded zero calls to `_legacy_build_company_api_direct_answer`, every applicable property/RAG turn still entered compiled `build_ai_support_answer` or `stream_ai_support_answer_events` and used other compiled helpers. That historical measurement demonstrates that the largest legacy direct-answer function may be cold; it does **not** demonstrate source-code independence.

Static Stage 4 classification identified 57 food, beverage, Shopify, vendor-feed, and retail-catalogue helpers inherited from another domain. The approved product decision excludes this historical retail behavior from the future readable engine. Real-estate project catalogue, location, price, construction, configuration, and inventory behavior remains supported. Existing legacy local-product endpoints/files were not deleted or rerouted because that cleanup is outside Stage 4.

## 4. Available solutions

### Option A - retire obsolete compiled fallbacks

Remove the Haystack `.pyc` fallback after the active source contract is characterized. This is low effort and improves honesty, but it leaves the principal answer-engine dependency untouched. The original answer runtime cannot be retired safely while the patched runtime remains generated from it and acts as fallback input.

### Option B - incremental replacement

Introduce a source-visible answer-engine interface, move orchestration stages from bytecode to source one at a time, and keep a reversible legacy adapter during comparison. This supports small reviewable changes and precise rollback. On its own, it risks a long-lived dual system unless each stage has an explicit retirement gate.

### Option C - reconstruct required legacy behavior

Use bytecode disassembly and differential harnesses for small, verified business rules that are reachable and have no source equivalent. This is appropriate as a surgical tool. It is unsuitable as the primary strategy: prior investigation found Python 3.12 closures/comprehensions difficult to decompile reliably, and a function-for-function result would preserve obsolete architecture and domain residue.

### Option D - rebuild the answer engine from existing components

Implement the currently supported retrieval -> deterministic answer or prompt -> generation -> confidence/handoff -> response contract in readable Python using existing services. This provides the best developer experience and removes unused historical behavior, but it needs strong characterization tests because bytecode may contain undocumented branches.

### Option E - eliminate Haystack

Replace the single-component Haystack pipeline with direct readable orchestration and remove `haystack-ai` after dependency verification. This is highly feasible and independent of the larger answer-engine replacement. It should not be marketed as full runtime independence.

### Option F - hybrid migration (recommended)

Combine A, B, C, D, and E in that order where useful: establish the active contract; retire the misleading Haystack binary fallback; remove the thin Haystack framework wrapper; build a readable answer engine incrementally from existing services; reconstruct only missing reachable rules; shadow/differential test; then remove both answer-engine binaries and patch machinery.

## 5. Feasibility comparison

| Option | Feasibility | Effort | Regression risk | Behavior preservation | Maintainability | Rollback |
| --- | --- | --- | --- | --- | --- | --- |
| A. Retire obsolete fallbacks only | Completed for conversation routing | Completed in Stage 1 | Low for the removed Haystack `.pyc`; not applicable to answer runtime | Preserves active source behavior; 39 post-fix differences were adjudicated | Small improvement | Restore from tagged release |
| B. Incremental replacement | High | 6-10 weeks as the main migration mechanism | Medium, controlled by stages | Strong when each seam is characterized | High if dual mode has a deadline | Per-stage legacy adapter |
| C. Full reconstruction | Feasible but high risk | 16-24+ weeks | High; opaque semantics and decompiler limitations | Highest theoretical legacy parity, but old behavior is not necessarily correct/current | Medium; recreates a 10k-line monolith | Straightforward until cutover |
| D. Rebuild supported engine | Feasible with moderate effort | 6-10 weeks | Medium-high without baseline; medium with staged comparison | Strong for verified supported behavior; intentionally excludes obsolete behavior | Very high | Adapter/feature-controlled cutover |
| E. Remove Haystack framework | **Completed in Stage 2** | Completed | Low | Preserved through the native compatibility adapter | Framework dependency removed | Restore the prior source wrapper and dependency from a release tag |
| F. Hybrid | **High; recommended** | **8-13 engineer-weeks plus stabilization** | **Medium, decreasing at each gate** | **Best balance: current contracts over obsolete bytecode parity** | **Very high** | Stage and release rollback |

Performance should improve slightly or remain neutral: removing dynamic `exec`, a general framework wrapper, and duplicate legacy localization/cache work reduces startup and per-turn overhead. That conclusion must be benchmarked; live CS API and LLM latency dominate normal turns.

Security should improve because source-less code executed at import time is difficult to review, scan, or attest. Migration risks include weakening prompt-injection controls, exposing raw retrieved content, changing cache/customer scoping, or bypassing live-data enforcement. Those are acceptance targets, not reasons to retain opaque code.

## 6. Developer experience comparison

| Criterion | Keep/patch binaries | Full reconstruction | Readable supported-engine rebuild | Recommended hybrid end state |
| --- | --- | --- | --- | --- |
| Find response owner | Poor; names exist but core bodies are opaque | Better, but one very large legacy module | Good, responsibilities can follow current service boundaries | Excellent after old adapter removal |
| Change routing/prompts/rules | Often requires wrappers or constant patching | Directly editable but tightly coupled | Directly editable in focused modules | Direct and source-visible |
| Debug actual execution | Cannot set useful breakpoints inside runtime | Possible but difficult in monolith | Normal debugger and intermediate state inspection | Normal debugger end to end |
| Unit-test components | Limited to public wrappers/differential behavior | Possible, with large surface | Strong, using injected retrieval/generation dependencies | Strong plus contract/integration tests |
| Extend safely | Adds more wrapper layers | Risks extending inherited architecture | Adds handlers/policies through explicit interfaces | Clear extension points without binary knowledge |
| Onboard developers | Requires runtime history and reverse engineering | Requires learning a reconstructed 10k-line module | Follows current architecture map | Best; one traceable request path |
| Python upgrades | Blocked at runtime header | Unblocked after cutover | Unblocked after cutover | Determined by maintained dependencies only |

The largest maintainability gain is not deleting three files; it is making the decision trail visible: which retrievers ran, which deterministic handler matched, whether the LLM was called, what evidence grounded the answer, why a handoff was recommended, and which finalizer replaced or localized the draft.

## 7. Recommended solution

Adopt Option F: a hybrid, incremental rebuild of only the verified supported answer engine.

The governing rules should be:

1. The active readable behavior and supported product contract are the target, not blind parity with old bytecode.
2. Keep endpoint schemas, security, conversation markers, feature flags, grounding, clarification, safe failure, localization, and action confirmation semantics stable.
3. Reuse existing CS API, property tools, knowledge retrieval, Sarvam, and workflow services.
4. Extract a small readable orchestration kernel before moving individual policies.
5. Reconstruct bytecode logic only when a reachable supported case lacks an adequate source implementation.
6. Maintain one temporary legacy adapter for differential/rollback use; do not add new permanent wrappers around the runtime.
7. Delete runtime files only after objective removal gates, and use a tagged release/build artifact for rollback rather than retaining a hidden production fallback.

No new AI framework is required. Ordinary Python functions, typed request/result models, and dependency-injected retriever/generator interfaces are sufficient for this application.

## 8. Proposed migration roadmap

### Stage 0 - baseline and contract ledger (1-2 weeks)

Objective: define what must be preserved before changing execution.

Work:

- classify the deterministic Haystack differential mismatches as intentional active-source behavior, stale-bytecode behavior, or actual defect;
- inventory bytecode helper reachability through characterization instrumentation at the three active entry points;
- define response-schema invariants for JSON and NDJSON;
- build a scenario matrix for property, knowledge, actions, languages, failures, flags, and state transitions;
- record latency and cache behavior without storing secrets/customer data.

Acceptance: approved supported-behavior ledger; deterministic fixtures; current JSON/stream parity tests; no unresolved mismatch silently assigned to bytecode as truth.

Rollback: none needed; read-only/test additions only. **STOP** if a reachable branch represents a missing product decision.

### Stage 1 - make conversation routing source-native and remove the Haystack binary fallback (3-7 days)

Status: **completed on 9 October 2026 under separate authorization**. The readable module is normally imported, the plural `wings` regression is covered, the opt-out route remains supported, and the obsolete runtime was removed. See `docs/runtime/STAGE_1_SOURCE_NATIVE_ROUTING.md`.

Objective: remove `graph/haystack_conversation_pipeline_runtime.pyc` from runtime/recovery behavior.

Work:

- import the readable module normally instead of compile/`exec`;
- preserve the wrapper fixes or merge them into the readable implementation;
- make missing source a startup error during development rather than falling back to stale bytecode;
- update the stale runtime documentation and differential expectations;
- after a clean source-only verification, remove the historical `.pyc` from the active repository/runtime package (retain history in Git/tag, not runtime).

Acceptance: met by Stage 1. Both routing modes pass source-only tests; startup succeeds without the file; the plural `wings` regression was fixed; 39 remaining deterministic differences are intentional source evolution.

Rollback: restore the prior source implementation from a release tag. Do not restore the `.pyc` as the normal fallback.

### Stage 2 - remove the Haystack framework shell (3-6 days; may follow Stage 1)

Status: **completed on 9 October 2026 under separate authorization**. The one-component framework shell is now a native Python adapter, `haystack-ai` is removed from application requirements, and an isolated clean installation/import proved the app starts with no `haystack` package. See `docs/runtime/STAGE_2_NATIVE_CONVERSATION_ROUTING.md`.

Objective: replace the one-component pipeline with direct Python orchestration.

Work: call the existing classify/select/conversation/support/validate sequence directly; remove decorators, singleton `Pipeline`, and the `haystack-ai` dependency after a repo-wide import check.

Acceptance: met by Stage 2. Route/output and reload/patch compatibility tests pass; no application import or dependency declaration requires Haystack; clean installation and application import succeed without it. This stage does not claim answer-engine independence.

Rollback: restore the prior source wrapper and dependency from a release tag.

### Stage 3 - introduce the readable answer-engine seam (1-2 weeks)

Status: **completed on 9 October 2026 under separate authorization**. JSON and streaming orchestration plus cache invalidation now use `services/answer_engine_service.py`; `LegacyCompiledAnswerEngine` remains the active provider. See `docs/runtime/STAGE_3_READABLE_ANSWER_ENGINE_INTERFACE.md`.

Objective: give JSON and streaming routes one source-visible contract while retaining the legacy adapter behind it.

Work:

- define typed input/result/event contracts matching current additive fields;
- route JSON, streaming, and invalidation through one readable backend protocol;
- add readable customer/conversation cache namespacing around the compiled base key;
- evaluate cache/retrieval ownership and defer the coupled implementation to Stage 4;
- preserve property buffering until live-data validation and localization finish;
- trace implementation, delivery, timing, terminal count, and returned metadata without logging private content.

Acceptance: met for the Stage 3 boundary. Compatibility signatures and patch points are preserved; synthetic direct/interface JSON and stream results match; cache email/history/request dimensions, copy isolation, TTL, and concurrent unique keys are characterized; endpoint regressions preserve terminal behavior. Cache ownership and retrieval assembly were not transferred because their effective behavior remains coupled to bytecode.

Rollback: select the legacy adapter at the seam. **STOP** if output or state contracts cannot be made identical without a product decision.

### Stage 4 - replace active deterministic and RAG/generation behavior (3-5 weeks)

Status: **completed on 9 October 2026 under separate authorization**. A readable backend owns the planned responsibility groups and passes constructed sanitized scenario coverage, mapped upstream contract suites, no-legacy JSON/stream execution, and live CS API/Sarvam checks. Historical retail catalogue behavior is deliberately excluded; the real-estate project catalogue remains supported. Production remains on the legacy backend. See `docs/runtime/STAGE_4_READABLE_ANSWER_ENGINE.md`.

Objective: move supported bytecode responsibilities into readable Python.

Recommended order:

1. confidence, handoff, and fallback policies;
2. workspace/company retrieval assembly and context sections;
3. direct source/document/company/contact behaviors;
4. property answer dispatch not already covered by router/property services;
5. prompt builders and Sarvam invocation;
6. response/cache assembly for JSON and streaming.

Use existing source-visible property builders first. Differentially reconstruct only a missing reachable rule. Do not port dormant food/product-feed helpers unless an approved current feature demonstrably depends on them.

Acceptance: all scenario families pass in readable mode; no supported scenario calls the legacy adapter; grounding and safe failure are unchanged; deterministic answers remain `used_llm=False`; action confirmations occur only after real local workflow success.

Current acceptance: met for the authorized Stage 4 scope. The constructed sanitized corpus covers engine-owned scenario families, upstream-owned contracts are mapped to their existing suites, legacy adapter traps remain clean, streaming emits one terminal result, and live CS API/Sarvam checks pass. No production-conversation corpus or performance/load benchmark is claimed; those remain Stage 5 inputs.

Rollback: per-handler fallback during development, then whole-engine adapter before release.

### Stage 5 - shadow/differential and live acceptance (1-2 weeks)

Status: **partial, continued on 12 October 2026 under separate authorization**. Eleven constructed offline differential cases, mocked JSON/NDJSON endpoint checks, concurrency and stream-closure tests, a synthetic benchmark, and read-only integration probes were completed. Scoped backend selection, CS API provenance, and unsupported generated price claims were corrected. The product owner approved grounded generation for `prefer_qwen_response=False` when deterministic handling is insufficient; the readable engine now implements this and the opt-out differential matches `used_llm` selection. A focused continuation reproduced and corrected synchronous stream cleanup after client disconnect. A further controlled socket check established that an in-flight synchronous provider call finishes before cleanup, while a synthetic stream configured for up to 16 MiB showed backpressure and concurrent request isolation. Approved production samples, real-provider interruption acceptance, release thresholds, current CS API-backed live acceptance, current browser acceptance, and a tested release rollback remain missing. See `docs/runtime/STAGE_5_DIFFERENTIAL_AND_CUTOVER_READINESS.md`. Production remains on the compiled backend.

Objective: demonstrate replacement safety under representative traffic and real dependencies.

Work: compare legacy and readable engines on identical sanitized fixtures, review expected differences, run both endpoints, test external failures, run approved CS API and Sarvam checks, and benchmark latency/cache behavior.

Acceptance: no unexplained contract/state/grounding differences; approved wording differences; live CS API and LLM checks pass or are explicitly blocked; error paths never invent property facts; observability can attribute every answer.

Rollback: release-level engine selection while observation continues. Do not expose duplicate external side effects; shadow mode must not create tickets, callbacks, or site visits.

### Stage 6 - final cutover and runtime deletion (3-5 days plus 1-2 weeks observation)

Objective: become genuinely independent of source-less application bytecode.

Work: remove imports of the legacy adapter; delete original and patched AI runtime files; delete patching and compatibility loader machinery; remove Python-3.12 restrictions that exist only for the blobs; verify the intended supported Python matrix against all remaining dependencies.

Acceptance: clean checkout starts and serves both endpoints with all three runtime files absent; no `marshal`/runtime `exec` loader remains; no normal, fallback, startup, or recovery path references the blobs; automated and live gates pass; rollback artifact/tag is tested.

The chatbot becomes genuinely runtime-independent only at the end of Stage 6, not when Haystack is removed.

## 9. Functional preservation strategy

Preserve contracts by ownership boundary rather than copying a monolith:

- `routers/assist.py` remains the HTTP/state coordinator for both endpoints.
- `prepare_turn()` remains the single turn analysis/context resolution step.
- router-level grounded property, discovery, home-type, amenity, and unsupported-capability handlers remain ahead of generative fallback.
- all project/locality/wing/floor/flat/home-type clarifications continue through `apply_clarification_contract()` before relevance checks, localization, and persistence.
- property data continues through the CS API/property-tool services; catalogue listings remain distinct from checked inventory.
- `ACROBUILD_DISCOVERY_SLOTS=false` continues to bypass discovery completely.
- `_enforce_live_property_data()` or a behaviorally equivalent readable successor remains authoritative for `live_api`, disclosed snapshot, failed, and unverified results.
- conversation markers remain server-only and preserve original request, scope, options, and retry query.
- action flows preserve the difference between a local request/ticket and an external CRM or confirmed booking.
- authentication, staff authorization, rate limits, CSRF, cookie scope, and customer OTP boundaries stay outside the migration.

Exact prose should be asserted only where it is contractual (clarification options, safe-failure statements, confirmations, disclaimers). Elsewhere tests should prefer semantic invariants so obsolete wording does not become accidental architecture.

## 10. Testing and verification strategy

### Baseline and differential testing

- Capture sanitized request, normalized turn analysis, retriever summaries, selected handler, final payload fields, and server-state markers.
- Compare legacy and replacement with identical deterministic service fixtures.
- Review differences against current contracts; do not automatically bless the binary.
- Add explicit dependency tests that fail if production imports tracked application `.pyc`, `marshal` loaders, or runtime `exec`.

### Required scenario matrix

- general and small talk; property/project overview; home types and BHK combinations;
- locality, project, wing, floor, flat, and home-type ambiguity plus short selections;
- discovery locality -> budget -> shortlist, wildcard/reset/correction, and flag-off behavior;
- inventory available/unavailable, price/base-cost estimates and exclusions, amenities, construction, documents, and workspace knowledge;
- multi-turn pronouns and current-project scope, refresh/restored state, explicit new question replacing pending state;
- English, native-script languages, and romanized languages with protected names/numbers;
- CS API success, partial failure, total failure, allowed snapshot, Sarvam failure, sparse retrieval, and unsupported capability;
- local ticket, callback/human-contact, and site-visit workflows without duplicate side effects;
- JSON/NDJSON final payload parity, buffered property text, terminal event semantics, and error shape;
- cache hit/miss/expiry/isolation and concurrent requests.

### Live verification

Run current approved CS API and LLM acceptance only after test-mode cutover is ready. Mocked tests are not live evidence. `GET /` or `/api/health` is not proof of either external integration. Avoid scripts that overwrite committed evidence during a read-only acceptance; use isolated output or explicit evidence-update approval.

### Safe-removal gates

Before deleting each runtime, prove:

| Artifact | Minimum deletion evidence |
| --- | --- |
| Haystack runtime `.pyc` | **Removed in Stage 1.** Source is a normal import; 39 post-fix differences were adjudicated; source-only startup and both routing modes pass; no active fallback/open reference remains. |
| Original AI runtime | Readable engine no longer imports either binary; patched runtime no longer needs regeneration; all supported deterministic/RAG/generation paths pass. Do not remove it merely while patched bytecode remains active. |
| Patched AI runtime | No startup, normal, fallback, streaming, cache, or recovery path calls it; clean source-only package passes full and live gates. |
| Loader/patch/compatibility machinery | Repo-wide dependency tripwire is clean; build/package manifests exclude blobs; Python compatibility tests pass without the header guard. |
| Haystack package | **Removed in Stage 2.** No application import or dependency declaration remains; source-native router parity and isolated clean install/startup passed. |

Latest checks during Stage 4:

- Initial `scripts/verify_pipeline_reconstruction.py` run: **FAIL - 48/13,077 mismatches**; Stage 0 identified unseeded sampling and established a repeatable **40/13,077** baseline.
- Stage 3 interface, cache, compatibility, and synthetic parity tests: **12 passed**.
- Stage 4 readable-engine and interface tests: **22 passed**; focused regressions: **310 passed, 6 subtests passed**; full backend: **1,936 passed, 182 subtests passed, 1 network-sandbox setup error**; the exact CS API-backed test passed outside the sandbox with 4 subtests.
- Broader routing/property/action regression set: **880 passed, 97 subtests passed**.
- Final readable-engine/interface/corpus/classification suite: **44 passed**.
- Final full backend suite in sandbox: **1,958 passed, 182 subtests passed, 1 setup error**, caused by `WinError 10013` reaching the configured CS API; the exact test passed outside the sandbox with **1 test and 4 subtests passed**.
- Final readable live CS API project-catalogue path, readable live Sarvam grounded-generation path, and direct sanitized Sarvam provider contract: **passed**.
- Stage 5 offline differential and endpoint/cancellation/concurrency checks: initially **7 passed**. The 12 October continuation resolved the opt-out generation decision and its readable behavior; focused Stage 4/5 checks passed **49 tests**.
- Stage 5 full backend suite: **1,965 passed, 182 subtests passed, 1 live-CS setup error in the network sandbox**. Two network-enabled reruns of that exact test timed out after 2.5 seconds and remain **BLOCKED**. A separate Stage 5 read-only live CS API/Sarvam probe passed with zero customer actions.
- Stage 5 synthetic benchmark, Ruff, compilation, clean import, runtime hashes, and `git diff --check`: **passed**; no production latency or rollback artifact was tested.
- Stage 5 continuation on 12 October: **49 focused tests passed; full backend run 1,976 passed, 182 subtests passed, 1 explicitly live test skipped under `CI=1`**. The exact live reverse-amenity setup and the separate CS API project-list probe timed out outside the sandbox; an independent synthetic Sarvam call passed. A loopback NDJSON socket probe passed normal completion but found no producer cleanup within two seconds after disconnect. Frontend build/type check, Ruff, compilation, clean import, and `git diff --check` passed. Browser acceptance and release rollback remain unverified.
- Focused Stage 5 blocker resolution on 12 October: the real-socket regression first reproduced missing upstream-generator and trace cleanup on disconnect, then passed after the route explicitly closed both. Targeted checks passed **6 tests**; the full backend suite with `CI=1` passed **1,977 tests and 182 subtests**, with the explicitly live CS API test skipped. No CS API timeout or confidence-policy code change was justified. See the Stage 5 report's section 10 for the exact remaining evidence limits.
- Final focused Stage 5 socket check on 12 October: **1 targeted test passed** for blocked synthetic provider cleanup after release, a 1 MiB completed stream, a paused stream configured for up to 16 MiB, disconnect, and concurrent isolation. No application code changed; real-provider interruption and production resource limits remain unverified. See the Stage 5 report's section 11.
- Ruff, compilation, clean imports without loading `services.ai_agent_service`, runtime-hash checks, and `git diff --check`: **passed**.
- The existing dirty Stage 0-2 working tree was preserved; no commit, reset, or broad staging was performed.

No full production conversation corpus, current browser acceptance, production performance/load benchmark, real-provider backpressure run, or external CRM/booking action was run or claimed. The 16 MiB loopback stream is synthetic evidence only.

## 11. Risks and unknowns

| Risk/unknown | Status | Mitigation or decision needed |
| --- | --- | --- |
| Undocumented reachable bytecode rules | Real | Characterization traces, scenario ledger, targeted disassembly/differential reconstruction. |
| 39 post-fix source/bytecode routing mismatches | Verified before Stage 1 removal | The plural `wings` regression was fixed; the remaining three families plus two boundary false-positive fixes are intentional source evolution. |
| Historical 0/200 legacy-direct-function result | Historical proxy only | Re-run non-mutating characterization on current code; do not infer that other bytecode is unused. |
| Historical food/product catalogue code | Classified and product-decided in Stage 4 | 57 retail-specific helpers are deliberately excluded from the future readable engine; protect real-estate catalogue behavior and leave legacy endpoint cleanup to separate authorization. |
| `docs/AI_CONTEXT.md` is referenced but missing | Verified current checkout | Restore or remove the stale instruction during an approved documentation stage; source remains authoritative. |
| Non-deterministic LLM wording | Real | Compare structured decisions/invariants, fixed-temperature test doubles, reviewed live samples. |
| Streaming/non-streaming drift | Real | Shared readable retrieval/policy core and terminal-payload parity tests. |
| Socket disconnect cleanup | Fixed for the synchronous NDJSON route on 12 October | Real loopback tests confirm upstream generator and trace cleanup. A controlled blocked provider continues until released, then closes without persisting; a bounded 16 MiB synthetic stream shows backpressure. Real-provider interruption and production load remain unverified. |
| Grounding/localization order drift | High impact | Keep clarification -> live-data guard -> localization -> evaluation order and protected-fact tests. |
| Cache isolation/PII | Readable mode implemented and characterized | The readable key covers all typed request fields; TTL, lock, deep-copy, customer/conversation/history isolation, and clearing are source-visible. Production storage remains compiled until cutover. |
| External CS API/LLM availability | Stage 5 read-only CS API and Sarvam probes passed; live reverse-amenity test setup timed out twice | Record each check separately. Availability is intermittent and must be retested for release. |
| Python upgrade compatibility | Blocked today by answer runtime | Test target Python only after blobs are out; remaining library compatibility may still constrain versions. |
| Performance regression | Unverified | Baseline p50/p95 retrieval, first-token, completion, memory, and cache behavior. |
| Product meaning of `prefer_qwen_response=False` | Resolved on 12 October: grounded Sarvam generation is permitted when deterministic handling is insufficient; readable mode now does so | Continue to verify representative conversations; the remaining opt-out differential is confidence policy (`medium` legacy, `high` readable). |

## 12. Estimated total effort

Assumptions: one senior Python engineer familiar with the project, normal code review support, existing CS API/Sarvam test access, no need to reproduce dormant product-feed features, and no major schema/API redesign.

| Workstream | Estimate |
| --- | ---: |
| Baseline, reachability, scenario/contract ledger | 1-2 weeks |
| Haystack `.pyc` and framework removal | 1-2 weeks total, partly parallel with baseline after mismatch decisions |
| Readable engine seam, cache, retrieval core | 1-2 weeks |
| Deterministic/RAG/prompt/generation replacement | 3-5 weeks |
| Differential, endpoint, failure, multilingual, live verification | 1-2 weeks |
| Cutover, packaging/Python checks, deletion | 0.5-1 week |
| **Total engineering** | **8-13 engineer-weeks** |
| Release observation/stabilization | **1-2 calendar weeks** |

Uncertainty is approximately +/-30%. The largest variables are reachable undocumented rules, availability of representative sanitized conversations, the required status of the opt-out route, and whether any legacy local-product-feed behavior is actually approved scope. Requiring complete function-for-function reconstruction would raise the estimate to roughly 16-24+ engineer-weeks.

## 13. Desired final architecture

The recommended end state is deliberately modest:

1. `routers/assist.py` owns HTTP, session restoration, endpoint parity, and final persistence.
2. `graph/main_orchestrator.py` or a small readable successor owns turn intent/language and selects general, action, grounded property, or knowledge/property engine paths.
3. A readable assist engine owns retrieval orchestration, deterministic-handler selection, prompt construction, generation, confidence/handoff, cache policy, and result/event assembly.
4. Existing property, clarification, discovery, knowledge, Sarvam, workflow, and security services remain the implementation boundaries.
5. JSON and NDJSON use the same retrieved evidence and policy decision; streaming is only a delivery adapter.
6. Every answer has observable provenance: route, selected handler, retrieval/source status, `used_llm`, confidence/handoff, and sanitized external call trace.
7. No application source is loaded from `.pyc`; no binary patching exists; no `exec()` is needed to compose application modules.
8. Python support follows maintained dependencies and tested deployment targets rather than legacy bytecode magic.

This does not require microservices, a new agent framework, or a large architectural rewrite.

## 14. Direct answers

1. **Can all three compiled runtime files be eliminated?** Yes. Stage 1 removed the Haystack runtime; both AI runtimes can be removed after the readable answer engine and removal gates are complete.
2. **Can Haystack itself be eliminated?** Yes; Stage 2 eliminated it. A native Python adapter now performs the prior single synchronous step. This remains separate from AI-runtime removal.
3. **How much of the existing AI answer engine can be reused or reconstructed?** Most external integrations, safety boundaries, state handling, and many current deterministic property behaviors are already readable and reusable. Reconstruct only reachable missing policies; Stage 0 did not establish a reliable percentage.
4. **Is a complete rewrite needed?** No. Replace the orchestration/policy core while retaining existing services and contracts.
5. **Is incremental migration safest?** Yes, provided dual mode is temporary and every stage has an explicit retirement gate.
6. **Can all currently supported behavior be preserved?** The verified supported contract can be preserved with high confidence through characterization, differential, endpoint, and live testing. Unknown bytecode behavior cannot honestly be guaranteed as supported until classified.
7. **Can developers eventually modify all core logic directly in Python?** Yes; that is the recommended final acceptance criterion.
8. **How much easier will debugging and feature work become?** Materially easier: normal imports, breakpoints in real implementations, explicit intermediate decisions, isolated unit tests, and no disassembly/patch regeneration. Exact productivity gains require post-migration measurement.
9. **Biggest technical risks?** Undocumented reachable rules, grounding/localization order, JSON/stream drift, state/cache isolation, non-deterministic LLM comparisons, and mistaken porting or removal of legacy behavior.
10. **Realistic engineering effort?** 8-13 engineer-weeks plus 1-2 weeks release observation under stated assumptions; 16-24+ weeks for full legacy reconstruction.
11. **Evidence required before removal?** No imports/fallbacks, source-only startup, dependency tripwire, full supported scenario suite, both endpoints, failure and multilingual cases, approved differentials, live CS API/Sarvam checks, performance/security review, and tested release rollback.
12. **Recommended next implementation stage after approval?** Complete Stage 5 evidence: production-sample differentials, controlled stream disconnect/backpressure, release thresholds, current CS API acceptance, and tested rollback. The opt-out decision and code correction are complete. Stage 6 is blocked pending those gates and separate authorization.

## 15. Final recommendation

- **Recommended approach:** retain the readable engine behind the Stage 3 seam, resolve the partial Stage 5 gates, then seek a separate Stage 6 cutover decision.
- **Feasibility:** high.
- **Estimated effort:** 8-13 engineer-weeks plus 1-2 weeks observation; +/-30% uncertainty.
- **Regression risk:** medium, manageable through staged adapters and objective gates; high for an all-at-once rewrite or blind full reconstruction.
- **Developer-maintainability benefit:** very high; complete readable execution, ordinary debugging/testing, simpler onboarding, and removal of the Python-bytecode constraint.
- **Main blocker:** no approved sanitized production conversation corpus, accepted real-provider interruption, approved performance/load thresholds, current CS API-backed and browser acceptance, or tested release rollback exists. Synthetic disconnect cleanup and bounded loopback backpressure checks pass.
- **Recommended next step:** complete the missing Stage 5 external and release acceptance evidence before requesting Stage 6 authorization.

## STOP

Stage 5 verification was separately authorized and remains partial. This report does not authorize Stage 6, production traffic shadowing, a backend switch, or deletion of either remaining runtime.
