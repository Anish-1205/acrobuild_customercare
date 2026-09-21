# Customer support chat flow

Primary path: widget → `/api/support/assist/stream` → orchestrator → (LLM | property/RAG/CS API).

```mermaid
flowchart TD
  UI["CustomerHomePage / widget"] -->|"POST stream prefer_qwen=true"| AssistStream["/api/support/assist/stream"]
  AssistStream --> Shortcuts{"Grounded amenity / location / site-visit?"}
  Shortcuts -->|yes| DirectAPI["CS API / articles — no LLM"]
  Shortcuts -->|no| Orch["stream_support_orchestration_events"]
  Orch --> Resolve["resolve_contextual_support_issue"]
  Resolve --> Branch{"prefer_qwen AND NOT property?"}
  Branch -->|yes| GeneralLLM["_build_live_general_llm_response → generate_qwen_chat_response"]
  Branch -->|property| PropertyPath["stream_ai_support_answer_events"]
  Branch -->|else| Haystack["run_conversation_pipeline"]
  PropertyPath --> RAG["Workspace RAG + Acrobuild CS API"]
  RAG --> Det["Deterministic builders"]
  Det --> MaybeLLM{"Need generative answer?"}
  MaybeLLM -->|yes| SupportLLM["generate_support_chat_response → LLM"]
  MaybeLLM -->|no| DetAnswer["API/RAG answer"]
  Haystack --> Route{"support vs conversation"}
  Route -->|conversation| ConvLLM["build_local_conversation_answer → LLM"]
  Route -->|support| PropertyPath
  GeneralLLM --> Post["localize + live-data enforce + RAG eval"]
  DetAnswer --> Post
  SupportLLM --> Post
  DirectAPI --> Post
  Post --> NDJSON["NDJSON delta + done"]
```

## LLM provider switch

All generative calls go through `qwen.generate_qwen_chat_response`, which dispatches to Sarvam (RunPod OpenAI-compatible API) — the only supported provider. RAG, CS API, tickets, and grounded shortcuts are unchanged.


### Property selection state

Project, wing, floor, flat, and home-type questions use the shared contract in
`services/property_clarification_service.py`. New builders declare
`clarification_entity`; a compatibility detector handles existing English
clarification prompts. Property generation stays in English until the contract
and relevance check finish, then the response is localized. Option names must
survive localization unchanged.

The server-only `pending_project_lookup` marker also accepts a structured
`selection` state: original question, current entity, live option names, selected
scope, and effective retry query. Both assist endpoints restore this state before
routing a short reply. Transient failures keep it without a one-retry cutoff;
new questions/actions replace it. The stored marker is not truncated with long
visible answers. Each resumed lookup re-reads live records.

See `docs/DISAMBIGUATION_AUDIT.md` for the audited generators and live evidence.
