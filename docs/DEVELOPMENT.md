# Development guide

## Prerequisites

- Python 3.12. Use the repository `.venv` when available; the remaining
  compiled answer engine rejects incompatible Python bytecode versions.
- Node.js and npm for the React/Vite frontend.
- External credentials only for the services being exercised. Never paste or
  commit `.env` values.

## Install and configure

```powershell
.venv/Scripts/python.exe -m pip install -r requirements.txt
npm install
Copy-Item .env.example .env
```

`.env.example` is the complete configuration template. The most important
groups are:

- Sarvam chat: `RUNPOD_BASE_URL`, `RUNPOD_API_KEY`, `MODEL_NAME`.
- Property data: `ACROBUILD_CS_API_BASE_URL`, `ACROBUILD_CS_API_KEY`,
  `ACROBUILD_CS_API_COMPANY_ID`.
- Security: unique production values for `AUTH_SECRET_KEY` and `OTP_SECRET`.
- Email OTP: `SMTP_*`.

`RUNPOD_*` names are retained for compatibility and may point to a direct
Sarvam or RunPod-hosted OpenAI-compatible endpoint. Sarvam is the only supported
chat provider. Administrators can save CS API settings at
`/admin/cs-api-settings`; saved values are stored in SQLite, take precedence for
new requests, and never rewrite `.env`.

## Run locally

Start each process from the repository root in a separate terminal:

```powershell
.venv/Scripts/python.exe -m uvicorn app:api --reload --host 127.0.0.1 --port 8000
npm run dev
```

The backend is at `http://127.0.0.1:8000` and the frontend at
`http://127.0.0.1:5173`.

Use `GET /api/health` for a configuration-oriented composite status. A green
health response does not send a real prompt to Sarvam or necessarily make a
network request to the CS API. Use the live acceptance tools for that evidence.

## Tests and static checks

Run pytest without `--basetemp`; the repository configuration disables its
cache plugin, and its default temporary location stays outside the project.

```powershell
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m mypy
npm test
npm run build
npm run lint
```

Start with task-specific tests. Broaden to the full backend/frontend checks when
the changed surface justifies it. Test counts in historical evidence are dated
records, not current expectations.

The full backend suite can require outbound CS API access for explicitly live
tests and a writable system temporary directory. Report an environment block as
blocked rather than a product pass or failure. Do not alter tests merely to hide
a live-data or environment mismatch.

## Live acceptance

These scripts use the configured real services and write committed evidence
snapshots under `docs/evidence/live/`:

```powershell
.venv/Scripts/python.exe scripts/live_disambiguation_check.py
.venv/Scripts/python.exe scripts/live_disambiguation_check.py --discovery
.venv/Scripts/python.exe scripts/live_project_discovery_check.py
.venv/Scripts/python.exe scripts/live_project_home_type_check.py
```

They do not authorize invented property data. If the catalogue cannot satisfy a
scenario, record `BLOCKED_BY_LIVE_DATA`. If credentials, network, browser, or
another dependency prevents execution, record `UNVERIFIED - BLOCKED BY
ENVIRONMENT`.

The 200-prompt evaluation uses a running backend:

```powershell
.venv/Scripts/python.exe scripts/evaluate_chatbot_prompts.py
```

Its input is `scripts/eval_prompts.json`; cache/output locations are configured
with the `EVAL_*` variables in `.env.example`.

## Logs and diagnostics

Application logs default to `logs/chatbot.log`. Each request receives an
`X-Request-ID`; search that identifier to correlate request, routing, LLM, and
CS API events. Relevant configuration is `LOG_LEVEL`, `CHATBOT_LOG_LEVEL`,
`LIB_LOG_LEVEL`, `LOG_JSON`, `LOG_COLOR`, and `LOG_FILE`.

Useful diagnostics:

```powershell
rg "<request-id>" logs/chatbot.log
rg "data api call.*status=failed" logs/chatbot.log
rg "property answer rejected" logs/chatbot.log
```

The repository VS Code launch configuration can start the backend under a
debugger. Set breakpoints in `routers/assist.py`, `graph/main_orchestrator.py`,
or the relevant service.

## Local artifacts

Keep `.env`, `support_system.db`, `logs/`, uploads, generated `data/`, model
caches, and evaluation outputs private. Ruff and mypy caches are configured
under ignored `data/`. Do not attach or publish local database or customer data.

To replace local tickets with the five synthetic demo tickets, use:

```powershell
.venv/Scripts/python.exe scripts/seed_demo_tickets.py --apply
```

This is destructive to tickets and related ticket records in that local
database; read the script help before using it outside a disposable workspace.
