# AcroBuild Customer Support Agent

![AcroBuild](public/Acrobuild_logo.png)

AcroBuild is a FastAPI and React/Vite support application for real-estate
customer chat and staff ticket operations. Customer chat combines grounded
property data from the AcroBuild CS API, workspace knowledge, and a Sarvam LLM.
SQLite stores tickets, workspace configuration, sessions, and short-lived chat
state.

Current source code is the authority when historical evidence or an old
changelog entry differs. Coding agents must also follow [AGENTS.md](AGENTS.md).

## Documentation

| Need | Read |
| --- | --- |
| Understand the system | [Architecture](docs/ARCHITECTURE.md) |
| Change customer chat or property behavior | [Chat and property flow](docs/CHAT_FLOW.md), then [AGENTS.md](AGENTS.md) |
| Install, test, or troubleshoot | [Development guide](docs/DEVELOPMENT.md) |
| Check implemented scope or limitations | [Product status](docs/PRODUCT_STATUS.md) |
| Review the frontend inventory and UX risks | [UI/UX frontend audit](docs/UI_UX_FRONTEND_AUDIT.md) |
| Use the frontend foundations and primitives | [Design-system foundation](docs/DESIGN_SYSTEM.md) |
| Review the frontend redesign roadmap | [UI/UX redesign plan](docs/UI_UX_REDESIGN_PLAN.md) |
| Work with the property API | [CS API integration](docs/integrations/CS_API.md) |
| Understand the compiled compatibility layer | [Compiled runtime](docs/runtime/COMPILED_RUNTIME.md) |
| Review dated acceptance artifacts | [Evidence index](docs/evidence/README.md) |
| Review dependency exceptions | [Security advisories](requirements/SECURITY_ADVISORIES.md) |

## Run locally on Windows

### Prerequisites

- Python 3.12. A supported compatibility component contains Python 3.12
  bytecode and will reject incompatible interpreter versions.
- Node.js and npm.
- PowerShell, with the repository root as the current directory.

### 1. Create the environment and install dependencies

```powershell
python --version  # Must report Python 3.12.x
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
npm ci
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

If `python` resolves to another version, invoke your Python 3.12 executable by
its full path when creating `.venv`. If `.venv` already exists, confirm
`.\.venv\Scripts\python.exe --version` reports 3.12 and then reuse it. Do not
overwrite an existing `.env`.

### 2. Configure external services

Use `.env.example` as the template and put local values in `.env`. The main
configuration groups are:

- Sarvam chat: `RUNPOD_BASE_URL`, `RUNPOD_API_KEY`, `MODEL_NAME`.
- Property data: `ACROBUILD_CS_API_BASE_URL`, `ACROBUILD_CS_API_KEY`,
  `ACROBUILD_CS_API_COMPANY_ID`.
- Production security: `AUTH_SECRET_KEY`, `OTP_SECRET`.
- Email OTP: the `SMTP_*` variables.
- Support schedule: `SUPPORT_TIMEZONE` (defaults to `Asia/Kolkata`).

Never commit `.env` or disclose its values. The application can start without
every optional integration, but features backed by an unconfigured service will
use their established unavailable/failure behavior.

### 3. Start the backend

Open a PowerShell terminal at the repository root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app:api --reload --host 127.0.0.1 --port 8000
```

### 4. Start the frontend

Open a second PowerShell terminal at the repository root:

```powershell
npm run dev
```

- Backend: `http://127.0.0.1:8000`
- Frontend: `http://127.0.0.1:5173`
- API documentation: `http://127.0.0.1:8000/docs`

Vite proxies the frontend's API requests to the backend on port 8000.

### 5. Verify startup

```powershell
Invoke-RestMethod http://127.0.0.1:8000/
Invoke-RestMethod http://127.0.0.1:8000/api/health
Invoke-WebRequest http://127.0.0.1:5173/ -UseBasicParsing
```

`GET /` proves only that the local backend responds. It does not prove that the
CS API or Sarvam is reachable. `/api/health` is configuration-oriented and is
also not a live external acceptance test. Use the scripts documented in the
[development guide](docs/DEVELOPMENT.md) when live-service evidence is required.

Press `Ctrl+C` in each terminal to stop the two development servers.

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

## Source material and evidence

`docs/AcroBuild_AI_Simple_Feature_Matrix.xlsx` is local product-requirement
source material, not proof that every listed feature is implemented. Dated
manual and live results under `docs/evidence/` are historical snapshots; rerun
the owning verification before treating them as current operational evidence.
