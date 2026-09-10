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

### Phase 2 — Patch `temperature` 0.35→0.1 and the `"gemini"` label — ⏳ NOT STARTED
- Targets: `build_ai_support_answer` and `stream_ai_support_answer_events` in
  `services/ai_agent_service_runtime.pyc`.
- Approach: edit a **copy** of the bytecode (rewrite the two `LOAD_CONST`
  operands), swap it in, run the full suite, report counts.

### Phase 3 — Reconstruct `haystack_conversation_pipeline_runtime.pyc` as `.py` — ⏳ NOT STARTED
- Function by function, lowest-level helpers first, running the tests that touch
  each as it lands.
- Keep the `.pyc` in place until the whole module passes all 634 tests.

### Phase 4 — Big answer-engine file — ⏳ NOT STARTED
- Spike first: decompile + verify ONE chunk of `build_company_api_direct_answer`,
  report how usable the output is, get sign-off before continuing.
- Then proceed in chunks, same discipline.

---

## Change log

| Date | Phase | What changed | Tests after | Notes |
|---|---|---|---|---|
| 2026-09-10 | 1 | `DECOMPILED_MAP.md` created (read-only) | not run (no code change) | — |
