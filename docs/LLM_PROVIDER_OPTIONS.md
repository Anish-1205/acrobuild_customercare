# LLM provider options — where we stand

Plain-language weighing of the choices for which model answers customer chat.
Written 2026-09-10.

---

## What exists today

- **Remote provider ("sarvam" slot)** — a generic OpenAI-compatible HTTP client
  (`sarvam_client.py`). Points at any URL + model name + API key. Today it targets
  a RunPod-hosted Sarvam model.
- **Local provider ("qwen" slot)** — loads a Hugging Face-format model with
  `transformers` (`qwen.py`). Runs in-process on this machine's CPU/GPU.
- **Fallback wiring** — `LLM_FALLBACK_PROVIDER` + latency routing. If the primary
  fails (or is slow past a threshold), the request retries on the other slot.
  Streaming never switches mid-answer.
- **A local quantized Qwen** you already have from another project (format TBC —
  likely GGUF).

---

## Option A — Local quantized model as the ONLY provider

Serve your GGUF model with Ollama / llama.cpp / LM Studio / vLLM, point the
"sarvam" slot at `http://localhost:<port>/v1`.

**Positives**
- No code changes. Three `.env` lines.
- No per-token API cost, no external vendor.
- Data never leaves your machine — good for customer PII.
- Quantized = modest hardware (a decent GPU, or CPU if patient).
- You already know this model from the other harness.

**Negatives**
- Single point of failure. Model server down = chat down (no backup).
- Quality ceiling of a small quantized model — weaker reasoning, more
  hallucination risk on property facts. The existing hallucination guards
  (`_enforce_live_property_data`) still apply, but the raw answers are rougher.
- You own uptime, restarts, GPU memory, driver issues.
- Throughput is bounded by one box — concurrent chats queue up.

---

## Option B — Remote model as primary, no local backup (roughly today's state)

**Positives**
- Best answer quality (larger model).
- Vendor handles uptime and scaling.
- No local GPU needed.

**Negatives**
- Ongoing cost per request.
- Customer messages leave your infrastructure.
- Full dependency on the vendor + network. An outage = chat down.
- Latency spikes seen in past traces (60–70s hangs, now deadline-capped at 45s).

---

## Option C — Remote primary + local quantized model as automatic fallback

Requires a small code change (~30 lines): let the "qwen" fallback slot also point
at a local OpenAI-compatible server instead of only the `transformers` loader.

**Positives**
- Chat keeps working during a vendor/network outage — degraded answer quality
  beats a dead chatbot.
- Normal traffic still gets the good remote model.
- Local box only has to handle load during incidents, not 24/7.

**Negatives**
- The ~30-line change + tests to maintain.
- Two systems to keep healthy instead of one.
- Fallback answers are visibly weaker; needs a UI note or logging so support
  staff know when it kicked in.
- Local server still has to be up and warm to be useful as a backup.

---

## Cross-cutting facts

| Topic | Status |
|---|---|
| Security (live path) | No known exploitable vulnerabilities. See `requirements/SECURITY_ADVISORIES.md`. |
| Security (local ML stack) | `transformers`/`accelerate`/`protobuf` carry advisories; must upgrade + retest **before** relying on any local model in production. |
| Compiled `.pyc` runtimes | Core, not removable. Editable source still missing — `temperature=0.35` on property answers can't be changed without it. |
| Malware scan on uploads | Not set up. Blocks uploads in production until ClamAV is installed. Deferred by decision. |
| Durable chat history | Done — SQLite, cookie-scoped, 2h retention, works across workers. |

---

## Suggested path

1. Confirm the format of your local quantized model (GGUF vs GPTQ vs safetensors).
2. Start with **Option A** in a staging setup — cheapest to try, reveals whether
   the quantized model's answer quality is acceptable for your customers.
3. If quality is fine → stay on A. If not → **Option C** (remote quality with a
   local safety net), accepting the small code change.
4. Before either goes to production: upgrade the ML dependency stack and re-run
   `pytest` + `pip-audit`.
