# Runtime Migration Stage 4: Readable Answer Engine

Date: 9 October 2026  
Status: complete; production remains on the legacy compiled backend

## 1. Outcome

Stage 4 added `services/readable_answer_engine.py`, an independently executable
answer engine behind the Stage 3 protocol. It does not import or invoke the
compiled runtime. Its source-visible flow owns:

1. request-scoped cache keying, TTL, locking, deep-copy isolation, and clearing;
2. contextual-query preparation;
3. workspace and company retrieval through the existing readable services;
4. deterministic company-contact and structured project handlers;
5. deterministic workspace and safe clarification fallbacks;
6. handler dispatch and decision metadata;
7. grounding and action-safety prompts;
8. the existing Sarvam-compatible generation facade and model validation;
9. confidence and handoff policy;
10. JSON response and single-generation NDJSON event assembly.

The production-selected backend remains `LegacyCompiledAnswerEngine`. A scoped
`use_answer_engine()` hook permits isolated readable-mode verification without
changing deployment configuration or beginning a cutover.

## 2. Readable execution flow

```text
AnswerEngineRequest
  -> full-scope cache key
  -> contextual query
  -> workspace retrieval + CS API company/property retrieval
  -> discard macro chunks
  -> deterministic dispatch
       company contact / project details / project catalogue / workspace
     OR grounded Sarvam generation
     OR safe clarification/failure fallback
  -> confidence + handoff + provenance fields
  -> cache copy
  -> JSON response or delta + exactly one done event
```

Streaming calls the same decision exactly once and adapts the completed result
to delivery events. The router continues to buffer property text and remains
responsible for clarification, live-data enforcement, localization, protected
facts, persistence, and final public payload fields.

## 3. Reused services

- `services.knowledge_index_service.search_workspace_knowledge`
- `services.acrobuild_company_service.search_company_knowledge`
- `qwen.generate_qwen_chat_response` and the configured Sarvam model
- `services.support_article_service.get_support_base_url`
- the Stage 3 `AnswerEngineRequest`, backend protocol, trace wrapper, and
  conversation scope

No new AI framework or provider was added.

## 4. Cache and security contract

The readable key hashes every answer-affecting request field, including email,
customer name, conversation id, bounded recent history, issue metadata, hint,
limit, and response preferences. Cached values are deep-copied on write/read,
guarded by a lock, expire after 45 seconds, and are clearable through the Stage
3 interface.

Prompts state that retrieved content is data rather than instructions, require
evidence-only property facts, prohibit invented inventory/pricing/availability,
and distinguish a request from a completed ticket, callback, or site visit.
The Stage 3 trace still records decision metadata rather than question, prompt,
evidence, customer identity, or answer text.

## 5. Historical catalogue classification

Static inspection of all 152 top-level runtime code objects identified 57
retail-specific helpers. Their names and constants concern Shopify CSV rows,
`macros`/`soulara` feeds, vendors, menus, snacks, drinks, sides, extras, product
prices, publication state, and retail recommendations. The readable
`local_product_feed_service.py` independently confirms that domain through its
Shopify column names and Macros/Soulara CSV paths.

`scripts/stage4_catalogue_classification.py` emits the exhaustive list:

| Classification | Evidence | Stage 4 decision |
| --- | --- | --- |
| 57 retail-specific helpers | Code-object names, retail-only constants, Shopify schema | Intentionally excluded from the future readable answer engine. |
| 12 retail helpers observed in Stage 0 | A synthetic property run reached selection/predicate/context checks but selected no retail response | Incidental legacy dispatch work is not product scope. |
| Real-estate project catalogue/location/floor/inventory/construction/price helpers | Current services, routes, tests, and disjoint runtime names | Preserved. |
| Generic normalization/deduplication/scoring/cache/confidence concepts | Legitimate cross-domain behavior | Reimplemented as small readable utilities, not imported from retail helpers. |
| Existing local-product endpoints/files | Still present in production source | Not deleted or rerouted; cleanup requires separate authorization. |

