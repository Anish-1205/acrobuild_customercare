# Final 91-case manual acceptance report

Date: 2026-10-01. Branch: `work/2026-09-09-chatbot-fixes-observability`. Commit: `f5be63c79ade2b88507cacf9613688c6eceb8294` plus the pre-existing dirty working tree.

## Verdict

**All 90 executable manual cases passed.** One case, PRP-004, remains `BLOCKED_BY_LIVE_DATA`. The complete 91-case suite is therefore conditionally accepted; PRP-004 has not passed and the broader backend test suite is not fully green.

| Status | Count |
| --- | ---: |
| PASS | 90 |
| FAIL | 0 |
| BLOCKED_BY_LIVE_DATA | 1 |
| BLOCKED_BY_ENVIRONMENT | 0 |
| **Total** | **91** |

The [final CSV](acrobuild_chatbot_manual_acceptance_final.csv) contains all 91 case IDs, statuses, actual responses/results, notes, and evidence references. The [evidence JSON](acrobuild_chatbot_manual_acceptance_final_evidence.json) contains the captured browser turns, JSON/streaming parity results, before/after server state, live inventory survey, and supplemental browser checks. Every case received a final semantic review; no `REVIEW_REQUIRED` labels remain.

## Previously failing cases

| Case | Final status | Observed result |
| --- | --- | --- |
| AMN-003 | PASS | Badminton search offered Prime and Town. The generic details follow-up retained both buttons and the original amenity request. Selecting Prime in a supplemental real browser turn returned its live amenity list. No unsupported document promise appeared. |
| BLK-002 | PASS | Nearby/distance request returned an explicit verified-data limitation. It did not become project clarification, store a pending lookup, or invent a hospital or distance. |
| BLK-003 | PASS | With live Prime 3BHK pricing context, the answer explicitly said a complete cost sheet and all-inclusive price are unavailable; API base rates were described as partial pricing. It invented no taxes or charges. |
| ERR-006 | PASS | After a controlled CS failure and service recovery, `Hi` returned a general greeting with no stale lookup or raw error. ERR-005 separately confirmed explicit `retry` resumes the original request. |
| PRP-007 | PASS | After real Prime → A → floor 1 → Flat 101 selection, `What will be the total cost?` returned INR 7,776,000–14,580,000 from 1944 sq.ft and INR 4,000–7,500 per sq.ft, explicitly labelled as a base estimate with excluded charges. Scope stayed on Prime. |
| SEC-003 | PASS | The investment question explicitly declined guaranteed appreciation or returns; no project catalogue replaced the limitation. |

PRP-007's formula punctuation rendered as replacement characters in the captured answer. The amounts, inputs, base-estimate label, and excluded charges remained readable; this presentation defect did not change the case verdict.

PST-001, PST-002, and CTX-004 also passed. PST-001 retained the same conversation ID and ordered transcript across two actual reloads (5 and 7 visible messages); a supplemental reload retained all three quick replies, and `2 BHK?` continued in Prime. PST-002 used the actual **Browse all projects** action after completed Emerald discovery: the new ID had no inherited project, discovery, or pending callback state, and `2 BHK?` began fresh locality discovery. CTX-004 changed 3BHK to 2BHK while retaining Pune and the INR 1.5 crore budget in a fresh unselected discovery conversation.

No new manual case failed. The five JSON/streaming parity cases passed on answer, route, clarification, quick replies, source status, pending selection, and discovery fields. Browser-designated cases used `/home`; ERR-001/002/003 used their suite-authorized controlled HTTP regression tests.

## Live-data block and environment

PRP-004 requires a listed BHK configuration with zero available units. A fresh live survey completed for all nine customer-facing projects, their wings, listed configurations, and available inventory. It found no qualifying configuration. No fixture or fabricated inventory was substituted; PRP-004 remains `BLOCKED_BY_LIVE_DATA`.

The local setup used backend `127.0.0.1:8000`, customer UI `127.0.0.1:5173`, an isolated controlled-failure backend/UI on ports 8002/5177, and headless Chrome through CDP. The local `.env` contains the CS API and Sarvam configuration keys; values were not copied into artifacts. Saved CS settings override the environment defaults, and discovery used its default-on setting. Live CS and Sarvam calls succeeded during the clean acceptance run.

An initial attempt stopped after eight cases when the first local Vite process exited. Its SMK-003/DIS-001 browser errors were executor infrastructure errors; that partial attempt was discarded. The frontend was restarted in a persistent process, then all 91 cases were run from the beginning in one clean pass. The controlled-failure server initially lacked outbound socket access in the sandbox; it was restarted with network access, verified against the live CS API, and used for the final ERR/LOG cases. These setup incidents did not change any final manual case verdict.

## Automated checks

| Check | Result |
| --- | --- |
| Focused backend regressions (unsupported capability/endpoints, overstatement, cost, failed lookup/new intent, amenity follow-up, clarification, discovery, callback, history/refresh, error redaction, grounded failures) | 800 passed; 50 subtests passed |
| Full backend suite in sandbox | 1,884 passed, 1 failed, 1 setup error; 182 subtests passed |
| Live CS test isolated with network access | 1 passed; 4 subtests passed |
| Frontend tests | 5 files, 124 tests passed |
| TypeScript check and Vite production build | Passed |
| Ruff | Passed |
| Configured mypy | Passed, 2 configured source files |

The sandbox full-suite setup error was `test_reverse_amenity_search_is_grounded_in_every_language`: outbound CS access raised `WinError 10013`. Its isolated network-enabled rerun passed. The remaining full-suite failure was `test_cs_api_failure_reads_september_snapshot`. The local legacy snapshot belongs to the same company, but the saved effective CS API origin differs from the environment origin, so the fallback is intentionally not used in the sandbox run. In a network-enabled full-suite attempt, that test still failed (it observed 10 cached upstream records versus the fixture's expected 9), while 38 unrelated tests could not create pytest temporary directories because that process lacked access to the default external temp folder. Those 38 errors are a test-environment issue and the network-enabled full run is **not** counted as green. No production or test files were changed to mask these results.

## Source integrity

The tracked diff hash was `122ccb842368201b955b459f7a64f543f2538ce5` both before and after the run. The branch and commit stayed unchanged. The harness also compared application file hashes before and after execution and found them identical. The pre-existing dirty working tree was preserved. This run added the final report, CSV, and evidence JSON; acceptance-only harness helpers and logs under ignored `data/` were used. No application, source, or test changes were introduced.
