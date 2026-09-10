"""Attach traceable evidence without representing lexical scores as probability."""
from datetime import datetime, timezone


def enrich_answer_evidence(payload, calls):
    if payload.get("used_llm"):
        from services.provider_resilience_service import completion_metadata
        payload["provider_execution"] = completion_metadata()
    citations = []
    retrieved_at = datetime.now(timezone.utc).isoformat()
    for chunk in payload.get("matched_chunks", []):
        source = chunk.get("source_key") or chunk.get("document_id") or chunk.get("article_id")
        if source:
            citations.append({"source_id": str(source), "title": chunk.get("title", chunk.get("project_name", "Evidence")),
                              "retrieved_at": retrieved_at, "freshness": "workspace",
                              "updated_at": chunk.get("updated_at")})
    for call in calls or []:
        if call.get("status") == "completed":
            citations.append({"source_id": call.get("endpoint", ""), "title": call.get("provider", "Property API"),
                              "retrieved_at": call.get("created_at", retrieved_at),
                              "freshness": "cached" if call.get("cache_hit") else "live"})
    payload["citations"] = citations
    if payload.get("confidence_label") == "low":
        payload["handoff_recommended"] = True
    payload["confidence_basis"] = "routing_and_evidence_heuristic; not a calibrated probability"
    return payload
