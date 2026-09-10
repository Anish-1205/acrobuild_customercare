# How often is the un-reconstructed answer-engine bytecode actually used?

Measurement to decide whether a full hand-reconstruction of
`services/ai_agent_service_runtime.pyc` (~10,400 lines, one 2,200-line function)
is worth the effort, or whether a narrow fix covers the real problem.

Measured 2026-09-10.

---

## 1. There is no production traffic

The app is not deployed. `logs/chatbot.log` is 415 lines total — **22 real chat
turns** from one evening of manual repro testing (2026-09-09), the rest is
pytest `testserver` noise. No APM, no historical window to analyse. Of the 5
turns that logged an `orchestration result`, 1 was a raw-document dump — not a
statistically meaningful sample.

So the numbers below come from the **200-prompt proxy corpus**
(`scripts/eval_prompts.json`) run through `run_support_orchestration`
in-process with the LLM call stubbed — `scripts/measure_bytecode_fallback.py`
(220 turns incl. follow-ups).

Caveat: the internal CS API (`10.10.1.23:9091`) is unreachable from this
machine, so live-inventory calls timed out; the **workspace knowledge index**
(`data/ai_index/…`, real project data) still fed retrieval, so the property path
executed with grounded data for most prompts.

---

## 2. Instrumentation added

New `bytecode_fallback` logger, wired in `services/ai_agent_service.py` right
after the bytecode is `exec`'d:

| Event | Fires when |
|---|---|
| `event=legacy_bytecode_invoked` | `_legacy_build_company_api_direct_answer` (the 2,200-line bytecode fn) is called — i.e. all ~10 deterministic pre-handlers missed |
| `event=raw_document_dump_path` | `should_return_verbatim_source_answer(...)` returned true — the gate for pasting a document verbatim |
| `event=generic_fallback_answer` | `build_fallback_assist_answer(...)` fired |

Verified: wrappers install correctly (`__wrapped__` present), events emit.
These now collect data automatically once there is real traffic.

---

## 3. Results — 200-prompt corpus

| Outcome | Count | % |
|---|---:|---:|
| Reached `_legacy_build_company_api_direct_answer` (the 2,200-line fn) | **0 / 200** | **0%** |
| Raw-document-dump answer | **0 / 200** | **0%** |
| Generic fallback-assist answer | **0 / 200** | **0%** |
| Deterministic pre-handler answer (grounded, real project data) | ~74 / 200 | 37% |
| LLM generation (with retrieved context) — stubbed here | ~114 / 200 | 57% |
| Relevance-guard clarification | ~12 / 200 | 6% |

By category, the deterministic pre-handlers in `services/ai_agent_service.py`
(`_build_project_catalogue_answer`, `_build_budget_project_recommendation`,
`_build_shop_availability_answer`, `_build_portfolio_overview_answer`, the
contextual cost/floor answers, …) plus the blob's own deterministic builders
absorbed every property/pricing/availability/comparison prompt that didn't go to
LLM generation. **The 2,200-line legacy function was invoked zero times across
220 turns.**

---

## 4. The raw-document-dump bug — what actually triggers it

It is **real** — the 2026-09-09 log has one ("what is the properties you offer?"
→ `agent_mode=fallback` → `"Here is the relevant information: 'Company: name:
GBK GROUP LLP …'"`). But it is **driven by retrieval quality, not query type**:

- That turn's retrieval returned essentially one lexical hit — the monolithic
  company record — and the verbatim/fallback path pasted it.
- Re-running the same and similar prompts now, with the workspace index holding
  real project data, retrieval returns ~10 project chunks and the dump path does
  **not** fire (0/200).

So the failure mode is "sparse/degraded retrieval → verbatim-dump on whatever
single chunk exists", which surfaces the giant `acrobuild-cs-company` record
because it's the highest-scoring lone hit.

---

## 5. Recommendation

**Full reconstruction of `ai_agent_service_runtime.pyc` is not justified by the
current evidence.** The un-reconstructed 2,200-line function is not on any hot
path in the measured corpus, and the one concrete user-visible defect (the
document dump) is a retrieval problem, not an answer-generation problem.

Narrow fixes that address the actual issue, in `.py` we already control:

1. **Relevance floor / thin-retrieval guard** — when the top retrieved chunk is
   below a score threshold or the only hit is the monolithic company record,
   return a "tell me the project / city / budget" clarification instead of
   letting the verbatim path run. Can live in the `build_company_api_direct_answer`
   wrapper or in `_enforce_live_property_data` (`api_context.py`).
2. **Exclude the monolithic `acrobuild-cs-company` record from property-search
   retrieval**, or split it into smaller titled chunks so it can't dominate as a
   single lexical hit.
3. Keep the `bytecode_fallback` logger and re-check these numbers once the app
   has real traffic — if `legacy_bytecode_invoked` climbs, revisit.

Phases 1–3 (documentation, the two constant patches, router reconstruction)
stand as delivered.
