# Compiled answer-runtime compatibility

The answer engine originated as Python 3.12 bytecode. Do not edit its original
`.pyc` files or loader behavior casually.

## Current state

| Runtime | Current execution path | Status |
| --- | --- | --- |
| `services/ai_agent_service_runtime.pyc` | `services/ai_agent_service.py` loads the patched copy when present, otherwise the original, then applies source-visible wrappers | Core answer engine remains bytecode-only |

`services/runtime_compatibility_service.py` validates the bytecode header before
loading the answer runtime. Use the repository Python 3.12 environment; a different interpreter
raises a controlled error instead of attempting an incompatible marshal load.

The historical conversation runtime was removed in Stage 1. Conversation
routing now uses a normal import of `haystack_conversation_pipeline_source.py`;
missing source raises the standard Python import error instead of executing stale
bytecode. Stage 2 replaced the one-component Haystack shell with a native Python
adapter that preserves the established input/output contract, and removed the
`haystack-ai` application dependency. The two answer-engine runtimes remain.

Stage 3 added `services/answer_engine_service.py` as the production integration
boundary. `graph/main_orchestrator.py` and the API compatibility exports use its
JSON, streaming, and cache-invalidation functions. The active backend is
`LegacyCompiledAnswerEngine`, which dynamically delegates to
`services.ai_agent_service` so existing monkeypatch points remain effective.
Stage 4 added `services/readable_answer_engine.py`, which independently owns the
same responsibility groups for isolated readable-mode verification. Production
selection remains legacy; see `STAGE_4_READABLE_ANSWER_ENGINE.md`.

Still supplied by the production-selected backend after completed Stage 4:

- retrieval assembly;
- response-cache keying, storage, TTL, and reads;
- deterministic handler selection and fallback policy;
- prompt construction and Sarvam invocation;
- confidence and handoff policy;
- response and stream-event assembly.

The readable backend implements each item above without importing the runtime.
Stage 4 verified the supported scenario families with a constructed sanitized
corpus, mapped upstream contract suites, no-legacy execution traps, and live CS
API and Sarvam checks. Historical food, beverage, Shopify, vendor-feed, and
retail-catalogue behavior was classified as unrelated product residue and is
intentionally unsupported by the future readable engine. Real-estate project
catalogue, location, price, construction, configuration, and inventory behavior
remains in scope. Production still selects the legacy backend; this is not a
cutover or runtime-removal claim.

The readable interface traces the implementation name, delivery mode, duration,
terminal-event count, and response metadata already returned by the backend. It
does not log questions, customer identity, prompts, or retrieved content, and it
does not claim cache-hit or handler information that the backend does not expose.

## What was verified

The conversation pipeline reconstruction was compared with the original
bytecode using `scripts/verify_pipeline_reconstruction.py`; the historical run
covered 13,077 cases with no mismatches. The answer-engine reconstruction spike
showed that automated Python 3.12 decompilation was not reliable for its closure
and comprehension-heavy functions.

That zero-mismatch result is historical, not the current parity target. Stage 0
made the verifier deterministic and recorded 40 classified differences across
the same 13,077 cases. Stage 1 fixed the plural `wings` routing regression and
recorded 39 expected differences before removing the binary. See
`STAGE_0_BASELINE_AND_CONTRACT_LEDGER.md` and
`STAGE_1_SOURCE_NATIVE_ROUTING.md`. Current readable behavior remains
authoritative where it intentionally evolved.

The answer-engine wrapper logs entry into legacy bytecode fallbacks. A historical
200-prompt proxy measurement reached neither the large legacy direct-answer
function nor the raw-document-dump branch. Source-visible guards were added for
thin retrieval and company-contact record leakage, so full reconstruction was
deferred.

These are dated engineering results. Rerun relevant tests before changing the
loaders or declaring bytecode removal safe.

## Supported maintenance commands

```powershell
.venv/Scripts/python.exe scripts/verify_pipeline_reconstruction.py <archived-conversation-runtime.pyc>
.venv/Scripts/python.exe scripts/patch_runtime_constants.py
```

The differential verifier requires an explicitly supplied historical artifact;
the removed conversation runtime is not kept in the active repository or
application package.

The patch script writes `services/ai_agent_service_runtime.patched.pyc`; it does
not overwrite the original. Review the script before running it and verify the
full backend suite afterward.

## Rules

- Never delete or overwrite an original runtime until equivalent readable
  source has passed differential and application regression tests.
- Keep bytecode-specific work on Python 3.12.
- Treat comments and historical disassembly as supporting evidence; the active
  loader and tests define current behavior.
- Prefer deterministic source-visible handlers around the bytecode for narrow
  fixes. Do not patch binary constants for ordinary product changes.
