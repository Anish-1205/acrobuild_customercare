# Property disambiguation audit — 2026-09-18

Verified against a fresh instance of the actual FastAPI app using TestClient and
`/api/support/assist/stream`, the configured live Sarvam model, the live CS API,
and real cookie-scoped SQLite conversation persistence. No model, API, or session
mocks were used in the live run. This does not restart an already-running backend.

Final live assertions passed for all 10 turns: Precious amenities (2), cost (2),
location (2), and Myspace wing → floor → flat (4). Every final response recorded
`source_status=live_api`. Precious fetched `/api/cs/projects/52/amenities` and
returned all 14 amenities. API spellings in the transcripts are preserved.

## Complete generator audit

Source grep was supplemented by inspecting string constants in the loaded
`ai_agent_service_runtime.pyc`: its legacy functions are not visible to source grep.
The original bytecode files were not edited.

| Generator / clarification point | Before | Resolution |
|---|---|---|
| `api_context.build_grounded_project_amenities_assist` — missing/partial/shared project name | Partial named-options fix; category-only state, one-retry cutoff | Shared options contract; full request and selected scope retained |
| `build_grounded_project_cost_clarification_assist` — missing/shared project | No-name case fell through; selected project could become relevance warning | Live project options; selected-project typology pricing; full pending state |
| `build_grounded_project_location_assist` — missing/shared project | Missing-name case fell through | Named project options and durable location request |
| Location shortcut — unrecognized locality / generic city question | Bare “Which city” | Lists real available projects; location intent retained |
| `build_grounded_site_visit_document_assist` — ambiguous project | Used “your selected project” | Enumerates matching projects before document guidance |
| Legacy `build_document_requirement_answer` | Bare project-name/purpose request | Outgoing chat response normalized by shared contract |
| Legacy `build_construction_update_answer` | Bare project/tower/unit request | Shared project/wing state; selected wing reads live construction fields |
| Legacy `build_unknown_clarification_answer` / thin retrieval fallback | Bare project-name request | Shared live options and complete original request |
| Legacy `build_site_visit_booking_answer` | Bare project-name/date/time request | Shared project selection before continuing original visit request |
| Legacy direct-answer wing list — “Choose a wing” | Names listed; inferred state from prose | Live names retained, structured wing state and inventory continuation |
| Legacy direct-answer wing selection — “Which wing” | No durable marker | Same shared wing contract |
| Legacy direct-answer floor list — “Choose a floor” | Options could be listed; inferred state | Real inventory floor options, durable scope, native inventory continuation |
| Legacy direct-answer floor prompt — “Which floor” | Generic prompt possible | Same floor contract |
| Legacy inventory mismatch — “choose another available home type or floor” | Generic prompt and lost constraints | Live home types scoped to project/wing/floor, retained original query |
| Legacy inventory retry — “check another floor” / “ask again as: floor” | Prose-only continuation | Shared floor-option detector and state |
| Legacy direct-answer pricing — “Which project … detailed price estimate” | Category lost on next name | Shared full pricing request and live selected-project pricing |
| Legacy catalogue — “Tell me which project … explore” / alternative-project prompt | Prose-only continuation | Shared named project options and scope |
| Flat/unit selection (generated replies and new handlers) | No common state contract | `clarification_entity=flat`, live scoped unit numbers; direct unit record lookup |
| Pipeline relevance validator | Could replace a valid selection request with a relevance warning | Applies contract first; preserves structured clarification |
| Property LLM-generated clarification | Wording/localization could bypass deterministic state | English generation → shared contract → validation → localization |
| Seed support articles, documentation macro, `database_service.generate_ai_reply` | Static project/reference instructions found by grep | Not interactive chat controllers; when their wording is emitted through assist, the shared delivery contract replaces bare entity requests. Admin-only template text remains unchanged. |
| `call_booking` / `human_contact` | Already use their own pending markers | Retained; excluded from property contract and covered by existing regression tests |
| Recommendation preference question (“price, space, amenities…”), relevance constraint relaxation | Asks preference/constraint, not an entity selection | No entity-option replacement needed |

