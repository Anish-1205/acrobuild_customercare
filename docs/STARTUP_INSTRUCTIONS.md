# Startup Instructions

Two servers: FastAPI backend (port 8000) and Vite frontend (port 5173). Run both.

## First-time setup

**Backend** (Python virtualenv already at `.venv/` in this repo — reuse it, don't recreate it):
```bash
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

**Frontend:**
```bash
npm install
```

**Environment variables:** copy `.env.example` to `.env` and fill in values (CS API key, LLM provider settings, etc.). Everything in it is optional — the app runs locally with defaults, but live property data and the remote LLM provider need their respective keys set.

## Every time — start both servers

**Backend** (from repo root):
```bash
.venv/Scripts/python.exe -m uvicorn app:api --host 127.0.0.1 --port 8000
```
`app:api` = the FastAPI app object named `api` inside `app.py`. `initialize_database()` runs on import and creates `support_system.db` if it doesn't exist yet.

To run it in the background and capture logs (useful when driving both servers from one shell):
```bash
.venv/Scripts/python.exe -m uvicorn app:api --host 127.0.0.1 --port 8000 > logs/uvicorn_run.log 2>&1 &
```

**Frontend** (from repo root, separate terminal or background job):
```bash
npm run dev
```
or, backgrounded with logs:
```bash
npm run dev > logs/vite_run.log 2>&1 &
```

## Verify it's up

```bash
curl -s http://127.0.0.1:8000/api/health
```
Healthy response looks like:
```json
{"status":"ok","checks":{"sqlite":{"status":"ok"},"llm":{"status":"ok",...},"cs_api":{"status":"ok"},"knowledge_index":{"status":"ok",...}}}
```

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5173
```
Should print `200`.

Then open the frontend at **http://localhost:5173**.

## Restarting after a code change

The backend does not run with `--reload` in the commands above, so Python changes (anything under `api_context.py`, `routers/`, `services/`, `graph/`) need a manual restart to take effect:

1. Find the running backend process (Windows/Git Bash): `ps -W | grep -i python`
2. Kill it: `kill -9 <pid>`
3. Start it again with the command above.

The frontend (Vite) hot-reloads on save — no restart needed for `src/` changes.

## Logs

- `logs/uvicorn_run.log` — backend stdout/stderr (when started backgrounded as above)
- `logs/vite_run.log` — frontend stdout/stderr (when started backgrounded as above)
- `logs/chatbot.log` — structured application/request logs (turn analysis, LLM calls, CS API calls, tracebacks)

## More detail

For architecture, module map, and deeper onboarding, see `docs/ONBOARDING.md`.
