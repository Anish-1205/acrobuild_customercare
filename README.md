# AI Customer Support Ticket Agent using Haystack

## AI models and external services
- **Sarvam (via RunPod)**: Remote LLM for chat responses
- **AI4Bharat IndicTrans2**: Indian language translation (22+ languages)
- **AI4Bharat Indic-Parler-TTS**: Indian language text-to-speech
- **Sentence Transformers**: Knowledge base semantic search

IndicTrans2, Indic-Parler-TTS, and sentence-transformers can run locally. Chat generation requires RunPod/Sarvam credentials. Depending on configuration and feature use, the application also connects to the Acrobuild CS API, SMTP, Edge TTS, Hugging Face model downloads, and administrator-supplied HTTP(S) knowledge sources.

## Setup

```bash
pip install -r requirements.txt
```

## Configuration

Create/update `.env` file with:
```env
# Required: RunPod/Sarvam credentials for chat generation
RUNPOD_BASE_URL=your_runpod_proxy_url
RUNPOD_API_KEY=your_runpod_api_key

# Optional: HuggingFace token for AI4Bharat models (get from https://huggingface.co/settings/tokens)
HF_TOKEN=your_token_here

# AI4Bharat TTS Configuration
INDIC_TTS_DEVICE=cpu  # or 'cuda' if GPU available
```

Chat generation requires RunPod/Sarvam credentials. Other external integrations require their corresponding credentials and network access.

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
