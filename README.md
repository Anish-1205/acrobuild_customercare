# AI Customer Support Ticket Agent using Haystack

## ⚡ AI Models (100% Local - No API Keys Required)
- **Qwen**: Local LLM for chat responses (Qwen/Qwen2.5-1.5B-Instruct or 0.5B-Instruct)
- **AI4Bharat IndicTrans2**: Indian language translation (22+ languages)
- **AI4Bharat Indic-Parler-TTS**: Indian language text-to-speech
- **Sentence Transformers**: Knowledge base semantic search

All models run locally with no external API dependencies.

## Setup

```bash
pip install -r requirements.txt
```

## Configuration

Create/update `.env` file with:
```env
# Optional: HuggingFace token for AI4Bharat models (get from https://huggingface.co/settings/tokens)
HF_TOKEN=your_token_here

# AI4Bharat TTS Configuration
INDIC_TTS_DEVICE=cpu  # or 'cuda' if GPU available
```

No Google API key or other external API keys needed!

## Run

```bash
uvicorn app:api --reload
```

The API will be available at `http://127.0.0.1:8000`

## React Frontend

The project now also includes a React migration workspace in `webapp/`.

```bash
cd webapp
npm install
npm run dev
```

With the backend running on `http://127.0.0.1:8000`, the React app will be available through Vite on `http://127.0.0.1:5173`.

