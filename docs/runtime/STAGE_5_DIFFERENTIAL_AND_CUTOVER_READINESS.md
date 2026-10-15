# Runtime Migration Stage 5: Differential Verification and Cutover Readiness

Date: 9 October 2026; focused continuation verified 12 October 2026  
Status: **PARTIAL; Stage 6 blocked**  
Production backend: `LegacyCompiledAnswerEngine`

## 1. Decision

Stage 5 established repeatable offline differential, endpoint, concurrency,
stream closure, performance, and read-only live integration evidence. It also
found and corrected two readable-path defects: cross-request selection through
a module-global test hook and incorrect source provenance for deterministic
property answers. A generated price unsupported by company evidence was
reproduced and rejected in the readable engine.

Stage 5 cannot approve cutover. No approved sanitized production conversation
corpus, production traffic shadow run, release performance thresholds, or tested
release rollback artifact is available. The 12 October continuation resolved
the `prefer_qwen_response=False` product decision and readable-engine mismatch;
see sections 9-10 for that evidence. The focused browser run in section 14 is
partial and corrected a public provider-error disclosure.

## 2. Evidence and differential method

`scripts/stage5_differential_check.py` feeds both backends identical constructed
workspace and CS API records, request fields, conversation context, and fixed
model output. Every legacy external retrieval/generation call is patched; the
script performs no network calls, database writes, or customer actions. It
records response decision fields and event types, not answer text, prompts,
customer identities, or retrieved source content.

Eleven cases cover project catalogue, location, configuration/price, inventory,
construction, workspace knowledge, opt-out mode, contextual follow-up, missing
data, provider timeout, and approved retail exclusion. Direct JSON/stream
results had one terminal `done` event in both engines for every case.

| Cases | Difference | Classification |
| --- | --- | --- |
| Seven project/workspace/context cases | Only raw `agent_mode` differs. Legacy emits `live_api` or `workflow`, outside the current `AGENT_MODE_ENUM`; readable emits `grounded` or `retrieval`. Provenance, confidence, handoff, retrieval mode, chunk count, and LLM use match. | Legacy label defect; readable uses supported enum. |
| `prefer_qwen_response=False` | The original Stage 5 comparison found legacy generation versus readable fallback. After the approved 12 October correction, both generate from evidence; confidence remains `medium` legacy versus `high` readable. | Product decision resolved; metadata difference reviewed in section 10. |
| Missing source data | Legacy can report `used_llm=True` with no retrieved chunks; readable gives a safe no-evidence fallback. | Approved safety difference; output wording and finalizer effects still need representative review. |
| Provider timeout | Both return a low-confidence, non-LLM fallback. Legacy stream emits `done` only; readable emits `delta`, then `done`. | Semantically equivalent terminal outcome in the buffered property endpoint; event shape differs at the engine boundary. |
| Historical retail request | Readable marks unsupported without retrieval/generation. | Approved Stage 4 product decision. Real-estate catalogue remains supported. |

These comparisons do not claim wording parity or production representativeness.
The Stage 4 corpus remains labelled `constructed_sanitized_scenarios` and maps
upstream-owned discovery, clarification, language, amenities, grounding, and
actions to their existing test suites. No approved production transcript was
found or added.

## 3. Defects reproduced and corrected

1. `use_answer_engine()` previously changed one global backend. A two-thread
   barrier test reproduced a cross-request selection leak. The scoped override
   now uses `ContextVar`; production still defaults to the legacy backend.
2. Deterministic company/project answers were marked `workspace` even when
   backed by CS API chunks. They now report `source_status=live_api` and a
   supported `grounded` agent mode. Workspace direct answers report
   `source_status=workspace` and `agent_mode=retrieval`.
3. A constructed company record with no price let a generated `INR 99,999`
   answer through. The readable engine now rejects currency amounts absent
   from current company price evidence and returns its low-confidence safe
   fallback. A matching evidence price remains permitted. This guard is
   deliberately narrow; nonnumeric semantic hallucinations and derived amounts
   still need representative validation before cutover.

## 4. Endpoint, stream, cache, and state behavior

An isolated FastAPI `TestClient` run selected the readable backend across both
JSON and NDJSON requests, using constructed CS API evidence and an in-memory
session. Both returned the same finalized property answer and `live_api`
status; the stream emitted one `delta` followed by one `done`, and each endpoint
appended one completed turn. The test patched unrelated clarification and
validator reads to keep the run offline; existing upstream suites cover those
components separately.

At the answer-engine seam, closing the readable stream after its first delta
produces no terminal event. The answer and cache entry already exist, so a
subsequent identical request reuses the cached answer without another model
call. Full consumption yields exactly one terminal result. The stream is pull
driven, but the readable engine completes retrieval and generation before its
first delta. The property router buffers all answer text until finalization.

The router appends a property turn when it processes the internal `done`, before
the buffered delta and terminal event are yielded to the client. A disconnect
after computation can therefore leave a persisted turn that the client did not
receive. The synchronous provider call has no cooperative cancellation while
blocked. TestClient does not establish real socket disconnect/backpressure
behavior; a controlled HTTP client/server test remains required.

Stage 3/4 cache tests cover scope dimensions, TTL, deep-copy isolation,
clearing, and concurrent unique keys. Stage 5 adds concurrent backend override
isolation and a 32-request synthetic concurrency benchmark. Cache invalidation
still targets the active scoped backend.

## 5. Live and performance evidence

A non-destructive live script read the configured CS API project list, verified
that the readable deterministic project answer contained a live listed name,
and generated one grounded answer from synthetic support evidence using the
configured Sarvam service. It reported 10 named projects at test time, passed
the CS API and Sarvam checks, and performed zero customer actions. It did not
test live inventory, price quotation, multilingual localization, partial CS
failure, or provider timeout; those are covered only by isolated tests or remain
unverified.

`scripts/stage5_synthetic_benchmark.py` measured 30 warm unique requests per
backend under the same mocked sources, with 32 unique requests on eight threads.
The final local run reported:

| Measure | Legacy | Readable |
| --- | ---: | ---: |
| Cache miss p50 / p95 | 3.775 / 4.146 ms | 0.078 / 0.101 ms |
| Cache hit p50 / p95 | 0.095 / 0.110 ms | 0.033 / 0.043 ms |
| First delta p50 / p95 | 3.801 / 4.102 ms | 0.079 / 0.101 ms |
| Stream completion p50 / p95 | 3.846 / 4.150 ms | 0.079 / 0.102 ms |
| 32 requests, eight workers | 81.006 ms, 32 success | 83.542 ms, 32 success |
| Cold module import median / traced peak | 1,395.382 ms / 21.637 MiB | 682.019 ms / 12.973 MiB |

Cold imports used three fresh Python processes per module. These timings omit
real CS API, Sarvam, database, browser, and production traffic latency. They
are diagnostic comparisons, not release thresholds or a speedup claim.

## 6. Security and side effects