Readable mode handles clear food/retail/vendor-feed requests as an explicit
unsupported capability without retrieval or generation. A bare `product`,
`vendor`, property shop, availability, price, or catalogue term is insufficient
to trigger this boundary, protecting real-estate behavior.

## 6. Representative coverage

`tests/fixtures/stage4_readable_scenarios.json` is explicitly labelled
`constructed_sanitized_scenarios`; it contains synthetic names and is not
production-conversation evidence. It covers project catalogue/detail, BHK and
pricing, inventory, construction, workspace knowledge, multilingual input
before finalization, contextual follow-up, retail exclusion, JSON, streaming,
and `prefer_qwen_response=False`.

The manifest maps upstream-owned discovery/feature flags, clarification,
home-type selection, amenities, multilingual finalization, actions, grounding,
snapshot, and failure contracts to their readable services and existing tests.
No actual production conversation transcript was added or claimed.

## 7. Legacy independence evidence

Tests replace both legacy adapter entry points with failures, then execute the
readable engine and full JSON/stream orchestration in both preference modes.
The contextual flat/floor calculation moved to
`services/contextual_property_answer_service.py`, and unused API compatibility
localizers became lazy exports. Therefore clean-process `import app` and
readable-mode execution do not import `services.ai_agent_service`, its cache, or
its helper functions.

## 8. Known differences and boundaries

- Historical food/vendor/local-product behavior is intentionally unsupported in
  the future readable engine. Production preserves it until a separately
  authorized cutover/cleanup.
- Readable streaming emits a completed answer as one delta and one `done` event.
  It shares one decision and preserves property buffering; live first-token,
  cancellation, backpressure, and load behavior belong to Stage 5.
- Direct deterministic behavior remains structured. Other supported engine
  questions use grounded generation or safe fallback; upstream discovery,
  clarification, localization, and action contracts remain with their services.
- No actual sanitized production conversation corpus or production performance
  sample was available. The committed corpus is constructed and sanitized.
- `prefer_qwen_response=False` remains supported and avoids forced generation.

## 9. Verification

Stage 4 verification results:

- readable engine plus Stage 3 interface: **22 passed**;
- focused regressions: **310 passed, 6 subtests passed**;
- full backend suite: **1,936 passed, 182 subtests passed, 1 sandbox-network
  setup error**; the exact CS API test then passed outside the sandbox with 4
  subtests;
- final readable-engine/interface/corpus/classification suite: **44 passed**;
- final full backend suite: **1,958 passed, 182 subtests passed, 1 sandbox-network
  setup error**; the exact CS API-backed test then passed outside the sandbox
  with **1 test and 4 subtests passed**;
- Ruff, compilation, clean imports, runtime hashes, and `git diff --check`:
  **passed**.

Continuation live checks used synthetic/no-customer input and caused no actions:

- readable live CS API project-catalogue path: **passed**;
- readable live Sarvam grounded-generation path: **passed**;
- direct sanitized Sarvam provider contract: **passed**.

No production conversation corpus, browser run, performance/load benchmark,
stream backpressure run, or external CRM/booking action was run or claimed.

## 10. Status and next gate

Stage 4 is **complete** for the approved source-migration scope. Supported
answer-engine responsibility groups have readable owners; the constructed
corpus and upstream suites cover supported families; independent JSON,
streaming, opt-out, cache, failure, and live integration checks do not require
the compiled module. Historical retail helpers are classified and excluded
without weakening real-estate catalogue behavior.

Stage 5 is technically ready but **not started or authorized**. Its entry work:

1. separately authorize shadow/differential acceptance;
2. supply approved sanitized production samples beyond the constructed corpus;
3. prevent duplicate side effects in shadow execution;
4. characterize stream cancellation/backpressure and comparable latency;
5. define rollout thresholds and release rollback evidence.

## STOP

Do not change production backend selection, begin shadow traffic, delete either
AI runtime, remove the loader/patch mechanism, or begin Stage 5 or Stage 6
without separate authorization.
