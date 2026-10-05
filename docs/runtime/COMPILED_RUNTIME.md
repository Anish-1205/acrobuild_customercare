# Compiled runtime compatibility

Two modules originated as Python 3.12 bytecode. Do not edit the original `.pyc`
files or loader behavior casually.

## Current state

| Runtime | Current execution path | Status |
| --- | --- | --- |
| `graph/haystack_conversation_pipeline_runtime.pyc` | `graph/haystack_conversation_pipeline.py` prefers `haystack_conversation_pipeline_source.py` and retains bytecode as fallback/reference | Source reconstruction is active |
| `services/ai_agent_service_runtime.pyc` | `services/ai_agent_service.py` loads the patched copy when present, otherwise the original, then applies source-visible wrappers | Core answer engine remains bytecode-only |

`services/runtime_compatibility_service.py` validates the bytecode header before
loading it. Use the repository Python 3.12 environment; a different interpreter
raises a controlled error instead of attempting an incompatible marshal load.

## What was verified

The conversation pipeline reconstruction was compared with the original
bytecode using `scripts/verify_pipeline_reconstruction.py`; the historical run
covered 13,077 cases with no mismatches. The answer-engine reconstruction spike
showed that automated Python 3.12 decompilation was not reliable for its closure
and comprehension-heavy functions.

The answer-engine wrapper logs entry into legacy bytecode fallbacks. A historical
200-prompt proxy measurement reached neither the large legacy direct-answer
function nor the raw-document-dump branch. Source-visible guards were added for
thin retrieval and company-contact record leakage, so full reconstruction was
deferred.

These are dated engineering results. Rerun relevant tests before changing the
loaders or declaring bytecode removal safe.

## Supported maintenance commands

```powershell
.venv/Scripts/python.exe scripts/verify_pipeline_reconstruction.py
.venv/Scripts/python.exe scripts/patch_runtime_constants.py
```

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
