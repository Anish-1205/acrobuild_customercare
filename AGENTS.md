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

- Every project/wing/floor/flat/home-type clarification must use
  `services/property_clarification_service.py` before relevance validation,
  localization, and conversation persistence.
- New answer builders must set `clarification_entity` (`project`, `wing`,
  `floor`, `flat`, or `home_type`). Do not generate a bare "specify the project"
  prompt. The contract fetches real matching names from the live CS API; an
  empty or unavailable catalogue must be reported honestly.
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