No Stage 5 check created a ticket, callback, visit, booking, CRM operation, or
payment. The offline comparator patches external retrieval/generation and calls
only the answer-engine seam. The endpoint test substitutes an in-memory
conversation session. The live script performs read-only CS API calls and one
synthetic Sarvam request. Existing authentication, authorization, feature-flag,
clarification, live-data enforcement, trace sanitization, and local action
tests remain part of the backend suite. No production traffic shadowing ran.

The currency guard strengthens one checkable property-fact boundary. Broader
prompt-injection resilience, location/configuration claim verification, cache
privacy under real concurrent traffic, and action-side-effect safety in a true
shadow environment remain release acceptance work.

## 7. Rollback and Stage 6 prerequisites

The in-process scoped override restores `legacy_compiled` after readable tests;
clean application import and the legacy interface suites pass. That verifies
the selection seam in a non-production process. No deployment backend switch,
tagged release artifact, package install, database recovery, or real rollback
was performed.

For a future cutover, prepare an immutable Python 3.12 release artifact with
both bytecode files and the loader, record its hashes and dependency lock,
test both assist endpoints and stored conversation markers on a disposable
environment, and verify that restoring the artifact resumes legacy answers
without schema or state loss. Restarting processes clears in-memory answer
caches; persisted conversation state remains in SQLite and needs a compatibility
test. Document and rehearse the actual deployment-specific restart/traffic
procedure before release.

Before Stage 6 authorization, supply approved sanitized production cases and reviewed
semantic differentials, run a controlled disconnect/backpressure test, set
release latency/error/grounding thresholds, complete live property and
multilingual acceptance, and test a recoverable release artifact. Proposed
thresholds for review: zero critical grounding/security/state regressions,
zero duplicate side effects, one terminal event on successful streams, no
cross-customer cache reuse, and no material p95/error-rate regression against
a same-environment live baseline. These are proposals, not approved criteria.

## 8. Verification summary

| Check | Result | Evidence class |
| --- | --- | --- |
| Stage 5 differential, concurrency, provenance, price-guard, cancellation, and endpoint tests | 7 passed | Constructed/offline and mocked endpoint |
| Full backend suite inside network sandbox | 1,965 passed, 182 subtests passed, 1 setup error | Automated; live CS API setup denied by sandbox |
| Exact CS API-backed regression outside sandbox | BLOCKED: two setup attempts timed out after 2.5 seconds | Live integration, not counted as passed |
| Read-only CS API project and grounded Sarvam probe | Both passed; 10 live project names observed; zero customer actions | Live integration with synthetic input |
| Local comparable benchmark | Completed; table above | Synthetic/mocked, not production |
| Ruff, Python compilation, clean process import, `git diff --check`, both runtime SHA-256 hashes | Passed | Static/local integrity |

The reverse-amenity HTTP test's setup error is isolated to fetching the live
project list and does not indicate a test assertion failure. It remains
**BLOCKED**, despite the separate successful CS API probe. The two runtime
hashes match the Stage 3/4 recorded values. No frontend/browser build or real
socket disconnect test was run.

## 9. Stage 5 continuation before the focused cleanup fix (12 October 2026)

The product owner approved grounded Sarvam generation when
`prefer_qwen_response=False` and deterministic handling cannot adequately answer.
The flag is not a blanket generation ban. `ReadableAnswerEngine.answer()` now
uses the existing generation path whenever retrieval provides chunks and no
deterministic handler answered. Existing handler precedence, no-evidence
fallback, prompt, echo check, property-price evidence check, provider-error
fallback, cache scope, and stream adapter remain in force. No provider or
production backend selection changed. Both preference modes passed mocked
JSON/NDJSON property endpoint tests for deterministic and generated answers,
plus direct generated-answer tests. The
endpoint opt-out branch still uses the native compatibility pipeline; the
mocked endpoint test isolates that pipeline's independent validator read.

The eleven-case offline comparison now finds `used_llm=True` in both engines
for the opt-out support-policy case, with one remaining metadata difference:
legacy confidence `medium` versus readable confidence `high`. Both retain
workspace provenance, no handoff, three chunks, and one stream terminal event.
The seven direct project/workspace/context cases still differ only in legacy
`agent_mode` labels. Missing evidence still gives the readable safe fallback;
provider timeout still gives equivalent low-confidence terminal outcomes with
different engine-level delta shape; the approved retail exclusion remains.
These are constructed comparisons, not production-sample or wording parity.

The focused Stage 4/5 suite passed 49 tests after updating the constructed
opt-out fixture for the approved behavior. The first unrestricted full backend
run had 1,973 passed, 182 subtests passed, one obsolete fixture assertion
(corrected), and one live CS API setup error from sandbox socket denial. The
final full backend run with `CI=1` (which skips the explicitly live test)
passed **1,976 tests and 182 subtests, with one skipped**. Ruff on changed
Python files, Python compilation, clean application import without loading the
compiled service, the frontend build/type check, and `git diff --check` passed.
No browser session was run.

The
read-only reverse-amenity test was rerun outside the sandbox: its project-list
connection timed out after 2.5 seconds, before HTTP response or assertions.
The standalone CS API probe likewise timed out on its first project-list read;
the exact live regression remains **BLOCKED** and current CS API acceptance is
unverified. An independent synthetic Sarvam call returned a nonempty response.
No timeout was raised or assertion weakened to turn the live test green.

The refreshed synthetic benchmark used the same constructed records and 30
warm unique requests per backend. Legacy/readable cache-miss p50/p95 were
3.631/4.201 ms and 0.096/0.112 ms; cache-hit p50/p95 were 0.097/0.109 ms
and 0.040/0.044 ms. First-delta p50/p95 were 3.566/4.660 ms and
0.097/0.106 ms. Stream completion p50/p95 were 3.610/4.710 ms and
0.097/0.107 ms. Thirty-two unique requests on eight workers all succeeded;
elapsed times were 76.144 ms legacy and 116.532 ms readable. Cold import
medians were 1,670.250 ms legacy module and 808.124 ms readable interface;
traced peak memory medians were 21.646 and 12.972 MiB. These measurements
exclude real CS API, Sarvam, browser, and production traffic. Variance between
runs is material, especially concurrent completion. No approved performance
threshold exists. Proposed release criteria remain zero critical grounding,
security, state, or duplicate-action regressions; one terminal event on normal
streams; no cross-customer cache reuse; and no material p95/error-rate regression
against a same-environment live baseline. Product/engineering approval and a
baseline are still required.

`scripts/stage5_socket_stream_check.py` exercised the real NDJSON route through
loopback Uvicorn with synthetic, action-free events and in-memory persistence.
A normally completed stream, read with 100 ms pauses between lines, emitted two
deltas and exactly one `done`, appended one turn, and closed its producer. A
client disconnect after the first delta did **not** run the synthetic producer's
`finally` cleanup within two seconds. This is a reproducible cancellation gap
for the synchronous streaming path; interrupted real Sarvam generation, large
payload backpressure, property buffering after disconnect, and cache effects
over a real socket remain unverified. The synthetic producer cannot establish
provider cancellation. Do not call stream-disconnect acceptance passed.