## Cross-cutting fixes and standing contract

- Persist full original request, options, entity, selected scope, and effective
  retry request in the existing pending-marker mechanism.
- Preserve state across repeated CS API failures, including initial failure before
  options are fetched. A new explicit question/action cancels the old selection.
- Preserve markers when visible answers exceed the previous 10,000-character limit.
- Recognize partial names; independent exact matches remain ambiguous. Full suffixed
  names still take precedence over contained base names.
- Both HTTP endpoints restore state before routing. Staged inventory selections
  use live records directly, preventing fallback into generic article text.
- New handlers must declare `clarification_entity`; the contract is required in
  `AGENTS.md` and described in `CHAT_FLOW.md`. Legacy wording recognition is a
  compatibility path, not the prescribed interface for new handlers.
- An empty/unreachable API cannot supply real options. It produces an honest
  availability message and preserves the request; it never invents a catalogue.

## Tests

Full suite: **789 passed, 95 subtests passed**, one pre-existing Starlette/AnyIO
DeprecationWarning. Command:

```powershell
.venv/Scripts/python.exe -m pytest tests/ -q -p no:cacheprovider --basetemp=.test-tmp-disambiguation-final
```

New regression coverage includes each legacy selection prompt, all three
no-project shortcuts, document ambiguity, partial/multiple project matches,
wing/floor/flat/home-type chains, construction and pricing intent retention,
three successive failures, initial options-fetch failure, new-question cancellation,
localization list preservation, long-answer marker persistence, and both endpoints.
The provider-switch test now isolates its circuit-breaker state; the first full
run exposed state leakage from earlier failure tests, rather than a routing error.

A real CS API timeout also occurred during an intermediate cost run. The next
“precious” turn retained the pricing intent and returned live prices. That run is
saved separately in `live_disambiguation_timeout_observed.json`; its earlier
floor response predates the final inventory fix and is not the acceptance result.

## Final live transcripts

### precious

**User:** vishwajeet lo amenities em em vunnai?

**Assistant:**

Andubaatulo unna matching project options ive:

- Vishwajeet Heights
- Vishwajeet Empire NX
- Vishwajeet Prime
- Vishwajeet Myspace
- Vishwajeet Precious
- Vishwajeet Town
- Vishwajeet Empire
- Vishwajeet Precious Phase-V
- Vishwajeet Paradise

Nenu ae project details check cheyali?

Verified live endpoints: `/api/cs/projects`.

**User:** precious

**Assistant:**

Vishwajeet Precious ki sambandhinchina andubatulo unna data lo ee sadupayalu unnayi:

- Baby Swimming Area
- Carrom
- Children's Playing Area
- Enterance Lobby
- Gated Community
- Gym
- Jogging Track
- Multipurpose Hall
- Park
- Party Lawn
- Paved Walkway
- Pool & Billards
- Swimming Pool
- Yoga & Meditation Area

Verified live endpoints: `/api/cs/projects`, `/api/cs/projects/52/amenities`.

### cost

**User:** What is the cost in Vishwajeet?

**Assistant:**

These are the available matching project options:

- Vishwajeet Heights
- Vishwajeet Empire NX
- Vishwajeet Prime
- Vishwajeet Myspace
- Vishwajeet Precious
- Vishwajeet Town
- Vishwajeet Empire
- Vishwajeet Precious Phase-V
- Vishwajeet Paradise

Which project would you like me to check?

Verified live endpoints: `/api/cs/projects`.

**User:** precious

**Assistant:**

Live API-listed base pricing for Vishwajeet Precious:

