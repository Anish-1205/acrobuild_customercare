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
| 2026-09-10 | 2 | patched `temperature`/`agent_mode` consts into `*_runtime.patched.pyc`; loader prefers it | 634 passed, 43 subtests | original `.pyc` md5 unchanged; ruff clean |