Only the constructed scenario corpus is available for this migration; no
approved sanitized production conversations were supplied. Existing browser
servers were not running, so no customer-browser acceptance was executed;
the successful frontend build is static evidence only.
Scoped backend restoration remains tested in process, and both original and
patched runtime files remain present. There is no immutable release artifact,
disposable deployment rehearsal, tested restart/traffic restoration, or stored
conversation rollback compatibility evidence. The rollback procedure in section
7 is therefore a proposal, not a tested release recovery.

**Current status: PARTIAL. Stage 6: BLOCKED.** The opt-out product decision is
resolved, while production-sample differentials, socket disconnect/cancellation
remediation and high-volume backpressure, approved performance thresholds,
current CS API-backed live acceptance, browser acceptance, and a tested release
rollback remain open. Production stays on `LegacyCompiledAnswerEngine`.

## 10. Focused blocker resolution (12 October 2026)

### Disconnect cleanup: reproduced and corrected

The earlier socket finding was a real cleanup defect, not merely a slow test.
A focused loopback regression reproduced that closing the client connection
after the first synthetic NDJSON delta left both the upstream event generator
and the request's data API trace open for over two seconds. The route had passed
a synchronous generator directly to Starlette `StreamingResponse`. Installed
Starlette 1.6.0 wraps synchronous iterators in a thread pool but does not close
the iterator on this disconnect path.

`routers/assist.py` now closes the route generator in a cancellation-shielded
response finalizer. The route generator also closes the upstream orchestration
iterator before ending its data API trace. The same real-socket test now passes:
the normal stream emits two deltas and exactly one `done`; a client that closes
after the first delta causes both cleanup signals within two seconds and adds
no completed turn. Reading a normal stream with 100 ms pauses between lines
also completes. The test uses synthetic events and in-memory persistence, so
it does not establish kernel-level high-volume backpressure or interruption of
a blocked synchronous Sarvam call. That provider call has no cooperative
cancellation; on disconnect, cleanup may wait for an in-flight call to return.
Those limits remain Stage 5 acceptance work.

The targeted socket, endpoint, and differential checks passed **6 tests**.
The full backend suite with `CI=1` passed **1,977 tests and 182 subtests**,
with the explicitly live CS API test skipped. Ruff, Python compilation, and
`git diff --check` passed on the focused changes.

### CS API timeout: no application change

The exact live reverse-amenity regression and the separate read-only project
probe previously timed out during TCP connection, before any HTTP response.
The current client constructs a company-scoped GET, uses configured or
administrator-saved connection settings, and passes the configured 2.5-second
timeout to `urllib`. This evidence does not identify an HTTP contract or
application parsing defect. Service availability, the configured network path,
and access from an approved environment must be checked by the operator; the
current live regression stays **BLOCKED**. No timeout, endpoint, credential,
snapshot, or application behavior was changed. The live calls were not repeated
in this focused continuation because the earlier connection failures already
pinpointed the current blocker.

### Confidence difference: no code change

The constructed opt-out case still returns `medium` from legacy and `high` from
readable. Both use the same evidence count, `used_llm=True`, workspace source,
and `handoff_recommended=False`. The readable label follows its documented
score heuristic; the legacy label follows its separate compiled policy. Both
values fit the response type. Current answer-evidence finalization triggers a
handoff only for `low`, and the customer chat UI does not display this label.
Staff knowledge views and API consumers can see the metadata difference, so it
remains a reviewed wording/metadata differential rather than proven behavioral
parity. No existing contract requires the readable score to imitate the blob.

### Remaining release evidence

The available Stage 4 corpus and Stage 5 differential cases are constructed;
there is no approved sanitized production-conversation corpus in the inspected
repository. Synthetic timing comparisons do not set a production SLO, and no
latency/error/grounding threshold has product and engineering approval. The
checkout has no Git tags or inspected release artifact that can serve as a
tested rollback; the previously documented scoped backend restoration is an
in-process check only. Supply representative authorized cases, approve release
thresholds with a same-environment baseline, provide a reachable CS API path,
and rehearse recovery of an immutable release with stored conversation state
before Stage 6 can be considered. No new infrastructure or production traffic
was created for this review.

**Current status: PARTIAL. Stage 6: BLOCKED.** The synchronous stream cleanup
defect is fixed; real-provider interruption and high-volume backpressure,
current CS API-backed acceptance, production cases, approved thresholds, and
release rollback remain unverified.

## 11. Final focused technical check and release handoff (12 October 2026)

The existing loopback probe was extended with a controlled blocked provider
iterator and a 512-event, 32 KiB-per-event synthetic stream. The blocked case
uses the real general-chat orchestration path with only Sarvam replaced by a
test iterator. After the client disconnected, the synchronous call kept waiting:
its provider iterator had **not** closed before release. Once released, the
provider iterator and request trace closed within two seconds. No terminal
event was reached and no turn was persisted. This establishes a bounded
cleanup path after an in-flight synchronous call returns; it does **not** show
immediate cancellation of the external call or bound the duration of a real
network stall. The provider's HTTP client owns its response context and read
timeout; real-provider disconnect behavior remains unverified.

With the bulk client paused for 300 ms after its first delta, the producer had
advanced four of 512 possible 32 KiB events (16 MiB if fully consumed). It
stopped after disconnect, closed its iterator and trace, and saved no turn. A
separate request completed concurrently with one terminal event and its own
saved turn. A completed 128-event stream (1 MiB of synthetic deltas), read with
5 ms pauses per line, emitted one terminal event and closed its producer. Each
synthetic request started one producer. This is evidence of bounded loopback
backpressure and request isolation; process peak memory, real provider output,
property buffering, and production traffic were not measured. No application
defect or code change was justified by these checks. The targeted socket
regression passed **1 test**.

| Release prerequisite | Available evidence | Missing evidence or decision | Code work now | Gate |
| --- | --- | --- | --- | --- |
| Reachable CS API | Earlier read-only probe passed; latest project-list and reverse-amenity attempts timed out during TCP connect | Operator-approved reachable network/service path and current read-only CS API acceptance | None demonstrated | Stage 5 and Stage 6 |
| Representative conversations | Constructed Stage 4 corpus and 11 Stage 5 differential cases | Approved sanitized production examples and reviewed contract differences | None until examples are available | Stage 5 and Stage 6 |
| Performance acceptance | Synthetic benchmark and bounded loopback backpressure result | Same-environment live baseline and approved p95, error, grounding, and resource limits | None demonstrated | Stage 5 and Stage 6 |
| Recoverable release | In-process backend restoration test; no Git tag in this checkout | Immutable known-good artifact or revision, then authorized non-production restart and stored-state rollback rehearsal | Release preparation, outside this check | Stage 5 and Stage 6 |
| Browser acceptance | Current local readable-backend chat, project choice, price follow-up, and stream-to-JSON recovery passed; synthetic inventory failure UI passed; configuration detail returned unavailable | Finish configuration and inventory acceptance with responsive live data, plus approved representative cases | Public provider-error disclosure was fixed; no frontend defect demonstrated | Stage 5 and Stage 6 |
| Real provider interruption | Controlled blocked-iterator test shows cleanup after release | Authorized non-production observation of slow/disconnected Sarvam stream and resource bound | None demonstrated | Stage 5 and Stage 6 |

