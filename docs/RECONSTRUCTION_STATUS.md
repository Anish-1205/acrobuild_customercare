# Bytecode reconstruction — running status

Tracks the effort to replace the two compiled-only runtimes with real `.py`
source. The original source is not recoverable; this is a rebuild.

Rules in force:
- **Never edit the original `.pyc` files** — work on copies only.
- Run the full test suite after every change; record exact pass/fail counts.
- Flag anything reconstructed by guesswork (not confident from the bytecode).

Last updated: 2026-09-10.

---

## Files

| File | Source lines (approx) | Functions | State |
|---|---:|---:|---|
| `graph/haystack_conversation_pipeline_runtime.pyc` | ~640 | 26 + 1 class | **bytecode-only** — Phase 3 target |
| `services/ai_agent_service_runtime.pyc` | ~10,400 | ~150 | **bytecode-only** — Phase 4 target |

Baseline test suite before any of this work: **634 passed, 43 subtests**
(`.venv/Scripts/python.exe -m pytest tests/ --basetemp=<writable>`).

---

## Phases

### Phase 1 — Document both files — ✅ DONE (2026-09-10)
- Output: `DECOMPILED_MAP.md`.
- Read-only. No tests affected.

### Phase 2 — Patch `temperature` 0.35→0.1 and the `"gemini"` label — ✅ DONE (2026-09-10)
- Tool: `scripts/patch_runtime_constants.py` — loads the marshalled module,
  swaps two constants inside `build_ai_support_answer` and
  `stream_ai_support_answer_events`, writes
  `services/ai_agent_service_runtime.patched.pyc`. **Original `.pyc` never
  written** (md5 unchanged).
- Changes: `temperature 0.35 → 0.1`; `agent_mode "gemini" → "remote_llm"`
  (the value `normalize_agent_mode()` already maps `"gemini"` to; a valid
  `AGENT_MODE_ENUM` member — **judgment call**, see note).
- Loader (`services/ai_agent_service.py`) now prefers `*_runtime.patched.pyc`
  when present. `.gitignore` keeps the patched file tracked.
- Tests after: **634 passed, 43 subtests** (identical to baseline). `ruff` clean.

**Judgment call:** the blob has no way to know which provider actually answered,
so the label is static. `"remote_llm"` preserves today's normalised behaviour
exactly (`normalize_agent_mode("gemini") == "remote_llm"`). If local Qwen is the
provider the label is technically wrong, but it already was — the real
provider-aware value comes from `get_llm_agent_mode()` in the orchestrator, which
is unaffected.

### Phase 3 — Reconstruct `haystack_conversation_pipeline_runtime.pyc` as `.py` — ✅ DONE (2026-09-10)
- `graph/haystack_conversation_pipeline_source.py` — all 26 functions + 1 class +
  module constants + pipeline construction, hand-reconstructed from the full
  bytecode disassembly.
- The loader `graph/haystack_conversation_pipeline.py` `exec`s the source in
  preference to the `.pyc` when present (exec, not import, so the loader's
  wrapper overrides still bind to the pipeline).
- `.pyc` left in place as the fallback and the reconstruction reference.
- Verified:
  - `scripts/verify_pipeline_reconstruction.py` — differential test, source vs
    bytecode in isolated namespaces with stubbed deps: **13,077 cases, 0
    mismatches**.
  - `pytest tests/` with the source active → **634 passed, 43 subtests**.
  - `ruff` clean.
- One bug found and fixed during differential testing: `validate_support_answer`
  "one recommended option" check — the bytecode flags when the answer *contains*
  cross-project phrasing (`and any(...)`), not when it lacks it.

**Reconstructed by careful bytecode tracing, then confirmed by 13k differential
cases — not guesswork.** The trickiest branches (`resolve_contextual_support_issue`
wing-reset condition, `is_contextual_property_reply` return shape,
`matches_live_company_context` try-scope) were all confirmed against the bytecode.

### Phase 4 — Big answer-engine file — 🔬 SPIKE DONE, awaiting decision (2026-09-10)

**pycdc built:** `zrax/pycdc` @ b428976, compiled with MinGW-w64 GCC 16.1 +
CMake 4.4 (both installed via winget, user scope). Build lives at
`<scratchpad>/pycdc/build/pycdc.exe` — not committed (third-party tool).

**pycdc 3.12 output quality — measured on 5 functions from this file:**

| Function | Result |
|---|---|
| `classify_confidence` (4 locals) | skeleton ~70% right; **2 bugs**: inverted `if assist_error or not matched_chunks`, and `float(X or 0)` flattened to `float(0)` (value dropped) |
| `has_sufficient_guidance` (4 locals) | skeleton right; same `float(0)` bug; final line emitted as `return None >= 7` (variable lost) |
| `should_use_llm_generation` (10 locals) | ~15 lines then **"Decompyle incomplete"** at `LOAD_FAST_AND_CLEAR`; guard sequence usable as scaffold |
| `build_contextual_assist_query` (21 locals, closure) | **total failure** — 0 lines, dies at `MAKE_CELL` |
| `build_company_api_direct_answer` (283 locals) | **total failure** — 0 lines, dies at `MAKE_CELL` |

pycdc's 3.12 backend does not support `MAKE_CELL`, `LOAD_FAST_AND_CLEAR`,
`RETURN_GENERATOR`, `DICT_UPDATE` — i.e. any closure, any inlined
comprehension/genexpr, any `{**a, ...}`. It also silently drops the RHS of
`X or Y` and conditional expressions. This file is saturated with those
constructs.

**Chunk reconstruction + differential harness (spike deliverable):**
`classify_confidence` + `has_sufficient_guidance` rebuilt from pycdc scaffold +
disassembly corrections, verified by `<scratchpad>/spike_diff.py` (code objects
extracted straight from the blob, no full-module import) — **6,014 cases, 0
mismatches**.

**Assessment:** pycdc is a *scaffold generator for small functions only*, not a
decompiler we can lean on. For anything with a comprehension or closure — most
of this file, and the entire 2,200-line function — it produces nothing. The
workable method is the Phase 3 method: hand-reconstruct from disassembly, verify
with a differential harness. pycdc output is a mild time-saver on the simplest
leaf helpers and nothing else.

**Decision needed:** proceed with full hand-reconstruction of this file
(large — ~150 functions, one 2,200-line function), or stop here with Phases 1–3
delivered and the two constants patched.

---

## Change log

| Date | Phase | What changed | Tests after | Notes |
|---|---|---|---|---|
| 2026-09-10 | 1 | `DECOMPILED_MAP.md` created (read-only) | not run (no code change) | — |
| 2026-09-10 | 2 | patched `temperature`/`agent_mode` consts into `*_runtime.patched.pyc`; loader prefers it | 634 passed, 43 subtests | original `.pyc` md5 unchanged; ruff clean |
| 2026-09-10 | 3 | reconstructed `haystack_conversation_pipeline_source.py`; loader `exec`s it in preference | 634 passed, 43 subtests | 13,077 differential cases 0 mismatches; ruff clean; `.pyc` untouched |
