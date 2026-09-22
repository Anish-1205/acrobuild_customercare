# AcroBuild Customer Support Agent

FastAPI and React/Vite customer support application for AcroBuild real estate.
The customer chat combines a Sarvam LLM, live property data from the AcroBuild
CS API, and workspace knowledge. Staff manage tickets and support content in
the admin workspace; SQLite stores local support data.

For an AI or developer handoff, start with [AI context](docs/AI_CONTEXT.md) and
[agent instructions](AGENTS.md). Add source files for the specific task using
the file map in that guide.

## AI models and external services
- **Sarvam**: Remote LLM for chat responses, through an OpenAI-compatible API
- **AI4Bharat IndicTrans2**: Indian language translation (22+ languages)
- **AI4Bharat Indic-Parler-TTS**: Indian language text-to-speech
- **Sentence Transformers**: Knowledge base semantic search

IndicTrans2, Indic-Parler-TTS, and sentence-transformers can run locally. Chat
generation needs a reachable Sarvam endpoint and credentials. Depending on
configuration and feature use, the application also connects to the AcroBuild
CS API, SMTP, Edge TTS, Hugging Face model downloads, and administrator-supplied
HTTP(S) knowledge sources.

## Setup

```bash
pip install -r requirements.txt
```

## Configuration

Copy `.env.example` to `.env` and set the external services you need. For chat:
```env
LLM_PROVIDER=sarvam
RUNPOD_BASE_URL=https://your-openai-compatible-sarvam-endpoint
RUNPOD_API_KEY=your_api_key
MODEL_NAME=your_deployed_model_id

# For live property answers
ACROBUILD_CS_API_BASE_URL=http://your-cs-api-host:port
ACROBUILD_CS_API_KEY=your_cs_api_key
ACROBUILD_CS_API_COMPANY_ID=your_company_id
```

The `RUNPOD_*` names are retained for compatibility and can point to a direct
Sarvam endpoint or a RunPod-hosted one. The LLM and CS API are independent:
`GET /` verifies only the local backend, not either external service. Keep
`.env` private.

Administrators can update the CS API base URL, API key, and company ID from
**CS API settings** in the admin dashboard header, or open
`http://127.0.0.1:5173/admin/cs-api-settings` after signing in. Save the three
values there to apply them to new property data requests without restarting
the backend. Saved values persist in the local SQLite database and take
precedence over `.env` after a restart. The dashboard never displays the saved
API key; leave its field blank to keep the current key. The settings API at
`/api/admin/cs-api-settings` requires an administrator session.

## Run

```bash
uvicorn app:api --reload
```

The API will be available at `http://127.0.0.1:8000`

Project guides, architecture notes, integration references, and verification reports are
catalogued in the [documentation index](docs/README.md).

## Repository layout

- `routers/` — FastAPI route modules
- `services/` — application and integration services
- `graph/` — support orchestration and workflow logic
- `src/` and `public/` — React application and static web assets
- `tests/` — backend test suite
- `scripts/` — development, evaluation, and maintenance utilities
- `requirements/` — grouped Python dependency manifests
- `docs/` — guides, architecture notes, and reports
- `resources/` — source-controlled reference and evaluation data
- `data/` — ignored runtime-generated data

## React Frontend

The React admin workspace lives in `src/` and runs from the repo root.

```bash
npm install
npm run dev
```

With the backend running on `http://127.0.0.1:8000`, the React app will be available through Vite on `http://127.0.0.1:5173`.

## Demo tickets

To replace all tickets in the local SQLite workspace with five synthetic
AcroBuild support tickets, run:

```bash
python scripts/seed_demo_tickets.py --apply
```

This deletes existing ticket messages, notes, tags, feedback, and proposals as
well as the tickets. Other workspace data stays intact. The ignored
`support_system.db` is local to each checkout, so run the script separately in
each environment where demo tickets are wanted.