The CS API, production-sample, performance, browser, provider, and release
rehearsal items require the named access, approved evidence, or release artifact.
No live service was retried and no release infrastructure was created here.

**Stage 5: PARTIAL. Stage 6: BLOCKED.** The minimum next action is to provide a
reachable approved CS API environment and representative sanitized production
cases, then agree release thresholds and an authorized rollback rehearsal.

## 12. Focused live CS API acceptance (12 October 2026)

The effective CS API configuration came from the saved administrator override,
not the environment defaults. Its key and positive company ID were configured;
the endpoint used a private-network HTTP address and the existing 2.5-second
timeout. Snapshot fallback was enabled in effective configuration. No credential,
URL, company ID, project name, price, or customer record is recorded here. The
focused read-only probes disabled snapshot fallback **in their own processes**
to require fresh HTTP evidence; they did not change saved or production settings.

The exact previously blocked regression,
`tests/test_reverse_amenity_search.py::AmenitySearchOverHttpTests::test_reverse_amenity_search_is_grounded_in_every_language`,
passed twice outside the network sandbox, including once after the focused code
change. Its existing assertions were preserved. This resolves its prior TCP
connection timeout in this execution environment. The test checks that any
listed project names belong to the fetched catalogue; it does not itself assert
that each language returns a nonempty list or that every upstream read was fresh
HTTP. Those stronger claims are not inferred from its pass result.

Fresh, snapshot-free HTTP reads succeeded for the project catalogue, one
project's wings and typologies, and the typologies used by the configuration and
estimate tool. The readable engine returned deterministic, company-evidenced
catalogue and project-detail answers; pricing named a base rate and final-quote
exclusions. Its direct JSON result and stream adapter agreed with exactly one
terminal event. A separate synthetic price request through both assist routes,
with an in-memory conversation session and readable backend selected only for
that process, returned HTTP 200, matching final answers, `source_status=live_api`,
company evidence, zero failed/snapshot/inventory calls, and one NDJSON `done`.
The endpoint used the existing grounded price shortcut, so that route result
verifies shared completion and delivery; the direct readable-engine check
verifies the Stage 4 engine. Sarvam was used for turn analysis on the endpoint
path, but a separate new Sarvam generation acceptance was outside this focused
CS API task.

One live inventory endpoint timed out at the configured 2.5 seconds in the
initial tool check and on one focused recheck. The typed inventory tool returned
`unavailable`/`failed` with no evidence; no availability claim was accepted.
This is a request timeout on that endpoint after other CS API reads
succeeded; the probe did not isolate its connect versus response-read phase.
It is not proof of an application parsing or authentication defect. Live
inventory and availability acceptance remain **BLOCKED**. An unknown project
returned `empty` with no evidence, and the unsupported cost-sheet tool returned
`blocked` without a network call. The estimate tool produced live evidence for
supported per-square-foot rate records; it does not establish a final cost sheet
or inventory availability.

The live timeout exposed one application defect: a price-only query also triggered
an inventory fetch. When that unrelated fetch timed out, retrieval lost otherwise
valid typology price evidence and the readable engine fell back. A new synthetic
regression reproduced the failure first. `services/acrobuild_company_service.py`
now reserves inventory reads for availability and other inventory intents, while
price-only queries use typology evidence. A combined price-and-availability query
still requests inventory. The regression then passed, and one snapshot-free live
price recheck selected `project_detail`, used company evidence, stated the base
rate with final-quote exclusions, made zero inventory calls, and returned one
matching stream terminal result. No timeout or assertion was weakened.

Focused automated checks: **263 passed, 1 explicitly live test skipped under
`CI=1`, and 15 subtests passed** across the readable engine, Stage 4/5 corpus,
endpoint, failure, property-tool, unsupported-capability, and amenity suites.
The full backend suite with `CI=1` passed **1,978 tests and 182 subtests, with
one explicitly live test skipped**. Ruff and `git diff --check` passed. The exact live reverse-amenity regression
passed separately outside the sandbox after the change. No production
conversation corpus, browser session, production traffic, release
rollback, or real-provider interruption check was run for this focused task.

**Stage 5: PARTIAL. Stage 6: BLOCKED.** Current catalogue, detail, BHK,
base-pricing, estimate, and JSON/NDJSON price-delivery evidence is stronger; live
inventory remains blocked by the CS API timeout. The other Stage 5 prerequisites
in section 11 remain open, including approved production samples, thresholds,
current browser acceptance, real-provider interruption, and a tested release
rollback. Production remains on `LegacyCompiledAnswerEngine`.

## 13. Focused inventory timeout diagnosis (12 October 2026)

The current inventory operation is the documented, company-scoped, read-only
`GET /api/cs/{companyId}/wings/{wingId}/inventory?availableOnly=true`. The wing
ID comes from the successful project-wings response. The client supplies its
existing server-side `apiKey` header and 2.5-second timeout. The configured
connection was present; project and wing reads succeeded in the diagnostic
process. No endpoint, parameter, credential, or timeout change was made.

One additional approved inventory request was instrumented in an isolated
process with snapshot fallback disabled. TCP connection completed in about
**16 ms**. The request then timed out inside `HTTPConnection.getresponse()`
while awaiting response headers; the underlying cause was `TimeoutError`. No
inventory HTTP status, response headers, body, or fresh inventory evidence was
received, and no snapshot supplied data. This establishes a **post-connection
response timeout**, narrowing the prior undifferentiated request timeout. It
does not distinguish slow CS API processing from a post-connection network
stall. The repository's request construction matches its documented inventory
contract; the absence of an HTTP response prevents confirmation of the remote
endpoint's current behavior. There is no demonstrated application defect to
correct or basis to raise the customer-facing timeout.

The relevant offline property-tool, readable scenario, snapshot/failure, and
price-isolation suites passed **119 tests**. These tests establish that failed
or unloaded inventory produces no accepted availability evidence and that price
retrieval remains independent of inventory. They are mocked or constructed
checks, not live inventory acceptance. No application code changed in this
diagnosis, so the full backend suite was not repeated.

**Live inventory retrieval: BLOCKED. Inventory grounding acceptance: BLOCKED.**
Stage 5 remains **PARTIAL** and Stage 6 remains **BLOCKED**. A responsive,
approved inventory endpoint is needed before live availability, scope, and
JSON/stream grounding can be accepted. The other release prerequisites listed
in section 11 carry forward unchanged. Production remains on
`LegacyCompiledAnswerEngine`.

