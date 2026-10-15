# Runtime Migration Stage 3: Readable Answer-Engine Interface

Date: 9 October 2026  
Status: complete; Stage 4 is not authorized

## 1. Summary

`services/answer_engine_service.py` is now the production integration boundary
for property/RAG answer generation. It defines a typed request, JSON and stream
entry points, a backend protocol, cache invalidation, and non-sensitive execution
tracing. The active implementation remains `LegacyCompiledAnswerEngine`, which
delegates to the existing Python 3.12 runtime without reproducing or replacing
its answer behavior.

Both `graph/main_orchestrator.py` and the compatibility exports in
`api_context.py` use this boundary. Existing signatures and patch points remain
available. Stage 3 did not delete, regenerate, or alter either runtime file, the
marshal loader, or the binary patch script.

## 2. Previous and current execution paths

Before Stage 3:

```text
main orchestrator/API imports -> services.ai_agent_service -> compiled runtime
```

After Stage 3:

```text
main orchestrator/API imports
  -> services.answer_engine_service
     -> LegacyCompiledAnswerEngine
        -> services.ai_agent_service
           -> compiled runtime
```

JSON uses `answer_support_request()` and streaming uses
`stream_support_request()`. Compatibility functions retain the legacy names and
signatures. Stream events are yielded unchanged; the interface observes their
types and terminal count but does not insert, remove, reorder, or rewrite them.
The existing router/orchestrator finalizers still own clarification, live-data
enforcement, localization, public trace/evaluation fields, persistence, and
property-text buffering.

## 3. Readable interface and ownership

Source-visible in Stage 3:

- `AnswerEngineRequest`, including server-only conversation scope;
- `AnswerEngineEvent` and the JSON/stream method boundary;
- `AnswerEngineBackend` and the active implementation identity;
- the temporary `LegacyCompiledAnswerEngine` adapter;
- cache invalidation delegation;
- customer-name and conversation-id cache namespace isolation;
- execution tracing for implementation, delivery mode, duration, event count,
  terminal count, source/retrieval status, `used_llm`, confidence, handoff, and
  agent mode.

The trace deliberately excludes questions, names, emails, conversation IDs,
prompts, retrieved content, and answer text. It reports only decisions already
observable in the returned response. Cache-hit and selected-handler information
remain unavailable because the compiled backend does not expose them.

Still compiled:

- retrieval and context-section assembly;
- the base cache key, TTL, storage, locking, reads, writes, and expiry;
- deterministic handler selection and fallback rules;
- prompt construction and Sarvam invocation;
- model validation and echo detection;
- confidence and handoff policy;
- JSON response and stream-event assembly.

Moving these responsibilities without duplicating or bypassing effective
bytecode behavior requires Stage 4 implementation and differential tests.

## 4. Cache compatibility and isolation

The compiled cache continues to own its base key, 45-second TTL, deep-copy
behavior, lock, storage, and invalidation. The base key already includes issue,
customer email, issue type, business-hours tag, article hint, recent messages,
limit, and response preferences.

Investigation found that it omitted `customer_name` and `conversation_id`, even
though customer name can affect fallback and generated content. Stage 3 adds a
readable `ContextVar` namespace containing those two values around each legacy
JSON or streaming call. This preserves the compiled cache algorithm while
preventing cache reuse across named customers or conversations, including
concurrent streams. Public function signatures remain unchanged.

Observable behavior is unchanged except for this intentional isolation fix: two
otherwise identical calls from different customers or conversations can no
longer reuse one another's cached payload.

## 5. Compatibility decisions

- Legacy JSON and streaming signatures match exactly.
- `graph.main_orchestrator.build_ai_support_answer` and
  `stream_ai_support_answer_events` remain patchable names.
- The adapter resolves `services.ai_agent_service` functions dynamically, so
  existing legacy monkeypatch points remain effective.
- `prefer_qwen_response=False` still reaches the same compiled support handler.
- JSON and NDJSON retain their distinct current execution behavior; Stage 3 did
  not force artificial parity.
- Stream cancellation/closure is re-raised and does not emit a synthetic result.
- Cache invalidation call sites and ordering are unchanged.
- Property clarification, grounding, localization, protected facts, state
  markers, feature flags, authentication, and action side effects remain outside
  the answer-engine seam.

## 6. Files changed by Stage 3

Added:

