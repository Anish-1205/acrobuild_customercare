# Dependency security advisories

Historical triage of `pip-audit` output. Re-run
`.venv/Scripts/python.exe -m pip_audit` before treating these findings as
current; package advisories and fix versions change independently of this file.

Last reviewed: 2026-09-10 — 42 findings across 5 packages.

| Package | Where | Verdict | Action |
|---|---|---|---|
| `pip` 25.0.1 (7 CVEs) | dev tooling only, never shipped | **Fixed** | Upgraded to 26.2.1 in the venv on 2026-09-10. Not pinned in `requirements/` (tooling). |
| `ecdsa` 0.19.2 — PYSEC-2026-1325 (Minerva timing attack) | transitive via `python-jose[cryptography]` (core auth) | **Not reachable** | Auth signs/verifies tokens with **HS256** (HMAC), see `services/auth_service.py:14`. The ECDSA code path is never called. No upstream fix exists. Revisit only if auth moves to ES256/ES512. |
| `transformers` 4.46.1 (~30 CVEs at review time) | `requirements/local-llm.txt` for optional local ML features | **Deferred in the recorded review** | The chat provider is Sarvam and does not load local Qwen. Local embeddings, translation, or speech may still exercise parts of the ML stack. Upgrade and regression-test the bundle before expanding those paths; never load user-supplied models. |
| `accelerate` 1.14.0 — CVE-2026-69112 | `requirements/local-llm.txt` | **Low risk today** | Local-ML stack only; no fix version published yet. Track with the `transformers` bump. |
| `protobuf` 4.25.9 — PYSEC-2026-1805 (recursion DoS) | transitive via the ML stack | **Low risk today** | Only parsed inside local model/tensor loading, not on any request path. Fix (>=5.29.6) will likely come naturally with the `transformers` bump. |

## Summary

- In the recorded review, the listed remote Sarvam request path did not touch
  `transformers` / `accelerate` / `protobuf`, and HS256 auth did not touch
  `ecdsa`. This statement is dated evidence, not a substitute for a fresh audit.
- **One concrete fix applied:** `pip` upgraded.
- **One bundle deferred on purpose:** `transformers` + `accelerate` + `protobuf`
  should be upgraded and regression-tested together before expanding local ML use.
- No dependency was found unused; nothing to remove.