## 14. Focused browser acceptance (12 October 2026)

**Browser acceptance: PARTIAL.** An existing local Vite frontend and a temporary
local ASGI server were used with the existing Playwright CLI. The ASGI wrapper
selected `READABLE_ANSWER_ENGINE` within each request and kept conversation
history in memory for this isolated check. The production backend selection and
database were not changed. The browser was not connected to production traffic.

The customer opened chat, sent a general greeting, and received one completed
NDJSON reply from the configured Sarvam path. A project-list question displayed
selectable project options. Selecting one option produced a project detail
answer; the next question about that project's 2 BHK price retained the chosen
scope and displayed a base-rate answer with quotation limits. Each observed turn
ended with one customer message, one bot message, and an enabled input. These
checks exercise browser rendering, contextual follow-up, and the isolated
readable selection. This browser run did not separately prove fresh CS API HTTP
provenance for every project field; saved snapshot fallback was not disabled.

A subsequent configuration question returned the established safe "Live
property data is unavailable" reply with the browser's failed-answer notice.
Configuration details therefore did **not** pass in this browser session. No
cause beyond the unavailable property-data result was established. The blocked
inventory request was not repeated. A controlled synthetic NDJSON failure reply
showed that the chat displays unknown availability without claiming units; this
is **mocked browser UI evidence**, not live inventory acceptance.

For transport recovery, a browser route intentionally reset one streaming
request. The existing frontend then called the JSON assist route, displayed one
completed answer, and accepted a subsequent normal streamed message. This
checks whole-request stream failure and recovery; it does not establish partial
real-provider interruption or resource limits. No ticket, visit, callback, or
booking action was submitted, and the observed replies made no confirmation
claim. Action confirmation behavior remains unverified in this browser run.

The initial local sandbox run also reproduced a customer-facing defect on a
general Sarvam failure: the chat displayed the raw provider exception. Both
JSON and streaming general routes used the same public failure builder.
`graph/main_orchestrator.py` now returns a generic customer-safe answer and
`assist_error` while preserving failed status and handoff metadata. A focused
regression first failed on the raw exception, then passed for both routes after
the fix. The sandbox network restriction is only the trigger used to expose the
defect; it is not live-provider failure acceptance. The focused backend set
passed **13 tests**. No frontend source was changed.

Live inventory, configuration detail in this browser run, approved sanitized
production conversations, agreed release thresholds and production performance,
real-provider interruption, and a tested release rollback remain open. Current
browser acceptance improved from unverified to **PARTIAL**. **Stage 5 remains
PARTIAL; Stage 6 remains BLOCKED.** Production remains on
`LegacyCompiledAnswerEngine`.

## 15. Final regression check after Sarvam error handling (12 October 2026)

**Verification: PASSED for the scoped code change.** The shared general-LLM
failure builder returns fixed customer-safe `answer` and `assist_error` values;
it retains `source_status=failed`, low confidence, and handoff metadata. The
existing Sarvam facade (`qwen.py`) still records generation and stream failures
through the internal `chatbot.llm` logger with provider, mode, duration, and
exception details. Router output does not copy those exception details into the
customer payload. No application code or test was changed in this check.

The targeted backend set passed **35 tests and 13 subtests**. The complete
backend suite with `CI=1` passed **1,979 tests and 182 subtests**, with **one
explicitly live test skipped**. A disposable, synthetic `TestClient` check of
both HTTP assist routes confirmed that failed JSON and NDJSON responses had
matching safe answers, no injected exception marker in public fields or stream
events, and exactly one NDJSON terminal event. The same check confirmed that
normal JSON and multi-piece NDJSON answers still matched and reported
`used_llm=True`. Ruff, Python compilation, and `git diff --check` passed. No
browser session or blocked live API call was repeated.

These results verify regression safety for the local code and synthetic
provider failures. They do not establish current live inventory, approved
production-conversation parity, production performance thresholds, real-provider
interruption behavior, or a tested release rollback. **Stage 5 remains PARTIAL;
Stage 6 remains BLOCKED.** Production continues to select
`LegacyCompiledAnswerEngine`.

## 16. Independent-QA defect fixes (13 October 2026)

**Scope: two confirmed customer-facing defects only, under separate explicit
authorization.** `docs/runtime/STAGE_5_INDEPENDENT_CHATBOT_QA.md` confirmed
two reproducible defects during a resumed independent QA pass; both were
fixed and verified in this focused follow-up. No production backend
selection changed, no compiled runtime was touched, and the unverified
"guarantee/book today" concern (QA finding D2) was explicitly left
unchanged.

### Defect 1 — exploratory greeting misrouted to a property-data dump

**Root cause.** The turn analyzer (`services/turn_analysis_service.py:analyze_turn`,
backed by a live Sarvam LLM call) correctly classified "Hi, I'm exploring
homes. What can you help me with?" as `intent="general"`. Downstream,
`routers/assist.py:_prepare_lookup_turn` unconditionally overrode that back
to `intent="property"` whenever `is_reverse_amenity_query()` matched the
issue text. That function is a deliberately cheap **shape-only** test
(`services/amenity_search_service.py:168-174`): it looks for a subject word
like "projects"/"homes"/"apartments" plus a cue word like "which"/"what", with
no check that an actual amenity was named — the docstring says that check is
"checked separately against live data by the caller." The override site in
`_prepare_lookup_turn` was not that caller; it used the shape test directly,
so any message containing both "homes" and "what" was promoted to `property`,
including a plain greeting.

