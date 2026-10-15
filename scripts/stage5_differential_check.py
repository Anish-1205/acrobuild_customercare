"""Offline, side-effect-free legacy/readable answer comparison.

All records and model output are constructed. This is characterization evidence,
not a production conversation sample or approval to run shadow traffic.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from services import ai_agent_service as legacy_module
from services.answer_engine_service import AnswerEngineRequest, LegacyCompiledAnswerEngine
from services.readable_answer_engine import ReadableAnswerEngine


ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = {
    "articles": [],
    "embedding_error": "",
    "index_built_at": None,
    "index_error": "",
    "knowledge_documents": [],
    "matched_chunks": [{
        "record_kind": "knowledge",
        "title": "Synthetic document guide",
        "record_summary": "Customers may ask support which identity documents to prepare.",
        "score": 8,
    }],
    "retrieval_mode": "lexical",
}
PROJECTS = {
    "source_key": "acrobuild-cs-projects",
    "record_kind": "company_api",
    "title": "Synthetic project catalogue",
    "projects": [
        {"id": 900001, "projectName": "Example Heights", "locality": "North Test", "city": "Test City"},
        {"id": 900002, "projectName": "Example Gardens", "locality": "South Test", "city": "Test City"},
    ],
    "score": 100,
}
DETAIL = {
    "source_key": "acrobuild-cs-project-900001",
    "record_kind": "company_api",
    "title": "Synthetic project detail",
    "project_name": "Example Heights",
    "project": {"id": 900001, "projectName": "Example Heights", "locality": "North Test"},
    "wings": [{"id": 11, "name": "Wing A", "constructionStatus": "In progress"}],
    "typologies": [{"typologyType": "2BHK", "saleableArea": 800, "minBasePrice": 5000,
                     "maxBasePrice": 5500}],
    "available_inventory": [{"id": 31, "unitNumber": "101", "floorNumber": 1}],
    "inventory_loaded": True,
    "score": 100,
}
CASES = [
    ("project_catalogue", "Show me all projects", True, False),
    ("project_location", "Where is Example Heights located?", True, False),
    ("configuration_price", "What is the 2BHK price in Example Heights?", True, False),
    ("inventory", "How many units are available in Example Heights?", True, False),
    ("construction", "What is the construction status of Example Heights?", True, False),
    ("workspace", "What documents should I prepare?", True, True),
    ("opt_out", "Explain the support policy", False, False),
    ("contextual_followup", "What about its price?", True, False),
    ("missing_data", "Where is Unknown Test Project?", True, False),
    ("provider_timeout", "Explain synthetic support policy", True, False),
    ("retail_exclusion", "List the snack vendor product feed", True, False),
]
CLASSIFICATION = {
    "project_catalogue": "legacy_implementation_defect_invalid_agent_mode",
    "project_location": "legacy_implementation_defect_invalid_agent_mode",
    "configuration_price": "legacy_implementation_defect_invalid_agent_mode",
    "inventory": "legacy_implementation_defect_invalid_agent_mode",
    "construction": "legacy_implementation_defect_invalid_agent_mode",
    "workspace": "legacy_implementation_defect_invalid_agent_mode",
    "opt_out": "approved_generation_flag_parity_confidence_policy_difference",
    "contextual_followup": "legacy_implementation_defect_invalid_agent_mode",
    "missing_data": "approved_intentional_safe_fallback",
    "provider_timeout": "semantically_equivalent_error_outcome",
    "retail_exclusion": "approved_intentional_retail_exclusion",
}


def _summary(response):
    return {
        "agent_mode": response.get("agent_mode"),
        "confidence_label": response.get("confidence_label"),
        "handoff_recommended": response.get("handoff_recommended"),
        "retrieval_mode": response.get("retrieval_mode"),
        "source_status": response.get("source_status"),
        "used_llm": response.get("used_llm"),
        "answer_present": bool(response.get("answer")),
        "matched_chunk_count": len(response.get("matched_chunks") or []),
    }


def run_comparison():
    """Return compact differences without recording text, identities, or prompts."""
    legacy = LegacyCompiledAnswerEngine()
    state = {"workspace": WORKSPACE, "company": [PROJECTS, DETAIL], "timeout": False}

    def generate(**_kwargs):
        if state["timeout"]:
            raise TimeoutError("synthetic provider timeout")
        return "Synthetic support evidence was reviewed."

    readable = ReadableAnswerEngine(
        workspace_search=lambda **_kwargs: state["workspace"],
        company_search=lambda _query: state["company"],
        generator=generate,
    )
    patches = (
        patch.object(legacy_module, "search_workspace_knowledge", side_effect=lambda **_kwargs: state["workspace"]),
        patch.object(legacy_module, "search_company_knowledge", side_effect=lambda _query: state["company"]),
        patch.object(legacy_module, "get_company_projects", return_value=[]),
        patch.object(legacy_module, "get_customer_context", return_value={}),
        patch.object(legacy_module, "generate_qwen_chat_response", side_effect=generate),
    )
    results = []
    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        for case_id, issue, prefer_qwen, fast in CASES:
            state["workspace"] = ({**WORKSPACE, "matched_chunks": [], "retrieval_mode": "empty"}
                                  if case_id == "missing_data" else WORKSPACE)
            state["company"] = [] if case_id in {"missing_data", "provider_timeout"} else [PROJECTS, DETAIL]
            state["timeout"] = case_id == "provider_timeout"
            request = AnswerEngineRequest(
                issue=issue,
                conversation_id=f"stage5-{case_id}",
                issue_type="property" if case_id not in {"workspace", "opt_out", "retail_exclusion"} else "support",
                prefer_qwen_response=prefer_qwen,
                prefer_fast_response=fast,
                conversation_messages=([{"sender": "customer", "text": "Tell me about Example Heights"}]
                                       if case_id == "contextual_followup" else []),
            )
            legacy.clear_cache()
            readable.clear_cache()
            old = legacy.answer(request)
            new = readable.answer(request)
            legacy.clear_cache()
            readable.clear_cache()
            old_events = list(legacy.stream(request))
            new_events = list(readable.stream(request))
            old_fields = _summary(old)
            new_fields = _summary(new)
            differences = sorted(field for field in old_fields if old_fields[field] != new_fields[field])
            results.append({
                "case": case_id,
                "classification": CLASSIFICATION[case_id],
                "legacy": old_fields,
                "readable": new_fields,
                "different_fields": differences,
                "legacy_event_types": [event.get("type") for event in old_events],
                "readable_event_types": [event.get("type") for event in new_events],
                "legacy_terminal_count": sum(event.get("type") == "done" for event in old_events),
                "readable_terminal_count": sum(event.get("type") == "done" for event in new_events),
            })
    return {"evidence_class": "constructed_synthetic_offline_differential", "cases": results}


if __name__ == "__main__":
    print(json.dumps(run_comparison(), indent=2, sort_keys=True))