- `services/answer_engine_service.py`
- `tests/test_answer_engine_service.py`
- `docs/runtime/STAGE_3_READABLE_ANSWER_ENGINE_INTERFACE.md`

Modified:

- `services/ai_agent_service.py` — readable cache namespace only; loader and
  answer wrappers otherwise unchanged;
- `graph/main_orchestrator.py` — routes answer calls through the seam and binds
  conversation cache scope;
- `api_context.py` — exports the seam's compatibility functions;
- `docs/ARCHITECTURE.md`;
- `docs/CHAT_FLOW.md`;
- `docs/runtime/COMPILED_RUNTIME.md`;
- `docs/RUNTIME_DEPENDENCY_ELIMINATION_FEASIBILITY.md`.

Removed: none.

## 7. Verification

| Check | Result | Evidence class |
| --- | --- | --- |
| Interface, signatures, production wiring, patch points, logs, failures, cache scope/copy/TTL/concurrency | 12 passed | Automated unit/synthetic |
| Direct legacy versus interface JSON and stream output | Identical in sanitized deterministic fixtures | Synthetic characterization |
| Broader routing, endpoint, property, clarification, discovery, multilingual, failure, and action suite | 880 passed, 97 subtests passed | Automated mocked |
| Full backend suite in network sandbox | 1,926 passed, 182 subtests passed, 1 setup error | Automated; one environment block |
| Exact CS API test outside sandbox | BLOCKED: two final attempts timed out during setup | Live integration unavailable |
| Clean-process `import app` | Passed | Local startup |
| Ruff on Stage 3 Python files | Passed | Static analysis |
| `git diff --check` | Passed | Repository hygiene |

The full-suite setup error was the known `WinError 10013` sandbox denial while
opening the configured CS API. Two final network-enabled reruns reached the
connection attempt but timed out after 2.5 seconds, so final live CS API evidence
is **BLOCKED**, not passed. The existing Starlette `BlockingPortal` deprecation
warning is unrelated.

No live Sarvam test, representative sanitized production conversation corpus,
frontend/browser test, production benchmark, or external CRM/booking action was
run or claimed.

## 8. Runtime integrity and behavior differences

The answer-engine runtime SHA-256 hashes remained:

- original: `CE5C73F0E32D514164AE1EA7E1E0E0DEB3F44AE4FB28461F5C3A77737D786660`
- patched: `500FF0D437D88F8627B7C0F25E8FDFD370BBD6EE7CAD8ED1D9ABAC25501EC0F4`

`scripts/patch_runtime_constants.py` has no Stage 3 diff. Required response and
stream behavior remained identical under the deterministic comparison and
regression suites. The only intentional behavior difference is stricter cache
separation by customer name and conversation ID.

## 9. Maintainability

Developers can now inspect one source file to see every input crossing into the
answer engine, the active implementation, JSON versus stream contracts, cache
invalidation, isolation scope, observable response decisions, and the exact list
of responsibilities that remain compiled. A future implementation can satisfy
the same protocol and be introduced behind this boundary without changing HTTP,
routing, clarification, or finalization contracts.

The adapter is explicitly temporary. It should be removed after Stage 4/5 prove
that supported scenarios no longer require the compiled backend.

No comparable production or live-service performance benchmark was available.
Stage 3 adds only local request construction, context scoping, and metadata
logging around the same backend calls; no latency improvement or production
overhead claim is made.

## 10. Stage 4 readiness and remaining risks

Stage 4 is **conditionally ready** from an integration perspective: the seam,
rollback point, compatibility tests, cache isolation tests, and deterministic
comparison are in place.

Conditions remain before broad behavior replacement or cutover:

- classify each migrated handler against supported scenarios rather than porting
  the 146-function static closure wholesale;
- obtain the product decision for inherited catalogue behavior before omission;
- preserve the unresolved `prefer_qwen_response=False` product contract;
- add approved representative sanitized conversation fixtures;
- run live Sarvam acceptance and broader CS API failure/latency checks;
- preserve JSON/stream grounding, localization, and action-side-effect gates.

These conditions do not block the completed Stage 3 interface, but they govern
which Stage 4 responsibilities can safely migrate.

## STOP

Do not begin Stage 4, replace compiled answer behavior, delete either runtime,
remove the loader/patch mechanism, or relax Python 3.12 compatibility without
separate authorization.
