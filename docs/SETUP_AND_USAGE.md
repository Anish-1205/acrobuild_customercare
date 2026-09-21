# Chatbot Setup and Usage Guide

## 🚀 Quick Start

### Install Dependencies
```bash
pip install -r requirements.txt
```

### Run the Backend
```bash
uvicorn app:api --reload
```

The API will be available at: `http://localhost:8000`

## 🤖 AI Models Used

### 1. **Chat LLM** (Primary AI) — switchable
- **Purpose**: Generate responses to customer questions
- **Providers** (set `LLM_PROVIDER` in `.env`):
  - `qwen` (default): local Transformers model via `qwen.py`
  - `sarvam`: RunPod OpenAI-compatible API via `sarvam_client.py`
- **Facade**: all generative calls still go through `generate_qwen_chat_response()` so property/RAG paths keep working
- See [CHAT_FLOW.md](CHAT_FLOW.md) for the full assist flow and branch diagram

```bash
# Local Qwen
LLM_PROVIDER=qwen
QWEN_ENABLE_CPU=true
QWEN_MAX_TOKENS=128

# Or RunPod Sarvam
LLM_PROVIDER=sarvam
RUNPOD_BASE_URL=https://your-pod.proxy.runpod.net
RUNPOD_API_KEY=your_key
MODEL_NAME=sarvamai/sarvam-30b-gguf:Q4_K_M
SARVAM_MAX_TOKENS=300
```

Restart the backend after changing `LLM_PROVIDER`. RAG, CS API, tickets, and grounded shortcuts are unchanged.

### 2. **AI4Bharat IndicTrans2** (Language Support)
- **Purpose**: Generate greetings in Indian languages
- **Type**: Local model (no API keys needed)
- **Languages Supported**:
  - Telugu, Hindi, Tamil, Kannada, Malayalam
  - Marathi, Bengali, Gujarati, Punjabi, Odia, Urdu
- **Current Usage**: Greetings only (not full translations)

### 3. **Sentence Transformers** (RAG)
- **Purpose**: Embed documents for knowledge base search
- **Model**: `all-MiniLM-L6-v2`
- **Type**: Local, no API keys

### 4. **FAISS** (Vector Search)
- **Purpose**: Fast similarity search in knowledge base
- **Type**: Local index, in-memory

## 📁 Project Structure

```
customer-support-agent/
├── app.py                              # FastAPI application
├── qwen.py                             # Qwen LLM integration
├── services/
│   ├── ai_agent_service.py            # Core chatbot logic ⭐
│   ├── database_service.py             # SQLite backend
│   ├── llm_service.py                  # LLM provider helpers
│   ├── knowledge_index_service.py     # Workspace knowledge index (RAG)
│   ├── acrobuild_company_service.py   # AcroBuild CS API client (live property data)
│   ├── indic_translation_service.py   # AI4Bharat integration
│   └── ... (other services)
├── graph/
│   └── workflow.py                     # Ticket routing & classification
├── qwen.py                             # Local Qwen + LLM_PROVIDER facade
├── sarvam_client.py                    # RunPod Sarvam client
├── CHAT_FLOW.md                        # Assist flow diagram
├── src/                                # React admin dashboard (Vite, run from root)
├── support_system.db                   # SQLite database
└── requirements.txt
```

## 🎯 API Endpoints

### Create Ticket
**Endpoint**: `POST /create_ticket`

**Request Body**:
```json
{
  "email": "customer@example.com",
  "subject": "Issue with order",
  "description": "My order hasn't arrived yet"
}
```

**Response**:
```json
{
  "ticket_id": "TKT-12345",
  "status": "created",
  "message": "నమస్తే! Good day. Your ticket has been created..."
}
```

### Health Check
**Endpoint**: `GET /`

**Response**:
```json
{
  "status": "healthy"
}
```

## 🔧 How Chatbot Works

### 1. Ticket Creation Flow
```
User Query
    ↓
Email/Subject/Description detected
    ↓
Issue Classification (via Qwen)
    ↓
Extract language preference
    ↓
Get customer context (VIP status, order history)
    ↓
Route to appropriate agent
    ↓
Generate response (Butler English)
    ↓
Format with language greeting
    ↓
Return to user
```

### 2. Response Generation
```python
# User asks in Telugu
user_input = "నా ఆర్డర్ ఎక్కడ ఉంది?"

# Step 1: Detect language
language = extract_voice_response_language(issue)  # "telugu"

# Step 2: LLM generates response
qwen_response = generate_qwen_chat_response(
    messages=[...],
    system_prompt=build_system_prompt()  # Butler-style instructions
)
# Returns: "Your order is being processed..."

# Step 3: Apply butler formatting
final_response = localize_ai_answer(qwen_response, issue)
# Returns: "నమస్తే! Good day. Your order is most certainly being processed..."

# Step 4: Send to user
return final_response
```

## 🌍 Language Support

