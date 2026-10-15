# Runtime Migration Stage 2: Native Conversation Routing

Date: 9 October 2026  
Status: complete; Stage 3 is not authorized

## Executive summary

Conversation routing no longer imports or executes the Haystack framework. The
single synchronous component and one-step `Pipeline` were replaced with a small
native Python adapter that preserves the established singleton, `.run()` input
shape, nested output shape, and public `run_conversation_pipeline()` behavior.

The `haystack-ai==3.1.1` application dependency was removed after a repository
dependency audit and an isolated clean installation. The clean environment did
not contain a `haystack` module, passed `pip check`, executed the native route,
and imported `app` successfully.

Both answer-engine runtimes, their loader, and the binary patching mechanism are
unchanged. Stage 2 does not make the answer engine source-independent.

## What Haystack was doing

The active use was limited to:

- `@component` and `@component.output_types` decoration on one synchronous
  `ConversationOrchestrator` class;
- a `Pipeline` containing only that orchestrator;
- conversion of the orchestrator result into
  `{"orchestrator": {"response": ...}}`.

No other application source imported Haystack. Its installed distribution was
not required by another declared application package. Historical module names,
test names, documentation, and the public `conversation_haystack` response value
are compatibility identifiers rather than runtime dependencies.

## Native implementation

`ConversationOrchestrator` is now an ordinary Python class. Its routing sequence
is unchanged:

1. normalize the issue and construct conversation state;
2. classify the conversation route;
3. run the conversation node or the supplied support handler;
4. validate support output;
5. return the existing response dictionary.

`ConversationPipeline` is a small adapter around that class. It deliberately
retains the historical `.run({"orchestrator": ...})` contract so current callers,
the source-native facade, monkeypatch points, and development reload behavior do
not need to change. The facade still rebuilds the singleton after installing its
compatibility overrides.

## Preserved contracts and decisions

- `run_conversation_pipeline()` remains the public execution function.
- `prefer_qwen_response=False` remains supported for JSON and NDJSON paths.
- The Stage 1 plural `wings` correction remains active, while embedded property
  substrings remain rejected.
- General/property routing, small talk, contextual project and configuration
  follow-ups, relevance validation, and safe failure behavior are unchanged.
- Property clarification still runs through the mandatory clarification service,
  and live-data enforcement remains in the shared route finalizer.
- Discovery and other feature flags remain at their existing boundaries.
- Historical module and response names were retained to avoid an unrelated API
  or caller compatibility change.
- No replacement orchestration framework was introduced.

## Dependency changes

Removed:

- `haystack-ai==3.1.1` from `requirements/core.txt`.

No transitive package was removed or upgraded as part of Stage 2. The stale
third-party logger-level entry for `haystack` was also removed. Application code
contains no Haystack import, decorator, or component instantiation.

The pre-existing developer `.venv` was not mutated and may retain an orphaned
Haystack installation until it is rebuilt. Fresh installs no longer select it,
and the isolated clean environment proves it is not required at runtime.

## Verification

| Check | Result | Evidence class |
| --- | --- | --- |
| Native adapter, dependency tripwire, clean-process guarded import, reload, wings, and opt-out tests | 7 passed | Automated/source inspection |
| Focused pipeline/context tests | 49 passed, 10 subtests passed | Automated mocked |
| Broader routing, endpoint, clarification, discovery, multilingual, failure, and feature-flag suite | 820 passed, 23 subtests passed | Automated mocked |
| Full backend suite in network sandbox | 1,914 passed, 182 subtests passed, 1 setup error | Automated; one environment block |
| Blocked CS API test rerun outside sandbox | 1 passed, 4 subtests passed | Live CS API for that test only |
| Isolated full requirements install without a `haystack` module | Passed; `pip check` clean, native execution and `import app` passed | Clean-install/startup evidence |
| Repository search for framework imports/decorators/dependency declaration | Passed | Static inspection |
| Ruff on changed Python files | Passed | Static analysis |
| `git diff --check` | Passed | Repository hygiene |

The full-suite setup error was `WinError 10013` when the sandbox blocked the
configured CS API connection. Its isolated network-enabled rerun passed. The
existing Starlette `BlockingPortal` deprecation warning remains unrelated.

The clean-install startup emitted the expected failed CS API probe inside the
network sandbox but completed successfully. No live Sarvam test, browser test,
production traffic benchmark, or external action was run or claimed.

## Runtime integrity

The answer-engine binaries retained identical SHA-256 hashes before and after
Stage 2:

- `ai_agent_service_runtime.pyc`:
  `CE5C73F0E32D514164AE1EA7E1E0E0DEB3F44AE4FB28461F5C3A77737D786660`
- `ai_agent_service_runtime.patched.pyc`:
  `500FF0D437D88F8627B7C0F25E8FDFD370BBD6EE7CAD8ED1D9ABAC25501EC0F4`

`services/ai_agent_service.py` and `scripts/patch_runtime_constants.py` have no
Stage 2 diff.

## Maintainability and performance

Developers can now step through the complete conversation-routing sequence with
ordinary Python debugging. Component registration, framework decorators,
telemetry setup, and framework-specific result plumbing are gone, while the
public compatibility seam remains explicit and unit-testable.

No comparable pre-Stage-2 framework-only benchmark was available, so this stage
makes no numerical latency claim. The removed wrapper was local and synchronous;
CS API and Sarvam latency continue to dominate real turns.

## Remaining limitations and Stage 3 readiness

- Property/RAG answers still execute Python 3.12 answer-engine bytecode.
- `prefer_qwen_response=False` still reaches that compiled support handler for
  property turns.
- Live Sarvam, production latency, cache isolation/concurrency, representative
  conversation-corpus comparison, and inherited catalogue product decisions
  remain unresolved Stage 0 findings.
- Historical `haystack` names remain as compatibility identifiers; renaming them
  is not required for dependency elimination and would need separate scope.

Stage 2 acceptance criteria are met. Stage 3 is technically ready to introduce
a readable answer-engine interface behind a temporary legacy adapter, but it is
not authorized by this work.

## STOP

Do not begin Stage 3, alter the answer-engine loader or patching mechanism, or
modify/delete either remaining compiled runtime without separate authorization.
