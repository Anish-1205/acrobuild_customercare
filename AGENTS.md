# AI Coding Agent Guide

## Purpose and reading order

This is an AcroBuild real estate customer support application: a FastAPI backend,
React/Vite frontend, SQLite workspace, live property CS API, and Sarvam chat LLM.
Read [AI_CONTEXT.md](docs/AI_CONTEXT.md) first for the current architecture and
task-specific file map, then [CHAT_FLOW.md](docs/CHAT_FLOW.md) for chat routing.
The code is authoritative when older documents disagree.

## Quick start

- Install Python dependencies: `pip install -r requirements.txt`
- Run the backend: `uvicorn app:api --reload`
- Install frontend dependencies: `npm install`; run it with `npm run dev`
- Backend: `http://127.0.0.1:8000`; frontend: `http://127.0.0.1:5173`
- `GET /` is a health check. `POST /create_ticket` creates a ticket.
- `POST /api/support/assist` and `/api/support/assist/stream` serve chat.
- Use `.env.example` as a configuration template. Never copy real `.env` values
  into prompts, docs, logs, or commits.

## Architecture

- `app.py` assembles routers; `api_context.py` creates the FastAPI app, shared
  dependencies, and Pydantic request models; `routers/` owns HTTP endpoints.
- `graph/main_orchestrator.py` routes support chat. `routers/assist.py` handles
  the two assist endpoints and their streaming response.
- `services/acrobuild_company_service.py` fetches live property data from the CS
  API. `services/property_clarification_service.py` handles ambiguous project,
  wing, floor, flat, and home-type selections.
- `services/knowledge_index_service.py` retrieves workspace articles and
  knowledge documents. `graph/workflow.py` classifies and routes tickets.
- `services/database_service.py` persists tickets and workspace data in the
  root-level `support_system.db` SQLite file.
- `qwen.py` is a compatibility facade despite its name. Chat generation has
  one supported provider, Sarvam, through `sarvam_client.py`. `RUNPOD_BASE_URL`
  and `RUNPOD_API_KEY` are legacy configuration names; the URL can point to an
  OpenAI-compatible Sarvam endpoint. `MODEL_NAME` selects the deployed model.
- `src/` is the React customer chat and admin workspace. `vite.config.ts`
  proxies API routes to the backend.

## Development conventions

- Use `snake_case` for Python functions and variables.
- Follow the existing section comment style: `# -----------------------------------`.
- Keep database access SQLite-based and preserve the separation between
  service modules and orchestration.
- Add Pydantic request validation at the API boundary in `api_context.py` or
  the relevant router.
- Do not treat a successful `GET /` as proof that the CS API or LLM works;
  those are separate external connections.

## Mandatory property clarification contract

- Every project/wing/floor/flat/home-type/locality clarification must use
  `services/property_clarification_service.py` before relevance validation,
  localization, and conversation persistence.
- New answer builders must set `clarification_entity` (`project`, `wing`,
  `floor`, `flat`, `home_type`, or `locality`). Do not generate a bare "specify
  the project" prompt. The contract fetches real matching names from the live
  CS API; an empty or unavailable catalogue must be reported honestly.
- Preserve the complete original question, selected scope, offered options,
  and retry query in the server-side pending selection marker. Do not derive
  intent from translated bot prose. Do not expire state after a fixed number
  of API failures. Explicit new questions/actions replace the pending request.
- List all applicable real options; do not silently select one of multiple
  matching records. A full suffixed project name takes precedence over its
  contained base name.
- Test new clarification points for named options, short follow-up selection,
  repeated API failures, and intent preservation. Cover both assist endpoints
  when changing routing. Run `scripts/live_disambiguation_check.py` for live
  acceptance (real LLM/API, no mocks); transcripts are written to
  `docs/live_disambiguation_results.json`.

## Discovery slot memory (Inquiry to Sales §28)

- The flow lives in `services/discovery_slot_service.py` and defaults on after
  Phase 1 live acceptance. `ACROBUILD_DISCOVERY_SLOTS` is read on every call;
  set it to `false` to disable discovery explicitly.
  With the flag off, `routers/assist.py` runs no discovery code path.
- `services/property_clarification_service.py` must never import
  `services/discovery_slot_service.py` (the discovery module depends on it
  through `services/project_home_type_service.py`). A test enforces this.
- Discovery drafts already carry their pending selection or
  `discovery_prompt`, so `apply_clarification_contract()` returns them
  unchanged. Do not add a second live read per turn.
- Locality options come only from live project `locality`/`city` values.
  Never store the customer's own text as a locality; an unknown place is
  quoted back once and live options are offered again.
- The "Any area" quick reply is never part of the pending option list.
- Live data reads for new property tools go through
  `services/property_tools_service.py`, which never imports the compiled
  runtime or `graph/`.

## Local test artifacts

- Run pytest without `--basetemp`; its default temporary directory is outside
  the project. Do not create unique root-level pytest temp directories.
- The pytest cache plugin is disabled in `pyproject.toml`. Ruff and mypy store
  their caches under ignored `data/`.
