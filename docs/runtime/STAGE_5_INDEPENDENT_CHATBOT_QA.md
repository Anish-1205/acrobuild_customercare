# Stage 5 independent chatbot QA

Date: 12 October 2026  
Status: **PARTIAL**; resumed after an interrupted session; no production cutover

## Scope and evidence rules

This is an independent, bounded customer-experience check of the current
chatbot. Scenarios below were selected before responses were observed. Source
contracts in `AGENTS.md`, `docs/CHAT_FLOW.md`, `docs/PRODUCT_STATUS.md`, and the
current routers, frontend, property services, and Stage 5 report define expected
behavior. Historical fixtures are context, not a current fact source. Dynamic
project, price, configuration, and inventory claims require current CS API
evidence or an explicitly disclosed permitted snapshot. A safe fallback proves
failure handling only. No ticket, callback, site visit, or booking is submitted.

## Pre-run expectation ledger

| ID | New customer prompt or action | Expected behavior and evidence class |
| --- | --- | --- |
| A1 | “Hi, I’m exploring homes. What can you help me with?” | A relevant greeting and supported help; no invented property or completed action. Semantic. |
| A2 | “Can you tell me today’s best mortgage rate across every bank?” | State limits of verified current financial data; do not invent a rate. Unsupported capability. |
| B1 | “I need a 2 BHK but haven’t picked an area yet.” | With discovery enabled, ask for an eligible live area or a supported wildcard, preserving the 2 BHK request. Contract plus dynamic choices. |
| B2 | “Anywhere is fine.” | Accept typed wildcard, then collect a free-text budget; do not invent budget-band buttons. Contract. |
| B3 | “My ceiling is 55 lakh.” | Ground any shortlist or base estimate in available catalogue data and disclose exclusions; otherwise report unavailable. Dynamic. |
| C1 | “Which developments can I explore right now?” | Show only names returned by the current catalogue or disclose failed lookup. Dynamic. |
| C2 | Select one offered project. | Establish project scope and answer with supported details; do not silently choose among options. Contract plus dynamic. |
| C3 | “Where is it, and what is its construction status?” | Retain selected project, answer supported parts with evidence, or disclose unavailable parts. Semantic plus dynamic. |
| C4 | “Does this one list any 2 BHK plans?” | Retain selected project and distinguish listed configurations from checked inventory. Dynamic. |
| D1 | “What is the listed base rate for those plans? Is that a final quote?” | Use verified rate evidence, preserve unit and exclusions, and avoid final-quote claims. Dynamic. |
| D2 | “Can you guarantee a 2 BHK is available to book today?” | Do not assert inventory or booking without fresh inventory evidence; use controlled failure evidence only while the inventory endpoint is blocked. Safety. |
| E1 | “Actually, show me options in another area.” | Treat this as a new search rather than silently retaining the earlier project. Contract. |
| F1 | “What about that one?” after a genuinely ambiguous choice. | Ask for a real eligible option when scope is unclear; retain the original intent through a short reply. Contract. |
| G1 | “इस प्रोजेक्ट में 2 BHK की कीमत क्या है?” | Understand native-script Hindi, protect names/numbers, and avoid unsupported pricing. Semantic plus dynamic. |
| G2 | “Is project me 2 BHK ka rate kya hai?” | Handle romanized Hindi within supported language behavior; retain scope and price grounding. Semantic plus dynamic. |
| H1 | Controlled CS API or Sarvam failure, then a new question. | Display safe error without provider internals; permit a subsequent turn. Synthetic failure plus browser UX. |
| H2 | Controlled interrupted stream, then a new question. | No duplicate completed answer; show recovery or interruption honestly and permit continuation. Synthetic transport plus browser UX. |

Result terms: **PASS** means the observed behavior and necessary evidence met the
stated expectation; **FAIL** means a reproducible contract or customer-experience
defect; **BLOCKED** means a required dependency or approved source was absent;
**UNVERIFIED** means available evidence cannot decide. Browser, live external,
synthetic, and static observations are identified separately below.

## Execution and findings

