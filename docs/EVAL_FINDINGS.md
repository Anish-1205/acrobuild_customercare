# Chatbot evaluation — findings and action list

Analysis of the 200-prompt evaluation. Reviewed 2026-09-10.

The harness is `scripts/evaluate_chatbot_prompts.py`; prompts are committed at
`scripts/eval_prompts.json`. See `SETUP_AND_USAGE.md` → "Running the prompt
evaluation" for how to run it.

---

## Headline

The last recorded run (`customer_support_chatbot_200_prompt_evaluation.xlsx`,
2026-09-08) shows **133/200 working (66.5%)**, average latency **29 s**.

**That pass rate is misleading — it is dominated by a slow LLM endpoint, not by
bad answers.** Breakdown of the 67 failures:

| Bucket | Count | Real cause |
|---|---:|---|
| **Request timed out (60 s)** | 41 | The RunPod *serverless* Sarvam endpoint was cold / saturated for most of the second half of the run (IDs 137–200 almost all failed this way). Not an answer-quality problem. |
| **Dumped the wrong document** | 16 | Property questions answered by pasting the raw "GBK GROUP LLP" company record or an unrelated ops SOP, prefixed "Here is the relevant information:". Retrieval relevance + fallback formatting. |
| **Refused a valid question** | 4 | "I'm sorry, but I can't assist with that." for company-info and nearby-landmark questions. |
| **Genuinely wrong answer** | ~6 | Answered from generic world knowledge (24-hr water/power), returned an unrelated SOP, or mishandled the `[Project A]` placeholder. |

So the true answer-quality ceiling is higher than 66.5%. **Fix latency first,
then re-measure, then fix content.**

---

## Priority 1 — Latency (kills the demo, blocks a real score)

**Symptom:** average 29 s; 41 prompts exceeded 60 s and returned nothing.

**Root cause:** `LLM_PROVIDER=sarvam` points at a RunPod **serverless** endpoint
running a 30B GGUF model, with **no fallback** configured. Serverless pods cold-
start; a 30B model is slow to load and slow to generate; concurrent eval workers
(4) made it worse.

**Options (pick one before the pitch):**
1. Move the demo to a RunPod **dedicated / always-on** pod — removes cold starts.
2. Point the provider at the **local quantized Qwen** you already have, served via
   Ollama / llama.cpp (`LLM_PROVIDER` stays `sarvam`, just repoint
   `RUNPOD_BASE_URL` / `MODEL_NAME` — see `LLM_PROVIDER_OPTIONS.md`).
3. Use a smaller, faster hosted model for the demo.

Also worth doing regardless: a warm-up ping on startup, and lower `EVAL_MAX_WORKERS`
to 1–2 so a demo-grade endpoint isn't hammered.

**Re-run the eval once this is sorted** — that is the real baseline.

---

## Priority 2 — Wrong-document dumps (16 failures, needs the `.pyc` source)

**Symptom:** e.g. "Find a compact studio apartment." →
"Here is the relevant information: 'Company: name: GBK GROUP LLP …'".

**Where it lives:** the retrieval engine and the "Here is the relevant
information:" fallback wording are both inside the compiled runtimes
(`services/ai_agent_service_runtime.pyc`,
`graph/haystack_conversation_pipeline_runtime.pyc`). CHANGELOG "Open items"
already flags this string as blob-sourced.

**Blocked until the `.pyc` source is recovered.** Then:
- Add a relevance floor — if the top chunk is below it, ask a clarifying question
  ("Which city and budget?") instead of pasting a document.
- Exclude the monolithic company record and internal ops SOPs from the
  property-search retrieval set, or split them into smaller titled chunks.
- Replace verbatim document paste with a short synthesized answer + a link.

## Priority 3 — Wrong refusals (4 failures, needs the `.pyc` source)

**Symptom:** "What does [Company Name] do?", "When was [Company Name] founded?",
"Which schools and hospitals are nearby?" → "I can't assist with that."

Company-overview and locality questions have real answers in the knowledge base /
CS API. The over-broad refusal is in the blob's support path. Fix alongside P2.

## Priority 4 — Generic-knowledge answers (~6, needs the `.pyc` source)

**Symptom:** "Is there 24-hour water and power backup?" → a generic paragraph
about buildings in general, not about an Acrobuild project.

Property-detail questions with no matched evidence should say the detail isn't
available for that project and offer a handoff — not answer from world knowledge.
The `_enforce_live_property_data` gate in `api_context.py` catches *figures*; it
does not catch qualitative fabrication like this. Extending that gate is possible
without the blob but risks false positives; better done once the generator is
readable.

---

## What is NOT broken

- Security / prompt-injection prompts (IDs 193–196) — where they completed rather
  than timing out, the bot refused correctly. The 66.5% undercounts this because
  the endpoint timed out on most of them.
- General chat, greetings, date/time grounding, language matching — solid.
- The recent romanised-Tamil/Telugu language fix holds.

---

## Recommended order of work

1. Fix the LLM endpoint latency (infra / provider choice). Re-run the eval.
2. Recover the `.pyc` source (in progress).
3. With the source: relevance floor + retrieval set cleanup (P2), scope the
   refusal rule (P3), tighten the no-evidence path (P4).
4. Re-run the eval; target 85%+ with average latency under ~5 s.
