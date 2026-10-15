"""Small Stage 5 read-only CS API and Sarvam probes with sanitized output."""
from __future__ import annotations

import json

from qwen import generate_qwen_chat_response
from services.acrobuild_company_service import get_company_projects, search_company_knowledge
from services.answer_engine_service import AnswerEngineRequest
from services.readable_answer_engine import ReadableAnswerEngine


EMPTY_WORKSPACE = {
    "articles": [], "knowledge_documents": [], "matched_chunks": [], "retrieval_mode": "empty",
}


def run():
    projects = get_company_projects()
    if not isinstance(projects, list) or not projects:
        raise RuntimeError("Live CS API returned no project list; catalogue grounding could not be verified")
    names = {str(project.get("projectName") or "").strip() for project in projects if isinstance(project, dict)}
    names.discard("")
    if not names:
        raise RuntimeError("Live CS API project list did not provide names")

    engine = ReadableAnswerEngine(
        workspace_search=lambda **_kwargs: EMPTY_WORKSPACE,
        company_search=search_company_knowledge,
    )
    catalogue = engine.answer(AnswerEngineRequest(
        issue="List the current AcroBuild projects", conversation_id="stage5-readonly-catalogue",
    ))
    if catalogue.get("selected_handler") != "project_catalogue" or catalogue.get("used_llm"):
        raise RuntimeError("Readable catalogue did not select the deterministic live project path")
    if not any(name in catalogue.get("answer", "") for name in names):
        raise RuntimeError("Readable catalogue answer did not contain a live project name")

    # Synthetic support evidence is deliberately unrelated to property data.
    generated = ReadableAnswerEngine(
        workspace_search=lambda **_kwargs: {
            "matched_chunks": [{"record_kind": "knowledge", "title": "Synthetic Stage 5 policy",
                                "record_summary": "A synthetic support request may be reviewed by the team.",
                                "score": 8}],
            "articles": [], "knowledge_documents": [], "retrieval_mode": "lexical",
        },
        company_search=lambda _query: [],
        generator=generate_qwen_chat_response,
    ).answer(AnswerEngineRequest(
        issue="How is this synthetic support request handled?",
        conversation_id="stage5-readonly-sarvam", issue_type="support",
    ))
    if not generated.get("used_llm") or not str(generated.get("answer") or "").strip():
        raise RuntimeError("Readable grounded Sarvam generation did not complete")
    return {
        "evidence_class": "live_readonly_synthetic_input",
        "cs_api": "passed",
        "readable_project_catalogue": "passed",
        "project_count": len(names),
        "sarvam_grounded_generation": "passed",
        "customer_actions": 0,
    }


if __name__ == "__main__":
    print(json.dumps(run(), sort_keys=True))
