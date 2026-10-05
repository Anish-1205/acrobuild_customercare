# AcroBuild Customer Support Agent

AcroBuild is a FastAPI and React/Vite support application for real-estate
customer chat and staff ticket operations. Customer chat combines grounded
property data from the AcroBuild CS API, workspace knowledge, and a Sarvam LLM.
SQLite stores tickets, workspace configuration, sessions, and short-lived chat
state.

## Read this first

1. [Documentation index](docs/README.md) — choose the guide for your task.
2. [Architecture](docs/ARCHITECTURE.md) — system boundaries and source map.
3. [Chat and property flow](docs/CHAT_FLOW.md) — routing, grounding, and state contracts.
4. [Development guide](docs/DEVELOPMENT.md) — setup, commands, tests, and diagnostics.
5. [Product status](docs/PRODUCT_STATUS.md) — implemented scope and known limits.

Coding agents must also follow [AGENTS.md](AGENTS.md). Current source code is
the authority when historical evidence or an old changelog entry differs.

## Quick start

Use Python 3.12 because one supported runtime component is still bytecode-only.

```powershell
.venv/Scripts/python.exe -m pip install -r requirements.txt
npm install
Copy-Item .env.example .env
```

Configure only the external services you need, then run the backend and frontend
in separate terminals:

```powershell
.venv/Scripts/python.exe -m uvicorn app:api --reload --host 127.0.0.1 --port 8000
npm run dev
```

- Backend: `http://127.0.0.1:8000`
- Frontend: `http://127.0.0.1:5173`
- Composite health: `http://127.0.0.1:8000/api/health`

`GET /` proves only that the local backend responds. It does not prove that the
CS API or Sarvam is reachable. See the [development guide](docs/DEVELOPMENT.md)
for configuration and verification.

## Repository layout

| Path | Purpose |
| --- | --- |
| `app.py`, `api_context.py`, `routers/` | FastAPI assembly, shared contracts, and routes |
| `graph/` | chat and ticket orchestration |
| `services/` | persistence, property, knowledge, security, and integration services |
| `src/`, `public/` | React customer and staff interfaces |
| `tests/` | backend regression suite |
| `scripts/` | evaluation, live acceptance, and maintenance tools |
| `docs/` | current guides, integration reference, and separated evidence |
| `requirements/` | dependency groups and security-advisory rationale |
| `resources/` | source-controlled evaluation inputs |
| `data/` | ignored local runtime and verification artifacts |

Never commit `.env`, `support_system.db`, logs, uploads, model caches, or other
runtime/customer data.
