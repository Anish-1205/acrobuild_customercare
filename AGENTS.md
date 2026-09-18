# AI Coding Agent Guide

## Purpose
This project is an AI-powered customer support ticketing agent built with FastAPI, Haystack, and a small local SQLite backing store. Chat generation uses **local Qwen** by default, with an optional **RunPod Sarvam** provider (`LLM_PROVIDER=sarvam`).

## Quick start
- Install dependencies: `pip install -r requirements.txt`
- Run the backend: `uvicorn app:api --reload`
- The backend exposes:
  - `GET /` for health
  - `POST /create_ticket` to create tickets via `graph.workflow.run_workflow`
  - `POST /api/support/assist` and `/api/support/assist/stream` for chat

Chat routing is documented in [CHAT_FLOW.md](CHAT_FLOW.md).

## Project structure
- `app.py` - application entrypoint and FastAPI routes
- `services/` - backend services for database, LLM, RAG, email, auth, and ticket logic
- `graph/workflow.py` - orchestrates ticket classification, priority, agent assignment, and ticket persistence
- `graph/main_orchestrator.py` - support chat orchestration (general LLM vs property/RAG)
- `services/database_service.py` - initializes SQLite `support_system.db` and stores tickets/messages
- `services/knowledge_index_service.py` - workspace knowledge index (articles + knowledge docs) used by the assist flow
- `services/llm_service.py` - LLM provider helpers (`LLM_PROVIDER`)
- `services/acrobuild_company_service.py` - AcroBuild CS API client for live property data
- `services/indic_translation_service.py` - AI4Bharat IndicTrans2 for Indian language translation
- `services/indic_tts_service.py` - AI4Bharat Indic-Parler-TTS for Indian language speech synthesis
- `qwen.py` - Qwen local runtime + provider facade for Sarvam
- `sarvam_client.py` - RunPod OpenAI-compatible Sarvam client
- `src/` - React admin workspace (Vite); run from repo root with `npm run dev`

## Important conventions
- Use `snake_case` for Python functions and variables
- Follow existing section comment style: `# -----------------------------------`
- Keep database access simple and SQLite-based
- Preserve the separation between service modules and orchestration in `graph/workflow.py`

## AI Models Used

### 1. Chat LLM (Qwen or Sarvam)
- **Facade**: `qwen.generate_qwen_chat_response`
- **Local**: `LLM_PROVIDER=qwen` → Hugging Face Transformers + PyTorch
- **Remote**: `LLM_PROVIDER=sarvam` → `sarvam_client.py` (`RUNPOD_BASE_URL`, `RUNPOD_API_KEY`, `MODEL_NAME`)
- **Purpose**: Chat response generation for general questions and property LLM fallback

### 2. AI4Bharat - IndicTrans2 (Translation)
- **File**: `services/indic_translation_service.py`
- **Model**: `ai4bharat/indictrans2-en-indic-dist-200M`
- **Purpose**: Translate English to 22+ Indian languages
- **Requires**: HF_TOKEN (for model access, one-time setup)

### 3. AI4Bharat - Indic-Parler-TTS (Text-to-Speech)
- **File**: `services/indic_tts_service.py`
- **Model**: `ai4bharat/indic-parler-tts`
- **Purpose**: Generate natural Indian language speech
- **Requires**: HF_TOKEN (for model access, one-time setup)

### 4. Sentence Transformers (Semantic Search)
- **File**: `services/knowledge_index_service.py`
- **Model**: `all-MiniLM-L6-v2`
- **Purpose**: Workspace knowledge retrieval (articles + knowledge docs) via semantic + lexical search
- **No API key required**

## Intelligent ticket routing
The workflow now performs context-aware classification:
- **Issue Classification**: Recognizes 6 categories (Billing, Account, Logistics, NDIS, Order, General) based on keywords and customer profile
- **Priority Escalation**: VIP customers (10+ orders or $1000+ spent) automatically get higher priority
- **Agent Routing**: Specialized agents per issue type plus VIP escalation (Agent John for high-value customers)
- **Customer Context**: Fetches order history, NDIS status, and spend from NuFoodz admin

## NuFoodz Integration
- `get_customer_context()` in workflow retrieves customer VIP status, order count, total spend, and NDIS flag from the API endpoint
- Customer data is fetched from `http://10.10.1.23:9092/api/customer?email={email}`

## Environment Setup
```bash
HF_TOKEN=<your_huggingface_token>  # For AI4Bharat models (optional)
LLM_PROVIDER=qwen                  # or sarvam
# When LLM_PROVIDER=sarvam:
RUNPOD_BASE_URL=https://your-pod.proxy.runpod.net
RUNPOD_API_KEY=<key>
MODEL_NAME=sarvamai/sarvam-30b-gguf:Q4_K_M
```

## Known caveats
- The main backend path uses `services/database_service.py` and `support_system.db`
- Local Qwen may require significant GPU/CPU resources; Sarvam needs a live RunPod endpoint

## Best next customizations
- Integrate LLM-powered classification in `graph/workflow.py` using the chat facade
- Load NuFoodz FAQ/docs into RAG instead of hardcoded knowledge base
- Add LLM-generated response suggestions based on issue type and customer history
- Create admin UI for managing agent assignments and routing rules
- Add a per-request UI model picker on top of the `LLM_PROVIDER` facade

## Mandatory property clarification contract
- Every project/wing/floor/flat/home-type clarification must use `services/property_clarification_service.py` before relevance validation, localization, and conversation persistence.
- New answer builders must set `clarification_entity` (`project`, `wing`, `floor`, `flat`, or `home_type`). Do not generate a bare "specify the project" prompt. The contract fetches real matching names from the live CS API; an empty or unavailable catalogue must be reported honestly.
- Preserve the complete original question, selected scope, offered options, and retry query in the server-side pending selection marker. Do not derive intent from translated bot prose. Do not expire state after a fixed number of API failures. Explicit new questions/actions replace the pending request.
- List all applicable real options; do not silently select one of multiple matching records. A full suffixed project name takes precedence over its contained base name.
- Test new clarification points for named options, short follow-up selection, repeated API failures, and intent preservation. Cover both assist endpoints when changing routing. Run `scripts/live_disambiguation_check.py` for live acceptance (real LLM/API, no mocks); transcripts are written to `docs/live_disambiguation_results.json`.