### Supported Languages
- English (USA/India)
- **Telugu** - నమస్తే greeting
- **Hindi** - नमस्ते greeting
- **Tamil** - வணக்கம் greeting
- **Kannada** - ನಮಸ್ಕಾರ greeting
- **Malayalam** - നമസ്കാരം greeting
- **Marathi** - नमस्कार greeting
- **Bengali** - নমস্কার greeting
- **Gujarati** - નમસ્તે greeting
- **Punjabi** - ਨਮਸ੍ਕਾਰ greeting
- **Odia** - ନମସ୍କାର greeting
- **Urdu** - السلام علیکم greeting

### How to Select Language
User can indicate language preference in multiple ways:
1. **Voice Language Marker**: `"Voice language: Telugu."`
2. **Unicode Script**: Message in Telugu script (detected automatically)
3. **Romanized Words**: "chestunnav", "emiti", etc.

### Response Format
Regardless of input language:
- **Greeting**: In user's language (one word/phrase only)
- **Response**: Professional English (butler-style)
- **Example**: "నమస్తే! Good day. How may I be of service?"

## 📊 Chatbot Features

### 1. Issue Classification
Automatically categorizes issues:
- **Billing** - Payment, refund, invoice issues
- **Account** - Login, profile, security
- **Logistics** - Shipping, delivery, tracking
- **NDIS** - NDIS-specific queries
- **Order** - Order status, modifications
- **General** - Other inquiries

### 2. Priority Escalation
**VIP Detection**:
- Customers with 10+ orders → High priority
- Customers with $1000+ spent → High priority
- Auto-assigned to Agent John for escalation

**Priority Levels**:
- 🔴 **Critical**: Security/fraud issues
- 🟠 **High**: VIP customers, escalations
- 🟡 **Medium**: Standard issues
- 🟢 **Low**: General inquiries

### 3. Agent Routing
Automatic routing based on issue type:
- **Billing Issues** → Agent Sarah
- **Account Issues** → Agent Mike
- **Logistics Issues** → Agent Lisa
- **NDIS Issues** → Agent David
- **Order Issues** → Agent Tom
- **VIP/High Priority** → Agent John

### 4. Knowledge Base (RAG)
Pre-loaded knowledge base with:
- Order policies
- Shipping information
- Billing FAQs
- Account management guides
- NDIS program details

Automatically searches relevant documents for each query.

## 📋 Running the prompt evaluation

`scripts/evaluate_chatbot_prompts.py` replays 200 test prompts against a running
backend and writes a scored spreadsheet. Prompts are committed at
`scripts/eval_prompts.json` (no external PDF needed).

```bash
# 1. start the backend (separate shell)
.venv/Scripts/python.exe -m uvicorn app:api --port 8000

# 2. run the eval
.venv/Scripts/python.exe scripts/evaluate_chatbot_prompts.py
```

Output: `customer_support_chatbot_200_prompt_evaluation.xlsx` (Summary +
per-prompt sheets). Partial progress is cached in
`data/chatbot_200_prompt_results.json` and resumed on the next run — delete it to
start clean.

Overrides (env vars): `EVAL_API_URL`, `EVAL_MAX_WORKERS` (default 4 — use 1–2
against a demo-grade or serverless endpoint), `EVAL_TIMEOUT_SECONDS`,
`EVAL_OUTPUT_PATH`, `EVAL_CACHE_PATH`, `EVAL_PROMPTS_PATH`.

Latest analysis and the fix list: `docs/EVAL_FINDINGS.md`.

## 🧪 Testing the Chatbot

### Test 1: Simple Query
```bash
curl -X POST "http://localhost:8000/create_ticket" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "subject": "Order Status",
    "description": "Where is my order?"
  }'
```

### Test 2: Telugu Query
```bash
curl -X POST "http://localhost:8000/create_ticket" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "subject": "ఆర్డర్ స్థితి",
    "description": "నా ఆర్డర్ ఎక్కడ ఉంది? Voice language: Telugu."
  }'
```

**Expected Response**:
```
నమస్తే! Good day. Your order is most certainly being processed. 
Might I suggest tracking your shipment through our website? 
I remain at your service should you require further assistance.
```

### Test 3: VIP Customer
```bash
curl -X POST "http://localhost:8000/create_ticket" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "vip@example.com",
    "subject": "Urgent: Order Issue",
    "description": "My premium order has an issue!"
  }'
```

**Expected**: Higher priority, routed to Agent John

## 🔐 Environment Variables

Create a `.env` file (no API keys needed!):
```env
# Optional: NuFoodz customer-context connection
NUFOODZ_API_BASE_URL=http://10.10.1.23:9092

# Database location (optional)
DATABASE_PATH=./support_system.db

# Optional: Qwen model path
QWEN_MODEL_PATH=~/models/qwen
```

## 🔎 Debugging the Chatbot (logs)

Every request gets a **12-char `request_id`** (also returned as the `X-Request-ID`
response header). All pipeline log lines for that turn carry it, so one turn is
reconstructable with a single grep.

Output goes to **the terminal running uvicorn** and to a rotating file
`logs/chatbot.log` (5 MB × 5, gitignored).