**Fix.** `routers/assist.py` now imports `is_amenity_lookup_query` (already
used correctly elsewhere, e.g. `api_context.py:1269`) and the override
condition is `is_reverse_amenity_query(turn.property_issue) and
is_amenity_lookup_query(turn.property_issue, live_amenity_names(live_amenity_index()))` —
requiring the live catalogue to actually contain the named amenity before
flipping intent. This mirrors the exact gate `build_grounded_amenity_search_assist`
already applies before answering, so a genuine reverse-amenity question
("which projects have a gym?") is unaffected, while a shape-only match with
no real amenity (a greeting, or "which projects do you personally like
best?") no longer gets promoted.

**Files changed:** `routers/assist.py` (one import added, one `elif`
condition tightened; see inline comment at the call site for the rationale).

**Tests added:** `tests/test_greeting_routing.py` (new file, 7 cases):
exploratory greetings and small talk stay `general`; a genuine reverse-amenity
query still routes to `property`; a same-shape message with no live amenity
named stays `general`; an explicit property request is unaffected; a greeting
combined with a real property request still routes to `property`. Verified
to fail against the pre-fix code (2 of 7 cases failed, isolating the exact
defect) and pass after the fix.

**Verification:**
- `tests/test_greeting_routing.py` — 7 passed.
- `tests/test_greeting_routing.py tests/test_reverse_amenity_search.py
  tests/test_chat_quick_replies.py tests/test_failed_lookup_new_intent.py
  tests/test_haystack_conversation_pipeline.py tests/test_general_local_llm.py
  tests/test_public_cs_api_trace.py` (`CI=1`) — 148 passed, 1 skipped (live
  acceptance, expected under `CI=1`), 21 subtests passed.
- `ruff check routers/assist.py tests/test_greeting_routing.py` — clean.
- `git diff --check` — clean (only LF/CRLF line-ending warnings).
- Direct reproduction against the live Sarvam analyzer and live CS API
  (`python -c "from routers.assist import _prepare_lookup_turn, ..."`)
  confirmed the greeting now resolves to `intent="general"` end to end, and
  "Which projects have a gym?" still resolves to `intent="property"`.

### Defect 2 — discovery shortlist prices and disclaimer hidden from customers

**Root cause.** `src/lib/customerChatContract.ts:visibleMessageText()`
truncated a bot message to the text before its first bullet whenever every
quick reply lacked an `action` field, on the assumption that the bullets were
always a pure restated list of the button labels (true for
`services/property_clarification_service.py:_explore_project_payload`, whose
bullets are exactly `"- {project name}"` with one matching quick reply each).
The discovery shortlist builder
(`services/discovery_slot_service.py:_results_draft`, lines 594-611) does not
fit that assumption: its bullets carry real content —
`"- {project}: estimated base amount from INR {amount}"` — and the mandatory
pricing disclaimer plus a closing prompt follow the bullets as additional
non-bulleted lines. Because the shortlist's quick replies also lack an
`action` field, the existing truncation fired and discarded every price, the
disclaimer, and the prompt, leaving the customer looking at a single
sentence ending in "(estimated base amount):" with no numbers.

**Fix.** `visibleMessageText()` now calls a new helper,
`bulletsAreRedundantWithQuickReplies()`, which only treats the bulleted
section as truly redundant when every line from the first bullet onward is
itself a bullet whose stripped content exactly matches one quick-reply label
— no extra text on the bullet line, and no trailing lines after the bullets.
Truncation only happens when that holds; otherwise the full backend text is
shown. No backend pricing calculation, disclaimer text, or quick-reply
behavior was changed.

**Files changed:** `src/lib/customerChatContract.ts` (new helper function;
`visibleMessageText()` now calls it before truncating).

**Tests added/updated:** `src/lib/customerChatContract.test.ts` — the
existing "shows only the prompt..." case was corrected to supply a matching
quick reply for every bulleted project name (the original fixture only
supplied one of two, which is not how the backend ever actually shapes this
response); two new cases added: bullets carrying real price/disclaimer
content are never truncated even with matching, action-less quick replies,
and a fallback list is kept unabridged when a quick reply only partially
covers the bulleted names.

**Verification:**
- `npx vitest run src/lib/customerChatContract.test.ts` — 7 passed.
- `npx vitest run` (full frontend suite) — 185 passed across 19 files.
- `npx tsc --noEmit -p tsconfig.json` — clean.
- `npm run build` — succeeded (vite build, 89 modules transformed).
- Direct reproduction against the real backend response captured during the
  independent QA pass (the live B3 discovery-shortlist payload, 9 priced
  projects plus the disclaimer) confirmed `visibleMessageText()` now returns
  the full answer text unabridged, including every price line and the
  exclusions disclaimer; this check used a temporary fixture/test file that
  was deleted immediately after confirming the result (not part of the
  committed diff).
- `git diff --check` — clean (only LF/CRLF line-ending warnings).

### What was not touched

- The suspected, unverified D2 QA finding ("Can you guarantee a 2 BHK is
  available to book today?" reusing a grounded availability answer without
  an explicit no-guarantee caveat) was explicitly out of scope and was not
  investigated further or changed.
- Production backend selection remains `LegacyCompiledAnswerEngine`; neither
  compiled runtime file was touched; no Stage 6 work was performed; no
  commit, deploy, or reset was made. The pre-existing dirty working tree from
  the Stage 0-5 migration work was preserved untouched aside from the four
  files listed above.
- The backend discovery/pricing logic and the amenity-search live-data
  grounding behavior were not changed — only the two narrow decision points
  (an intent-override condition, and a frontend display-truncation
  condition) that caused the observed customer-facing symptoms.

## 17. Final verification and full-suite permission-error follow-up (13 October 2026)

**Scope: verification only, no application code changed.** The prior full
backend run (section 16 verification) reported 1,946 passed and 40 errors,
all `PermissionError: [WinError 5] Access is denied:
'C:\Users\anish\AppData\Local\Temp\pytest-of-anish'`. This follow-up
determined the exact cause before dismissing or acting on them.

**Cause.** `os.listdir()` on
`C:\Users\anish\AppData\Local\Temp\pytest-of-anish` fails with the same
`PermissionError` outside of pytest entirely, while `os.stat()` on the same
path succeeds — the directory exists but cannot be enumerated under its
current ACL. No pytest, QA-server, or other related process held an open
handle on it at the time (checked via `psutil.process_iter`), so this is a
pre-existing Windows permission state on that shared per-user pytest base
temp directory, not a lock contested by this session's own work and not
caused by either of the two QA fixes. Every one of the 40 errored tests used
the `tmp_path` pytest fixture (which roots itself under that directory) and
failed during fixture setup, before any test body or assertion ran; none of
the 40 touch `routers/assist.py`'s routing logic or
`src/lib/customerChatContract.ts`.

**Resolution used.** Per AGENTS.md's instruction not to pass `--basetemp` or
create a root-level project temp directory, the fix was to point the
`TEMP`/`TMP` environment variables at a writable directory outside the
project (this session's existing isolated scratchpad path) for the duration
of the run, which is what `tmp_path` roots itself under when no `--basetemp`
is given. No `--basetemp` flag was passed and no directory was created
inside the repository.

- Confirming rerun, the two previously all-failing files only
  (`tests/test_conversation_history_endpoint.py`,
  `tests/test_cs_api_settings.py`) with `TEMP`/`TMP` redirected: **15
  passed**, 0 errors.
- Full backend suite (`CI=1`, same redirected `TEMP`/`TMP`,
  `python -m pytest tests/ -q`): **1,986 passed, 1 skipped (live
  acceptance, expected under `CI=1`), 182 subtests passed, 0 errors**, in
  133.34s. 1,986 passed vs. the earlier run's 1,946 — exactly the 40
  previously-errored tests now pass; no other count changed.

**Classification of the 40 prior errors: environmental, not an application
defect.** They do not indicate a regression from either QA fix and require
no code change.

**Fix re-verification (unchanged from section 16, reconfirmed clean):**
- `routers/assist.py`, `src/lib/customerChatContract.ts`,
  `src/lib/customerChatContract.test.ts`, `tests/test_greeting_routing.py` —
  byte-for-byte unchanged since section 16.
- `tests/test_greeting_routing.py tests/test_reverse_amenity_search.py
  tests/test_chat_quick_replies.py tests/test_failed_lookup_new_intent.py
  tests/test_haystack_conversation_pipeline.py tests/test_general_local_llm.py
  tests/test_public_cs_api_trace.py` (`CI=1`, redirected `TEMP`/`TMP`) — 148
  passed, 1 skipped, 21 subtests passed (identical to section 16).
- `npx vitest run` (full frontend suite) — 185 passed across 19 files
  (identical to section 16).
- `npx tsc --noEmit -p tsconfig.json` — clean.
- `ruff check routers/assist.py tests/test_greeting_routing.py` — clean.
- `git diff --check` — clean (only LF/CRLF line-ending warnings).

**Files changed in this verification pass: none.** Only diagnostic commands
were run (temporary `TEMP`/`TMP` environment overrides for test invocations);
no source, test, or doc content other than this section and the paired
update to `STAGE_5_INDEPENDENT_CHATBOT_QA.md` was modified.

**Both QA fixes: fully verified**, including a now fully clean full backend
suite with zero errors of any kind.

### Stage 5 impact

Fixing these two defects removes a concrete, previously-undocumented
release blocker for any cutover that depends on discovery shortlists being
usable and on greetings not derailing into a property-data dump. It does not
close the pre-existing Stage 5 gates: no approved sanitized production
conversation corpus, no agreed release performance thresholds, no tested
release rollback artifact, and no current browser/CS-API-backed acceptance
beyond what section 14 already recorded. **Stage 5 remains PARTIAL; Stage 6
remains BLOCKED pending those separate gates and separate authorization.**

## 18. Focused intermittent discovery locality failure

The reported `3BHK` → `Pune` attempts have no retained per-request CS API
trace, so their exact external outcomes cannot be reconstructed. They may have
had different catalogue or typology responses. A deterministic offline test
nonetheless reproduced a genuine application defect on both assist endpoints:
the current Pune project's typology request completed, a Thane project's
typology request failed in the same turn, and the shared live-data guard
replaced the valid Pune budget question with “Live property data is unavailable
right now. Please try again shortly.” The first turn had stored `config=[3]`
and a pending locality selection; the second retained that state. The guard
was correctly conservative about a failed call but could not distinguish an
unrelated Thane read because discovery had searched every area again.

`services/discovery_slot_service.py` now uses the selected locality to filter
the current live project catalogue before reading project typologies. The
locality is still checked against current CS API project records; an invalid or
no-longer-matching area falls back to the existing full search so current
eligible choices can be offered. Budget replies reuse the stored, previously
verified locality. A failure of a required Pune catalogue or typology read
still produces the established safe fallback. The original 3BHK requirement,
server-side slots, pending selection, and budget-question order are preserved.
The change makes no inventory request and does not alter the production answer
engine choice.

Focused HTTP regressions in `tests/test_discovery_flow.py` cover JSON and
NDJSON for: mixed Pune success/Thane failure; a later budget reply while Thane
remains unavailable; required Pune typology failure; and recovery on a new
successful request. Before the fix, both mixed-outcome cases failed with
`source_status=failed`; after the fix, all four parameterized cases pass.
Existing unknown-area, stale-state, snapshot, clarification, and discovery
tests also pass.

- Focused reproduction before correction: **2 failed**, as expected, on JSON
  and NDJSON; the final response was the generic live-data failure despite a
  successful Pune project read.
- Focused new tests after correction: **4 passed**.
- Relevant offline regression set across eight files: **562 passed**, one
  third-party deprecation warning. Ruff on both changed Python files,
  `compileall`, and `git diff --check` passed.
- A broader nine-file run had **616 passed, 2 failed**. The two failures were
  both `test_chat_quick_replies.py::test_both_assist_endpoints_return_project_choices`:
  an unrelated test path attempted the configured CS API from the network
  sandbox and received `WinError 10013`. Neither failure exercised the changed
  discovery branch. These tests were not rerun against a live service; no
  blocked inventory endpoint was called by this investigation.

This removes the demonstrated same-turn mixed-outcome defect. It does not
prove what happened in either original customer attempt, current CS API
availability, or live inventory acceptance. Stage 5 remains **PARTIAL** and
Stage 6 remains **BLOCKED** by the separate external and release gates above.

## 19. Mortgage intent and construction-status answer correction

Independent QA's A2 mortgage question and C3 construction-status follow-up were
reproduced with focused offline tests before correction. A2 matched the generic
`bank` nearby-place detector and returned a location-data limitation. Current
supported sources provide project base pricing but no verified cross-bank
mortgage rates or lender comparison. The unsupported-capability detector now
recognizes mortgage/home-loan rate intent before nearby places and offer
wording. It answers that current rates cannot be verified or compared here;
ordinary nearby-bank questions retain their existing route. No financing
product or partnership was added.

C3 reached the readable project-detail handler with a selected project and
location evidence. Wing-level `constructionStatus` is the supported status
field. When that field was absent, the handler silently omitted the requested
status. It now includes verified wing statuses when present and a scoped
cannot-verify statement for missing status, including partially populated wing
records. It does not infer progress or possession dates. JSON and NDJSON
finalization retain the same answer. `source_status=live_api` describes the
source of the project record, not independent verification of an absent field.

The focused pre-fix run had **5 expected failures**: two mortgage phrasings on
each endpoint and the missing construction-status engine case. After the fix,
the focused run passed **8 tests**. The relevant offline regression set passed
**253 tests**; a separate synthetic JSON/NDJSON construction test passed for
present and absent status. Ruff and `git diff --check` passed. A first broader
test command named a nonexistent test file and collected no tests; it was
corrected before the 252-test run. No live CS API, inventory request, browser
retest, customer action, backend default change, or compiled-runtime change was
part of this correction. Stage 5 remains **PARTIAL** and Stage 6 **BLOCKED** by
the existing external evidence, release gates, and separate authorization.

## 20. Focused browser verification of mortgage and construction corrections

**Browser acceptance: PARTIAL (12 October 2026).** The existing customer chat
ran in Playwright against local Vite and a disposable, synthetic FastAPI
fixture. The fixture selected `readable_v1` per request, kept conversation
history in memory, and served two fictional project records from in-process
data. It made no live CS API, inventory, Sarvam, production, or customer-action
request. Production selection remained `legacy_compiled`.

| Scenario | Customer-visible result | Assessment |
| --- | --- | --- |
| Best mortgage rate across banks | Said it has no verified current mortgage/home-loan rates and cannot compare lenders; no lender, rate, or eligibility was claimed. | **PASS** for relevance and safe wording. Captured NDJSON result used `readable_v1`, `unsupported_capability=mortgage_rates`, and one terminal event. |
| Banks near Example Heights | Returned the established nearby-place/location-data limitation, with no bank location invented. | **PASS** for routing preservation; one NDJSON terminal event. |
| Example Heights, then “What is its construction status?” | Retained Example Heights and displayed fixture wing A's `constructionStatus` value “In progress.” | **PASS** for documented synthetic evidence and browser rendering; one NDJSON terminal event. This is not independent live status verification. |
| Example Gardens with missing wing status | After a named location answer, the pronoun follow-up asked “Which project should I check?” Clicking the offered Example Gardens repeated that prompt. A fresh browser conversation with the explicit question “What is the construction status of Example Gardens?” did the same. | **FAIL**: the customer never sees the intended cannot-verify statement. A direct JSON request reproduced the project clarification (`clarification_entity=project`). |

The engine directly constructs “Construction status for the project was not
provided in the retrieved project records, so I can't verify it.” The current
`clarification_entity()` detector then matches `provide` inside `provided` and
the later `project` in `project records`, interpreting this factual disclosure
as a request to select a project. The full endpoint replaces the correct draft
with a project-choice response. This source-level reproduction isolates the
failure to post-processing, not the fixture's missing status field or browser
rendering. The prior isolated endpoint regression patched clarification and
therefore did not exercise this interaction. No application correction was made
in this verification-only session.

Completed observed NDJSON turns showed one terminal result and no duplicate
answer in the chat. No raw internal exception appeared in the customer-visible
responses. The local page logged unauthenticated staff-session requests and a
help-article CORS error because the disposable fixture used a separate local
origin; these did not prevent chat requests and are not evidence of production
chat behavior. The temporary fixture, its databases, and browser/server
processes were removed after the check. The only retained source/documentation
change from this session is this report.

An initial failed fixture startup exposed an isolation mistake: the imported
admin-settings service still pointed at the ignored local `support_system.db`.
That file's modification time changed at 16:34:08 before the fixture path was
corrected and the successful browser run began. No customer-action endpoint was
called, but the database's exact data-level effect was not established. Its
private contents were not inspected or rolled back. The subsequent successful
run used a separate disposable database for both database and admin-settings
services. This local runtime-artifact limit must not be counted as a clean
database-isolation check.

The missing-status browser scenario is a demonstrated customer-facing blocker
for Stage 5 acceptance. Current live construction status remains unverified;
the previously open production-sample, performance, real-provider, inventory,
and release-rollback gates also remain. Stage 5 is **PARTIAL** and Stage 6 is
**BLOCKED** pending correction, renewed acceptance, the separate gates, and
separate authorization.

### Focused correction: false project clarification after missing status (12 October 2026)

The browser failure above was reproduced by a new test: the legacy prose
detector read `provide` inside `provided` and treated a factual reference to
project records as a selection request. `clarification_entity()` now accepts
legacy selection wording only at the start of a sentence or line and matches
whole-word request verbs. Explicit `clarification_entity` metadata and existing
pending selections still take precedence. The construction answer builder,
project evidence, and grounding policy were not changed.

With synthetic project evidence, JSON and NDJSON now preserve the cannot-verify
answer when wing status is absent, return the verified status when present, and
create no false pending selection. The focused clarification, ambiguity,
project-context, engine, and endpoint suite passed **85 tests and 7 subtests**;
the legacy project/wing/floor/flat/home-type prompts and repeated selection
continuity passed. A full backend run with `CI=1` passed **1,994 tests and 182
subtests**, skipped the explicitly live test, and had **13 failures**. All 13
followed blocked CS API socket calls (`WinError 10013`) in endpoint tests; this
run cannot establish a clean full-suite pass in the network sandbox. No live
CS API or browser acceptance was repeated. The previous local database
isolation incident remains unassessed. The existing private database was not
inspected or intentionally modified; isolation of every test in the broad
suite was not independently established.

Stage 5 remains **PARTIAL**. The earlier browser failure has an offline
correction, but post-fix browser/live construction acceptance and the separate
production-sample, external, performance, and rollback gates remain open.
Stage 6 remains **BLOCKED**.

### Focused test isolation and construction browser check (12 October 2026)

**Isolation: verified for this browser fixture.** A temporary process redirected
the four SQLite paths in `database_service`, `admin_settings_service`,
`macro_service`, and `cs_api_settings_service` to one newly created disposable
database. A connection guard rejected any other on-disk SQLite target.
Application startup and migrations completed under that guard before browser
requests. File logging was disabled; CS API and Sarvam calls used synthetic
in-process evidence/test doubles. The disposable databases were removed after
the fixture processes stopped. This does not assess the earlier `support_system.db` incident,
and it does not establish isolation for the previous full pytest run.

The customer chat ran through local Vite and the isolated FastAPI server with
`readable_v1` selected only in the fixture. Browser-visible NDJSON results:

| Scenario | Observed result | Assessment |
| --- | --- | --- |
| Select Maple Gardens, then ask “What is its construction status?” | “Construction status for the project was not provided in the retrieved project records, so I can't verify it.” No Maple Gardens selection button or repeated prompt appeared. | **PASS** for the post-fix customer-visible missing-status path and project context, with synthetic evidence. |
| Select Cedar Heights, then ask the same follow-up | Displayed the fixture's exact wing A value, “In progress,” with no invented timeline. | **PASS** with synthetic evidence. |
| Ask for “the project” with neither fixture project selected | A controlled synthetic generator requested project clarification; the browser offered both real fixture choices, Cedar Heights and Maple Gardens. | **PASS** for the clarification contract and displayed options; live model choice remains unverified. |
| Select Maple Gardens from that clarification | The old selection question did not repeat, but the response was the generic cannot-confirm fallback instead of the specific missing-status sentence. | **PARTIAL** for resumed-answer specificity; no fabricated status appeared. |

The initial fixture used two names sharing “Example.” Direct readable-engine
execution selected the first project's details for a request naming the second
project because `_project_detail_answer()` accepts any overlapping project-name
token. Shared finalization rejected that mismatched answer and showed a safe
fallback. This is a separate reproducible matching weakness; no application
change was made under this verification-only authorization. The final browser
scenarios used distinct fictional project names to isolate the clarification
fix. The first fixture attempt also omitted completed synthetic CS call traces,
which correctly triggered the live-data guard; that fixture error was corrected
before the final scenarios.

The previous full-suite result remains **1,994 passed, 1 skipped, 13 failed,
182 subtests passed**. The 13 failures all involved blocked CS API socket
access (`WinError 10013`) in the sandbox. No network retry was made because
the prior blocked calls already established that limitation; the suite is
**BLOCKED**, not passed. Current independent live construction-status evidence,
approved production samples, release thresholds, real-provider interruption,
inventory acceptance, and tested rollback remain open. Stage 5 is **PARTIAL**;
Stage 6 remains **BLOCKED** and unauthorized.

## STOP

Stage 5 remains partial. Keep production on `LegacyCompiledAnswerEngine` and
retain both runtime files, loader, patcher, and legacy adapter. Do not start
Stage 6 or production traffic shadowing without separate authorization.