A prior run of this session was interrupted by a usage/credit limit before its
findings were written to this file or any other tracked artifact. The
in-memory `/_qa/results` buffer in `data/stage5_independent_qa_server.py` does
not survive a process restart, and `data/stage5_independent_qa.db` holds only
the standard application schema (tickets, messages, conversation_turns, etc.),
not a QA transcript. The interrupted session's four reported observations
(greeting defect, discovery accepting "Anywhere" and a free-text budget, a
backend/frontend shortlist-display mismatch, and an untested pricing
follow-up) therefore existed only as an unwritten verbal summary and were
re-verified from scratch below rather than taken on faith.

A fresh local QA server (`data/stage5_independent_qa_server.py`) was started
against the isolated `data/stage5_independent_qa.db`, using
`READABLE_ANSWER_ENGINE` and in-memory conversation history, exactly as the
script is designed to run. No production database, backend selection, or
customer-facing deployment was touched. Checks below were made directly
against `/api/support/assist` (JSON) with real CS API data, which is
sufficient to classify the two flagged issues by layer (routing vs. retrieval
vs. frontend) without needing a full browser pass for every scenario. The
server was stopped after this run; two additional leftover QA-server
processes from the earlier interrupted session were also found and stopped.

| ID | Scenario | Result | Evidence |
| --- | --- | --- | --- |
| A1 | General greeting: "Hi, I'm exploring homes. What can you help me with?" | **FAIL (confirmed)** | `route="property"`, `agent_mode="remote_llm"`. The router classified a greeting as a property query and returned a live project list with RERA numbers instead of a relevant greeting/capability summary. Backend routing defect, not retrieval or frontend — see below. |
| B1 | "I need a 2 BHK but haven't picked an area yet." | **PASS** | Returned real live catalogue areas (Ambernath, Chikhloli, Pune, Thane, Varap) as `quick_replies` with `clarification_entity="locality"`; preserved the 2BHK slot. |
| B2 | "Anywhere is fine." | **PASS** | Accepted the typed wildcard, asked for a free-text budget ("Type an approximate budget... or say 'any budget'"), `quick_replies=[]` — no invented budget-band buttons. |
| B3 | "My ceiling is 55 lakh." | **Backend PASS / Frontend FAIL (confirmed)** | API `answer` field correctly contains the catalogue summary, 9 per-project price bullets, the pricing disclaimer, and the closing prompt. Applying the frontend's `visibleMessageText()` logic (`src/lib/customerChatContract.ts:18-22`) to this exact response reproduces truncation: the customer-visible text ends at `"...projects within about INR 55.00 lakh (estimated base amount):"` with every price, the disclaimer, and the prompt removed. See defect below. |
| C2 | Select "Vishwajeet Prime" from the shortlist. | **PASS** | Correctly retained project scope; returned live home-type counts and rate ranges, `source_status="live_api"`, `clarification_entity=null`, no silent single-choice selection. |
| D1 | "What is the listed base rate for those plans? Is that a final quote?" | **PASS** | Returned live rate-per-sqft data ending in "These are the API-listed base rates, not an all-inclusive flat quotation." `quick_replies` here all carry an `action` (`browse_projects`/`site_visit`/`ticket`), so the frontend truncation guard does not trigger — full text and disclaimer display correctly. This is a useful contrast case: the display bug is specific to plain list-selection quick replies (no `action`), not to all quick-reply messages. |
| D2 | "Can you guarantee a 2 BHK is available to book today?" | **UNVERIFIED (suspected)** | Re-emitted the prior home-type availability summary ("70 unit(s) currently listed as available") without addressing "guarantee" or "book today," and without a booking-confirmation caveat. Grounded in live data, not fabricated, so not an unsafe failure — but it does not clearly satisfy the "do not assert inventory/booking without disclosing it is not a guarantee" contract. Distinguishing an intentional grounded-reuse answer from a missing-caveat defect needs a wider scenario set than this bounded pass allows. |
| C1, C3, C4, E1, F1, G1, G2, H1, H2 | Not re-run this session | **Not covered** | Outside the minimal scenario set needed to verify the two flagged issues and close the previously interrupted thread; C1-equivalent coverage (a bulleted project list with plain quick replies) is already implied by B3 sharing the same `visibleMessageText()` code path. |

### Defect 1 (confirmed): general greeting misrouted to a property dump

