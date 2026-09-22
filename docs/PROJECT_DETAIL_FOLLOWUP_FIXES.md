# Project-detail follow-up fixes

## Context and compound requests

The history resolver used substring matching. An Empire NX mention matched both
Empire and Empire NX, so it could be skipped and an older project used instead.
Its contextual-reply detector also missed short configuration-only follow-ups.
The shared partial-name matcher separately preferred a complete base-name token
over a suffixed candidate: `Empire` could silently select Empire.

History now resolves full names with suffix precedence, configuration follow-ups
preserve the project and original question, and ambiguous fragments retain all
candidates. `2bk` is normalized to `2BHK`; explicit configurations survive an LLM
translation that drops a conjunct. New portfolio questions and explicit project
changes keep their own scope.

The deeper state problem was that only an unfinished clarification had durable
server-side scope. After a successful project answer, the resolver inferred the
project again from visible prose. A concise answer that omitted the project name
therefore broke the next bare follow-up. Successful scoped answers now store an
invisible current-project marker, exact project-button selections update it, and
new catalogue searches explicitly clear it. Visible history remains a fallback.

The answer dispatcher also rewrote questions containing `details` into a generic
overview, erasing home-type constraints. Specific requests no longer undergo that
rewrite. A shared grounded shortcut reads project typologies and available units,
answers every requested type, and distinguishes an unlisted configuration from a
listed configuration with no currently available units. More specific wing/floor,
budget and comparison requests retain their existing builders.

## Guard message

`validate_support_node` in `graph/haystack_conversation_pipeline_source.py`
generated the reported message. Its validator checked only the first BHK match;
project validation could also accept Empire as evidence for Empire NX. It now
checks every requested type and uses suffix-aware project resolution. Residual
validation failures explain that the details could not be confirmed and offer a
retry or a call, without asking customers to relax internal constraints.

Catalogue-wide home-type questions now filter project typology records directly,
return only projects listing every requested BHK type, and store a selection whose
original filter intent survives the click. BHK filters run before reverse amenity
search because both share phrases such as “what properties have”; BHK questions
are excluded from the amenity lookup so an amenity failure cannot abort them.

Live checks found no 3BHK in Empire NX's configuration or available-unit records.
The bot now states that limitation and lists the configurations actually present,
rather than claiming no 3BHK can ever exist or returning the relevance guard.

## Human handoff

Completed property answers offer three action buttons. Support tickets reuse
`openFollowUpForm` and `/create_ticket`; site visits reuse `openSiteVisitBooking`
and `/api/site-visits`; calls reuse the deterministic `call_booking` chat flow
and its ticket workflow. The visit form receives the project from the answer's
evidence. These are requests through existing workflows; no new booking system
was introduced.

Action buttons preserve the complete answer body. Previously the frontend hid
everything after the first bullet whenever any quick replies were present, which
would hide amenities or home-type details when these new buttons appeared.

## Verification

- Targeted regressions cover both assist endpoints, NX context, ambiguous names,
  every requested type, missing/empty inventory, explicit scope changes, and
  repeated API failures with intent preservation.
- The wider project/entity, budget, pending-selection and language suite passes.
- The TypeScript check and production frontend build pass.
- `scripts/live_disambiguation_check.py` passes using the real CS API and LLM;
  transcript: `docs/live_disambiguation_results.json`.
- `scripts/live_project_home_type_check.py` passes both endpoints, including
  `2bhk matrame cheppu`, `indhulo 2bk and 3bhk details cheppu`, `3bhk levva?`,
  the English overview → explicit 3BHK → bare `2bhk?` sequence, catalogue-wide
  `what properties have 3bhk?`, and project re-selection; transcript:
  `docs/live_project_home_type_results.json`.

Live checks inspect available data and returned handoff actions; they do not
submit real customer tickets, callbacks, or site visits.
