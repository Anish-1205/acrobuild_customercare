# AI context: AcroBuild Customer Support Agent

Use this page to brief another coding AI. Pair it with `AGENTS.md` for project
rules, then add source files for the task at hand. The source code is the final
authority; some older documents describe previous versions of the project.

## What the application does

The React/Vite app has a customer chat experience and a staff workspace for
tickets, articles, knowledge documents, macros, tags, workflow rules, and
business hours. The FastAPI backend answers chat, reads live real estate data
from AcroBuild's CS API, searches workspace knowledge, and stores support data
in SQLite. Chat generation uses Sarvam through an OpenAI-compatible HTTP API.

```mermaid
flowchart LR
  UI[React app in src/] -->|Vite proxy| API[FastAPI app.py + routers/]
  API --> Chat[graph/main_orchestrator.py]
  API --> Tickets[graph/workflow.py]
  Chat --> Property[CS API + property clarification]
  Chat --> Knowledge[Workspace knowledge index]
  Chat --> LLM[qwen.py facade → sarvam_client.py]
  Tickets --> DB[(support_system.db)]
  API --> DB
```

## Start and configuration

1. Install Python packages with `pip install -r requirements.txt` and frontend
   packages with `npm install`.
2. Copy `.env.example` to `.env` and provide the external service settings you
   need. Keep `.env` private.
3. Start the backend with `uvicorn app:api --reload` and the frontend with
   `npm run dev`. The default local URLs are `http://127.0.0.1:8000` and
   `http://127.0.0.1:5173`.
4. `GET /` checks only the local backend. Sarvam generation requires
   `RUNPOD_BASE_URL` and `RUNPOD_API_KEY`; set `MODEL_NAME` to the model served
   by that endpoint. The `RUNPOD_*` names are historical; the URL may be a
   direct Sarvam endpoint or a
   RunPod-hosted OpenAI-compatible endpoint. Live property answers require
   `ACROBUILD_CS_API_BASE_URL`, `ACROBUILD_CS_API_KEY`, and
   `ACROBUILD_CS_API_COMPANY_ID`, plus network access
   to that API. The two external services can fail independently.
   Administrators can edit the three CS API values using **CS API settings**
   in the dashboard header (`/admin/cs-api-settings`). Saved values are stored
   in SQLite and override the environment defaults on new API requests,
   including after restarts; `.env` is not rewritten. The existing key is never
   sent to the browser, and a blank key field preserves it. Cached responses
   are isolated by connection configuration. Legacy snapshots are not reused
   when the configured server differs from the environment default.

## File map for another AI

| Work area | Read these files |
| --- | --- |
| App and HTTP contracts | `app.py`, `api_context.py`, relevant file in `routers/` |
| Chat routing | `routers/assist.py`, `graph/main_orchestrator.py`, `docs/CHAT_FLOW.md` |
| Customer chat refresh | `services/conversation_store_service.py`, `routers/assist.py` history route, `src/lib/conversationSession.ts`, `src/pages/CustomerHomePage.tsx` |
| Property answers and clarification | `services/acrobuild_company_service.py`, `services/property_clarification_service.py`, `services/ai_agent_service.py` |
| Typed CS API tools (additive) | `services/property_tools_service.py`: `ToolResult` with `source_status`, `BLOCKED_TOOLS`/`blocked()`, `clean_place_text()`, `search_projects()`, `list_localities()` |
| Discovery slot memory (flag `ACROBUILD_DISCOVERY_SLOTS`) | `services/discovery_slot_service.py`, the `discovery_slots` marker helpers in `services/conversation_store_service.py`, the discovery wiring in `routers/assist.py`, `docs/PHASE1_PLAN.md` |
| LLM calls | `qwen.py`, `sarvam_client.py`, `services/llm_service.py` |
| Workspace knowledge/RAG | `services/knowledge_index_service.py`, `services/knowledge_ingestion_service.py` |
| Tickets and routing | `graph/workflow.py`, `services/ticket_metadata_service.py`, `services/database_service.py` |
| Authentication and staff workspace | `routers/sessions.py`, `routers/workspace.py`, `services/auth_service.py` |
| Frontend | `src/App.tsx`, task-specific files in `src/`, `src/lib/api.ts`, `vite.config.ts` |
| Dependencies and configuration | `requirements.txt`, `requirements/`, `package.json`, `.env.example` |
| Tests | Relevant files in `tests/`; use `scripts/live_disambiguation_check.py` for live property clarification acceptance |
| Discovery and tool tests | `tests/test_property_tools_service.py`, `tests/test_discovery_slots.py`, `tests/test_discovery_slot_service.py`, `tests/test_locality_clarification_contract.py`, `tests/test_discovery_flow.py`, `tests/test_locality_sanitise_match.py`, `tests/test_discovery_review_fixes.py` |

## Behavior and boundaries

- `api_context.py` defines shared Pydantic request models and creates the
  FastAPI app. `app.py` registers route modules. The customer chat route has
  both JSON and streaming variants.
- Chat selects a conversational LLM path or a property/knowledge path. Property
  facts should come from the live CS API or workspace knowledge. When live data
  is unavailable, the assistant should say so instead of inventing inventory.
- Project, wing, floor, flat, home-type, and locality disambiguation uses
  `services/property_clarification_service.py`. Read the mandatory contract in
  `AGENTS.md` before editing these flows.
- The discovery slot flow (configuration, area, budget) defaults on after
  Phase 1 live acceptance; `ACROBUILD_DISCOVERY_SLOTS=false` disables it.
  See `docs/CHAT_FLOW.md` and the
  discovery rules in `AGENTS.md`.
- `qwen.py` retains old function names for callers but dispatches to Sarvam
  only. Local Qwen inference is not a supported chat provider.
- `support_system.db`, `.env`, logs, uploads, model caches, and generated
  `data/` content are local runtime artifacts. Do not use them as portable AI
  context or publish their contents.
- The long `docs/ONBOARDING.md` and other historical guides may contain stale
  architecture or security claims. Check current code before relying on them.

## Suggested context bundle

For a general handoff, share `AGENTS.md`, this file, `README.md`,
`docs/CHAT_FLOW.md`, and `.env.example`. For a specific change, add only the
relevant files from the table above. Never attach `.env`, the SQLite database,
or customer data.
