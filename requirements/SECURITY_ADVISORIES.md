# Dependency security advisories

Triage of `pip-audit` output. Re-run: `.venv/Scripts/python.exe -m pip_audit`.

Last reviewed: 2026-09-10 — 42 findings across 5 packages.

| Package | Where | Verdict | Action |
|---|---|---|---|
| `pip` 25.0.1 (7 CVEs) | dev tooling only, never shipped | **Fixed** | Upgraded to 26.2.1 in the venv on 2026-09-10. Not pinned in `requirements/` (tooling). |
| `ecdsa` 0.19.2 — PYSEC-2026-1325 (Minerva timing attack) | transitive via `python-jose[cryptography]` (core auth) | **Not reachable** | Auth signs/verifies tokens with **HS256** (HMAC), see `services/auth_service.py:14`. The ECDSA code path is never called. No upstream fix exists. Revisit only if auth moves to ES256/ES512. |
| `transformers` 4.46.1 (~30 CVEs) | `requirements/local-llm.txt` (+ retrieval/translation/tts) | **Low risk today, must fix before enabling local LLM** | Almost every CVE requires loading an attacker-controlled model, config, or tokenizer, or feeding adversarial text to a specific pipeline. This app runs a fixed, self-hosted Qwen and does not load user-supplied models. Bump to a current 4.5x **together with** the local-fallback-provider work, where the ML stack is actually exercised and tested against `haystack-ai==3.1.1` and `sentence-transformers==5.7.0`. |
| `accelerate` 1.14.0 — CVE-2026-69112 | `requirements/local-llm.txt` | **Low risk today** | Local-ML stack only; no fix version published yet. Track with the `transformers` bump. |
| `protobuf` 4.25.9 — PYSEC-2026-1805 (recursion DoS) | transitive via the ML stack | **Low risk today** | Only parsed inside local model/tensor loading, not on any request path. Fix (>=5.29.6) will likely come naturally with the `transformers` bump. |

## Summary

- **Nothing on the live request path is exploitable.** The remote provider (Sarvam)
  path does not touch `transformers` / `accelerate` / `protobuf`; auth does not
  touch `ecdsa`.
- **One concrete fix applied:** `pip` upgraded.
- **One bundle deferred on purpose:** `transformers` + `accelerate` + `protobuf`
  get upgraded and regression-tested as part of turning on the local fallback LLM.
- No dependency was found unused; nothing to remove.
