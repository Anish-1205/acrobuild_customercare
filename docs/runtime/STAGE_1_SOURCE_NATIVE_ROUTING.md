# Runtime Migration Stage 1: Source-Native Conversation Routing

Date: 9 October 2026  
Status: complete; Stage 2 is not authorized

## Executive summary

Conversation routing now uses a normal Python import of
`graph/haystack_conversation_pipeline_source.py`. The compatibility facade no
longer compiles or executes source text, unmarshals bytecode, checks for a
binary fallback, or attempts recovery from stale conversation bytecode.

The obsolete conversation runtime was removed from the active repository. The
Haystack framework remains installed and continues to execute the existing
one-component pipeline. Both answer-engine runtimes and their patching/loading
mechanism are unchanged.

The Stage 0 plural `wings` concern was confirmed as a narrow heuristic
regression and corrected by adding the plural term to the existing whole-word
property vocabulary. The primary analyzer, wing-detail validation, property
clarification contract, and customer-facing wing behavior already establish
this as property intent. Embedded substrings remain rejected.

## Stage 0 gate review

| Gate | Result |
| --- | --- |
| Forty differences reviewed | Accepted except plural `wings`, which was corrected |
| Safe-fallback copy | Preserved as intentional source evolution |
| Property-scoped pricing | Preserved as intentional source evolution |
| All explicit projects required | Preserved as intentional source evolution |
| Boundary false positives | Preserved; embedded `home`/`bhk`-like fuzz remains non-property |
| `prefer_qwen_response=False` | Preserved for JSON and streaming orchestration |
| Historical catalogue status | Unchanged |
| Missing product decision blocking Stage 1 | None |

After the `wings` correction, the final pre-removal differential was **39
expected differences across 13,077 cases**:

- 27 safe relevance fallback copy differences;
- 6 property-scoped pricing differences;
- 4 complete-project comparison differences;
- 2 intentional embedded-substring boundary differences.

The verifier intentionally exited non-zero because current readable behavior is
not supposed to match obsolete bytecode in those cases.

## Implementation

`graph/haystack_conversation_pipeline.py` is now a source-native compatibility
facade. It imports the readable module normally, installs the four existing
source-visible overrides, bridges the two patchable retrieval/project-name
dependencies, and rebuilds the existing one-component Haystack pipeline. This
preserves the previous runtime behavior and test seams without dynamic `exec()`.

If the readable implementation is missing or invalid, Python raises an explicit
normal import failure. There is no bytecode recovery branch.

The historical differential tool now requires an explicit path to an archived
runtime. It does not assume or open an active-repository fallback.

Removed artifact:

- `graph/haystack_conversation_pipeline_runtime.pyc`

The deletion is recoverable from Git history; it is no longer part of startup,
normal execution, emergency recovery, or the active application package.

## Preserved contracts

- General versus property/support routing.
- Greetings, small talk, capability answers, and relevance validation.
- Project, BHK, wing, floor, flat, locality, and contextual follow-ups.
- Mandatory clarification and live-property grounding.
- Pending selection/current-project state and original-intent preservation.
- JSON and NDJSON completion semantics.
- Multilingual analysis/localization boundaries.
- Safe fallback wording and failure status.
- `ACROBUILD_DISCOVERY_SLOTS` and all other feature flags.
- `prefer_qwen_response=False` behavior.
- Existing Haystack dependency and one-component pipeline.
- Both compiled AI answer runtimes and their patching/loader machinery.

## Intentional behavior deviation

`show me the wings` now routes to property support in the heuristic fallback.
This is the only intentional customer-visible behavior change in Stage 1. The
singular `wing`, real-estate plural usage, and unrelated-word boundary behavior
remain covered independently.

## Verification

| Check | Result | Evidence class |
| --- | --- | --- |
| Clean-process `import app` and conversation module without removed runtime | Passed | Local source-only startup |
| New source-native/wings/opt-out/reload tests | 5 passed | Automated mocked/source inspection |
| Focused pipeline/context/property suite | 111 passed, 10 subtests passed | Automated mocked |
| Broader discovery/clarification/endpoint suite | 397 passed, 13 subtests passed | Automated mocked |
| Full backend suite in network sandbox | 1,912 passed, 182 subtests passed, 1 setup error | Automated; one environment block |
| Blocked CS API test rerun outside sandbox | 1 passed, 4 subtests passed | Live CS API for that test only |
| Ruff on changed Python files | Passed | Static analysis |
| `git diff --check` | Passed | Repository hygiene |

The full-suite setup error was `WinError 10013` when the sandbox blocked the
configured CS API connection. Its isolated network-enabled rerun passed. The
existing Starlette `BlockingPortal` deprecation warning remains unrelated.

No live Sarvam acceptance, browser/frontend verification, production traffic
benchmark, or external CRM/booking action was run or claimed for Stage 1.

## Remaining risks and limitations

- Haystack remains a runtime dependency until an explicitly authorized Stage 2.
- The source facade still carries compatibility overrides; Stage 2 should merge
  or replace them only with parity tests in place.
- The answer engine still executes the original/patched Python 3.12 bytecode.
- Historical differential reruns now require an explicitly supplied archived
  artifact; this is deliberate so production packaging cannot silently regain a
  fallback.
- The product status of inherited catalogue behavior remains unresolved and was
  not changed.
- Live Sarvam behavior remains unverified by this stage.

## Completion and next-stage readiness

All Stage 1 acceptance criteria are met. Conversation routing is readable,
normally imported, source-only, and independently startable; the obsolete
runtime is removed; opt-out and endpoint contracts remain protected; and the AI
answer engine was not changed.

**Stage 1 status: complete.**

**Stage 2 status: technically ready, not authorized.** Stage 2 may replace the
one-component Haystack shell with direct Python orchestration and then remove
`haystack-ai`, but it must preserve the facade overrides, routing outputs,
opt-out behavior, and all current endpoint/state contracts.

## STOP

Do not remove Haystack, modify the answer engine, delete either remaining
runtime, or begin Stage 2 without explicit authorization.