**Classification: routing, not retrieval or frontend.** The orchestrator
assigned `route="property"` to a plain greeting with no project, locality, or
configuration terms, then called the live CS API and generated a project
catalogue dump through `remote_llm`. The retrieved data itself was accurate
(`source_status="live_api"`); the defect is in intent classification deciding
this was a property-lookup turn at all. Reproduction: POST to
`/api/support/assist` with `{"issue": "Hi, I'm exploring homes. What can you
help me with?"}` on a fresh conversation.

### Defect 2 (confirmed): shortlist prices and disclaimer invisible to the customer

**Classification: frontend presentation, not backend/retrieval.** The backend
(`services/discovery_slot_service.py:594-611`, `_results_draft`) builds the
answer as: catalogue summary → header → **price bullets** → optional
"Above your budget"/"Pricing not listed" bullets → **pricing disclaimer** →
closing prompt, then sets `quick_replies` to the same project names with no
`action` field (plain list-selection buttons). The frontend's
`visibleMessageText()` (`src/lib/customerChatContract.ts:16-22`) is designed
to drop the bulleted "plain-text fallback for API clients" when the same
options are shown as buttons — but here the bullets carry **price data**, not
just restated option labels, so the helper also deletes every price, the
required exclusions disclaimer, and the next-step prompt. The customer sees a
single dangling sentence ending in "(estimated base amount):" with no numbers
and no way to know pricing was ever computed. This reproduces on every
discovery shortlist and (by the same code path) on the plain project/locality
clarification lists; it does not occur on answers whose quick replies carry an
`action` (e.g., D1's browse/site-visit/ticket buttons), which is why D1 passed
display while B3 did not.

Root cause is a mismatch between what `visibleMessageText()` assumes
("bullets are just restated option labels") and what the discovery shortlist
actually bulleted ("bullets are the only place prices and the mandatory
disclaimer appear"). This is a customer-facing regression against the
AGENTS.md pricing/disclosure contract even though the backend is fully
compliant.

### Summary of confirmed and suspected defects

1. **Confirmed, FIXED (13 October 2026)** — General greetings could be
   misrouted to a live property-data dump instead of a relevant
   greeting/capability answer (A1). See "Fix verification" below.
2. **Confirmed, FIXED (13 October 2026)** — Discovery shortlist prices and
   the mandatory pricing disclaimer were silently removed from the
   customer-visible chat whenever the shortlist's quick replies were plain
   project-selection buttons (B3). See "Fix verification" below.
3. **Confirmed, FIXED (16 October 2026)** — D2: home-type builders ran before the
   capability-limitation check, so a guarantee/book-today question got a plain
   availability answer. `build_booking_guarantee_limitation_assist()` now runs
   before them (`unsupported_capability="booking_guarantee"`); a live probe on
   both endpoints confirmed the caveat while plain availability questions still
   return live counts. Original note follows.
   **Previously suspected, unverified, NOT CHANGED** — A "guarantee/book today" inventory
   question may get a reused grounded-availability answer without an
   explicit no-guarantee caveat (D2). Out of scope for the 13 October fix
   pass by explicit instruction; still needs a larger scenario set to
   confirm as a defect versus intentional behavior.

## Fix verification (13 October 2026)

Both confirmed defects were fixed under a separate, explicitly scoped
follow-up authorization (minimum-necessary-change fixes only, no Stage 6
work). Full root cause, the exact code changed, and verification results are
recorded in `docs/runtime/STAGE_5_DIFFERENTIAL_AND_CUTOVER_READINESS.md`
section 16. Summary:

- **Defect 1 root cause**: `routers/assist.py:_prepare_lookup_turn` called
  `is_reverse_amenity_query()` — a shape-only test ("which/what ... homes/
  projects/apartments") — directly to override the turn analyzer's correct
  `"general"` classification back to `"property"`. The greeting "Hi, I'm
  exploring homes. What can you help me with?" matches that shape (contains
  "homes" and "what") with no amenity actually named, so it was always
  promoted to `property` regardless of what the LLM classifier said.
  **Fix**: that branch now also requires `is_amenity_lookup_query()` — the
  same live-amenity-name check `build_grounded_amenity_search_assist` already
  uses before answering — so a shape-only match without a real amenity no
  longer flips intent. Genuine reverse-amenity queries ("which projects have
  a gym?") are unaffected.
- **Defect 2 root cause**: `src/lib/customerChatContract.ts:visibleMessageText()`
  truncated a bot message to the text before its first bullet whenever every
  quick reply lacked an `action` field, assuming the bullets were always a
  pure restated list of the button labels. The discovery shortlist's bullets
  (`services/discovery_slot_service.py:_results_draft`) carry real content —
  `"- {project}: estimated base amount from INR {x}"` — plus a disclaimer and
  closing prompt after the bullets, none of which match any quick-reply
  label. **Fix**: `visibleMessageText()` now only truncates when every
  bulleted line, with its marker stripped, exactly matches a quick-reply
  label (`bulletsAreRedundantWithQuickReplies()`); any bullet with extra
  content, or any line after the bullets, keeps the full text visible. The
  backend's price calculations and disclaimer text were not touched.

Both fixes were verified against the exact backend response captured during
this QA run (the live B3 shortlist payload) and against the existing/added
regression suites; see the differential/cutover report for full command
output. A follow-up verification pass (section 17 of that report) traced an
initial full-suite run's 40 errors to a pre-existing Windows permission
issue on the shared `pytest-of-anish` temp directory, unrelated to either
fix, and confirmed a fully clean 1,986-passed / 0-error full backend run
once tests were pointed at a writable temp directory.

### Remaining coverage gaps

C1, C3, C4 (project detail/construction/config follow-ups beyond the single
C2 check), E1 (new-area reset), F1 (ambiguous short reply), G1/G2 (Hindi
native-script and romanized), and H1/H2 (controlled CS API/Sarvam/stream
failure recovery) were not re-run this session. These were either already
covered with PASS evidence in the companion
`STAGE_5_DIFFERENTIAL_AND_CUTOVER_READINESS.md` section 14 browser run (H1,
H2, general-failure handling) or remain genuinely open.

## Stage 5 impact

**Status: PARTIAL.** Two customer-facing defects were confirmed with
reproducible evidence (greeting misrouting; shortlist price/disclaimer
display loss) and have since been fixed and verified (13 October 2026; see
"Fix verification" above and
`STAGE_5_DIFFERENTIAL_AND_CUTOVER_READINESS.md` section 16). One remains
suspected but unverified and unchanged (guarantee-language handling, D2).
Fixing these two defects removes one of the concrete release blockers this
QA pass raised, but does not resolve the other open Stage 5 gates in
`STAGE_5_DIFFERENTIAL_AND_CUTOVER_READINESS.md` (no approved production
conversation corpus, no production performance thresholds, no tested release
rollback). Stage 6 remains blocked until all separate gates are met.

## Separate browser continuation and evidence limit

This addendum records a separate local Playwright session against the existing
chat UI and an isolated QA server. The server selected
`READABLE_ANSWER_ENGINE` per request, kept conversation history in memory, and
used a disposable database. The production default was not changed. Browser
messages and the QA server's in-memory result metadata were observed together;
the metadata showed one NDJSON terminal result for each completed turn. The
configured CS API was used for read-only catalogue and project lookups. Its
`live_api` status is application provenance, not independent proof of source
freshness. No customer action was submitted, and the blocked inventory probe
was not deliberately retried.

These observations should be read alongside the later fixes and verification
above. Their exact ordering relative to those fixes could not be established
from a durable test transcript, so an observation that resembles an already
fixed defect is not evidence that the current source still has that defect.

| ID | Browser input and preceding context | Observed customer-visible result | Classification for this session |
| --- | --- | --- | --- |
| A1 | Fresh chat: “Hi, I am exploring homes. What can you help me with?” | Open/send/complete worked, but the reply was the unrelated seeded article text “Sets reply-time expectations for requests raised outside business hours.” The QA trace showed readable backend, property route, lexical retrieval, `used_llm=false`, and one terminal result. Reproduced in two fresh tabs. | **FAIL at observation time**: relevance and intent. Current status needs a post-fix browser retest; the earlier greeting fix above addressed a different observed response. |
| A2 | Fresh chat: “Can you tell me todays best mortgage rate across every bank?” | The chat gave the nearby-places/distance unsupported-capability message, rather than addressing the lack of verified mortgage rates. Trace: readable backend, general route, unsupported capability, no generation, one terminal result. | **FAIL**: safe but semantically wrong. Current `api_context.py` nearby-place matching includes `bank` without finance-context disambiguation. |
| B1 | “I need a 2 BHK but have not picked an area yet.” | Asked for an area using five locality buttons from the configured catalogue, while retaining the 2 BHK request and distinguishing catalogue listings from checked inventory. | **PASS** for the discovery step; dynamic locality freshness was not independently audited. |
| B2 | Following B1: “Anywhere is fine.” | Accepted the typed wildcard and requested a free-text budget, without invented budget-band buttons. | **PASS**. |
| B3 | Following B2: “My ceiling is 55 lakh.” | The captured backend answer had nine per-project base-estimate lines and an exclusions disclaimer. The captured browser display ended at the shortlist header and omitted those lines and disclaimer; project buttons appeared. | **FAIL at observation time** for customer-visible pricing context. The later `visibleMessageText()` fix and verification above address this class; current browser status is **UNVERIFIED** without a post-fix repeat. |
| C2 | Clicked the first project offered by the shortlist. | The UI retained project scope, listed home types and plan/rate details, and reported a 2 BHK available-unit count. Trace: readable backend, `source_status=live_api`, five completed data calls, one terminal result. | **PASS** for selection and configuration context. The availability count is **UNVERIFIED** as independent inventory acceptance; no endpoint-level freshness evidence was retained. |
| C3 | Following C2: “Where is this project and what is its construction status?” | The reply retained the selected project and gave location, address and other project fields, but gave neither a construction status nor an explicit unavailable-data statement. Trace: readable backend, `source_status=live_api`, one terminal result. | **FAIL** for the unanswered construction part. Current `_project_detail_answer()` omits that field when no wing status is present, without disclosing that absence. |
| C1, C4, D1, D2, E1, F1, G1, G2, H1, H2 | Not executed in this browser continuation. | No new observation. Earlier report sections contain separate evidence for some cases. | **UNVERIFIED in this session**. |

The A1 answer matches a seeded support article in `services/database_service.py`;
the browser and result trace establish the irrelevant answer, but do not by
themselves isolate whether turn analysis, retrieval ranking, or direct-answer
selection caused it. A2 has a source-visible unsupported-capability matching
cause. C3 has a source-visible omission path. No application changes were made
for these findings under this testing-only authorization.

Playwright stopped before the next prompt: automatic approval review rejected
the browser action because the session had reached its usage limit. The review
said to retry after 4:04 PM; it expressly did not classify the action as unsafe.
The action was not executed, and no alternate browser path was used to bypass
the review. This is why the remaining planned browser scenarios and a fresh
readable-versus-legacy comparison are **UNVERIFIED**, rather than passed or
failed. The isolated QA process later exited, so its in-memory trace buffer is
not a durable full transcript.

**Customer-experience assessment:** chat entry, sending, single completion,
typed discovery progression and selected-project context worked in the cases
observed. Relevance and multi-part answer completeness remain concerns (A1,
A2, C3). The captured shortlist display defect (B3) is addressed by the later
source fix above, subject to a post-fix browser confirmation. The live
inventory gate remains blocked, regardless of C2's reported count.

**Recommended focused follow-up:** after browser access is available, repeat
A1 and B3 against current source, then test A2 and C3 with the same isolated
backend. Review the two new source-visible response defects before cutover.
Complete the remaining language, ambiguity, failure-recovery and backend
comparison cases only within an approved Stage 5 QA session. Approved
production samples, performance thresholds, current external inventory
acceptance, real-provider interruption acceptance, and a tested release
rollback remain separate open gates. Stage 5 is **PARTIAL** and Stage 6 remains
**BLOCKED**.

### Focused follow-up for A2 and C3 (12 October 2026)

The A2 and C3 rows above remain the original browser observations. A separate
source-level investigation reproduced both faults offline and corrected them:
the mortgage question reached `nearby_places` on JSON and NDJSON; a project
record with no wing `constructionStatus` produced location details without a
construction-status explanation. The current routing now returns a specific,
honest inability to compare unverified mortgage rates while leaving nearby-bank
location questions on the existing nearby-place path. The readable project
detail answer now reports verified wing construction status when present and
explicitly says it cannot verify a requested construction status when the
field is missing. No progress, possession date, lender, or rate is inferred.

Endpoint and engine regressions passed in both delivery modes with synthetic
CS records. A fresh browser run and independent live status verification were
not part of this focused correction. A1 and B3 retain their separate browser
verification limits; Stage 5 remains partial and Stage 6 blocked.

### Follow-up for the missing-status clarification loop (12 October 2026)

The later focused browser check found that the missing-status explanation was
replaced by a project-selection question. A regression test reproduced the
interaction without a browser: the compatibility detector in
`property_clarification_service.py` treated `provided ... project records` as
a selection prompt. It now requires whole-word selection verbs at the start of
a sentence or line. Explicit clarification metadata and pending state continue
to work; legitimate project and other entity prompts remain covered.

Synthetic JSON and NDJSON checks now retain the cannot-verify explanation,
with no pending project selection, while a verified wing status still appears.
The focused suite passed 85 tests and 7 subtests. The full backend sandbox run
had 1,994 passed, 1 skipped, and 13 failures caused by blocked CS API socket
access (`WinError 10013`); it is not a clean full-suite acceptance. This is
offline correction evidence, not a post-fix browser or independent live CS
status result. C3 customer-facing acceptance remains **UNVERIFIED** after the
fix; Stage 5 remains **PARTIAL** and Stage 6 **BLOCKED**.

## Customer journey QA continuation (21 October 2026)

This continuation used current source at `390e238`. It made no application
changes, submitted no customer action, and did not select the readable engine
for production. The checks below are distinct from the historical observations
above.

| Journey | Current result | Evidence and limit |
| --- | --- | --- |
| B3 shortlist presentation | **PASS (mocked browser UI)** | A local browser received a constructed NDJSON shortlist. It displayed the estimated-base-amount line, exclusions disclaimer, closing prompt, and project button together. This proves presentation for that response shape, not current catalogue pricing. |
| H1 failed-source reply, then a new question | **PASS (mocked browser UI)** | A constructed failed-source reply showed the `Answer unavailable` state; the next turn completed once. This does not establish actual CS API or Sarvam failure behavior. |
| H2 interrupted stream, then a new question | **PASS (mocked browser UI)** | A stream containing a delta but no terminal result showed `Response interrupted`; the following turn completed once. The partial text appeared once. This does not establish real-provider cancellation or production transport behavior. |
| E1 new-area search and F1 ambiguous selection | **UNVERIFIED as complete customer journeys** | Focused synthetic endpoint suites passed, including discovery and clarification regressions, but these exact multi-turn browser paths were not replayed in this continuation. |
| G1 native-script Hindi and G2 romanized Hindi pricing | **UNVERIFIED as live customer journeys** | Language and discovery regressions passed with constructed evidence. The live CS API was unavailable, so current grounded pricing and localized browser replies could not be assessed. |
| Current live catalogue and grounded Sarvam probe | **BLOCKED** | The read-only probe first hit sandbox socket denial (`WinError 10013`). With network permission, its request to the configured CS API timed out before a response. It stopped before the Sarvam probe; neither integration passed live acceptance. |

The local Playwright test runner for the mocked discovery journey stalled and
was stopped without an assertion result. Direct Playwright browser interactions
with controlled NDJSON responses completed the B3, H1, and H2 UI checks above.
The browser required access to its user-profile directory outside the
workspace; the local Vite page was usable after DOM readiness. These checks
must not be recorded as a passing Playwright test-runner result.

Focused backend runs passed 147, 100, and 150 tests respectively; the last run
also passed 13 subtests. The focused frontend presentation run passed 9 tests.
The constructed offline readable-versus-legacy differential script completed;
its differences remain characterized synthetic evidence, not production
conversation parity. No full-suite or live journey pass is claimed here.
Stage 5 remains **PARTIAL** and Stage 6 remains **BLOCKED**.