- 2BHK 1341(SQ.FT): INR 3400.0 to INR 4300.0 (Rate Per Sq.Ft.)
- 1BHK 1085(SQ.FT): INR 3400.0 to INR 4300.0 (Rate Per Sq.Ft.)
- 1BHK 954(SQ.FT): INR 3400.0 to INR 4300.0 (Rate Per Sq.Ft.)
- 2BHK 1246(SQ.FT): INR 3400.0 to INR 4300.0 (Rate Per Sq.Ft.)
- 2BHK 1373(SQ.FT): INR 3400.0 to INR 4300.0 (Rate Per Sq.Ft.)
- 1BHK 953(SQ.FT): INR 3400.0 to INR 4300.0 (Rate Per Sq.Ft.)
- 2BHK 1412(SQ.FT): INR 3400.0 to INR 4300.0 (Rate Per Sq.Ft.)
- 1BHK 1134(SQ.FT): INR 3400.0 to INR 4300.0 (Rate Per Sq.Ft.)
- 2BHK 1206(SQ.FT): INR 3400.0 to INR 4300.0 (Rate Per Sq.Ft.)
- 2BHK 1322(SQ.FT): INR 3400.0 to INR 4300.0 (Rate Per Sq.Ft.)
- 2BHK 1283(SQ.FT): INR 3400.0 to INR 4300.0 (Rate Per Sq.Ft.)
- 1BHK 904(SQ.FT): INR 3400.0 to INR 4300.0 (Rate Per Sq.Ft.)
- 2BHK 1254(SQ.FT): INR 3400.0 to INR 4300.0 (Rate Per Sq.Ft.)

These are the API-listed base rates, not an all-inclusive flat quotation.

Verified live endpoints: `/api/cs/projects`, `/api/cs/projects/52/typologies`.

### location

**User:** Where is the project located?

**Assistant:**

These are the available matching project options:

- Vishwajeet Heights
- Vishwajeet Empire NX
- Vishwajeet Prime
- Vishwajeet Myspace
- Vishwajeet Precious
- Vishwajeet Town
- Vishwajeet Empire
- Vishwajeet Precious Phase-V
- Vishwajeet Paradise

Which project would you like me to check?

Verified live endpoints: `/api/cs/projects`.

**User:** precious

**Assistant:**

Vishwajeet Precious: Kalyan-Murbad Road, near Sacred Heart School, Varap, Kalyan West, Maharashtra , Varap, Thane

Verified live endpoints: `/api/cs/projects`.

### wing

**User:** Show me wings in Vishwajeet Myspace

**Assistant:**

These are the available matching wing options for Vishwajeet Myspace:

- Jupiter C
- Jupiter D
- Venus A
- Venus B

Which wing would you like me to check?

Verified live endpoints: `/api/cs/projects`, `/api/cs/projects/54/wings`, `/api/cs/projects/54/typologies`.

**User:** Venus A

**Assistant:**

These are the available matching floor options for Vishwajeet Myspace, Venus A:

- 0
- 1
- 2
- 3
- 4
- 5
- 6
- 7
- 8
- 9
- 10
- 11
- 12
- 13
- 14
- 15

Which floor would you like me to check?

Verified live endpoints: `/api/cs/projects`, `/api/cs/projects/54/wings`, `/api/cs/wings/64/inventory`.

**User:** 1

**Assistant:**

These are the available matching flat options for Vishwajeet Myspace, Venus A, 1:

- 101
- 102
- 103
- 104
- 105
- 106

Which flat would you like me to check?

Verified live endpoints: `/api/cs/projects`, `/api/cs/projects/54/wings`, `/api/cs/wings/64/inventory`.

**User:** 101

**Assistant:**

Live available homes in Vishwajeet Myspace, Venus A wing:

- Flat 101; floor 1; configuration: 1BHK 660(SQ.FT); carpet area: 333.14 sq. ft.; saleable area: 660.0 sq. ft.; base rate: INR 2900.0 to INR 3500.0 (Rate Per Sq.Ft.)

Verified live endpoints: `/api/cs/projects`, `/api/cs/projects/54/wings`, `/api/cs/wings/64/inventory`, `/api/cs/wings/64/typologies`.