### Env knobs (`.env`)
```env
LOG_LEVEL=INFO            # root / uvicorn
CHATBOT_LOG_LEVEL=INFO    # our loggers; set DEBUG for full prompts,
                          # retrieved chunks and raw LLM output
LOG_FILE=logs/chatbot.log # "" to disable the file sink
LOG_JSON=false            # true -> one JSON object per line
LIB_LOG_LEVEL=WARNING     # httpx / haystack / transformers chatter

# Chatbot tuning
SARVAM_DEADLINE_SECONDS=45  # wall-clock cap on one LLM call; deadline -> graceful fallback
SARVAM_TIMEOUT_SECONDS=120  # httpx client ceiling
LLM_HISTORY_TURNS=10        # conversation turns sent to the model (full store stays 60)
```

### What each turn logs (INFO)
| Logger | Line | Tells you |
|---|---|---|
| `chatbot.request` | `request in` / `request out` | method, path, status, total ms |
| `chatbot.assist` | `turn start` | question preview, customer (masked), `conversation_id`, flags, history length |
| `chatbot.orchestrator` | `orchestration branch` | `general_llm` / `property` / `rag_pipeline` and why |
| `chatbot.orchestrator` | `retrieval chunk` (DEBUG) / `property turn retrieved no evidence` (WARNING) | what the retriever returned; scores per chunk |
| `chatbot.llm` | `llm call` / `llm reply` / `llm stream done` | provider, model, latency, reply size, deadline failures |
| `chatbot.dataapi` | `data api call` | CS API endpoint, status, ms, record count; `cache_hit=True` = served from the per-turn memo (no network) |
| `chatbot.assist` | `turn done` | source_status, retrieval_mode, used_llm, confidence, handoff, data-API failures, answer preview |
| `api_context` | `property answer rejected` | grounding gate fired — a property answer with unverifiable figures was replaced with a handoff |

### `agent_mode` values (normalized enum)
`remote_llm` · `local_llm` · `retrieval` · `grounded` · `fallback` · `live_data_error`.
Legacy blob labels (`gemini`, `knowledge_retrieval`, …) are mapped to these by
`normalize_agent_mode` in `services/observability.py`.

### Trace one turn / one conversation
```bash
grep "a71075f19eb7" logs/chatbot.log                    # one turn, by request_id (X-Request-ID header)
grep "conversation_id=<uuid>" logs/chatbot.log          # every turn in a chat session
grep "turn done" logs/chatbot.log | grep handoff=True   # every escalation
grep "data api call" logs/chatbot.log | grep status=failed
grep "property answer rejected" logs/chatbot.log        # blocked hallucinations
```

### Step-debugging in VSCode
`.vscode/launch.json` ships a **“FastAPI: debug chatbot”** config (debugpy,
`justMyCode=false`, forces `CHATBOT_LOG_LEVEL=DEBUG`). Set breakpoints in
`routers/assist.py`, `graph/main_orchestrator.py`, or `qwen.py` and press F5.
`.vscode/settings.json` pins the interpreter to `.venv`.

## 📈 Performance Tips

### 1. Speed Up Responses
- RAG search returns results in < 100ms
- Qwen inference: ~2-5 seconds per response
- Total response time: ~5-10 seconds

### 2. Improve Accuracy
- Provide clear system prompt (already optimized)
- Use RAG for specific knowledge
- Train on domain-specific data

### 3. Scale the System
- Qwen can run on CPU or GPU
- GPU (NVIDIA): 3-5x faster inference
- Multi-GPU support for parallel requests

## 🐛 Troubleshooting

### Issue: "No module named 'qwen'"
**Solution**: Install Qwen locally
```bash
pip install -r requirements.txt
# Ensure qwen.py is in project root
```

### Issue: "Responses in full Telugu/Hindi script"
**Solution**: Ensure butler-style functions are applied
- Check: `localize_ai_answer()` is being called
- Verify: `build_system_prompt()` includes English-only instructions

### Issue: Slow responses
**Solution**:
- Enable GPU if available
- Check system resource usage
- Monitor LLM inference time

### Issue: Inaccurate answers
**Solution**:
- Review system prompt instructions
- Check RAG knowledge base has relevant docs
- Verify customer context is being fetched

## 📞 Support Services Integration

The chatbot integrates with:
1. **NuFoodz Admin API** - Optional customer context used for routing when `NUFOODZ_API_BASE_URL` is configured; failures degrade to an anonymous/default customer profile and are logged.
2. **SQLite Database** - Ticket storage, conversation history
3. **Knowledge Base** - Document search via RAG
4. **Qwen LLM** - Response generation
5. **AI4Bharat** - Language greetings

Core chat can run locally. SMTP, Edge TTS, URL ingestion, NuFoodz, Acrobuild CS API, and RunPod/Sarvam are external dependencies when enabled.

## 🎯 Next Steps

1. ✅ Chatbot running with Qwen + AI4Bharat
2. ✅ Butler-style English responses working
3. ✅ Language detection and greetings working
4. ⬜ Fine-tune system prompt for your use case
5. ⬜ Train on your domain-specific FAQ
6. ⬜ Deploy to production (gunicorn/uvicorn)

---

**System Status**: ✅ Ready for use
**AI Models**: Qwen + AI4Bharat (no API keys)
**Response Type**: Professional butler-style English
**Last Updated**: 2025-01-16
